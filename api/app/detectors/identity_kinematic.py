"""Detector 4: Identity / Kinematic Inconsistency.

Flags impossible speeds, teleportation (implied speed >> reported SOG),
and duplicate MMSI behavior.
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
DUPLICATE_MMSI_LIMIT = 100


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


def detect_identity_kinematic():
    """Run identity/kinematic inconsistency detection."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

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
            is_high_speed_craft = (
                vessel_type is not None and vessel_type in HIGH_SPEED_VESSEL_TYPES
            )
            speed_limit = HIGH_SPEED_SOG if is_high_speed_craft else MAX_NORMAL_SOG

            for index, curr in enumerate(positions):
                sog = curr[4]

                if sog is not None and sog > speed_limit:
                    severity = min(sog / 80.0, 1.0)
                    alerts.append(
                        {
                            "mmsi": mmsi,
                            "alert_type": "identity_inconsistency",
                            "severity": round(severity, 3),
                            "observed_at": curr[1],
                            "lon": curr[2],
                            "lat": curr[3],
                            "details": {
                                "sub_type": "impossible_speed",
                                "reported_sog": sog,
                                "speed_limit": speed_limit,
                                "vessel_type": vessel_type,
                                "is_hsc": is_high_speed_craft,
                            },
                            "explanation": (
                                f"Vessel {mmsi} reported SOG of {sog:.1f} knots, "
                                f"exceeding {'HSC' if is_high_speed_craft else 'normal'} "
                                f"limit of {speed_limit:.0f} knots."
                            ),
                        }
                    )

                if index == 0:
                    continue

                prev = positions[index - 1]
                time_diff = (curr[1] - prev[1]).total_seconds()
                if time_diff <= 0 or time_diff >= MAX_TELEPORT_WINDOW_SECONDS:
                    continue

                dist_nm = haversine_nm(prev[3], prev[2], curr[3], curr[2])
                implied_speed = (dist_nm / time_diff) * 3600
                if implied_speed <= MIN_TELEPORT_SPEED:
                    continue

                reported = max(prev[4] or 0, curr[4] or 0)
                if reported <= 0:
                    continue

                ratio = implied_speed / reported
                if ratio <= TELEPORT_SPEED_RATIO:
                    continue

                severity = min(implied_speed / 100.0, 1.0)
                alerts.append(
                    {
                        "mmsi": mmsi,
                        "alert_type": "identity_inconsistency",
                        "severity": round(severity, 3),
                        "observed_at": curr[1],
                        "lon": curr[2],
                        "lat": curr[3],
                        "details": {
                            "sub_type": "teleportation",
                            "distance_nm": round(dist_nm, 2),
                            "time_seconds": round(time_diff),
                            "implied_speed_knots": round(implied_speed, 1),
                            "reported_sog": reported,
                            "ratio": round(ratio, 1),
                        },
                        "explanation": (
                            f"Vessel {mmsi} moved {dist_nm:.1f} nm in {time_diff:.0f}s "
                            f"(implied {implied_speed:.0f} knots), but reported SOG "
                            f"{reported:.1f} knots. Ratio: {ratio:.1f}x."
                        ),
                    }
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
            LIMIT %s
            """,
            (DUPLICATE_MMSI_DISTANCE_METERS, DUPLICATE_MMSI_LIMIT),
        )
        for dupe in cur.fetchall():
            alerts.append(
                {
                    "mmsi": dupe[0],
                    "alert_type": "identity_inconsistency",
                    "severity": 0.9,
                    "observed_at": dupe[1],
                    "lon": dupe[2],
                    "lat": dupe[3],
                    "details": {
                        "sub_type": "duplicate_mmsi",
                        "location_1": {"lat": dupe[3], "lon": dupe[2]},
                        "location_2": {"lat": dupe[5], "lon": dupe[4]},
                        "distance_meters": round(dupe[6], 1),
                    },
                    "explanation": (
                        f"MMSI {dupe[0]} reported at two locations {dupe[6]:.0f}m "
                        f"apart at the same time ({dupe[1].isoformat()}). Possible "
                        "MMSI spoofing or sharing."
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

        print(f"Identity/kinematic detector: {len(alerts)} alerts generated.")
        return alerts
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    detect_identity_kinematic()
