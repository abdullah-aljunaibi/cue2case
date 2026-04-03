"""Detector 3: Loitering / Anchorage Anomaly (Context-Aware).

Flags vessels with unusual dwell behavior. Context-aware: considers
whether dwell occurs in expected zones (anchorage, harbor) vs
unexpected zones (approach corridor, restricted areas, open water).
"""
import os
import json
import math
from itertools import groupby

import psycopg2
from psycopg2.extras import execute_values

DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://cue2case:cue2case_dev@localhost:5433/cue2case"
)

LOW_SPEED_THRESHOLD = 1.0  # knots
MIN_DWELL_MINUTES = 120     # 2 hours minimum dwell
MAX_SPREAD_NM = 0.5         # nautical miles for tight clustering
MIN_STOP_DURATION_SEC = 300  # 5 min minimum per stop episode
MIN_STOP_START_EPISODES = 3  # repeated stop-start count
MAX_STOP_CLUSTER_DURATION_SEC = 8 * 3600  # cap cluster span at 8 hours


def haversine_nm(lat1, lon1, lat2, lon2):
    """Distance in nautical miles."""
    R_NM = 3440.065
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R_NM * 2 * math.asin(math.sqrt(a))


def check_geofence_context(cur, lon, lat):
    """Check which geofence zones a point falls in."""
    cur.execute("""
        SELECT name, zone_type
        FROM geofence
        WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
    """, (lon, lat))
    return cur.fetchall()


def calculate_dwell_severity(dwell_minutes, spread_nm, zone_types):
    """Calculate severity considering zone context.

    Dwell in anchorage/harbor = expected (low severity).
    Dwell in approach/restricted/open water = suspicious (high severity).
    """
    # Base from duration
    if dwell_minutes >= 480:
        base = 0.7
    elif dwell_minutes >= 240:
        base = 0.5
    elif dwell_minutes >= 120:
        base = 0.3
    else:
        base = 0.2

    # Tighter spread = more deliberate loitering
    if spread_nm < 0.1:
        base += 0.05

    # Zone context modifiers
    if 'restricted' in zone_types:
        base += 0.25  # loitering near restricted zone is very suspicious
    elif 'approach' in zone_types:
        base += 0.15  # loitering in approach corridor is suspicious
    elif 'anchorage' in zone_types:
        base -= 0.15  # expected behavior
    elif 'harbor' in zone_types:
        base -= 0.1   # expected behavior
    else:
        base += 0.1   # open water loitering = somewhat suspicious

    return max(0.05, min(round(base, 3), 1.0))


