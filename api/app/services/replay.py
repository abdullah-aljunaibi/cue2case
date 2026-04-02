"""Incident replay service.

Assembles a time-ordered narrative from AIS positions, alerts,
cues, notes, and status changes for a given case.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://cue2case:cue2case_dev@localhost:5433/cue2case",
)


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _narrative_for_position(position: Dict[str, Any], vessel_name: str, mmsi: str, is_first: bool) -> str:
    label = vessel_name or "Unknown vessel"
    timestamp = position["observed_at"].astimezone(timezone.utc).strftime("%H:%M UTC")
    sog = position.get("sog")
    lon = position.get("lon")
    lat = position.get("lat")
    if is_first:
        return f"Vessel {label} (MMSI {mmsi}) first detected at {timestamp}"
    if sog is not None:
        return f"AIS position update at {timestamp} — speed {float(sog):.1f} kn near ({float(lat):.4f}, {float(lon):.4f})"
    return f"AIS position update at {timestamp} near ({float(lat):.4f}, {float(lon):.4f})"


def _narrative_for_alert(alert: Dict[str, Any]) -> str:
    alert_type = str(alert.get("alert_type") or "alert").replace("_", " ")
    explanation = alert.get("explanation")
    details = alert.get("details") or {}
    if alert.get("alert_type") == "ais_silence":
        gap_minutes = details.get("gap_minutes") or details.get("duration_minutes")
        if isinstance(gap_minutes, (int, float)):
            return f"AIS silence alert triggered — {int(gap_minutes)} minute gap detected"
    if explanation:
        clean = " ".join(str(explanation).split())
        return f"{alert_type.capitalize()} alert triggered — {clean}"
    return f"{alert_type.capitalize()} alert triggered"


def _narrative_for_cue(cue: Dict[str, Any]) -> str:
    data = cue.get("data") or {}
    cue_type = str(cue.get("cue_type") or "other").replace("_", " ")
    source = cue.get("source") or "external source"
    if data.get("ofac_match") or data.get("watchlist_hit") or data.get("sanctions_match"):
        confidence = data.get("confidence") or data.get("level") or "high"
        return f"External cue: OFAC watchlist match (confidence: {confidence})"
    summary = data.get("summary") or data.get("description") or data.get("label")
    if summary:
        return f"External cue from {source}: {summary}"
    return f"External cue from {source}: {cue_type} reported"


def _narrative_for_note(note: Dict[str, Any]) -> str:
    content = " ".join(str(note.get("content") or "").split())
    return f"Operator note: '{content}'"


def _narrative_for_status_change(entry: Dict[str, Any]) -> str:
    details = entry.get("details") or {}
    old = details.get("old")
    new = details.get("new")
    actor = entry.get("actor") or "system"
    if entry.get("action") == "case_status_updated" and old is not None and new is not None:
        return f"Case status changed from {old} to {new} by {actor}"
    if entry.get("action") == "case_assignment_updated":
        return f"Case assignment updated to {new or 'unassigned'} by {actor}"
    return f"Case audit event: {entry.get('action')} by {actor}"


def build_replay(case_id: str) -> Dict[str, Any]:
    """Build a time-ordered replay for a case."""
    UUID(str(case_id))
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    ic.id,
                    ic.title,
                    ic.mmsi,
                    ic.status,
                    ic.priority,
                    ic.summary,
                    ic.recommended_action,
                    ic.start_observed_at,
                    ic.end_observed_at,
                    ic.created_at,
                    ic.updated_at,
                    v.vessel_name,
                    v.vessel_type,
                    v.length,
                    v.width
                FROM investigation_case ic
                LEFT JOIN vessel v ON v.mmsi = ic.mmsi
                WHERE ic.id = %s
                """,
                (case_id,),
            )
            case_row = cur.fetchone()
            if not case_row:
                raise ValueError(f"Case not found: {case_id}")

            start_time = case_row.get("start_observed_at") or case_row.get("created_at")
            end_time = case_row.get("end_observed_at") or case_row.get("updated_at") or case_row.get("created_at")

            cur.execute(
                """
                SELECT
                    id,
                    observed_at,
                    ST_X(geom) AS lon,
                    ST_Y(geom) AS lat,
                    sog,
                    cog,
                    heading,
                    nav_status
                FROM ais_position
                WHERE mmsi = %s
                  AND observed_at BETWEEN %s AND %s
                ORDER BY observed_at ASC, id ASC
                """,
                (case_row["mmsi"], start_time, end_time),
            )
            positions = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                    a.id,
                    a.alert_type,
                    a.severity,
                    a.observed_at,
                    a.details,
                    a.explanation
                FROM case_evidence ce
                JOIN alert a ON a.id = ce.evidence_ref
                WHERE ce.case_id = %s AND ce.evidence_type = 'alert'
                ORDER BY a.observed_at ASC, a.id ASC
                """,
                (case_id,),
            )
            alerts = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT id, source, cue_type, observed_at, data, created_at
                FROM external_cue
                WHERE case_id = %s
                ORDER BY observed_at ASC NULLS LAST, created_at ASC, id ASC
                """,
                (case_id,),
            )
            cues = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT id, author, content, created_at
                FROM analyst_note
                WHERE case_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (case_id,),
            )
            notes = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT id, action, actor, details, created_at
                FROM audit_log
                WHERE entity_type = 'case' AND entity_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (case_id,),
            )
            audit_entries = [dict(row) for row in cur.fetchall()]

        events: List[Dict[str, Any]] = []

        for index, position in enumerate(positions):
            events.append(
                {
                    "timestamp": _iso(position["observed_at"]),
                    "event_type": "position",
                    "data": {
                        "id": position["id"],
                        "lon": float(position["lon"]),
                        "lat": float(position["lat"]),
                        "sog": float(position["sog"]) if position.get("sog") is not None else None,
                        "cog": float(position["cog"]) if position.get("cog") is not None else None,
                        "heading": float(position["heading"]) if position.get("heading") is not None else None,
                        "nav_status": position.get("nav_status"),
                    },
                    "narrative": _narrative_for_position(position, case_row.get("vessel_name") or "Unknown vessel", case_row["mmsi"], index == 0),
                }
            )

        for alert in alerts:
            events.append(
                {
                    "timestamp": _iso(alert["observed_at"]),
                    "event_type": "alert",
                    "data": {
                        "id": str(alert["id"]),
                        "alert_type": alert.get("alert_type"),
                        "severity": float(alert.get("severity") or 0.0),
                        "details": alert.get("details") or {},
                        "explanation": alert.get("explanation"),
                    },
                    "narrative": _narrative_for_alert(alert),
                }
            )

        for cue in cues:
            cue_time = cue.get("observed_at") or cue.get("created_at")
            events.append(
                {
                    "timestamp": _iso(cue_time),
                    "event_type": "cue",
                    "data": {
                        "id": str(cue["id"]),
                        "source": cue.get("source"),
                        "cue_type": cue.get("cue_type"),
                        "data": cue.get("data") or {},
                    },
                    "narrative": _narrative_for_cue(cue),
                }
            )

        for note in notes:
            events.append(
                {
                    "timestamp": _iso(note["created_at"]),
                    "event_type": "note",
                    "data": {
                        "id": str(note["id"]),
                        "author": note.get("author"),
                        "content": note.get("content"),
                    },
                    "narrative": _narrative_for_note(note),
                }
            )

        for entry in audit_entries:
            events.append(
                {
                    "timestamp": _iso(entry["created_at"]),
                    "event_type": "status_change",
                    "data": {
                        "id": entry.get("id"),
                        "action": entry.get("action"),
                        "actor": entry.get("actor"),
                        "details": entry.get("details") or {},
                    },
                    "narrative": _narrative_for_status_change(entry),
                }
            )

        events.sort(key=lambda item: (item["timestamp"], item["event_type"], str(item["data"].get("id", ""))))

        coordinates = [
            [float(position["lon"]), float(position["lat"])]
            for position in positions
            if position.get("lon") is not None and position.get("lat") is not None
        ]
        track_geojson = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
            "properties": {
                "case_id": str(case_row["id"]),
                "mmsi": case_row["mmsi"],
                "point_count": len(coordinates),
            },
        }

        return {
            "case_summary": {
                "id": str(case_row["id"]),
                "title": case_row.get("title"),
                "status": case_row.get("status"),
                "priority": case_row.get("priority"),
                "summary": case_row.get("summary"),
                "recommended_action": case_row.get("recommended_action"),
            },
            "vessel": {
                "mmsi": case_row.get("mmsi"),
                "name": case_row.get("vessel_name"),
                "type": case_row.get("vessel_type"),
                "length": float(case_row["length"]) if case_row.get("length") is not None else None,
                "width": float(case_row["width"]) if case_row.get("width") is not None else None,
            },
            "time_window": {
                "start": _iso(start_time),
                "end": _iso(end_time),
            },
            "events": events,
            "track_geojson": track_geojson,
        }
    finally:
        conn.close()
