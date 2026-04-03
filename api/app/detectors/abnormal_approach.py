"""Detector 1: Abnormal Approach (Context-Aware).

Flags abrupt speed, heading, and course changes for vessels that appear to be
on inbound transit, while suppressing normal maneuvering inside harbor and
anchorage areas.
"""

import json
import math
import os
from datetime import timedelta
from itertools import groupby

import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://cue2case:cue2case_dev@localhost:5433/cue2case",
)

# Long Beach / San Pedro Bay inbound traffic from the Pacific typically heads
# north to east as vessels come up from the south/southwest into the bay.
EXPECTED_INBOUND_HEADING_RANGE = (0, 90)  # degrees, expected inbound approach band
COG_CHANGE_THRESHOLD = 60.0  # degrees change in 5 min while moving
MIN_MOVING_SOG = 3.0  # knots
MIN_HEADING_RANGE_SOG = 5.0  # knots
TIME_WINDOW = timedelta(minutes=5)
PORT_CENTER = (-118.25, 33.73)  # Long Beach approximate center


def haversine_nm(lat1, lon1, lat2, lon2):
    """Return distance between two lat/lon points in nautical miles."""
    radius_nm = 3440.065
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return radius_nm * 2 * math.asin(math.sqrt(a))


def heading_diff(h1, h2):
    """Calculate minimum angular difference between two headings."""
    if h1 is None or h2 is None:
        return None
    diff = abs(h1 - h2) % 360
    return min(diff, 360 - diff)


def check_geofence_context(cur, lon, lat):
    """Check which geofence zones a point falls in."""
    cur.execute(
        """
        SELECT name, zone_type
        FROM geofence
        WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
        """,
        (lon, lat),
    )
    return cur.fetchall()


def get_vessel_thresholds(vessel_type):
    """Return vessel-class-aware approach thresholds."""
    if vessel_type is None:
        return {"speed_delta": 8.0, "heading_change": 90.0}

    if 50 <= vessel_type <= 59 or vessel_type in {31, 32}:
        return {"speed_delta": 12.0, "heading_change": 120.0}

    if 70 <= vessel_type <= 89:
        return {"speed_delta": 5.0, "heading_change": 60.0}

    if 60 <= vessel_type <= 69:
        return {"speed_delta": 8.0, "heading_change": 90.0}

    return {"speed_delta": 8.0, "heading_change": 90.0}


def is_heading_in_expected_range(heading):
    """Return True when heading falls within the expected inbound range."""
    if heading is None:
        return False

    start, end = EXPECTED_INBOUND_HEADING_RANGE
    if start <= end:
        return start <= heading <= end
    return heading >= start or heading <= end


def is_operating_context_relevant(zone_types):
    """Return True when a vessel is in an approach-relevant operating context."""
    return "approach" in zone_types or not ({"harbor", "anchorage"} & zone_types)


def is_inbound(segment_positions):
    """Return True if a segment/window is approaching port (distance decreasing)."""
    if len(segment_positions) < 2:
        return True  # can't tell, assume inbound

    first_lon, first_lat = segment_positions[0][2], segment_positions[0][3]
    last_lon, last_lat = segment_positions[-1][2], segment_positions[-1][3]
    dist_first = haversine_nm(first_lat, first_lon, PORT_CENTER[1], PORT_CENTER[0])
    dist_last = haversine_nm(last_lat, last_lon, PORT_CENTER[1], PORT_CENTER[0])
    return dist_last <= dist_first  # segment moved closer to port = inbound


