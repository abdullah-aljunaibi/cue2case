"""Detector 1: Abnormal Port Approach.

Flags vessels with sudden speed/heading changes or corridor deviation
in the port approach area.
"""

import json
import os
from datetime import timedelta
from itertools import groupby

import psycopg2

DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://cue2case:cue2case_dev@localhost:5433/cue2case",
)

# Long Beach approach corridor (approximate center line)
# Main channel runs roughly NW-SE at heading ~310-330 inbound
APPROACH_BBOX = {
    "min_lat": 33.68,
    "max_lat": 33.76,
    "min_lon": -118.25,
    "max_lon": -118.15,
}
EXPECTED_INBOUND_HEADING_RANGE = (280, 360)  # degrees, roughly NW approach
SPEED_CHANGE_THRESHOLD = 8.0  # knots change in 5 min
HEADING_CHANGE_THRESHOLD = 90.0  # degrees change in 5 min
TIME_WINDOW = timedelta(minutes=5)


def heading_diff(h1, h2):
    """Calculate minimum angular difference between two headings."""
    if h1 is None or h2 is None:
        return None
    diff = abs(h1 - h2) % 360
    return min(diff, 360 - diff)


def detect_abnormal_approach():
    """Run abnormal approach detection on all positions in approach area."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT mmsi, observed_at, ST_X(geom) as lon, ST_Y(geom) as lat,
                   sog, cog, heading
            FROM ais_position
            WHERE ST_Y(geom) BETWEEN %s AND %s
              AND ST_X(geom) BETWEEN %s AND %s
            ORDER BY mmsi, observed_at
            """,
            (
                APPROACH_BBOX["min_lat"],
                APPROACH_BBOX["max_lat"],
                APPROACH_BBOX["min_lon"],
                APPROACH_BBOX["max_lon"],
            ),
        )

        rows = cur.fetchall()
        alerts = []

        for mmsi, group in groupby(rows, key=lambda row: row[0]):
            positions = list(group)
            if len(positions) < 2:
                continue

            for i in range(1, len(positions)):
                prev = positions[i - 1]
                curr = positions[i]

                time_diff = curr[1] - prev[1]
                if time_diff > TIME_WINDOW or time_diff.total_seconds() <= 0:
                    continue

                if prev[4] is not None and curr[4] is not None:
                    speed_change = abs(curr[4] - prev[4])
                    if speed_change > SPEED_CHANGE_THRESHOLD:
                        severity = min(speed_change / 20.0, 1.0)
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
                                },
                                "explanation": (
                                    f"Vessel {mmsi} had sudden speed change of "
                                    f"{speed_change:.1f} knots ({prev[4]:.1f} → "
                                    f"{curr[4]:.1f}) within "
                                    f"{time_diff.total_seconds():.0f}s in port approach area."
                                ),
                            }
                        )

                h_diff = heading_diff(prev[6], curr[6])
                if h_diff is not None and h_diff > HEADING_CHANGE_THRESHOLD:
                    severity = min(h_diff / 180.0, 1.0)
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
                                "delta_heading": round(h_diff, 2),
                                "time_delta_sec": time_diff.total_seconds(),
                            },
                            "explanation": (
                                f"Vessel {mmsi} made sharp heading change of "
                                f"{h_diff:.0f}° ({prev[6]:.0f}° → {curr[6]:.0f}°) "
                                f"within {time_diff.total_seconds():.0f}s in port "
                                f"approach area."
                            ),
                        }
                    )

        if alerts:
            from psycopg2.extras import execute_values

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
        cur.close()
        conn.close()


if __name__ == "__main__":
    detect_abnormal_approach()
