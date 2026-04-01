"""Detector 4: Split identity and kinematic anomalies with geofence context.

Flags kinematic anomalies (impossible speed, teleportation, null-SOG jumps,
GPS spikes) separately from identity anomalies (duplicate MMSI reports).
"""

import json
import math
import os
from itertools import groupby

import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://cue2case:cue2case_dev@localhost:5433/cue2case",
)

MAX_NORMAL_SOG = 35.0  # knots for non-high-speed craft
HIGH_SPEED_VESSEL_TYPES = range(40, 50)  # HSC types in AIS
HIGH_SPEED_SOG = 60.0  # knots allowed for high-speed craft
TELEPORT_SPEED_RATIO = 3.0  # implied speed > 3x reported SOG
MIN_TELEPORT_SPEED = 50.0  # minimum implied speed to flag (knots)
MAX_TELEPORT_WINDOW_SECONDS = 3600  # compare only points within 1 hour
DUPLICATE_MMSI_DISTANCE_METERS = 1000  # same MMSI/time but > 1km apart
RESTRICTED_ZONE_NEAR_METERS = 2000
GPS_SPIKE_RETURN_DISTANCE_NM = 1.0
GPS_SPIKE_MIN_LEG_DISTANCE_NM = 3.0


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


def clamp(value, minimum=0.0, maximum=1.0):
    """Clamp a numeric value to the supplied range."""
    return max(minimum, min(value, maximum))


def get_speed_limit(vessel_type):
    """Return vessel-type-aware speed limit."""
    is_high_speed_craft = (
        vessel_type is not None and vessel_type in HIGH_SPEED_VESSEL_TYPES
    )
    return (
        HIGH_SPEED_SOG if is_high_speed_craft else MAX_NORMAL_SOG,
        is_high_speed_craft,
    )


def check_geofence_context(cur, lon, lat):
    """Return geofence context, including nearby restricted zones."""
    cur.execute(
        """
        SELECT name,
               zone_type,
               ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326)) AS contains_point,
               ST_Distance(
                   geom::geography,
                   ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
               ) AS distance_m
        FROM geofence
        WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
           OR (zone_type = 'restricted' AND ST_DWithin(
               geom::geography,
               ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
               %s
           ))
        ORDER BY distance_m ASC, name ASC
        """,
        (
            lon,
            lat,
            lon,
            lat,
            lon,
            lat,
            lon,
            lat,
            RESTRICTED_ZONE_NEAR_METERS,
        ),
    )
    return cur.fetchall()


def build_zone_context(zones):
    """Format geofence rows into alert-friendly dictionaries."""
    return [
        {
            "name": zone[0],
            "type": zone[1],
            "contains_point": bool(zone[2]),
            "distance_m": round(float(zone[3]), 1) if zone[3] is not None else None,
        }
        for zone in zones
    ]


def build_reason_lists(zone_context, vessel_type, is_high_speed_craft):
    """Build suspicious and benign reasons shared by identity/kinematic alerts."""
    reasons_suspicious = []
    reasons_benign = []

    zone_types = {zone["type"] for zone in zone_context}
    restricted_hits = [zone for zone in zone_context if zone["type"] == "restricted"]

    if restricted_hits:
        inside_restricted = any(zone["contains_point"] for zone in restricted_hits)
        nearest_restricted = min(zone["distance_m"] or 0 for zone in restricted_hits)
        if inside_restricted:
            reasons_suspicious.append("inside a restricted area")
        elif nearest_restricted <= RESTRICTED_ZONE_NEAR_METERS:
            reasons_suspicious.append(
                f"near a restricted area ({nearest_restricted:.0f} m)"
            )

    if not zone_types:
        reasons_benign.append("no geofence context available for the position")
    elif {"harbor", "anchorage"} & zone_types:
        reasons_benign.append("operating in harbor/anchorage context where AIS artifacts can be more common")

    if vessel_type is None:
        reasons_benign.append("vessel type unavailable, so generic thresholds were used")
    elif is_high_speed_craft:
        reasons_benign.append("high-speed craft can legitimately report higher transit speeds")

    return reasons_suspicious, reasons_benign


def severity_with_zone_boost(base, zone_context):
    """Boost severity when restricted-zone context is present."""
    restricted_hits = [zone for zone in zone_context if zone["type"] == "restricted"]
    if not restricted_hits:
        return round(clamp(base), 3)

    if any(zone["contains_point"] for zone in restricted_hits):
        return round(clamp(base + 0.15), 3)

    nearest_restricted = min(zone["distance_m"] or RESTRICTED_ZONE_NEAR_METERS for zone in restricted_hits)
    if nearest_restricted <= RESTRICTED_ZONE_NEAR_METERS:
        return round(clamp(base + 0.10), 3)

    return round(clamp(base), 3)


