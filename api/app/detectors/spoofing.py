"""Detector 5: Spoofing / GPS Manipulation.

Flags impossible speed jumps, teleport clusters, positions on land,
and duplicate timestamps with conflicting positions.
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

IMPOSSIBLE_SPEED_THRESHOLD_KTS = 60.0
TELEPORT_DISTANCE_NM = 100.0
TELEPORT_TIME_SECONDS = 600  # 10 minutes

# Duqm inland bounding boxes (simple rectangles known to be on land)
LAND_BBOXES = [
    {"label": "duqm_inland_west", "min_lat": 19.60, "max_lat": 19.75, "min_lon": 57.55, "max_lon": 57.65},
    {"label": "duqm_inland_north", "min_lat": 19.75, "max_lat": 19.85, "min_lon": 57.65, "max_lon": 57.75},
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
    """Check if position falls inside a known land bounding box."""
    for bbox in LAND_BBOXES:
        if bbox["min_lat"] <= lat <= bbox["max_lat"] and bbox["min_lon"] <= lon <= bbox["max_lon"]:
            return bbox["label"]
    return None


def detect_spoofing():
    """Run spoofing detection for impossible jumps, teleports, land hits, and duplicate timestamps."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    try:
        # Fetch all positions ordered by vessel and time
        cur.execute(
            """
            SELECT mmsi, observed_at, ST_Y(geom) AS lat, ST_X(geom) AS lon
            FROM ais_position
            ORDER BY mmsi, observed_at
            """
        )
        rows = cur.fetchall()
        alerts = []

        for mmsi, group in groupby(rows, key=lambda row: row[0]):
            positions = list(group)

            # Check each position for land
            for _, observed_at, lat, lon in positions:
                land_label = is_position_on_land(lat, lon)
                if land_label:
                    alerts.append((
                        mmsi, "spoofing", 0.5, observed_at, lon, lat,
                        json.dumps({"subtype": "position_on_land", "land_bbox": land_label, "lat": lat, "lon": lon}),
                        f"Vessel {mmsi} reported position at {lat:.5f}, {lon:.5f} inside inland area {land_label}."
                    ))

            if len(positions) < 2:
                continue

            # Check consecutive pairs for speed/teleport
            for i in range(1, len(positions)):
                _, prev_time, prev_lat, prev_lon = positions[i - 1]
                _, curr_time, curr_lat, curr_lon = positions[i]

                seconds = (curr_time - prev_time).total_seconds()
                if seconds <= 0:
                    continue

                distance_nm = haversine_nm(prev_lat, prev_lon, curr_lat, curr_lon)
                speed_kts = distance_nm / (seconds / 3600.0)

                # Teleport: >100nm in <10 minutes
                if distance_nm > TELEPORT_DISTANCE_NM and seconds < TELEPORT_TIME_SECONDS:
                    alerts.append((
                        mmsi, "spoofing", 0.9, curr_time, curr_lon, curr_lat,
                        json.dumps({
                            "subtype": "teleport", "distance_nm": round(distance_nm, 2),
                            "time_seconds": round(seconds), "speed_kts": round(speed_kts, 1),
                            "from": {"lat": prev_lat, "lon": prev_lon},
                            "to": {"lat": curr_lat, "lon": curr_lon},
                        }),
                        f"Vessel {mmsi} teleported {distance_nm:.1f}nm in {seconds:.0f}s ({speed_kts:.0f}kt)."
                    ))
                # Impossible speed: >60kt
                elif speed_kts > IMPOSSIBLE_SPEED_THRESHOLD_KTS:
                    alerts.append((
                        mmsi, "spoofing", 0.7, curr_time, curr_lon, curr_lat,
                        json.dumps({
                            "subtype": "impossible_speed", "speed_kts": round(speed_kts, 1),
                            "distance_nm": round(distance_nm, 2), "time_seconds": round(seconds),
                        }),
                        f"Vessel {mmsi} moved {distance_nm:.1f}nm in {seconds:.0f}s ({speed_kts:.0f}kt)."
                    ))

        # Duplicate timestamps: same MMSI, same time, different positions >1km apart
        cur.execute(
            """
            SELECT
                a.mmsi, a.observed_at,
                ST_Y(a.geom) AS lat_a, ST_X(a.geom) AS lon_a,
                ST_Y(b.geom) AS lat_b, ST_X(b.geom) AS lon_b,
                ST_Distance(a.geom::geography, b.geom::geography) AS distance_meters
            FROM ais_position a
            JOIN ais_position b ON a.mmsi = b.mmsi
                AND a.observed_at = b.observed_at
                AND a.id < b.id
            WHERE ST_Distance(a.geom::geography, b.geom::geography) > 1000
            ORDER BY a.mmsi, a.observed_at
            """
        )
        for row in cur.fetchall():
            mmsi, observed_at, lat_a, lon_a, lat_b, lon_b, dist_m = row
            alerts.append((
                mmsi, "spoofing", 0.6, observed_at, lon_a, lat_a,
                json.dumps({
                    "subtype": "duplicate_timestamp", "distance_meters": round(dist_m, 1),
                    "position_a": {"lat": lat_a, "lon": lon_a},
                    "position_b": {"lat": lat_b, "lon": lon_b},
                }),
                f"Vessel {mmsi} reported conflicting positions {dist_m:.0f}m apart at {observed_at.isoformat()}."
            ))

        if alerts:
            execute_values(
                cur,
                """
                INSERT INTO alert (mmsi, alert_type, severity, observed_at, geom, details, explanation)
                VALUES %s
                """,
                alerts,
                template="(%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s::jsonb, %s)",
            )
            conn.commit()

        print(f"Spoofing detector: {len(alerts)} alerts generated.")
        return len(alerts)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    detect_spoofing()