def build_reason_lists(zone_types, curr_sog, movement_nm, threshold_source):
    """Build suspicious and benign reasoning lists for alert details."""
    reasons_suspicious = []
    reasons_benign = []

    if "approach" in zone_types:
        reasons_suspicious.append("inside an approach corridor where inbound tracks should be stable")
    elif not ({"harbor", "anchorage"} & zone_types):
        reasons_suspicious.append("outside harbor and anchorage zones during transit")

    if "restricted" in zone_types:
        reasons_suspicious.append("near a restricted area")

    if curr_sog is not None and curr_sog > MIN_MOVING_SOG:
        reasons_suspicious.append(f"moving at {curr_sog:.1f} knots, so abrupt maneuvers are more meaningful")

    if movement_nm is not None and movement_nm >= 0.25:
        reasons_suspicious.append(f"covered {movement_nm:.2f} nm between reports")

    if threshold_source == "tug_service":
        reasons_benign.append("tug/service craft often maneuver aggressively")
    elif threshold_source == "passenger":
        reasons_benign.append("passenger/ferry traffic may make operational course adjustments")
    elif threshold_source == "default":
        reasons_benign.append("vessel class unknown or generic thresholds applied")

    if "harbor" in zone_types:
        reasons_benign.append("inside harbor where maneuvering is often normal")
    if "anchorage" in zone_types:
        reasons_benign.append("inside anchorage where heading swings can be benign")

    return reasons_suspicious, reasons_benign


