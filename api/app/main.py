"""FastAPI app exposing read-only Cue2Case API endpoints backed by PostgreSQL."""

import json
import os
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Dict, List, Optional

import psycopg2
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.extras import RealDictCursor

app = FastAPI(title="Cue2Case API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AVAILABLE_ROUTES = [
    "/",
    "/health",
    "/cases",
    "/cases/{case_id}",
    "/alerts",
    "/vessels/{mmsi}",
    "/tracks/{mmsi}",
    "/map/cases",
]


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_ASYNC")
    if not database_url:
        raise HTTPException(status_code=500, detail="Database URL is not configured")
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return database_url


@contextmanager
def get_db_cursor():
    connection = psycopg2.connect(get_database_url(), cursor_factory=RealDictCursor)
    try:
        with connection.cursor() as cursor:
            yield cursor
    finally:
        connection.close()


def normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_value(item) for key, item in value.items()}
    return value


def normalize_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return {key: normalize_value(value) for key, value in row.items()}


@app.get("/")
async def root():
    return {
        "service": "cue2case-api",
        "version": app.version,
        "status": "ok",
        "routes": AVAILABLE_ROUTES,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "cue2case-api"}


@app.get("/cases")
async def list_cases(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = None,
    min_score: Optional[float] = None,
):
    filters: List[str] = []
    params: List[Any] = []

    if status:
        filters.append("ic.status = %s")
        params.append(status)
    if min_score is not None:
        filters.append("ic.anomaly_score >= %s")
        params.append(min_score)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.extend([limit, offset])

    query = f"""
        SELECT
            ic.id,
            ic.title,
            ic.mmsi,
            ic.anomaly_score,
            ic.status,
            ic.priority,
            ic.summary,
            ic.recommended_action,
            ic.created_at,
            ic.updated_at,
            v.vessel_name,
            COUNT(ce.id) AS evidence_count
        FROM investigation_case ic
        LEFT JOIN vessel v ON v.mmsi = ic.mmsi
        LEFT JOIN case_evidence ce ON ce.case_id = ic.id
        {where_clause}
        GROUP BY ic.id, v.vessel_name
        ORDER BY ic.anomaly_score DESC, ic.created_at DESC
        LIMIT %s OFFSET %s
    """

    with get_db_cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()

    return [normalize_row(dict(row)) for row in rows]


@app.get("/cases/{case_id}")
async def get_case(case_id: int):
    case_query = """
        SELECT
            ic.id,
            ic.title,
            ic.mmsi,
            ic.anomaly_score,
            ic.status,
            ic.priority,
            ic.summary,
            ic.recommended_action,
            ic.created_at,
            ic.updated_at,
            v.vessel_name,
            v.vessel_type,
            v.length,
            v.width
        FROM investigation_case ic
        LEFT JOIN vessel v ON v.mmsi = ic.mmsi
        WHERE ic.id = %s
    """
    evidence_query = """
        SELECT
            id,
            case_id,
            evidence_type,
            evidence_ref,
            data,
            provenance,
            created_at
        FROM case_evidence
        WHERE case_id = %s
        ORDER BY created_at ASC, id ASC
    """

    with get_db_cursor() as cursor:
        cursor.execute(case_query, [case_id])
        case_row = cursor.fetchone()
        if not case_row:
            raise HTTPException(status_code=404, detail="Case not found")

        cursor.execute(evidence_query, [case_id])
        evidence_rows = cursor.fetchall()

    case_data = normalize_row(dict(case_row))
    case_data["evidence"] = [normalize_row(dict(row)) for row in evidence_rows]
    return case_data


@app.get("/alerts")
async def list_alerts(
    mmsi: Optional[int] = None,
    alert_type: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    filters: List[str] = []
    params: List[Any] = []

    if mmsi is not None:
        filters.append("a.mmsi = %s")
        params.append(mmsi)
    if alert_type:
        filters.append("a.alert_type = %s")
        params.append(alert_type)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.extend([limit, offset])

    query = f"""
        SELECT
            a.id,
            a.mmsi,
            a.alert_type,
            a.severity,
            a.observed_at,
            ST_X(a.geom::geometry) AS lon,
            ST_Y(a.geom::geometry) AS lat,
            a.details,
            a.explanation,
            a.created_at
        FROM alert a
        {where_clause}
        ORDER BY a.observed_at DESC, a.id DESC
        LIMIT %s OFFSET %s
    """

    with get_db_cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()

    return [normalize_row(dict(row)) for row in rows]


@app.get("/vessels/{mmsi}")
async def get_vessel(mmsi: int):
    vessel_query = """
        SELECT
            v.mmsi,
            v.vessel_name,
            v.vessel_type,
            v.length,
            v.width,
            COALESCE(alert_counts.alert_count, 0) AS alert_count,
            COALESCE(case_counts.case_count, 0) AS case_count,
            latest_track.latest_position
        FROM vessel v
        LEFT JOIN (
            SELECT mmsi, COUNT(*) AS alert_count
            FROM alert
            GROUP BY mmsi
        ) alert_counts ON alert_counts.mmsi = v.mmsi
        LEFT JOIN (
            SELECT mmsi, COUNT(*) AS case_count
            FROM investigation_case
            GROUP BY mmsi
        ) case_counts ON case_counts.mmsi = v.mmsi
        LEFT JOIN (
            SELECT mmsi, MAX(end_time) AS latest_position
            FROM track_segment
            GROUP BY mmsi
        ) latest_track ON latest_track.mmsi = v.mmsi
        WHERE v.mmsi = %s
    """

    with get_db_cursor() as cursor:
        cursor.execute(vessel_query, [mmsi])
        vessel_row = cursor.fetchone()

    if not vessel_row:
        raise HTTPException(status_code=404, detail="Vessel not found")

    return normalize_row(dict(vessel_row))


@app.get("/tracks/{mmsi}")
async def get_tracks(mmsi: int):
    query = """
        SELECT
            id,
            mmsi,
            start_time,
            end_time,
            ST_AsGeoJSON(geom) AS geometry,
            point_count,
            avg_sog,
            max_sog
        FROM track_segment
        WHERE mmsi = %s
        ORDER BY start_time DESC, id DESC
        LIMIT 20
    """

    with get_db_cursor() as cursor:
        cursor.execute(query, [mmsi])
        rows = cursor.fetchall()

    tracks = []
    for row in rows:
        track = normalize_row(dict(row))
        track["geometry"] = json.loads(track["geometry"]) if track.get("geometry") else None
        tracks.append(track)

    return tracks


@app.get("/map/cases")
async def list_case_map_points(
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    query = """
        WITH latest_alert AS (
            SELECT DISTINCT ON (a.mmsi)
                a.mmsi,
                ST_X(a.geom::geometry) AS lon,
                ST_Y(a.geom::geometry) AS lat,
                a.observed_at
            FROM alert a
            ORDER BY a.mmsi, a.observed_at DESC, a.id DESC
        )
        SELECT
            ic.id AS case_id,
            ic.title,
            ic.anomaly_score,
            ic.priority,
            ic.mmsi,
            v.vessel_name,
            la.lon,
            la.lat
        FROM investigation_case ic
        LEFT JOIN vessel v ON v.mmsi = ic.mmsi
        LEFT JOIN latest_alert la ON la.mmsi = ic.mmsi
        ORDER BY ic.anomaly_score DESC, ic.created_at DESC
        LIMIT %s OFFSET %s
    """

    with get_db_cursor() as cursor:
        cursor.execute(query, [limit, offset])
        rows = cursor.fetchall()

    return [normalize_row(dict(row)) for row in rows]
