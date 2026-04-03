"""Template-driven case narrative generator for analyst-ready investigation briefs."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db import get_db_cursor, normalize_row


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _iso(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _title_case_alert(alert_type: Optional[str]) -> str:
    return str(alert_type or "alert").replace("_", " ").title()


def _format_vessel_type(value: Any) -> str:
    return "Unknown" if value in (None, "") else str(value)


def _build_alert_description(alert: Dict[str, Any]) -> str:
    details = _as_dict(alert.get("details"))
    explanation = alert.get("explanation")
    if explanation:
        return " ".join(str(explanation).split())
    for key in ("summary", "description", "reason", "note", "label"):
        if details.get(key):
            return " ".join(str(details[key]).split())
    if alert.get("alert_type") == "ais_silence":
        gap_minutes = details.get("gap_minutes") or details.get("duration_minutes")
        if isinstance(gap_minutes, (int, float)):
            return f"AIS gap of {int(gap_minutes)} minutes detected"
    return "Automated detection flagged for analyst review"


def _benign_explanations(alert_types: List[str]) -> List[str]:
    explanations: List[str] = []
    unique_types = set(alert_types)
    if "loitering" in unique_types:
        explanations.append("Vessel may have been waiting for berth assignment or pilot.")
    if "ais_silence" in unique_types:
        explanations.append("Equipment malfunction or poor satellite coverage possible.")
    if "abnormal_approach" in unique_types:
        explanations.append("Weather avoidance or traffic separation compliance.")
    if not explanations:
        explanations.append("Routine commercial maneuvering or port congestion may account for some observed behavior.")
    return explanations


def _fetch_external_cues(case_id: str) -> List[Dict[str, Any]]:
    cue_queries = [
        """
        SELECT id, source, cue_type, observed_at, data, created_at
        FROM external_cue
        WHERE linked_case_id = %s
        ORDER BY observed_at ASC NULLS LAST, created_at ASC, id ASC
        """,
        """
        SELECT id, source, cue_type, observed_at, data, created_at
        FROM external_cue
        WHERE case_id = %s
        ORDER BY observed_at ASC NULLS LAST, created_at ASC, id ASC
        """,
    ]

    for query in cue_queries:
        try:
            with get_db_cursor() as cursor:
                cursor.execute(query, [case_id])
                return [normalize_row(dict(row)) for row in cursor.fetchall()]
        except Exception:
            continue
    return []


def generate_narrative(case_id: str) -> Optional[Dict[str, Any]]:
    """Generate analyst-ready case narrative from DB data."""
    case_query = """
        SELECT
            ic.id,
            ic.title,
            ic.mmsi,
            ic.priority,
            ic.summary,
            ic.recommended_action,
            ic.start_observed_at,
            ic.end_observed_at,

            ic.anomaly_score,
            ic.confidence_score,
            v.vessel_name,
            v.vessel_type,
            v.vessel_type AS vessel_type_code
        FROM investigation_case ic
        LEFT JOIN vessel v ON v.mmsi = ic.mmsi
        WHERE ic.id = %s
    """
    alerts_query = """
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
        ORDER BY a.observed_at ASC NULLS LAST, a.id ASC
    """

    with get_db_cursor() as cursor:
        cursor.execute(case_query, [case_id])
        case_row = cursor.fetchone()
        if not case_row:
            return None

        cursor.execute(alerts_query, [case_id])
        alert_rows = cursor.fetchall()

    case_data = normalize_row(dict(case_row))
    alerts = [normalize_row(dict(row)) for row in alert_rows]
    external_cues = _fetch_external_cues(case_id)

    vessel_name = case_data.get("vessel_name") or "Unknown vessel"
    vessel_type = _format_vessel_type(case_data.get("vessel_type"))
    vessel_flag = "Unknown"
    start_time = case_data.get("start_observed_at")
    end_time = case_data.get("end_observed_at") or start_time
    priority = case_data.get("priority") or "unknown"
    confidence = round(float(case_data.get("confidence_score") or 0.0) * 100)
    anomaly_score = round(float(case_data.get("anomaly_score") or 0.0), 2)

    alert_types = [str(alert.get("alert_type") or "alert") for alert in alerts]
    unique_alert_types = sorted({_title_case_alert(alert_type) for alert_type in alert_types})
    cue_types = sorted({str(cue.get("cue_type") or "other").replace("_", " ") for cue in external_cues})

    timeline: List[Dict[str, Any]] = []
    timeline_lines: List[str] = []
    evidence_citations: List[Dict[str, Any]] = []

    for alert in alerts:
        timestamp = _iso(alert.get("observed_at"))
        alert_type_label = _title_case_alert(alert.get("alert_type"))
        description = _build_alert_description(alert)
        severity = int(round(float(alert.get("severity") or 0.0) * 5)) if float(alert.get("severity") or 0.0) <= 1 else int(round(float(alert.get("severity") or 0.0)))
        severity = max(0, min(severity, 5))
        timeline_entry = {
            "timestamp": timestamp,
            "alert_type": alert.get("alert_type"),
            "description": description,
            "severity": severity,
            "alert_id": str(alert.get("id")),
        }
        timeline.append(timeline_entry)
        timeline_lines.append(f"- {timestamp} — {alert_type_label}: {description} (severity {severity}/5)")
        evidence_citations.append(
            {
                "type": "alert",
                "id": str(alert.get("id")),
                "alert_type": alert.get("alert_type"),
                "timestamp": timestamp,
            }
        )

    for cue in external_cues:
        evidence_citations.append(
            {
                "type": "external_cue",
                "id": str(cue.get("id")),
                "cue_type": cue.get("cue_type"),
                "source": cue.get("source"),
                "timestamp": _iso(cue.get("observed_at") or cue.get("created_at")),
            }
        )

    alert_type_text = ", ".join(unique_alert_types) if unique_alert_types else "No alert types"
    summary_start = _iso(start_time)
    summary_end = _iso(end_time)
    benign_lines = [f"- {item}" for item in _benign_explanations(alert_types)]

    evidence_line = f"{len(alerts)} alerts across {alert_type_text.lower() if unique_alert_types else 'no alert categories'}. {len(external_cues)} external cues corroborate."
    if external_cues:
        evidence_line += f" External intelligence ({', '.join(cue_types)}) supports investigation."

    narrative_sections = [
        f"CASE BRIEF: {case_data.get('title') or 'Untitled Case'}",
        f"Vessel: {vessel_name} (MMSI: {case_data.get('mmsi') or 'Unknown'}, Type: {vessel_type}, Flag: {vessel_flag})",
        f"Period: {summary_start} to {summary_end}",
        f"Priority: {priority} | Confidence: {confidence}% | Anomaly Score: {anomaly_score}",
        "",
        "SUMMARY:",
        f"{vessel_name} triggered {len(alerts)} alerts ({alert_type_text}) between {summary_start} and {summary_end} in the Port of Duqm approach zone.",
        "",
        "ALERT TIMELINE:",
        * (timeline_lines or ["- No linked alerts available."]),
        "",
        "EVIDENCE:",
        evidence_line,
        "",
        "BENIGN EXPLANATIONS CONSIDERED:",
        *benign_lines,
        "",
        "RECOMMENDED ACTIONS:",
        case_data.get("recommended_action") or "Review alert evidence and assess for escalation.",
    ]

    return {
        "narrative": "\n".join(narrative_sections),
        "evidence_citations": evidence_citations,
        "timeline": timeline,
    }
