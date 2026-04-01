"""Detector 3: Loitering / Anchorage Anomaly.

Flags vessels with unusual dwell behavior: extended low-speed periods,
tight spatial clustering, or repeated stop-start patterns.
"""
import os
import json
import math
from datetime import timedelta
from itertools import groupby

import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://cue2case:cue2case_dev@localhost:5433/cue2case"
)

LOW_SPEED_THRESHOLD = 1.0  # knots
MIN_DWELL_MINUTES = 120     # 2 hours
MAX_SPREAD_NM = 0.5         # nautical miles
MIN_STOP_START_COUNT = 3    # repeated stops


def haversine_nm(lat1, lon1, lat2, lon2):
    """Distance in nautical miles."""
    R_NM = 3440.065
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R_NM * 2 * math.asin(math.sqrt(a))


def detect_loitering():
    """Run loitering detection."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    print("Fetching AIS positions for loitering detection...")
    cur.execute("""
        SELECT mmsi, observed_at, ST_X(geom) as lon, ST_Y(geom) as lat, sog
        FROM ais_position
        ORDER BY mmsi, observed_at
    """)
    rows = cur.fetchall()
    print(f"Fetched {len(rows)} positions.")

    alerts = []

    for mmsi, group in groupby(rows, key=lambda r: r[0]):
        positions = list(group)
        if len(positions) < 5:
            continue

        # Track low-speed runs
        low_speed_start = None
        low_speed_positions = []
        stop_start_count = 0
        was_stopped = False

        for i, pos in enumerate(positions):
            sog = pos[4]
            if sog is None:
                # Unknown speed breaks any active low-speed run.
                was_stopped = False
                if low_speed_positions and low_speed_start is not None:
                    dwell_minutes = (low_speed_positions[-1][1] - low_speed_positions[0][1]).total_seconds() / 60.0

                    if dwell_minutes >= MIN_DWELL_MINUTES:
                        # Calculate spatial spread
                        center_lat = sum(p[3] for p in low_speed_positions) / len(low_speed_positions)
                        center_lon = sum(p[2] for p in low_speed_positions) / len(low_speed_positions)
                        max_spread = max(
                            haversine_nm(center_lat, center_lon, p[3], p[2])
                            for p in low_speed_positions
                        )

                        if max_spread < MAX_SPREAD_NM:
                            severity = min(dwell_minutes / 480.0, 1.0)  # 8hr = 1.0
                            alerts.append({
                                'mmsi': mmsi,
                                'alert_type': 'loitering',
                                'severity': round(severity, 3),
                                'observed_at': low_speed_positions[0][1],
                                'lon': center_lon,
                                'lat': center_lat,
                                'details': {
                                    'sub_type': 'extended_dwell',
                                    'dwell_minutes': round(dwell_minutes, 1),
                                    'spread_nm': round(max_spread, 3),
                                    'position_count': len(low_speed_positions),
                                    'start_time': low_speed_positions[0][1].isoformat(),
                                    'end_time': low_speed_positions[-1][1].isoformat(),
                                },
                                'explanation': (
                                    f"Vessel {mmsi} loitered for {dwell_minutes:.0f} minutes "
                                    f"within {max_spread:.2f} nm radius near "
                                    f"({center_lat:.4f}, {center_lon:.4f})."
                                )
                            })

                low_speed_start = None
                low_speed_positions = []
                continue  # skip positions with unknown speed

            is_low = sog < LOW_SPEED_THRESHOLD

            # Stop-start detection
            if is_low and not was_stopped:
                stop_start_count += 1
                was_stopped = True
            elif not is_low:
                was_stopped = False

            if is_low:
                if low_speed_start is None:
                    low_speed_start = i
                low_speed_positions.append(pos)
                continue

            # End of low-speed run — check if it qualifies
            if low_speed_positions and low_speed_start is not None:
                dwell_minutes = (low_speed_positions[-1][1] - low_speed_positions[0][1]).total_seconds() / 60.0

                if dwell_minutes >= MIN_DWELL_MINUTES:
                    # Calculate spatial spread
                    center_lat = sum(p[3] for p in low_speed_positions) / len(low_speed_positions)
                    center_lon = sum(p[2] for p in low_speed_positions) / len(low_speed_positions)
                    max_spread = max(
                        haversine_nm(center_lat, center_lon, p[3], p[2])
                        for p in low_speed_positions
                    )

                    if max_spread < MAX_SPREAD_NM:
                        severity = min(dwell_minutes / 480.0, 1.0)  # 8hr = 1.0
                        alerts.append({
                            'mmsi': mmsi,
                            'alert_type': 'loitering',
                            'severity': round(severity, 3),
                            'observed_at': low_speed_positions[0][1],
                            'lon': center_lon,
                            'lat': center_lat,
                            'details': {
                                'sub_type': 'extended_dwell',
                                'dwell_minutes': round(dwell_minutes, 1),
                                'spread_nm': round(max_spread, 3),
                                'position_count': len(low_speed_positions),
                                'start_time': low_speed_positions[0][1].isoformat(),
                                'end_time': low_speed_positions[-1][1].isoformat(),
                            },
                            'explanation': (
                                f"Vessel {mmsi} loitered for {dwell_minutes:.0f} minutes "
                                f"within {max_spread:.2f} nm radius near "
                                f"({center_lat:.4f}, {center_lon:.4f})."
                            )
                        })

            low_speed_start = None
            low_speed_positions = []

        # Check final run
        if low_speed_positions and low_speed_start is not None:
            dwell_minutes = (low_speed_positions[-1][1] - low_speed_positions[0][1]).total_seconds() / 60.0
            if dwell_minutes >= MIN_DWELL_MINUTES:
                center_lat = sum(p[3] for p in low_speed_positions) / len(low_speed_positions)
                center_lon = sum(p[2] for p in low_speed_positions) / len(low_speed_positions)
                max_spread = max(
                    haversine_nm(center_lat, center_lon, p[3], p[2])
                    for p in low_speed_positions
                )
                if max_spread < MAX_SPREAD_NM:
                    severity = min(dwell_minutes / 480.0, 1.0)
                    alerts.append({
                        'mmsi': mmsi,
                        'alert_type': 'loitering',
                        'severity': round(severity, 3),
                        'observed_at': low_speed_positions[0][1],
                        'lon': center_lon,
                        'lat': center_lat,
                        'details': {
                            'sub_type': 'extended_dwell',
                            'dwell_minutes': round(dwell_minutes, 1),
                            'spread_nm': round(max_spread, 3),
                            'position_count': len(low_speed_positions),
                            'start_time': low_speed_positions[0][1].isoformat(),
                            'end_time': low_speed_positions[-1][1].isoformat(),
                        },
                        'explanation': (
                            f"Vessel {mmsi} loitered for {dwell_minutes:.0f} minutes "
                            f"within {max_spread:.2f} nm radius near "
                            f"({center_lat:.4f}, {center_lon:.4f})."
                        )
                    })

        # Stop-start pattern
        if stop_start_count >= MIN_STOP_START_COUNT:
            severity = min(stop_start_count / 10.0, 1.0)
            mid = positions[len(positions) // 2]
            alerts.append({
                'mmsi': mmsi,
                'alert_type': 'loitering',
                'severity': round(severity, 3),
                'observed_at': positions[0][1],
                'lon': mid[2],
                'lat': mid[3],
                'details': {
                    'sub_type': 'stop_start_pattern',
                    'stop_count': stop_start_count,
                    'total_positions': len(positions),
                },
                'explanation': (
                    f"Vessel {mmsi} exhibited repeated stop-start behavior "
                    f"({stop_start_count} stops) over {len(positions)} position reports."
                )
            })

    # Insert alerts
    if alerts:
        alert_rows = [(
            a['mmsi'], a['alert_type'], a['severity'], a['observed_at'],
            a['lon'], a['lat'], json.dumps(a['details']), a['explanation']
        ) for a in alerts]

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

    print(f"Loitering detector: {len(alerts)} alerts generated.")
    cur.close()
    conn.close()
    return alerts


if __name__ == '__main__':
    detect_loitering()
