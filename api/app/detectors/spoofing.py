"""Detector for AIS spoofing and GPS manipulation patterns."""

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

IMPOSSIBLE_SPEED_THRESHOLD_KTS = 60.0
TELEPORT_DISTANCE_THRESHOLD_NM = 100.0
TELEPORT_WINDOW = timedelta(minutes=10)

# Simple inland bounding boxes near Duqm where legitimate vessel positions are unlikely.
# Each tuple is (min_lat, max_lat, min_lon, max_lon, label).
DUQM_LAND_BBOXES = [
    (19.55, 19.72, 57.56, 57.80, "duqm_inland_north"),
    (19.40, 19.55, 57.62, 57.92, "duqm_industrial_inland"),
    (19.23, 19.40, 57.70, 57.98, "duqm_airport_inland"),
]


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


def is_position_on_land(lat, lon):
    """Return the matching Duqm inland bbox label when the position falls on land."""
    for min_lat, max_lat, min_lon, max_lon, label in DUQM_LAND_BBOXES:
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            return label
    return None


def get_track_segment_id(cur, mmsi, observed_at):
    """Best-effort lookup of the enclosing track segment for a position timestamp."""
    cur.execute(
        """
        SELECT id
        FROM track_segment
        WHERE mmsi = %s
          AND start_time <= %s
          AND end_time >= %s
        ORDER BY start_time DESC
        LIMIT 1
        """,
        (mmsi, observed_at, observed_at),
    )
    row = cur.fetchone()
    return row[0] if row else None



def build_alert(
    cur,
    *,
    mmsi,
    title,
    description,
    severity,
    latitude,
    longitude,
    detected_at,
    start_observed_at,
    end_observed_at,
    metadata,
):
    """Build an alert row for bulk insertion."""
    return (
        mmsi,
        "spoofing",
        title,
        description,
        severity,
        latitude,
        longitude,
        detected_at,
        start_observed_at,
        end_observed_at,
        json.dumps(metadata),
        get_track_segment_id(cur, mmsi, detected_at),
    )