def detect_loitering():
    """Run context-aware loitering detection."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur_geo = conn.cursor()

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

        # --- Extended Dwell Detection ---
        low_speed_start = None
        low_speed_positions = []

        # --- Episode-level Stop-Start Detection ---
        stop_episodes = []  # list of (start_time, end_time, positions)
        current_stop_start = None
        current_stop_positions = []

        for i, pos in enumerate(positions):
            sog = pos[4]
            if sog is None:
                # Unknown speed: end any active low-speed run
                if low_speed_positions:
                    _process_dwell(mmsi, low_speed_positions, cur_geo, alerts)
                low_speed_start = None
                low_speed_positions = []
                # Also end any stop episode
                if current_stop_start is not None and current_stop_positions:
                    duration = (current_stop_positions[-1][1] - current_stop_start).total_seconds()
                    if duration >= MIN_STOP_DURATION_SEC:
                        stop_episodes.append((current_stop_start, current_stop_positions[-1][1], len(current_stop_positions)))
                current_stop_start = None
                current_stop_positions = []
                continue

            is_low = sog < LOW_SPEED_THRESHOLD

            # Extended dwell tracking
            if is_low:
                if low_speed_start is None:
                    low_speed_start = i
                low_speed_positions.append(pos)
            else:
                if low_speed_positions:
                    _process_dwell(mmsi, low_speed_positions, cur_geo, alerts)
                low_speed_start = None
                low_speed_positions = []

            # Episode-level stop-start tracking
            if is_low:
                if current_stop_start is None:
                    current_stop_start = pos[1]
                current_stop_positions.append(pos)
            else:
                if current_stop_start is not None and current_stop_positions:
                    duration = (current_stop_positions[-1][1] - current_stop_start).total_seconds()
                    if duration >= MIN_STOP_DURATION_SEC:
                        stop_episodes.append((current_stop_start, current_stop_positions[-1][1], len(current_stop_positions)))
                current_stop_start = None
                current_stop_positions = []

        # Process final dwell run
        if low_speed_positions:
            _process_dwell(mmsi, low_speed_positions, cur_geo, alerts)

        # Process final stop episode
        if current_stop_start is not None and current_stop_positions:
            duration = (current_stop_positions[-1][1] - current_stop_start).total_seconds()
            if duration >= MIN_STOP_DURATION_SEC:
                stop_episodes.append((current_stop_start, current_stop_positions[-1][1], len(current_stop_positions)))

        # --- Stop-Start Pattern Alerts (clustered by 2-hour proximity) ---
        if len(stop_episodes) >= MIN_STOP_START_EPISODES:
            # Cluster episodes within 2 hours of each other, but prevent one
            # rolling chain from spanning multiple days.
            clusters = []
            current_cluster = [stop_episodes[0]]
            cluster_start = stop_episodes[0][0]
            for ep in stop_episodes[1:]:
                within_gap = (ep[0] - current_cluster[-1][1]).total_seconds() <= 7200
                within_max_span = (ep[1] - cluster_start).total_seconds() <= MAX_STOP_CLUSTER_DURATION_SEC
                if within_gap and within_max_span:
                    current_cluster.append(ep)
                else:
                    clusters.append(current_cluster)
                    current_cluster = [ep]
                    cluster_start = ep[0]
            clusters.append(current_cluster)

            for cluster in clusters:
                if len(cluster) < MIN_STOP_START_EPISODES:
                    continue

                cluster_start = cluster[0][0]
                cluster_end = cluster[-1][1]

                # Only use low-speed stop-episode positions when deriving the
                # cluster centroid and geofence context.
                cluster_positions = [
                    p
                    for p in positions
                    if any(ep_start <= p[1] <= ep_end for ep_start, ep_end, _ in cluster)
                ]
                if not cluster_positions:
                    continue

                avg_lon = sum(p[2] for p in cluster_positions) / len(cluster_positions)
                avg_lat = sum(p[3] for p in cluster_positions) / len(cluster_positions)

                zones = check_geofence_context(cur_geo, avg_lon, avg_lat)
                zone_types = {z[1] for z in zones}

                if 'restricted' in zone_types:
                    severity = min(len(cluster) / 6.0 + 0.3, 1.0)
                elif 'anchorage' in zone_types or 'harbor' in zone_types:
                    severity = max(len(cluster) / 15.0, 0.1)
                else:
                    severity = min(len(cluster) / 8.0, 1.0)

                reasons_suspicious = []
                reasons_benign = []

                if 'restricted' in zone_types:
                    reasons_suspicious.append("near restricted zone")
                if len(cluster) >= 5:
                    reasons_suspicious.append(f"high stop count ({len(cluster)} episodes)")
                if 'anchorage' in zone_types:
                    reasons_benign.append("in designated anchorage area")
                if 'harbor' in zone_types:
                    reasons_benign.append("in harbor operations zone")

                alerts.append({
                    'mmsi': mmsi,
                    'alert_type': 'loitering',
                    'severity': max(0.05, min(round(severity, 3), 1.0)),
                    'observed_at': cluster_start,
                    'lon': avg_lon,
                    'lat': avg_lat,
                    'details': {
                        'sub_type': 'stop_start_pattern',
                        'stop_episodes': len(cluster),
                        'cluster_start': cluster_start.isoformat(),
                        'cluster_end': cluster_end.isoformat(),
                        'min_stop_duration_sec': MIN_STOP_DURATION_SEC,
                        'zone_context': [{'name': z[0], 'type': z[1]} for z in zones],
                        'reasons_suspicious': reasons_suspicious,
                        'reasons_benign': reasons_benign,
                    },
                    'explanation': (
                        f"Vessel {mmsi} exhibited repeated stop-start behavior "
                        f"({len(cluster)} episodes in {(cluster_end - cluster_start).total_seconds() / 3600:.1f}h window, each ≥{MIN_STOP_DURATION_SEC}s). "
                        + (f"Suspicious: {'; '.join(reasons_suspicious)}. " if reasons_suspicious else "")
                        + (f"Possibly benign: {'; '.join(reasons_benign)}." if reasons_benign else "")
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
    cur_geo.close()
    cur.close()
    conn.close()
    return alerts


def _process_dwell(mmsi, low_speed_positions, cur_geo, alerts):
    """Process a completed low-speed dwell run."""
    dwell_minutes = (low_speed_positions[-1][1] - low_speed_positions[0][1]).total_seconds() / 60.0

    if dwell_minutes < MIN_DWELL_MINUTES:
        return

    center_lat = sum(p[3] for p in low_speed_positions) / len(low_speed_positions)
    center_lon = sum(p[2] for p in low_speed_positions) / len(low_speed_positions)
    max_spread = max(
        haversine_nm(center_lat, center_lon, p[3], p[2])
        for p in low_speed_positions
    )

    if max_spread >= MAX_SPREAD_NM:
        return

    # Geofence context
    zones = check_geofence_context(cur_geo, center_lon, center_lat)
    zone_types = {z[1] for z in zones}

    severity = calculate_dwell_severity(dwell_minutes, max_spread, zone_types)

    reasons_suspicious = []
    reasons_benign = []

    if 'restricted' in zone_types:
        reasons_suspicious.append("near restricted zone")
    if 'approach' in zone_types:
        reasons_suspicious.append("in approach corridor — unexpected dwell")
    if dwell_minutes > 360:
        reasons_suspicious.append(f"very long dwell ({dwell_minutes:.0f} min)")

    if 'anchorage' in zone_types:
        reasons_benign.append("in designated anchorage area")
    if 'harbor' in zone_types:
        reasons_benign.append("in harbor/terminal area — likely berthed")
    if max_spread < 0.05:
        reasons_benign.append(f"very tight cluster ({max_spread:.3f} nm) — likely moored")

    alerts.append({
        'mmsi': mmsi,
        'alert_type': 'loitering',
        'severity': severity,
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
            'zone_context': [{'name': z[0], 'type': z[1]} for z in zones],
            'reasons_suspicious': reasons_suspicious,
            'reasons_benign': reasons_benign,
        },
        'explanation': (
            f"Vessel {mmsi} loitered for {dwell_minutes:.0f} minutes "
            f"within {max_spread:.2f} nm radius near "
            f"({center_lat:.4f}, {center_lon:.4f}). "
            + (f"Suspicious: {'; '.join(reasons_suspicious)}. " if reasons_suspicious else "")
            + (f"Possibly benign: {'; '.join(reasons_benign)}." if reasons_benign else "")
        )
    })


if __name__ == '__main__':
    detect_loitering()
