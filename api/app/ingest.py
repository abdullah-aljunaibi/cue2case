"""AIS CSV ingestion script.

Usage: python -m app.ingest /path/to/longbeach_2024_01_15.csv

Reads a filtered NOAA AIS CSV, upserts vessels, and bulk-inserts AIS positions.
Uses synchronous psycopg2 for simplicity in batch scripts.
"""
import csv
import os
import sys
from datetime import datetime

import psycopg2
from psycopg2.extras import execute_values


DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://cue2case:cue2case_dev@localhost:5433/cue2case"
)


def parse_float(val):
    """Parse float, return None for empty/invalid."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def parse_int(val):
    """Parse int, return None for empty/invalid."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def ingest_csv(filepath: str):
    """Ingest a filtered AIS CSV into the database."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    vessels = {}  # mmsi -> vessel data
    positions = []

    print(f"Reading {filepath}...")
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            mmsi = row['MMSI'].strip()
            # Skip invalid MMSI (must be exactly 9 digits)
            if not mmsi or len(mmsi) != 9 or not mmsi.isdigit():
                continue

            # Collect unique vessels
            if mmsi not in vessels:
                vessels[mmsi] = {
                    'mmsi': mmsi,
                    'vessel_name': row.get('VesselName', '').strip() or None,
                    'vessel_type': parse_int(row.get('VesselType')),
                    'length': parse_float(row.get('Length')),
                    'width': parse_float(row.get('Width')),
                }

            # Parse position
            lat = parse_float(row['LAT'])
            lon = parse_float(row['LON'])
            if (
                lat is None or lon is None
                or not (-90 <= lat <= 90)
                or not (-180 <= lon <= 180)
            ):
                continue

            sog = parse_float(row['SOG'])
            if sog is not None and (sog < 0 or sog >= 102.3):
                sog = None

            cog_val = parse_float(row['COG'])
            if cog_val is not None and (cog_val < 0 or cog_val >= 360):
                cog_val = None

            heading_val = parse_float(row['Heading'])
            if heading_val is not None and heading_val == 511.0:
                heading_val = None
            if heading_val is not None and (heading_val < 0 or heading_val >= 360):
                heading_val = None
            nav_status = parse_int(row.get('Status'))

            try:
                observed_at = datetime.fromisoformat(row['BaseDateTime'])
            except (ValueError, KeyError):
                continue

            positions.append((
                mmsi,
                observed_at,
                lon, lat,  # ST_MakePoint takes (lon, lat)
                sog,
                cog_val,
                heading_val,
                nav_status,
            ))

    # Upsert vessels
    print(f"Upserting {len(vessels)} vessels...")
    vessel_data = [(v['mmsi'], v['vessel_name'], v['vessel_type'], v['length'], v['width']) for v in vessels.values()]
    execute_values(
        cur,
        """
        INSERT INTO vessel (mmsi, vessel_name, vessel_type, length, width)
        VALUES %s
        ON CONFLICT (mmsi) DO UPDATE SET
            vessel_name = COALESCE(EXCLUDED.vessel_name, vessel.vessel_name),
            vessel_type = COALESCE(EXCLUDED.vessel_type, vessel.vessel_type),
            length = COALESCE(EXCLUDED.length, vessel.length),
            width = COALESCE(EXCLUDED.width, vessel.width)
        """,
        vessel_data,
    )
    conn.commit()
    print(f"Vessels upserted.")

    # Bulk insert positions
    print(f"Inserting {len(positions)} AIS positions...")
    BATCH_SIZE = 10000
    for i in range(0, len(positions), BATCH_SIZE):
        batch = positions[i:i + BATCH_SIZE]
        execute_values(
            cur,
            """
            INSERT INTO ais_position (mmsi, observed_at, geom, sog, cog, heading, nav_status)
            VALUES %s
            """,
            batch,
            template="(%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, %s)",
        )
        conn.commit()
        print(f"  Inserted batch {i // BATCH_SIZE + 1} ({len(batch)} rows)")

    print(f"Done. {len(vessels)} vessels, {len(positions)} positions ingested.")
    cur.close()
    conn.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python -m app.ingest <csv_path>")
        sys.exit(1)
    ingest_csv(sys.argv[1])
