"""Detector 2: AIS Silence.

Flags vessels that stop broadcasting AIS for suspicious durations.
A gap > 15 minutes between consecutive positions is flagged.
"""

import json
import os
from itertools import groupby

import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://cue2case:cue2case_dev@localhost:5433/cue2case",
)

MIN_SILENCE_MINUTES = 15
SEVERITY_THRESHOLDS = [
    (120, 0.9),  # 2+ hours
    (60, 0.7),  # 1+ hour
    (30, 0.5),  # 30+ minutes
    (15, 0.3),  # 15+ minutes
]


def calculate_severity(gap_minutes):
    """Map gap duration in minutes to a severity score."""
    for threshold_minutes, severity in SEVERITY_THRESHOLDS:
        if gap_minutes >= threshold_minutes:
            return severity
    return 0.2


def detect_ais_silence():
    """Run AIS silence detection across all vessels."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    try:
        print("Fetching AIS positions for silence detection...")
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
            if len(positions) < 2:
                continue

            for i in range(1, len(positions)):
                prev = positions[i - 1]
                curr = positions[i]

                gap = curr[1] - prev[1]
                gap_minutes = gap.total_seconds() / 60.0

                if gap_minutes < MIN_SILENCE_MINUTES:
                    continue

                severity = calculate_severity(gap_minutes)
                alerts.append(
                    {
                        "mmsi": mmsi,
                        "alert_type": "ais_silence",
                        "severity": round(severity, 3),
                        "observed_at": prev[1],
                        "lon": prev[2],
                        "lat": prev[3],
                        "details": {
                            "gap_minutes": round(gap_minutes, 1),
                            "last_seen": prev[1].isoformat(),
                            "last_lat": prev[3],
                            "last_lon": prev[2],
                            "last_sog": prev[4],
                            "reappeared_at": curr[1].isoformat(),
                            "reappeared_lat": curr[3],
                            "reappeared_lon": curr[2],
                            "reappeared_sog": curr[4],
                        },
                        "explanation": (
                            f"Vessel {mmsi} went silent for {gap_minutes:.0f} minutes. "
                            f"Last seen at ({prev[3]:.4f}, {prev[2]:.4f}) at {prev[1].isoformat()}, "
                            f"reappeared at ({curr[3]:.4f}, {curr[2]:.4f}) at {curr[1].isoformat()}."
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

        print(f"AIS silence detector: {len(alerts)} alerts generated.")
        return alerts
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    detect_ais_silence()
