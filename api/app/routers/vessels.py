"""FastAPI router for vessel listing and 360-degree vessel detail endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.db import get_db_cursor, normalize_row

router = APIRouter(prefix="/vessels", tags=["vessels"])


@router.get("/")
async def list_vessels(
    search: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    filters: List[str] = []
    params: List[Any] = []

    if search:
        filters.append("(CAST(v.mmsi AS TEXT) ILIKE %s OR v.vessel_name ILIKE %s)")
        search_term = f"%{search.strip()}%"
        params.extend([search_term, search_term])

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.extend([limit, offset])

    query = f"""
        SELECT
            v.mmsi,
            v.vessel_name,
            v.vessel_type,
            v.length,
            v.width,
            v.created_at,
            COALESCE(case_counts.total_cases, 0) AS total_cases,
            COALESCE(alert_counts.total_alerts, 0) AS total_alerts,
            last_position.last_seen
        FROM vessel v
        LEFT JOIN (
            SELECT mmsi, COUNT(*) AS total_cases
            FROM investigation_case
            GROUP BY mmsi
        ) case_counts ON case_counts.mmsi = v.mmsi
        LEFT JOIN (
            SELECT mmsi, COUNT(*) AS total_alerts
            FROM alert
            GROUP BY mmsi
        ) alert_counts ON alert_counts.mmsi = v.mmsi
        LEFT JOIN (
            SELECT mmsi, MAX(observed_at) AS last_seen
            FROM ais_position
            GROUP BY mmsi
        ) last_position ON last_position.mmsi = v.mmsi
        {where_clause}
        ORDER BY last_position.last_seen DESC NULLS LAST, v.created_at DESC, v.mmsi ASC
        LIMIT %s OFFSET %s
    """

    with get_db_cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()

    return [normalize_row(dict(row)) for row in rows]


@router.get("/{mmsi}")
async def get_vessel_detail(mmsi: str):
    vessel_query = """
        SELECT
            mmsi,
            vessel_name,
            vessel_type,
            length,
            width,
            created_at
        FROM vessel
        WHERE mmsi = %s
    """
    cases_query = """
        SELECT
            id,
            title,
            status,
            anomaly_score,
            rank_score,
            created_at
        FROM investigation_case
        WHERE mmsi = %s
        ORDER BY created_at DESC, id DESC
    """
    alerts_query = """
        SELECT
            id,
            alert_type,
            severity,
            title,
            detected_at
        FROM alert
        WHERE mmsi = %s
        ORDER BY detected_at DESC NULLS LAST, id DESC
    """
    tracks_query = """
        SELECT
            id,
            start_time,
            end_time,
            num_points
        FROM track_segment
        WHERE mmsi = %s
        ORDER BY start_time DESC NULLS LAST, id DESC
    """
    external_cues_query = """
        SELECT
            ec.id,
            ec.cue_type,
            ec.source,
            ec.description,
            ec.created_at
        FROM external_cue ec
        INNER JOIN investigation_case ic ON ic.id = ec.linked_case_id
        WHERE ic.mmsi = %s
        ORDER BY ec.created_at DESC, ec.id DESC
    """
    stats_query = """
        SELECT
            (SELECT COUNT(*) FROM investigation_case WHERE mmsi = %s) AS total_cases,
            (SELECT COUNT(*) FROM alert WHERE mmsi = %s) AS total_alerts,
            (SELECT COUNT(*) FROM ais_position WHERE mmsi = %s) AS total_positions,
            (SELECT MIN(observed_at) FROM ais_position WHERE mmsi = %s) AS first_seen,
            (SELECT MAX(observed_at) FROM ais_position WHERE mmsi = %s) AS last_seen
    """
    alert_types_query = """
        SELECT alert_type, COUNT(*) AS count
        FROM alert
        WHERE mmsi = %s
        GROUP BY alert_type
        ORDER BY alert_type ASC
    """

    with get_db_cursor() as cursor:
        cursor.execute(vessel_query, [mmsi])
        vessel_row = cursor.fetchone()
        if not vessel_row:
            raise HTTPException(status_code=404, detail="Vessel not found")

        cursor.execute(cases_query, [mmsi])
        case_rows = cursor.fetchall()

        cursor.execute(alerts_query, [mmsi])
        alert_rows = cursor.fetchall()

        cursor.execute(tracks_query, [mmsi])
        track_rows = cursor.fetchall()

        cursor.execute(external_cues_query, [mmsi])
        external_cue_rows = cursor.fetchall()

        cursor.execute(stats_query, [mmsi, mmsi, mmsi, mmsi, mmsi])
        stats_row = cursor.fetchone()

        cursor.execute(alert_types_query, [mmsi])
        alert_type_rows = cursor.fetchall()

    stats = normalize_row(dict(stats_row))
    stats["alert_types"] = {
        row["alert_type"]: row["count"]
        for row in [normalize_row(dict(alert_type_row)) for alert_type_row in alert_type_rows]
        if row["alert_type"] is not None
    }

    return {
        "vessel": normalize_row(dict(vessel_row)),
        "cases": [normalize_row(dict(row)) for row in case_rows],
        "alerts": [normalize_row(dict(row)) for row in alert_rows],
        "tracks": [normalize_row(dict(row)) for row in track_rows],
        "external_cues": [normalize_row(dict(row)) for row in external_cue_rows],
        "stats": stats,
    }
