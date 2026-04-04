"""Detector 2: AIS Silence (Context-Aware).

Flags vessels that stop broadcasting AIS for suspicious durations.
Context-aware: considers WHERE silence occurred, distance traveled during
gap, and whether reappearance location is consistent with expected movement.
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

MIN_SILENCE_MINUTES = 15
REPEATED_SILENCE_WINDOW = timedelta(hours=24)
REPEATED_SILENCE_THRESHOLD = 3


def haversine_nm(lat1, lon1, lat2, lon2):
    """Distance in nautical miles."""
    R_NM = 3440.065
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R_NM * 2 * math.asin(math.sqrt(a))


def load_geofences(cur):
    """Load geofence zones for context checking."""
    cur.execute("""
        SELECT id, name, zone_type, geom
        FROM geofence
    """)
    return cur.fetchall()


def check_geofence_context(cur, lon, lat):
    """Check which geofence zones a point falls in."""
    cur.execute("""
        SELECT name, zone_type
        FROM geofence
        WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
    """, (lon, lat))
    return cur.fetchall()


def calculate_severity(gap_minutes, distance_nm, geofence_zones_before, geofence_zones_after):
    """Calculate severity based on gap duration, movement, and geofence context.
    
    Factors:
    - Base: gap duration
    - Boost: large distance traveled during silence (possible evasion)
    - Boost: silence near restricted/approach zones
    - Reduce: silence in anchorage/harbor (more normal)
    """
    # Base severity from duration
    if gap_minutes >= 120:
        base = 0.7
    elif gap_minutes >= 60:
        base = 0.5
    elif gap_minutes >= 30:
        base = 0.35
    else:
        base = 0.2

    # Distance modifier: large movement during silence is suspicious
    if distance_nm > 5:
        base += 0.2
    elif distance_nm > 2:
        base += 0.1

    # Geofence context modifiers
    zone_types_before = {z[1] for z in geofence_zones_before}
    zone_types_after = {z[1] for z in geofence_zones_after}
    all_zones = zone_types_before | zone_types_after

    if 'restricted' in all_zones:
        base += 0.15  # silence near restricted zone
    if 'approach' in all_zones:
        base += 0.05  # silence in approach corridor
    if 'anchorage' in zone_types_before and 'anchorage' in zone_types_after:
        base -= 0.15  # both in anchorage = likely benign
    if 'harbor' in zone_types_before and 'harbor' in zone_types_after:
        base -= 0.1   # both in harbor = likely benign

    return max(0.05, min(round(base, 3), 1.0))


def count_clustered_episodes(episodes, current_episode, window=REPEATED_SILENCE_WINDOW):
    """Count silence episodes whose start times fall within the trailing window."""
    current_start = current_episode['start']
    window_start = current_start - window
    return sum(
        1
        for episode in episodes
        if window_start <= episode['start'] <= current_start
    )


def detect_ais_silence():
    """Run context-aware AIS silence detection."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur_geo = conn.cursor()  # separate cursor for geofence queries

    print("Fetching AIS positions for silence detection...")
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
        if len(positions) < 2:
            continue

        episodes = []

        for i in range(1, len(positions)):
            prev = positions[i-1]
            curr = positions[i]

            gap = curr[1] - prev[1]
            gap_minutes = gap.total_seconds() / 60.0

            if gap_minutes >= MIN_SILENCE_MINUTES:
                distance_nm = haversine_nm(prev[3], prev[2], curr[3], curr[2])

                # Check geofence context
                zones_before = check_geofence_context(cur_geo, prev[2], prev[3])
                zones_after = check_geofence_context(cur_geo, curr[2], curr[3])

                severity = calculate_severity(gap_minutes, distance_nm, zones_before, zones_after)

                # Determine if benign
                zone_types_before = {z[1] for z in zones_before}
                zone_types_after = {z[1] for z in zones_after}
                
                reasons_suspicious = []
                reasons_benign = []

                if distance_nm > 5:
                    reasons_suspicious.append(f"moved {distance_nm:.1f} nm during silence")
                if 'restricted' in (zone_types_before | zone_types_after):
                    reasons_suspicious.append("near restricted zone")
                if gap_minutes > 60:
                    reasons_suspicious.append(f"extended gap ({gap_minutes:.0f} min)")
                
                if 'anchorage' in zone_types_before and 'anchorage' in zone_types_after:
                    reasons_benign.append("remained in anchorage area")
                if 'harbor' in zone_types_before and 'harbor' in zone_types_after:
                    reasons_benign.append("remained in harbor")
                if distance_nm < 0.5:
                    reasons_benign.append(f"minimal movement ({distance_nm:.2f} nm)")

                # Ensure dual reasoning is always present for analyst trust
                if not reasons_suspicious:
                    reasons_suspicious.append(f"AIS gap of {gap_minutes:.0f} minutes warrants review")
                if not reasons_benign:
                    if distance_nm < 1.0:
                        reasons_benign.append("minimal displacement suggests equipment issue or port-side gap")
                    else:
                        reasons_benign.append("gap may reflect transit through coverage dead zone")

                episode = {
                    'start': prev[1],
                    'end': curr[1],
                    'gap_minutes': gap_minutes,
                    'distance_nm': distance_nm,
                }
                episodes.append(episode)

                clustered_episode_count = count_clustered_episodes(episodes, episode)
                if clustered_episode_count >= REPEATED_SILENCE_THRESHOLD:
                    severity = min(severity + 0.1, 1.0)

                alert_details = {
                    'gap_minutes': round(gap_minutes, 1),
                    'distance_during_gap_nm': round(distance_nm, 2),
                    'last_seen': prev[1].isoformat(),
                    'last_lat': prev[3],
                    'last_lon': prev[2],
                    'last_sog': prev[4],
                    'reappeared_at': curr[1].isoformat(),
                    'reappeared_lat': curr[3],
                    'reappeared_lon': curr[2],
                    'reappeared_sog': curr[4],
                    'zones_before': [{'name': z[0], 'type': z[1]} for z in zones_before],
                    'zones_after': [{'name': z[0], 'type': z[1]} for z in zones_after],
                    'reasons_suspicious': reasons_suspicious,
                    'reasons_benign': reasons_benign,
                }
                if clustered_episode_count >= REPEATED_SILENCE_THRESHOLD:
                    alert_details['repeated_silences_24h'] = clustered_episode_count

                alerts.append({
                    'mmsi': mmsi,
                    'alert_type': 'ais_silence',
                    'severity': severity,
                    'observed_at': prev[1],
                    'lon': prev[2],
                    'lat': prev[3],
                    'details': alert_details,
                    'explanation': (
                        f"Vessel {mmsi} went silent for {gap_minutes:.0f} minutes "
                        f"and moved {distance_nm:.1f} nm during gap. "
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

    print(f"AIS silence detector: {len(alerts)} alerts generated.")
    cur_geo.close()
    cur.close()
    conn.close()
    return alerts


if __name__ == '__main__':
    detect_ais_silence()
