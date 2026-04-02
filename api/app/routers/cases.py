"""FastAPI router for case listing, detail, workflow, notes, and audit endpoints."""

import json
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Query

from app.db import get_db_cursor, normalize_row, normalize_value

router = APIRouter(prefix="/cases", tags=["cases"])

ALLOWED_CASE_STATUSES = {"new", "in_review", "escalated", "resolved", "dismissed"}


def _sanitize_md(text: str) -> str:
    """Strip markdown metacharacters from user/DB content."""
    if not text:
        return ""
    for ch in ['#', '*', '_', '`', '[', ']', '(', ')', '>', '|', '~']:
        text = text.replace(ch, '')
    return text.strip()


@router.get("/")
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
        filters.append("ic.rank_score >= %s")
        params.append(min_score)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.extend([limit, offset])

    query = f"""
        SELECT
            ic.id,
            ic.title,
            ic.mmsi,
            ic.anomaly_score,
            ic.rank_score,
            ic.confidence_score,
            ic.status,
            ic.priority,
            ic.summary,
            ic.recommended_action,
            ic.start_observed_at,
            ic.end_observed_at,
            ic.created_at,
            ic.updated_at,
            v.vessel_name,
            COUNT(ce.id) AS evidence_count
        FROM investigation_case ic
        LEFT JOIN vessel v ON v.mmsi = ic.mmsi
        LEFT JOIN case_evidence ce ON ce.case_id = ic.id
        {where_clause}
        GROUP BY ic.id, v.vessel_name
        ORDER BY ic.rank_score DESC, ic.created_at DESC
        LIMIT %s OFFSET %s
    """

    with get_db_cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()

    return [normalize_row(dict(row)) for row in rows]


@router.get("/{case_id}")
async def get_case(case_id: UUID):
    case_query = """
        SELECT
            ic.id,
            ic.title,
            ic.mmsi,
            ic.anomaly_score,
            ic.rank_score,
            ic.confidence_score,
            ic.status,
            ic.priority,
            ic.summary,
            ic.recommended_action,
            ic.assigned_to,
            ic.zone_context,
            ic.start_observed_at,
            ic.end_observed_at,
            ic.created_at,
            ic.updated_at,
            ST_X(ic.primary_geom) AS primary_lon,
            ST_Y(ic.primary_geom) AS primary_lat,
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
            observed_at,
            timeline_order,
            created_at
        FROM case_evidence
        WHERE case_id = %s
        ORDER BY observed_at ASC NULLS LAST, timeline_order ASC, created_at ASC, id ASC
    """

    case_id_str = str(case_id)

    with get_db_cursor() as cursor:
        cursor.execute(case_query, [case_id_str])
        case_row = cursor.fetchone()
        if not case_row:
            raise HTTPException(status_code=404, detail="Case not found")

        cursor.execute(evidence_query, [case_id_str])
        evidence_rows = cursor.fetchall()

    case_data = normalize_row(dict(case_row))
    case_data["primary_geom"] = {
        "lon": case_data.pop("primary_lon"),
        "lat": case_data.pop("primary_lat"),
    }
    case_data["evidence"] = [normalize_row(dict(row)) for row in evidence_rows]

    # Add live score breakdown
    try:
        from app.services.scoring import compute_score_breakdown

        case_data["score"] = compute_score_breakdown(case_id_str)
    except Exception:
        case_data["score"] = None

    return case_data