def build_alert(
    mmsi,
    alert_type,
    observed_at,
    lon,
    lat,
    details,
    explanation,
    base_severity,
    zone_context,
):
    """Create a normalized alert payload."""
    details = dict(details)
    details["zone_context"] = zone_context
    details["reasons_suspicious"] = details.get("reasons_suspicious", [])
    details["reasons_benign"] = details.get("reasons_benign", [])

    return {
        "mmsi": mmsi,
        "alert_type": alert_type,
        "severity": severity_with_zone_boost(base_severity, zone_context),
        "observed_at": observed_at,
        "lon": lon,
        "lat": lat,
        "details": details,
        "explanation": explanation,
    }


def detect_gps_spikes(positions, speed_limit):
    """Return index->spike metadata for one-point GPS spike anomalies."""
    spikes = {}

    for index in range(1, len(positions) - 1):
        prev = positions[index - 1]
        curr = positions[index]
        nxt = positions[index + 1]

        dt_prev = (curr[1] - prev[1]).total_seconds()
        dt_next = (nxt[1] - curr[1]).total_seconds()
        dt_bridge = (nxt[1] - prev[1]).total_seconds()
        if (
            dt_prev <= 0
            or dt_next <= 0
            or dt_bridge <= 0
            or dt_prev >= MAX_TELEPORT_WINDOW_SECONDS
            or dt_next >= MAX_TELEPORT_WINDOW_SECONDS
            or dt_bridge >= (MAX_TELEPORT_WINDOW_SECONDS * 2)
        ):
            continue

        leg_in_nm = haversine_nm(prev[3], prev[2], curr[3], curr[2])
        leg_out_nm = haversine_nm(curr[3], curr[2], nxt[3], nxt[2])
        bridge_nm = haversine_nm(prev[3], prev[2], nxt[3], nxt[2])

        implied_in = (leg_in_nm / dt_prev) * 3600
        implied_out = (leg_out_nm / dt_next) * 3600
        implied_bridge = (bridge_nm / dt_bridge) * 3600

        if leg_in_nm < GPS_SPIKE_MIN_LEG_DISTANCE_NM or leg_out_nm < GPS_SPIKE_MIN_LEG_DISTANCE_NM:
            continue
        if implied_in < MIN_TELEPORT_SPEED or implied_out < MIN_TELEPORT_SPEED:
            continue
        if bridge_nm > GPS_SPIKE_RETURN_DISTANCE_NM:
            continue
        if implied_bridge > max(speed_limit * 1.25, 20.0):
            continue

        spikes[index] = {
            "leg_in_nm": leg_in_nm,
            "leg_out_nm": leg_out_nm,
            "bridge_nm": bridge_nm,
            "dt_prev": dt_prev,
            "dt_next": dt_next,
            "dt_bridge": dt_bridge,
            "implied_in": implied_in,
            "implied_out": implied_out,
            "implied_bridge": implied_bridge,
        }

    return spikes


