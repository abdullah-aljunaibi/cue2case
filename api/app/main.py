"""FastAPI app exposing read-only Cue2Case API endpoints backed by PostgreSQL."""

import json
import os
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import psycopg2
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.extras import RealDictCursor

from api.app.routers.cases import router as cases_router

app = FastAPI(title="Cue2Case API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for demo
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cases_router)

AVAILABLE_ROUTES = [
    "/",
    "/health",
    "/cases",
    "/cases/{case_id}",
    "/cases/{case_id}/notes",
    "/cases/{case_id}/audit",
    "/alerts",
    "/vessels/{mmsi}",
    "/tracks/{mmsi}",
    "/map/cases",
    "/external-cues",
    "/external-cues/import-sample",
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


def validate_external_cue_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    allowed_cue_types = {"rf_detection", "imagery", "tip", "other"}
    source = payload.get("source")
    cue_type = payload.get("cue_type")
    observed_at = payload.get("observed_at")
    lon = payload.get("lon")
    lat = payload.get("lat")
    data = payload.get("data", {})
    case_id = payload.get("case_id")

    if not source or not isinstance(source, str):
        raise HTTPException(status_code=400, detail="source is required")
    if not cue_type or not isinstance(cue_type, str):
        raise HTTPException(status_code=400, detail="cue_type is required")
    if cue_type not in allowed_cue_types:
        raise HTTPException(status_code=400, detail="cue_type must be one of rf_detection, imagery, tip, other")
    if (lon is None) != (lat is None):
        raise HTTPException(status_code=400, detail="lon and lat must be provided together")
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="data must be an object")

    if lon is not None and lat is not None:
        try:
            lon = float(lon)
            lat = float(lat)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="lon and lat must be numbers") from exc

    return {
        "source": source,
        "cue_type": cue_type,
        "observed_at": observed_at,
        "lon": lon,
        "lat": lat,
        "data": data,
        "case_id": case_id,
    }


def serialize_external_cue_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return normalize_row(dict(row))


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
            ic.confidence_score,
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


@app.get("/external-cues")
async def list_external_cues(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    cue_type: Optional[str] = None,
    source: Optional[str] = None,
):
    filters: List[str] = []
    params: List[Any] = []

    if cue_type:
        filters.append("cue_type = %s")
        params.append(cue_type)
    if source:
        filters.append("source = %s")
        params.append(source)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.extend([limit, offset])

    query = f"""
        SELECT
            id,
            source,
            cue_type,
            observed_at,
            ST_X(geom::geometry) AS lon,
            ST_Y(geom::geometry) AS lat,
            data,
            case_id,
            created_at
        FROM external_cue
        {where_clause}
        ORDER BY observed_at DESC NULLS LAST, created_at DESC
        LIMIT %s OFFSET %s
    """

    with get_db_cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()

    return [serialize_external_cue_row(row) for row in rows]


@app.post("/external-cues")
async def create_external_cue(payload: Dict[str, Any] = Body(...)):
    cue = validate_external_cue_payload(payload)
    geom_sql = "NULL"
    params: List[Any] = [
        cue["source"],
        cue["cue_type"],
        cue["observed_at"],
        json.dumps(cue["data"]),
        cue["case_id"],
    ]

    if cue["lon"] is not None and cue["lat"] is not None:
        geom_sql = "ST_SetSRID(ST_MakePoint(%s, %s), 4326)"
        params.extend([cue["lon"], cue["lat"]])

    query = f"""
        INSERT INTO external_cue (
            source,
            cue_type,
            observed_at,
            geom,
            data,
            case_id
        )
        VALUES (%s, %s, %s, {geom_sql}, %s::jsonb, %s)
        RETURNING
            id,
            source,
            cue_type,
            observed_at,
            ST_X(geom::geometry) AS lon,
            ST_Y(geom::geometry) AS lat,
            data,
            case_id,
            created_at
    """

    with get_db_cursor() as cursor:
        cursor.execute(query, params)
        row = cursor.fetchone()
        cursor.connection.commit()

    return serialize_external_cue_row(row)


@app.post("/external-cues/import-sample")
async def import_sample_external_cues():
    sample_cues = [
        {
            "source": "demo-imagery-feed",
            "cue_type": "imagery",
            "observed_at": "2026-03-31T18:45:00Z",
            "lon": -118.1937,
            "lat": 33.7701,
            "data": {"confidence": 0.81, "note": "Small contact near port approach"},
        },
        {
            "source": "demo-tipline",
            "cue_type": "tip",
            "observed_at": "2026-03-31T19:05:00Z",
            "lon": -118.1753,
            "lat": 33.7552,
            "data": {"reporter": "anonymous", "note": "Unusual nighttime transfer activity"},
        },
        {
            "source": "demo-rf-sensor",
            "cue_type": "rf_detection",
            "observed_at": "2026-03-31T19:20:00Z",
            "lon": -118.2141,
            "lat": 33.7824,
            "data": {"band": "VHF", "signal_strength": -61.4},
        },
    ]

    with get_db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM external_cue")
        existing_count = cursor.fetchone()["count"]
        if existing_count:
            return {"message": "External cues already exist", "count": existing_count}

        insert_query = """
            INSERT INTO external_cue (
                source,
                cue_type,
                observed_at,
                geom,
                data,
                case_id
            )
            VALUES (
                %s,
                %s,
                %s,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                %s::jsonb,
                %s
            )
            RETURNING
                id,
                source,
                cue_type,
                observed_at,
                ST_X(geom::geometry) AS lon,
                ST_Y(geom::geometry) AS lat,
                data,
                case_id,
                created_at
        """

        inserted_rows = []
        for cue in sample_cues:
            cursor.execute(
                insert_query,
                [
                    cue["source"],
                    cue["cue_type"],
                    cue["observed_at"],
                    cue["lon"],
                    cue["lat"],
                    json.dumps(cue["data"]),
                    None,
                ],
            )
            inserted_rows.append(cursor.fetchone())

        cursor.connection.commit()

    return {
        "message": "Inserted sample external cues",
        "count": len(inserted_rows),
        "items": [serialize_external_cue_row(row) for row in inserted_rows],
    }