@router.patch("/{case_id}")
async def update_case(
    case_id: UUID,
    payload: Dict[str, Any] = Body(default={}),
):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be an object")

    status_provided = "status" in payload
    assigned_to_provided = "assigned_to" in payload

    if not status_provided and not assigned_to_provided:
        raise HTTPException(status_code=400, detail="At least one of status or assigned_to must be provided")

    new_status = payload.get("status")
    new_assigned_to = payload.get("assigned_to")

    if status_provided and new_status not in ALLOWED_CASE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="status must be one of new, in_review, escalated, resolved, dismissed",
        )
    if assigned_to_provided and new_assigned_to is not None and not isinstance(new_assigned_to, str):
        raise HTTPException(status_code=400, detail="assigned_to must be a string or null")
    if status_provided and new_status is not None and not isinstance(new_status, str):
        raise HTTPException(status_code=400, detail="status must be a string")

    case_id_str = str(case_id)

    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, status, assigned_to
            FROM investigation_case
            WHERE id = %s
            """,
            [case_id_str],
        )
        current_case = cursor.fetchone()
        if not current_case:
            raise HTTPException(status_code=404, detail="Case not found")

        updates: List[str] = []
        update_params: List[Any] = []
        audit_entries: List[tuple[str, Dict[str, Any], str]] = []

        if status_provided and current_case["status"] != new_status:
            updates.append("status = %s")
            update_params.append(new_status)
            audit_entries.append(
                (
                    "case_status_updated",
                    {"field": "status", "old": current_case["status"], "new": new_status},
                    new_assigned_to or current_case["assigned_to"] or "system",
                )
            )

        if assigned_to_provided and current_case["assigned_to"] != new_assigned_to:
            updates.append("assigned_to = %s")
            update_params.append(new_assigned_to)
            audit_entries.append(
                (
                    "case_assignment_updated",
                    {"field": "assigned_to", "old": current_case["assigned_to"], "new": new_assigned_to},
                    new_assigned_to or current_case["assigned_to"] or "system",
                )
            )

        if updates:
            update_params.extend([case_id_str])
            cursor.execute(
                f"""
                UPDATE investigation_case
                SET {', '.join(updates)}, updated_at = NOW()
                WHERE id = %s
                RETURNING id,
                          title,
                          mmsi,
                          anomaly_score,
                          rank_score,
                          confidence_score,
                          status,
                          priority,
                          summary,
                          recommended_action,
                          assigned_to,
                          start_observed_at,
                          end_observed_at,
                          created_at,
                          updated_at
                """,
                update_params,
            )
            updated_case = cursor.fetchone()

            for action, details, actor in audit_entries:
                cursor.execute(
                    """
                    INSERT INTO audit_log (action, entity_type, entity_id, actor, details)
                    VALUES (%s, 'case', %s, %s, %s::jsonb)
                    """,
                    [action, case_id_str, actor, json.dumps(normalize_value(details))],
                )
        else:
            cursor.execute(
                """
                SELECT id,
                       title,
                       mmsi,
                       anomaly_score,
                       rank_score,
                       confidence_score,
                       status,
                       priority,
                       summary,
                       recommended_action,
                       assigned_to,
                       start_observed_at,
                       end_observed_at,
                       created_at,
                       updated_at
                FROM investigation_case
                WHERE id = %s
                """,
                [case_id_str],
            )
            updated_case = cursor.fetchone()

        cursor.connection.commit()

    return normalize_row(dict(updated_case))


@router.get("/{case_id}/notes")
async def list_case_notes(case_id: UUID):
    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM investigation_case WHERE id = %s",
            [str(case_id)],
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")

        cursor.execute(
            """
            SELECT id, case_id, author, content, created_at
            FROM analyst_note
            WHERE case_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            [str(case_id)],
        )
        rows = cursor.fetchall()

    return [normalize_row(dict(row)) for row in rows]


@router.post("/{case_id}/notes")
async def create_case_note(
    case_id: UUID,
    payload: Dict[str, Any] = Body(default={}),
):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be an object")

    author = payload.get("author")
    content = payload.get("content")

    if not author or not isinstance(author, str):
        raise HTTPException(status_code=400, detail="author is required")
    if not content or not isinstance(content, str):
        raise HTTPException(status_code=400, detail="content is required")

    case_id_str = str(case_id)

    with get_db_cursor() as cursor:
        cursor.execute("SELECT 1 FROM investigation_case WHERE id = %s", [case_id_str])
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")

        cursor.execute(
            """
            INSERT INTO analyst_note (case_id, author, content)
            VALUES (%s, %s, %s)
            RETURNING id, case_id, author, content, created_at
            """,
            [case_id_str, author, content],
        )
        note_row = cursor.fetchone()

        cursor.execute(
            """
            INSERT INTO audit_log (action, entity_type, entity_id, actor, details)
            VALUES (%s, 'case', %s, %s, %s::jsonb)
            """,
            [
                "case_note_created",
                case_id_str,
                author,
                json.dumps(normalize_value({"note_id": note_row["id"], "content": content})),
            ],
        )

        cursor.connection.commit()

    return normalize_row(dict(note_row))