def detect_identity_kinematic():
    """Run identity/kinematic inconsistency detection."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur_geo = conn.cursor()

    try:
        cur.execute("SELECT mmsi, vessel_type FROM vessel")
        vessel_types = {row[0]: row[1] for row in cur.fetchall()}

        print("Fetching AIS positions for kinematic analysis...")
        cur.execute(
            """
            SELECT mmsi, observed_at, ST_X(geom) as lon, ST_Y(geom) as lat, sog
            FROM ais_position
            ORDER BY mmsi, observed_at
            """
        )
        rows = cur.fetchall()
        print(f"Fetched {len(rows)} positions.")

        alerts = []

        for mmsi, group in groupby(rows, key=lambda row: row[0]):
            positions = list(group)
            vessel_type = vessel_types.get(mmsi)
            speed_limit, is_high_speed_craft = get_speed_limit(vessel_type)
            spike_indexes = detect_gps_spikes(positions, speed_limit)

            for index, curr in enumerate(positions):
                zones = check_geofence_context(cur_geo, curr[2], curr[3])
                zone_context = build_zone_context(zones)
                base_suspicious, base_benign = build_reason_lists(
                    zone_context, vessel_type, is_high_speed_craft
                )
                sog = curr[4]

                if index in spike_indexes:
                    spike = spike_indexes[index]
                    reasons_suspicious = base_suspicious + [
                        "one AIS point deviates sharply from the surrounding track",
                        f"rapid outbound/inbound jumps of {spike['leg_in_nm']:.1f} nm and {spike['leg_out_nm']:.1f} nm",
                        f"track returns close to baseline on the next report ({spike['bridge_nm']:.2f} nm apart)",
                    ]
                    reasons_benign = base_benign + [
                        "pattern matches a one-point GPS/AIS position spike rather than sustained movement"
                    ]
                    alerts.append(
                        build_alert(
                            mmsi=mmsi,
                            alert_type="kinematic_anomaly",
                            observed_at=curr[1],
                            lon=curr[2],
                            lat=curr[3],
                            details={
                                "sub_type": "gps_spike",
                                "distance_from_prev_nm": round(spike["leg_in_nm"], 2),
                                "distance_to_next_nm": round(spike["leg_out_nm"], 2),
                                "baseline_distance_nm": round(spike["bridge_nm"], 2),
                                "time_from_prev_seconds": round(spike["dt_prev"]),
                                "time_to_next_seconds": round(spike["dt_next"]),
                                "implied_speed_from_prev_knots": round(spike["implied_in"], 1),
                                "implied_speed_to_next_knots": round(spike["implied_out"], 1),
                                "baseline_implied_speed_knots": round(spike["implied_bridge"], 1),
                                "vessel_type": vessel_type,
                                "is_hsc": is_high_speed_craft,
                                "reasons_suspicious": reasons_suspicious,
                                "reasons_benign": reasons_benign,
                            },
                            explanation=(
                                f"Vessel {mmsi} shows a one-point GPS spike: the track jumps "
                                f"{spike['leg_in_nm']:.1f} nm and {spike['leg_out_nm']:.1f} nm around "
                                f"{curr[1].isoformat()}, then returns within {spike['bridge_nm']:.2f} nm "
                                "of the baseline track."
                            ),
                            base_severity=0.45 + min(max(spike["implied_in"], spike["implied_out"]) / 400.0, 0.20),
                            zone_context=zone_context,
                        )
                    )

                if sog is not None and sog > speed_limit:
                    reasons_suspicious = base_suspicious + [
                        f"reported SOG of {sog:.1f} knots exceeds the vessel-class limit of {speed_limit:.0f} knots"
                    ]
                    reasons_benign = list(base_benign)
                    alerts.append(
                        build_alert(
                            mmsi=mmsi,
                            alert_type="kinematic_anomaly",
                            observed_at=curr[1],
                            lon=curr[2],
                            lat=curr[3],
                            details={
                                "sub_type": "impossible_speed",
                                "reported_sog": sog,
                                "speed_limit": speed_limit,
                                "vessel_type": vessel_type,
                                "is_hsc": is_high_speed_craft,
                                "reasons_suspicious": reasons_suspicious,
                                "reasons_benign": reasons_benign,
                            },
                            explanation=(
                                f"Vessel {mmsi} reported SOG of {sog:.1f} knots, exceeding the "
                                f"{'high-speed craft' if is_high_speed_craft else 'normal'} limit of "
                                f"{speed_limit:.0f} knots."
                            ),
                            base_severity=min(sog / 80.0, 1.0),
                            zone_context=zone_context,
                        )
                    )

                if index == 0 or index in spike_indexes or (index - 1) in spike_indexes:
                    continue

                prev = positions[index - 1]
                time_diff = (curr[1] - prev[1]).total_seconds()
                if time_diff <= 0 or time_diff >= MAX_TELEPORT_WINDOW_SECONDS:
                    continue

                dist_nm = haversine_nm(prev[3], prev[2], curr[3], curr[2])
                implied_speed = (dist_nm / time_diff) * 3600
                if implied_speed <= MIN_TELEPORT_SPEED:
                    continue

                prev_sog = prev[4] or 0
                curr_sog = curr[4] or 0
                reported = max(prev_sog, curr_sog)

                if reported > 0:
                    ratio = implied_speed / reported
                    if ratio <= TELEPORT_SPEED_RATIO:
                        continue

                    reasons_suspicious = base_suspicious + [
                        f"moved {dist_nm:.1f} nm in {time_diff:.0f}s (implied {implied_speed:.0f} knots)",
                        f"reported SOG only reached {reported:.1f} knots ({ratio:.1f}x lower than implied)",
                    ]
                    reasons_benign = base_benign + [
                        "teleportation can reflect AIS lag, timestamp skew, or sensor fusion errors"
                    ]
                    alerts.append(
                        build_alert(
                            mmsi=mmsi,
                            alert_type="kinematic_anomaly",
                            observed_at=curr[1],
                            lon=curr[2],
                            lat=curr[3],
                            details={
                                "sub_type": "teleportation",
                                "distance_nm": round(dist_nm, 2),
                                "time_seconds": round(time_diff),
                                "implied_speed_knots": round(implied_speed, 1),
                                "reported_sog": reported,
                                "ratio": round(ratio, 1),
                                "vessel_type": vessel_type,
                                "is_hsc": is_high_speed_craft,
                                "reasons_suspicious": reasons_suspicious,
                                "reasons_benign": reasons_benign,
                            },
                            explanation=(
                                f"Vessel {mmsi} moved {dist_nm:.1f} nm in {time_diff:.0f}s "
                                f"(implied {implied_speed:.0f} knots), while reported SOG only reached "
                                f"{reported:.1f} knots."
                            ),
                            base_severity=min(implied_speed / 100.0, 1.0),
                            zone_context=zone_context,
                        )
                    )
                else:
                    reasons_suspicious = base_suspicious + [
                        f"geometric jump of {dist_nm:.1f} nm in {time_diff:.0f}s implies {implied_speed:.0f} knots",
                        "reported SOG was null or zero on both sides of the jump",
                    ]
                    reasons_benign = base_benign + [
                        "missing SOG lowers confidence because the jump may be a sensor or timestamp artifact"
                    ]
                    alerts.append(
                        build_alert(
                            mmsi=mmsi,
                            alert_type="kinematic_anomaly",
                            observed_at=curr[1],
                            lon=curr[2],
                            lat=curr[3],
                            details={
                                "sub_type": "null_sog_jump",
                                "distance_nm": round(dist_nm, 2),
                                "time_seconds": round(time_diff),
                                "implied_speed_knots": round(implied_speed, 1),
                                "reported_sog": 0,
                                "vessel_type": vessel_type,
                                "is_hsc": is_high_speed_craft,
                                "reasons_suspicious": reasons_suspicious,
                                "reasons_benign": reasons_benign,
                            },
                            explanation=(
                                f"Vessel {mmsi} made a geometric jump of {dist_nm:.1f} nm in "
                                f"{time_diff:.0f}s (implied {implied_speed:.0f} knots), but adjacent "
                                "reports had null/zero SOG."
                            ),
                            base_severity=0.5 + min(implied_speed / 300.0, 0.20),
                            zone_context=zone_context,
                        )
                    )

        print("Checking for duplicate MMSI...")
        cur.execute(
            """
            SELECT a.mmsi,
                   a.observed_at,
                   ST_X(a.geom) as lon1,
                   ST_Y(a.geom) as lat1,
                   ST_X(b.geom) as lon2,
                   ST_Y(b.geom) as lat2,
                   ST_Distance(a.geom::geography, b.geom::geography) as dist_m
            FROM ais_position a
            JOIN ais_position b
              ON a.mmsi = b.mmsi
             AND a.observed_at = b.observed_at
             AND a.id < b.id
            WHERE ST_Distance(a.geom::geography, b.geom::geography) > %s
            """,
            (DUPLICATE_MMSI_DISTANCE_METERS,),
        )
        for dupe in cur.fetchall():
            mid_lon = (dupe[2] + dupe[4]) / 2
            mid_lat = (dupe[3] + dupe[5]) / 2
            zones = check_geofence_context(cur_geo, mid_lon, mid_lat)
            zone_context = build_zone_context(zones)
            _, is_high_speed_craft = get_speed_limit(vessel_types.get(dupe[0]))
            reasons_suspicious, reasons_benign = build_reason_lists(
                zone_context, vessel_types.get(dupe[0]), is_high_speed_craft
            )
            reasons_suspicious = reasons_suspicious + [
                f"same MMSI reported simultaneously at two locations {dupe[6]:.0f} meters apart"
            ]
            reasons_benign = reasons_benign + [
                "duplicate shore feeds can create mirrored reports, but simultaneous separation this large is unusual"
            ]
            alerts.append(
                build_alert(
                    mmsi=dupe[0],
                    alert_type="identity_anomaly",
                    observed_at=dupe[1],
                    lon=dupe[2],
                    lat=dupe[3],
                    details={
                        "sub_type": "duplicate_mmsi",
                        "location_1": {"lat": dupe[3], "lon": dupe[2]},
                        "location_2": {"lat": dupe[5], "lon": dupe[4]},
                        "distance_meters": round(dupe[6], 1),
                        "reasons_suspicious": reasons_suspicious,
                        "reasons_benign": reasons_benign,
                    },
                    explanation=(
                        f"MMSI {dupe[0]} was reported at two locations {dupe[6]:.0f}m apart "
                        f"at the same time ({dupe[1].isoformat()}). This is an identity anomaly, "
                        "not just a kinematic inconsistency."
                    ),
                    base_severity=0.9,
                    zone_context=zone_context,
                )
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

        print(f"Identity/kinematic detector: {len(alerts)} alerts generated.")
        return alerts
    finally:
        cur.close()
        cur_geo.close()
        conn.close()


if __name__ == "__main__":
    detect_identity_kinematic()
