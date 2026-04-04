"""Incrementally refresh live Duqm AIS snapshots and rebuild downstream artifacts."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import psycopg2
from psycopg2.extras import execute_values

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.case_engine import build_cases
from app.detectors.abnormal_approach import detect_abnormal_approach
from app.detectors.ais_silence import detect_ais_silence
from app.detectors.identity_kinematic import detect_identity_kinematic
from app.detectors.loitering import detect_loitering
from app.detectors.spoofing import detect_spoofing
from app.segment import run_segmentation


API_KEY = "b51bab23-b9e6-4da4-9d29-9de3ca5bddb1"
BASE_URL = "https://api.datalastic.com/api/v0"
DUQM_LAT = 19.67459
DUQM_LON = 57.70646
RADIUS = 50
DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://cue2case:cue2case_dev@localhost:5433/cue2case",
)


def api_get(endpoint, params):
    """Call the Datalastic API and return the decoded JSON payload."""
    query = dict(params)
    query["api-key"] = API_KEY
    url = f"{BASE_URL}/{endpoint}?{urlencode(query)}"
    with urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_float(value):
    """Parse a float, returning None when missing or invalid."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def parse_int(value):
    """Parse an int, returning None when missing or invalid."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_heading(value):
    """Normalize heading into the DB-compatible range."""
    heading = parse_float(value)
    if heading is None or heading == 511.0 or heading < 0 or heading >= 360:
        return None
    return heading


def normalize_cog(value):
    """Normalize course over ground into the DB-compatible range."""
    cog = parse_float(value)
    if cog is None or cog < 0 or cog >= 360:
        return None
    return cog


def normalize_sog(value):
    """Normalize speed over ground into the DB-compatible range."""
    sog = parse_float(value)
    if sog is None or sog < 0 or sog >= 102.3:
        return None
    return sog


def parse_observed_at(vessel):
    """Use API timestamp when available, otherwise fall back to current UTC."""
    candidates = [
        vessel.get("last_position_UTC"),
        vessel.get("last_position_utc"),
        vessel.get("last_position_at"),
        vessel.get("observed_at"),
        vessel.get("timestamp"),
    ]
    for raw in candidates:
        if not raw:
            continue
        text = str(raw).strip()
        if not text:
            continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    return datetime.utcnow()


def build_vessel_row(vessel):
    """Map a Datalastic vessel payload into the vessel table shape."""
    return (
        vessel["mmsi"],
        vessel.get("name") or vessel.get("vessel_name") or None,
        parse_int(vessel.get("type") or vessel.get("vessel_type")),
        parse_float(vessel.get("length")),
        parse_float(vessel.get("width") or vessel.get("beam")),
    )


def build_position_record(vessel):
    """Map a Datalastic vessel payload into an AIS position insert candidate."""
    lat = parse_float(vessel.get("lat"))
    lon = parse_float(vessel.get("lon"))
    mmsi = str(vessel.get("mmsi", "")).strip()

    if not mmsi or len(mmsi) != 9 or not mmsi.isdigit():
        return None
    if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return None

    return {
        "mmsi": mmsi,
        "observed_at": parse_observed_at(vessel),
        "lon": lon,
        "lat": lat,
        "sog": normalize_sog(vessel.get("speed") or vessel.get("sog")),
        "cog": normalize_cog(vessel.get("course") or vessel.get("cog")),
        "heading": normalize_heading(vessel.get("heading")),
        "nav_status": parse_int(
            vessel.get("navigational_status")
            or vessel.get("nav_status")
            or vessel.get("status")
        ),
    }


def dedupe_positions(conn, raw_positions):
    """Skip exact duplicate payload rows already present in the DB or repeated in one run."""
    if not raw_positions:
        return [], 0

    unique_positions = []
    seen_keys = set()
    for position in raw_positions:
        dedupe_key = (
            position["mmsi"],
            position["observed_at"],
            position["lat"],
            position["lon"],
        )
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        unique_positions.append(position)

    lookup_pairs = sorted({(pos["mmsi"], pos["observed_at"]) for pos in unique_positions})
    existing_keys = set()
    cur = conn.cursor()
    try:
        execute_values(
            cur,
            """
            SELECT
                ap.mmsi,
                ap.observed_at,
                ST_Y(ap.geom) AS lat,
                ST_X(ap.geom) AS lon
            FROM ais_position ap
            JOIN (VALUES %s) AS incoming (mmsi, observed_at)
              ON ap.mmsi = incoming.mmsi
             AND ap.observed_at = incoming.observed_at
            """,
            lookup_pairs,
            template="(%s, %s)",
        )
        for row in cur.fetchall():
            existing_keys.add((row[0], row[1], float(row[2]), float(row[3])))
    finally:
        cur.close()

    positions_to_insert = []
    skipped_duplicates = 0
    for position in unique_positions:
        dedupe_key = (
            position["mmsi"],
            position["observed_at"],
            position["lat"],
            position["lon"],
        )
        if dedupe_key in existing_keys:
            skipped_duplicates += 1
            continue
        positions_to_insert.append(position)

    skipped_duplicates += max(0, len(raw_positions) - len(unique_positions))
    return positions_to_insert, skipped_duplicates


def upsert_vessels(cur, vessel_rows):
    """Upsert vessel metadata."""
    if not vessel_rows:
        return 0
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
        vessel_rows,
    )
    return len(vessel_rows)


def insert_positions(cur, positions):
    """Insert current live AIS snapshot positions."""
    if not positions:
        return 0
    execute_values(
        cur,
        """
        INSERT INTO ais_position (mmsi, observed_at, geom, sog, cog, heading, nav_status)
        VALUES %s
        """,
        [
            (
                pos["mmsi"],
                pos["observed_at"],
                pos["lon"],
                pos["lat"],
                pos["sog"],
                pos["cog"],
                pos["heading"],
                pos["nav_status"],
            )
            for pos in positions
        ],
        template="(%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, %s)",
    )
    return len(positions)


def clear_alerts(cur):
    """Clear alerts before rebuilding detector outputs."""
    cur.execute("DELETE FROM alert")


def detector_count(result):
    """Normalize detector return values into alert counts."""
    if result is None:
        return None
    if isinstance(result, int):
        return result
    if isinstance(result, list):
        return len(result)
    if isinstance(result, tuple):
        return len(result)
    return None


def count_cases(conn):
    """Return the current investigation case count."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM investigation_case")
        return cur.fetchone()[0]
    finally:
        cur.close()