def detect_abnormal_approach():
    """Run abnormal approach detection with vessel-class and geofence context."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur_geo = conn.cursor()

    try:
        cur.execute(
            """
            SELECT mmsi, vessel_type, vessel_name, length, width
            FROM vessel
            """
        )
        vessel_info = {
            row[0]: {
                "vessel_type": row[1],
                "vessel_name": row[2],
                "length": row[3],
                "width": row[4],
            }
            for row in cur.fetchall()
        }

        print("Fetching AIS positions for abnormal approach detection...")
        cur.execute(
            """
            SELECT mmsi, observed_at, ST_X(geom) as lon, ST_Y(geom) as lat,
                   sog, cog, heading
            FROM ais_position
            ORDER BY mmsi, observed_at
            """
        )

        rows = cur.fetchall()
        alerts = []

        for mmsi, group in groupby(rows, key=lambda row: row[0]):
            positions = list(group)
            if len(positions) < 2:
                continue

            vessel = vessel_info.get(mmsi, {})
            vessel_type = vessel.get("vessel_type")
            thresholds = get_vessel_thresholds(vessel_type)

            if vessel_type is None:
                threshold_source = "default"
            elif 50 <= vessel_type <= 59 or vessel_type in {31, 32}:
                threshold_source = "tug_service"
            elif 70 <= vessel_type <= 89:
                threshold_source = "cargo_tanker"
            elif 60 <= vessel_type <= 69:
                threshold_source = "passenger"
            else:
                threshold_source = "default"

            for i in range(1, len(positions)):
                prev = positions[i - 1]
                curr = positions[i]

                time_diff = curr[1] - prev[1]
                if time_diff > TIME_WINDOW or time_diff.total_seconds() <= 0:
                    continue

                segment_positions = [prev, curr]
                if not is_inbound(segment_positions):
                    continue

                zones = check_geofence_context(cur_geo, curr[2], curr[3])
                zone_types = {zone[1] for zone in zones}
                if not is_operating_context_relevant(zone_types):
                    continue

                movement_nm = haversine_nm(prev[3], prev[2], curr[3], curr[2])
                reasons_suspicious, reasons_benign = build_reason_lists(
                    zone_types, curr[4], movement_nm, threshold_source
                )
                zone_context = [{"name": zone[0], "type": zone[1]} for zone in zones]
                vessel_label = vessel.get("vessel_name") or str(mmsi)

                if prev[4] is not None and curr[4] is not None:
                    speed_change = abs(curr[4] - prev[4])
                    if speed_change > thresholds["speed_delta"]:
                        severity = min(speed_change / (thresholds["speed_delta"] * 2.0), 1.0)
                        speed_suspicious = reasons_suspicious + [
                            (
                                f"speed changed by {speed_change:.1f} knots in "
                                f"{time_diff.total_seconds():.0f}s"
                            )
                        ]
                        alerts.append(
                            {
                                "mmsi": mmsi,
                                "alert_type": "abnormal_approach",
                                "severity": round(severity, 3),
                                "observed_at": curr[1],
                                "lon": curr[2],
                                "lat": curr[3],
                                "details": {
                                    "sub_type": "speed_change",
                                    "prev_sog": prev[4],
                                    "curr_sog": curr[4],
                                    "delta_sog": round(speed_change, 2),
                                    "time_delta_sec": time_diff.total_seconds(),
                                    "distance_nm": round(movement_nm, 3),
                                    "vessel_type": vessel_type,
                                    "vessel_name": vessel.get("vessel_name"),
                                    "threshold_speed_delta": thresholds["speed_delta"],
                                    "zone_context": zone_context,
                                    "reasons_suspicious": speed_suspicious,
                                    "reasons_benign": reasons_benign,
                                },
                                "explanation": (
                                    f"Vessel {vessel_label} had a sudden speed change of "
                                    f"{speed_change:.1f} knots ({prev[4]:.1f} → {curr[4]:.1f}) "
                                    f"within {time_diff.total_seconds():.0f}s. "
                                    + (f"Suspicious: {'; '.join(speed_suspicious)}. " if speed_suspicious else "")
                                    + (f"Possibly benign: {'; '.join(reasons_benign)}." if reasons_benign else "")
                                ),
                            }
                        )

                if curr[4] is not None and curr[4] > MIN_MOVING_SOG:
                    h_diff = heading_diff(prev[6], curr[6])
                    if h_diff is not None and h_diff > thresholds["heading_change"]:
                        severity = min(h_diff / 180.0, 1.0)
                        heading_suspicious = reasons_suspicious + [
                            (
                                f"heading changed by {h_diff:.0f}° while underway, above class threshold "
                                f"{thresholds['heading_change']:.0f}°"
                            )
                        ]
                        alerts.append(
                            {
                                "mmsi": mmsi,
                                "alert_type": "abnormal_approach",
                                "severity": round(severity, 3),
                                "observed_at": curr[1],
                                "lon": curr[2],
                                "lat": curr[3],
                                "details": {
                                    "sub_type": "heading_change",
                                    "prev_heading": prev[6],
                                    "curr_heading": curr[6],
                                    "curr_sog": curr[4],
                                    "delta_heading": round(h_diff, 2),
                                    "time_delta_sec": time_diff.total_seconds(),
                                    "distance_nm": round(movement_nm, 3),
                                    "vessel_type": vessel_type,
                                    "vessel_name": vessel.get("vessel_name"),
                                    "threshold_heading_change": thresholds["heading_change"],
                                    "zone_context": zone_context,
                                    "reasons_suspicious": heading_suspicious,
                                    "reasons_benign": reasons_benign,
                                },
                                "explanation": (
                                    f"Vessel {vessel_label} made a sharp heading change of "
                                    f"{h_diff:.0f}° ({prev[6]:.0f}° → {curr[6]:.0f}°) "
                                    f"within {time_diff.total_seconds():.0f}s while moving at "
                                    f"{curr[4]:.1f} knots. "
                                    + (f"Suspicious: {'; '.join(heading_suspicious)}. " if heading_suspicious else "")
                                    + (f"Possibly benign: {'; '.join(reasons_benign)}." if reasons_benign else "")
                                ),
                            }
                        )

                if (
                    prev[4] is not None
                    and curr[4] is not None
                    and prev[5] is not None
                    and curr[5] is not None
                    and prev[4] > MIN_MOVING_SOG
                    and curr[4] > MIN_MOVING_SOG
                ):
                    cog_diff = heading_diff(prev[5], curr[5])
                    if cog_diff is not None and cog_diff > COG_CHANGE_THRESHOLD:
                        severity = min(cog_diff / 180.0, 1.0)
                        cog_suspicious = reasons_suspicious + [
                            f"course over ground changed by {cog_diff:.0f}° while underway"
                        ]
                        alerts.append(
                            {
                                "mmsi": mmsi,
                                "alert_type": "abnormal_approach",
                                "severity": round(severity, 3),
                                "observed_at": curr[1],
                                "lon": curr[2],
                                "lat": curr[3],
                                "details": {
                                    "sub_type": "cog_change",
                                    "prev_cog": prev[5],
                                    "curr_cog": curr[5],
                                    "prev_sog": prev[4],
                                    "curr_sog": curr[4],
                                    "delta_cog": round(cog_diff, 2),
                                    "time_delta_sec": time_diff.total_seconds(),
                                    "distance_nm": round(movement_nm, 3),
                                    "vessel_type": vessel_type,
                                    "vessel_name": vessel.get("vessel_name"),
                                    "threshold_cog_change": COG_CHANGE_THRESHOLD,
                                    "zone_context": zone_context,
                                    "reasons_suspicious": cog_suspicious,
                                    "reasons_benign": reasons_benign,
                                },
                                "explanation": (
                                    f"Vessel {vessel_label} changed course over ground by "
                                    f"{cog_diff:.0f}° ({prev[5]:.0f}° → {curr[5]:.0f}°) while moving at "
                                    f"{prev[4]:.1f}-{curr[4]:.1f} knots within "
                                    f"{time_diff.total_seconds():.0f}s. "
                                    + (f"Suspicious: {'; '.join(cog_suspicious)}. " if cog_suspicious else "")
                                    + (f"Possibly benign: {'; '.join(reasons_benign)}." if reasons_benign else "")
                                ),
                            }
                        )

                if curr[6] is not None and curr[4] is not None and curr[4] > MIN_HEADING_RANGE_SOG:
                    if not is_heading_in_expected_range(curr[6]):
                        range_start, range_end = EXPECTED_INBOUND_HEADING_RANGE
                        severity = min((curr[4] - MIN_HEADING_RANGE_SOG) / 10.0 + 0.4, 1.0)
                        range_suspicious = reasons_suspicious + [
                            (
                                f"heading {curr[6]:.0f}° is outside expected inbound range "
                                f"{range_start}°-{range_end}°"
                            )
                        ]
                        alerts.append(
                            {
                                "mmsi": mmsi,
                                "alert_type": "abnormal_approach",
                                "severity": round(severity, 3),
                                "observed_at": curr[1],
                                "lon": curr[2],
                                "lat": curr[3],
                                "details": {
                                    "sub_type": "unexpected_heading",
                                    "heading": curr[6],
                                    "sog": curr[4],
                                    "distance_nm": round(movement_nm, 3),
                                    "vessel_type": vessel_type,
                                    "vessel_name": vessel.get("vessel_name"),
                                    "expected_inbound_heading_range": [range_start, range_end],
                                    "zone_context": zone_context,
                                    "reasons_suspicious": range_suspicious,
                                    "reasons_benign": reasons_benign,
                                },
                                "explanation": (
                                    f"Vessel {vessel_label} reported heading {curr[6]:.0f}° at "
                                    f"{curr[4]:.1f} knots, outside expected inbound range "
                                    f"{range_start}°-{range_end}°. "
                                    + (f"Suspicious: {'; '.join(range_suspicious)}. " if range_suspicious else "")
                                    + (f"Possibly benign: {'; '.join(reasons_benign)}." if reasons_benign else "")
                                ),
                            }
                        )

        if alerts:
            alert_rows = [
                (
                    alert["mmsi"],
                    alert["alert_type"],
                    alert["severity"],
                    alert["observed_at"],
                    alert["lon"],
                    alert["lat"],
                    json.dumps(alert["details"]),
                    alert["explanation"],
                )
                for alert in alerts
            ]

            execute_values(
                cur,
                """
                INSERT INTO alert (mmsi, alert_type, severity, observed_at, geom, details, explanation)
                VALUES %s
                """,
                alert_rows,
                template="(%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s::jsonb, %s)",
            )
            conn.commit()

        print(f"Abnormal approach detector: {len(alerts)} alerts generated.")
        return alerts
    finally:
        cur_geo.close()
        cur.close()
        conn.close()


if __name__ == "__main__":
    detect_abnormal_approach()