@router.get("/{case_id}/audit")
async def list_case_audit_log(case_id: UUID):
    with get_db_cursor() as cursor:
        cursor.execute("SELECT 1 FROM investigation_case WHERE id = %s", [str(case_id)])
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")

        cursor.execute(
            """
            SELECT id, action, entity_type, entity_id, actor, details, created_at
            FROM audit_log
            WHERE entity_type = 'case' AND entity_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            [str(case_id)],
        )
        rows = cursor.fetchall()

    return [normalize_row(dict(row)) for row in rows]


@router.get("/{case_id}/replay")
async def get_case_replay(case_id: UUID):
    """Get time-ordered incident replay for a case."""
    from app.services.replay import build_replay

    case_id_str = str(case_id)

    with get_db_cursor() as cursor:
        cursor.execute("SELECT 1 FROM investigation_case WHERE id = %s", [case_id_str])
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")

    try:
        return build_replay(case_id_str)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Replay service unavailable") from exc


@router.get("/{case_id}/score")
async def get_case_score(case_id: UUID):
    """Get explainable score breakdown for a case."""
    from app.services.scoring import compute_score_breakdown

    case_id_str = str(case_id)

    with get_db_cursor() as cursor:
        cursor.execute("SELECT 1 FROM investigation_case WHERE id = %s", [case_id_str])
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")

    try:
        return compute_score_breakdown(case_id_str)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Scoring service unavailable") from exc


@router.post("/{case_id}/actions")
async def perform_case_action(
    case_id: UUID,
    payload: Dict[str, Any] = Body(default={}),
):
    """Perform a workflow action: acknowledge, assign, dismiss, escalate, mark_under_review, export_brief."""
    action = payload.get("action")
    actor = payload.get("actor", "system")
    reason = payload.get("reason", "")
    assignee = payload.get("assignee")

    valid_actions = {"acknowledge", "assign", "dismiss", "escalate", "mark_under_review", "export_brief"}
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"action must be one of {sorted(valid_actions)}")
    if (reason is not None and len(str(reason)) > 500) or (assignee is not None and len(str(assignee)) > 500):
        raise HTTPException(status_code=400, detail="reason/assignee must be under 500 characters")

    case_id_str = str(case_id)
    status_map = {
        "acknowledge": "in_review",
        "assign": "in_review",
        "dismiss": "dismissed",
        "escalate": "escalated",
        "mark_under_review": "in_review",
    }

    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT id, status, assigned_to, title, mmsi FROM investigation_case WHERE id = %s",
            [case_id_str],
        )
        current = cursor.fetchone()
        if not current:
            raise HTTPException(status_code=404, detail="Case not found")

        if action == "export_brief":
            from app.services.replay import build_replay
            from app.services.scoring import compute_score_breakdown

            try:
                score = compute_score_breakdown(case_id_str)
                replay = build_replay(case_id_str)
            except Exception as exc:
                raise HTTPException(status_code=503, detail="Brief generation failed") from exc
            brief = f"# Case Brief: {_sanitize_md(current['title'])}\n\n"
            brief += f"**MMSI:** {_sanitize_md(current['mmsi'])}\n"
            brief += f"**Status:** {_sanitize_md(current['status'])}\n"
            brief += f"**Rank Score:** {score.get('rank_score', 'N/A')}\n\n"
            brief += "## Why Now\n"
            for reason_item in score.get("why_now", []):
                brief += f"- {_sanitize_md(reason_item)}\n"
            brief += "\n## Top Reasons\n"
            for reason_item in score.get("top_reasons", []):
                brief += f"- {_sanitize_md(reason_item)}\n"
            brief += f"\n## Confidence\n{_sanitize_md(score.get('confidence_explainer', 'N/A'))}\n"
            if score.get("benign_context"):
                brief += f"\n## Benign Context\n{_sanitize_md(score['benign_context'])}\n"
            brief += f"\n## Timeline ({len(replay.get('events', []))} events)\n"
            for event in replay.get("events", [])[:20]:
                brief += f"- [{event.get('timestamp', '')}] {_sanitize_md(event.get('narrative', ''))}\n"
            return {"format": "markdown", "content": brief}

        new_status = status_map.get(action)
        updates = []
        params = []

        if new_status and new_status != current["status"]:
            updates.append("status = %s")
            params.append(new_status)

        if action == "assign" and assignee:
            updates.append("assigned_to = %s")
            params.append(assignee)
        elif action == "acknowledge":
            updates.append("assigned_to = %s")
            params.append(actor)

        if updates:
            params.append(case_id_str)
            cursor.execute(
                f"UPDATE investigation_case SET {', '.join(updates)}, updated_at = NOW() WHERE id = %s RETURNING id, title, mmsi, status, assigned_to, rank_score, updated_at",
                params,
            )

        cursor.execute(
            "INSERT INTO audit_log (action, entity_type, entity_id, actor, details) VALUES (%s, 'case', %s, %s, %s::jsonb)",
            [
                f"case_{action}",
                case_id_str,
                actor,
                json.dumps(normalize_value({"action": action, "reason": reason, "assignee": assignee})),
            ],
        )
        cursor.connection.commit()

        cursor.execute(
            "SELECT id, title, mmsi, status, assigned_to, rank_score, updated_at FROM investigation_case WHERE id = %s",
            [case_id_str],
        )
        updated = cursor.fetchone()

    return {"action": action, "case": normalize_row(dict(updated)), "audit_logged": True}