def main():
    print("Fetching live vessels near Duqm...")
    payload = api_get("vessel_inradius", {"lat": DUQM_LAT, "lon": DUQM_LON, "radius": RADIUS})
    live_vessels = payload.get("data", {}).get("vessels", [])

    vessels_by_mmsi = {}
    raw_positions = []
    for vessel in live_vessels:
        position = build_position_record(vessel)
        if position is None:
            continue
        vessels_by_mmsi[position["mmsi"]] = vessel
        raw_positions.append(position)

    conn = psycopg2.connect(DATABASE_URL)
    try:
        cur = conn.cursor()
        try:
            vessel_rows = [build_vessel_row(vessel) for vessel in vessels_by_mmsi.values()]
            positions_to_insert, skipped_duplicates = dedupe_positions(conn, raw_positions)

            vessels_upserted = upsert_vessels(cur, vessel_rows)
            positions_inserted = insert_positions(cur, positions_to_insert)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

        cur = conn.cursor()
        try:
            clear_alerts(cur)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

        print("Rebuilding derived artifacts...")
        run_segmentation()
        abnormal_count = detector_count(detect_abnormal_approach())
        silence_count = detector_count(detect_ais_silence())
        loitering_count = detector_count(detect_loitering())
        identity_kinematic_count = detector_count(detect_identity_kinematic())
        spoofing_count = detector_count(detect_spoofing())
        build_cases()
        cases_rebuilt = count_cases(conn)
    finally:
        conn.close()

    print("\nLive refresh summary:")
    print(f"  vessels seen: {len(live_vessels)}")
    print(f"  vessels upserted: {vessels_upserted}")
    print(f"  positions inserted: {positions_inserted}")
    print(f"  positions skipped as duplicates: {skipped_duplicates}")
    if abnormal_count is not None:
        print(f"  abnormal approach alerts: {abnormal_count}")
    if silence_count is not None:
        print(f"  AIS silence alerts: {silence_count}")
    if loitering_count is not None:
        print(f"  loitering alerts: {loitering_count}")
    if identity_kinematic_count is not None:
        print(f"  identity/kinematic alerts: {identity_kinematic_count}")
    if spoofing_count is not None:
        print(f"  spoofing alerts: {spoofing_count}")
    print(f"  cases rebuilt: {cases_rebuilt}")


if __name__ == "__main__":
    main()