def detect_spoofing():
    """Run spoofing detection for impossible jumps, teleports, land hits, and duplicate timestamps."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur_track = conn.cursor()

    try:
        cur.execute(
            """
            SELECT id, mmsi, observed_at, ST_X(geom) AS lon, ST_Y(geom) AS lat
            FROM ais_position
            ORDER BY mmsi, observed_at, id
            """
        )
        rows = cur.fetchall()
        alerts = []

        for mmsi, group in groupby(rows, key=lambda row: row[1]):
            positions = list(group)
            if not positions:
                continue

            for position in positions:
                _, _, observed_at, lon, lat = position
                land_label = is_position_on_land(lat, lon)
                if land_label:
                    alerts.append(
                        build_alert(
                            cur_track,
                            mmsi=mmsi,
                            title="AIS position reported inland near Duqm",
                            description=(
                                f"Vessel {mmsi} reported AIS position at {lat:.5f}, {lon:.5f}, "
                                f"inside inland area {land_label} near Duqm."
                            ),
                            severity=2,
                            latitude=lat,
                            longitude=lon,
                            detected_at=observed_at,
                            start_observed_at=observed_at,
                            end_observed_at=observed_at,
                            metadata={
                                "subtype": "position_on_land",
                                "land_bbox": land_label,
                                "latitude": lat,
                                "longitude": lon,
                            },
                        )
                    )

            if len(positions) < 2:
                continue

            for i in range(1, len(positions)):
                prev = positions[i - 1]
                curr = positions[i]

                prev_id, _, prev_time, prev_lon, prev_lat = prev
                curr_id, _, curr_time, curr_lon, curr_lat = curr

                time_diff = curr_time - prev_time
                seconds = time_diff.total_seconds()
                if seconds <= 0:
                    continue

                distance_nm = haversine_nm(prev_lat, prev_lon, curr_lat, curr_lon)
                speed_kts = distance_nm / (seconds / 3600.0)

                if speed_kts > IMPOSSIBLE_SPEED_THRESHOLD_KTS:
                    alerts.append(
                        build_alert(
                            cur_track,
                            mmsi=mmsi,
                            title="Impossible AIS speed jump detected",
                            description=(
                                f"Vessel {mmsi} moved {distance_nm:.2f} nm in {seconds:.0f} seconds "
                                f"({speed_kts:.1f} kt) between consecutive AIS reports."
                            ),
                            severity=3,
                            latitude=curr_lat,
                            longitude=curr_lon,
                            detected_at=curr_time,
                            start_observed_at=prev_time,
                            end_observed_at=curr_time,
                            metadata={
                                "subtype": "impossible_speed_jump",
                                "from_position_id": prev_id,
                                "to_position_id": curr_id,
                                "distance_nm": round(distance_nm, 3),
                                "time_delta_seconds": round(seconds, 3),
                                "calculated_speed_kts": round(speed_kts, 3),
                                "from": {
                                    "observed_at": prev_time.isoformat(),
                                    "latitude": prev_lat,
                                    "longitude": prev_lon,
                                },
                                "to": {
                                    "observed_at": curr_time.isoformat(),
                                    "latitude": curr_lat,
                                    "longitude": curr_lon,
                                },
                            },
                        )
                    )

                if distance_nm > TELEPORT_DISTANCE_THRESHOLD_NM and time_diff < TELEPORT_WINDOW:
                    alerts.append(
                        build_alert(
                            cur_track,
                            mmsi=mmsi,
                            title="AIS teleport cluster detected",
                            description=(
                                f"Vessel {mmsi} appeared {distance_nm:.2f} nm away within "
                                f"{seconds / 60.0:.1f} minutes between AIS reports."
                            ),
                            severity=4,
                            latitude=curr_lat,
                            longitude=curr_lon,
                            detected_at=curr_time,
                            start_observed_at=prev_time,
                            end_observed_at=curr_time,
                            metadata={
                                "subtype": "teleport_cluster",
                                "from_position_id": prev_id,
                                "to_position_id": curr_id,
                                "distance_nm": round(distance_nm, 3),
                                "time_delta_seconds": round(seconds, 3),
                                "time_delta_minutes": round(seconds / 60.0, 3),
                                "from": {
                                    "observed_at": prev_time.isoformat(),
                                    "latitude": prev_lat,
                                    "longitude": prev_lon,
                                },
                                "to": {
                                    "observed_at": curr_time.isoformat(),
                                    "latitude": curr_lat,
                                    "longitude": curr_lon,
                                },
                            },
                        )
                    )

        cur.execute(
            """
            SELECT
                a.mmsi,
                a.observed_at,
                a.id,
                ST_Y(a.geom) AS lat_a,
                ST_X(a.geom) AS lon_a,
                b.id,
                ST_Y(b.geom) AS lat_b,
                ST_X(b.geom) AS lon_b,
                ST_Distance(a.geom::geography, b.geom::geography) AS distance_meters
            FROM ais_position a
            JOIN ais_position b
              ON a.mmsi = b.mmsi
             AND a.observed_at = b.observed_at
             AND a.id < b.id
            WHERE ST_Distance(a.geom::geography, b.geom::geography) > 1000
            ORDER BY a.mmsi, a.observed_at, a.id, b.id
            """
        )

        for row in cur.fetchall():
            (
                mmsi,
                observed_at,
                position_a_id,
                lat_a,
                lon_a,
                position_b_id,
                lat_b,
                lon_b,
                distance_meters,
            ) = row
            alerts.append(
                build_alert(
                    cur_track,
                    mmsi=mmsi,
                    title="Duplicate AIS timestamps with conflicting positions",
                    description=(
                        f"Vessel {mmsi} reported multiple positions at {observed_at.isoformat()} "
                        f"that were {distance_meters:.0f} meters apart."
                    ),
                    severity=2,
                    latitude=lat_a,
                    longitude=lon_a,
                    detected_at=observed_at,
                    start_observed_at=observed_at,
                    end_observed_at=observed_at,
                    metadata={
                        "subtype": "duplicate_timestamp",
                        "position_a_id": position_a_id,
                        "position_b_id": position_b_id,
                        "distance_meters": round(distance_meters, 3),
                        "position_a": {"latitude": lat_a, "longitude": lon_a},
                        "position_b": {"latitude": lat_b, "longitude": lon_b},
                    },
                )
            )

        if alerts:
            execute_values(
                cur,
                """
                INSERT INTO alert (
                    mmsi,
                    alert_type,
                    title,
                    description,
                    severity,
                    latitude,
                    longitude,
                    detected_at,
                    start_observed_at,
                    end_observed_at,
                    metadata,
                    track_segment_id
                )
                VALUES %s
                """,
                alerts,
                template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)",
            )
            conn.commit()

        print(f"Spoofing detector: {len(alerts)} alerts generated.")
        return len(alerts)
    finally:
        cur_track.close()
        cur.close()
        conn.close()


if __name__ == "__main__":
    detect_spoofing()
