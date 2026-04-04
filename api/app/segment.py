"""Track segmentation script.

Usage: python -m app.segment

Reads AIS positions from the database, groups them by vessel,
splits them into segments by time/distance gaps, and inserts
track segments into the track_segment table.
"""
import math
import os

from datetime import timedelta
from itertools import groupby

import psycopg2
from psycopg2.extras import execute_values


DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://cue2case:cue2case_dev@localhost:5433/cue2case"
)

# Segmentation thresholds
MAX_TIME_GAP = timedelta(minutes=30)
MAX_DISTANCE_NM = 10.0  # nautical miles
BATCH_SIZE = 500
MIN_SEGMENT_POINTS = 3


def haversine_nm(lat1, lon1, lat2, lon2):
    """Calculate distance in nautical miles between two lat/lon points."""
    radius_nm = 3440.065  # Earth radius in nautical miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return radius_nm * c


def build_segments(positions):
    """Split a vessel's ordered positions into track segments.

    Each position is (observed_at, lon, lat, sog, cog, heading).
    Returns a list of segments, each containing ordered positions.
    """
    if len(positions) < MIN_SEGMENT_POINTS:
        return []

    segments = []
    current = [positions[0]]

    for idx in range(1, len(positions)):
        prev = current[-1]
        curr = positions[idx]

        time_gap = curr[0] - prev[0]
        distance_gap = haversine_nm(prev[2], prev[1], curr[2], curr[1])

        if time_gap > MAX_TIME_GAP or distance_gap > MAX_DISTANCE_NM:
            if len(current) >= MIN_SEGMENT_POINTS:
                segments.append(current)
            current = [curr]
            continue

        current.append(curr)

    if len(current) >= MIN_SEGMENT_POINTS:
        segments.append(current)

    return segments


def has_valid_linestring_geometry(segment):
    """Return True when a segment can form a valid non-degenerate LINESTRING."""
    distinct_coords = {(point[1], point[2]) for point in segment}
    return len(distinct_coords) >= 2


def segment_to_row(mmsi, segment):
    """Convert a position segment into a track_segment insert tuple."""
    if not has_valid_linestring_geometry(segment):
        return None

    coords = ", ".join(f"{point[1]} {point[2]}" for point in segment)
    wkt = f"LINESTRING({coords})"

    sog_values = [point[3] for point in segment if point[3] is not None]
    avg_sog = round(sum(sog_values) / len(sog_values), 2) if sog_values else 0
    max_sog = round(max(sog_values), 2) if sog_values else 0

    return (
        mmsi,
        segment[0][0],
        segment[-1][0],
        wkt,
        len(segment),
        avg_sog,
        max_sog,
    )


def run_segmentation():
    """Read AIS positions, build segments, and bulk insert them."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    try:
        print("Clearing existing track segments...")
        cur.execute("DELETE FROM track_segment")
        conn.commit()

        print("Fetching AIS positions...")
        cur.execute(
            """
            SELECT mmsi, observed_at, ST_X(geom) AS lon, ST_Y(geom) AS lat, sog, cog, heading
            FROM ais_position
            ORDER BY mmsi, observed_at
            """
        )
        rows = cur.fetchall()
        print(f"Fetched {len(rows)} positions.")

        segments_to_insert = []
        vessel_count = 0
        skipped_invalid_segments = 0

        for mmsi, group in groupby(rows, key=lambda row: row[0]):
            positions = [
                (row[1], row[2], row[3], row[4], row[5], row[6])
                for row in group
            ]
            segments = build_segments(positions)
            for segment in segments:
                row = segment_to_row(mmsi, segment)
                if row is None:
                    skipped_invalid_segments += 1
                    continue
                segments_to_insert.append(row)

            vessel_count += 1
            if vessel_count % 50 == 0:
                print(f"  Processed {vessel_count} vessels...")

        print(f"Inserting {len(segments_to_insert)} track segments...")
        for idx in range(0, len(segments_to_insert), BATCH_SIZE):
            batch = segments_to_insert[idx:idx + BATCH_SIZE]
            execute_values(
                cur,
                """
                INSERT INTO track_segment (
                    mmsi,
                    start_time,
                    end_time,
                    geom,
                    point_count,
                    avg_sog,
                    max_sog
                )
                VALUES %s
                """,
                batch,
                template="(%s, %s, %s, ST_GeomFromText(%s, 4326), %s, %s, %s)",
            )
            conn.commit()
            print(f"  Inserted batch {idx // BATCH_SIZE + 1}")

        print(
            f"Done. {vessel_count} vessels → {len(segments_to_insert)} track segments "
            f"({skipped_invalid_segments} invalid segments skipped)."
        )
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    run_segmentation()
