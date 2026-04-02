"""Explainable case scoring service.

Produces transparent rank scores with component breakdown,
why-now reasoning, and confidence explanation.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import Json, RealDictCursor

DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://cue2case:cue2case_dev@localhost:5433/cue2case",
)

CUE_TYPE_WEIGHTS = {
    "imagery": 0.18,
    "rf_detection": 0.16,
    "tip": 0.14,
    "other": 0.08,
}

HIGH_RISK_VESSEL_TYPES = {30, 31, 32, 33, 34, 35, 36, 37, 50, 51, 52, 55}
ROUTINE_COMMERCIAL_TYPES = {60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _round(value: float) -> float:
    return round(float(value), 4)


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"raw": value}
        except json.JSONDecodeError:
            return {"raw": value}
    return {"raw": value}


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _extract_zone_context(alerts: List[Dict[str, Any]]) -> Tuple[Optional[str], float]:
    criticality = 0.3
    zone_label = None
    for alert in alerts:
        details = _as_dict(alert.get("details"))
        raw_zone = details.get("zone_context")
        if not raw_zone:
            continue

        zone_items = raw_zone if isinstance(raw_zone, list) else [raw_zone]
        for zone_item in zone_items:
            if isinstance(zone_item, dict):
                zone_label = zone_item.get("name") or zone_item.get("zone") or zone_label
                for key in ("criticality", "score", "risk", "priority"):
                    raw_value = zone_item.get(key)
                    if isinstance(raw_value, (int, float)):
                        criticality = max(criticality, float(raw_value))
                lowered = json.dumps(zone_item).lower()
            else:
                zone_label = str(zone_item)
                lowered = zone_label.lower()

            if any(token in lowered for token in ("government", "naval", "military", "restricted", "critical")):
                criticality = max(criticality, 0.85)
            elif any(token in lowered for token in ("berth", "port", "terminal", "approach", "corridor", "harbor")):
                criticality = max(criticality, 0.6)

    return zone_label, _clamp(criticality, 0.0, 1.0)


def _compute_behavior_severity(alerts: List[Dict[str, Any]]) -> float:
    if not alerts:
        return 0.0
    severities = sorted(float(alert.get("severity") or 0.0) for alert in alerts)
    peak = severities[-1]
    average = sum(severities) / len(severities)
    multi_alert_bonus = min(0.15, 0.03 * max(0, len(alerts) - 1))
    return _clamp((peak * 0.65) + (average * 0.35) + multi_alert_bonus, 0.0, 1.0)


def _compute_cue_corroboration(cues: List[Dict[str, Any]]) -> float:
    if not cues:
        return 0.0
    total = 0.0
    for cue in cues:
        cue_type = (cue.get("cue_type") or "other").lower()
        total += CUE_TYPE_WEIGHTS.get(cue_type, 0.08)
        data = _as_dict(cue.get("data"))
        confidence = str(data.get("confidence") or data.get("level") or "").lower()
        if confidence in {"high", "strong", "confirmed"}:
            total += 0.06
        elif confidence in {"medium", "moderate"}:
            total += 0.03
        if data.get("watchlist_hit") or data.get("ofac_match"):
            total += 0.05
    return _clamp(max(0.1, total), 0.0, 0.5)


def _compute_identity_risk(vessel_type: Optional[int], cues: List[Dict[str, Any]]) -> float:
    risk = 0.15
    if vessel_type in HIGH_RISK_VESSEL_TYPES:
        risk += 0.25
    elif vessel_type in ROUTINE_COMMERCIAL_TYPES:
        risk += 0.05
    else:
        risk += 0.12

    for cue in cues:
        data = _as_dict(cue.get("data"))
        if data.get("watchlist_hit") or data.get("ofac_match") or data.get("sanctions_match"):
            risk += 0.3
        if data.get("identity_mismatch") or data.get("spoofing_suspected"):
            risk += 0.2

    return _clamp(risk, 0.0, 1.0)


def _compute_freshness(reference_time: Optional[datetime]) -> float:
    if reference_time is None:
        return 0.0
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)
    age_hours = max(0.0, (datetime.now(timezone.utc) - reference_time.astimezone(timezone.utc)).total_seconds() / 3600.0)
    if age_hours <= 2:
        return 1.0
    if age_hours <= 6:
        return _clamp(1.0 - ((age_hours - 2) * 0.12), 0.0, 1.0)
    if age_hours <= 24:
        return _clamp(0.52 - ((age_hours - 6) * 0.02), 0.0, 1.0)
    return _clamp(0.16 - ((age_hours - 24) * 0.005), 0.0, 1.0)


def _compute_uncertainty_penalty(case_row: Dict[str, Any], alerts: List[Dict[str, Any]], cues: List[Dict[str, Any]]) -> Tuple[float, List[str]]:
    missing: List[str] = []
    penalty = 0.0

    if not alerts:
        missing.append("No linked alert evidence")
        penalty += 0.35
    if not cues:
        missing.append("No external cues attached")
        penalty += 0.18
    if not case_row.get("start_observed_at") or not case_row.get("end_observed_at"):
        missing.append("Incomplete case time window")
        penalty += 0.12
    if case_row.get("mmsi") in (None, "", "unknown"):
        missing.append("Missing vessel identity")
        penalty += 0.14
    if case_row.get("primary_lon") is None or case_row.get("primary_lat") is None:
        missing.append("Missing primary case location")
        penalty += 0.1
    if not case_row.get("summary"):
        missing.append("Case summary not populated")
        penalty += 0.05

    return -_clamp(penalty, 0.0, 0.75), missing


def _confidence_explainer(case_row: Dict[str, Any], alert_count: int, cue_count: int, missing_count: int) -> str:
    confidence = float(case_row.get("confidence_score") or 0.0)
    if confidence >= 0.85:
        label = "high"
    elif confidence >= 0.65:
        label = "moderate"
    else:
        label = "limited"
    return (
        f"Confidence is {label} ({confidence:.2f}) based on {alert_count} linked alert(s), "
        f"{cue_count} external cue(s), and {missing_count} identified evidence gap(s)."
    )


def _top_reasons(components: Dict[str, float]) -> List[str]:
    labels = {
        "behavior_severity": "Behavior severity",
        "zone_criticality": "Zone criticality",
        "cue_corroboration": "Cue corroboration",
        "identity_risk": "Identity risk",
        "freshness": "Freshness",
        "uncertainty_penalty": "Uncertainty penalty",
    }
    ordered = sorted(components.items(), key=lambda item: abs(item[1]), reverse=True)
    return [f"{labels[name]} ({value:+.3f})" for name, value in ordered[:3]]


def _build_why_now(case_row: Dict[str, Any], alerts: List[Dict[str, Any]], cues: List[Dict[str, Any]], zone_label: Optional[str]) -> List[str]:
    reasons: List[str] = []
    if alerts:
        top_alert = max(alerts, key=lambda alert: (float(alert.get("severity") or 0.0), alert.get("observed_at") or datetime.min.replace(tzinfo=timezone.utc)))
        alert_type = str(top_alert.get("alert_type") or "activity").replace("_", " ")
        severity = float(top_alert.get("severity") or 0.0)
        if severity >= 0.75:
            zone_phrase = f" near {zone_label}" if zone_label else ""
            reasons.append(f"High-severity {alert_type} detected{zone_phrase}")

    if cues:
        reasons.append(f"{len(cues)} corroborating external cue{'s' if len(cues) != 1 else ''} attached")
        if any(_as_dict(cue.get("data")).get(key) for cue in cues for key in ("watchlist_hit", "ofac_match", "sanctions_match")):
            reasons.append("Watchlist vessel indicator present in external cue set")

    start_observed_at = case_row.get("start_observed_at")
    if start_observed_at is not None:
        if start_observed_at.tzinfo is None:
            start_observed_at = start_observed_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - start_observed_at.astimezone(timezone.utc) <= timedelta(hours=2):
            reasons.append("Case opened within last 2 hours")

    anomaly_score = float(case_row.get("anomaly_score") or 0.0)
    confidence_score = float(case_row.get("confidence_score") or 0.0)
    if anomaly_score >= 0.7 and confidence_score >= 0.7:
        reasons.append("Anomaly score remains elevated with strong supporting evidence")
    if not reasons and alerts:
        alert_type = str(alerts[-1].get("alert_type") or "activity").replace("_", " ")
        reasons.append(f"Recent {alert_type} evidence keeps the case active")

    return reasons[:5]


def _build_benign_context(vessel_type: Optional[int], cues: List[Dict[str, Any]], case_row: Dict[str, Any]) -> Optional[str]:
    weather = False
    similar_patterns = 0
    for cue in cues:
        data = _as_dict(cue.get("data"))
        text_blob = json.dumps(data).lower()
        if any(token in text_blob for token in ("weather", "marine advisory", "sea state", "storm", "wind", "current")):
            weather = True
        for key in ("similar_vessel_count", "peer_count", "pattern_count"):
            value = data.get(key)
            if isinstance(value, int):
                similar_patterns = max(similar_patterns, value)

    if weather:
        return "Marine weather advisory active in area — may explain reduced speed"
    if vessel_type in ROUTINE_COMMERCIAL_TYPES:
        return "Vessel type consistent with routine commercial traffic"
    if similar_patterns >= 2:
        return f"Similar pattern observed by {similar_patterns} other vessels in same time window"
    if float(case_row.get("anomaly_score") or 0.0) < 0.35:
        return "Observed pattern may reflect routine variation rather than a persistent threat"
    return None


def compute_score_breakdown(case_id: str) -> Dict[str, Any]:
    """Compute explainable score breakdown for a case."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    ic.id,
                    ic.mmsi,
                    ic.title,
                    ic.anomaly_score,
                    ic.confidence_score,
                    ic.rank_score,
                    ic.status,
                    ic.priority,
                    ic.summary,
                    ic.recommended_action,
                    ic.assigned_to,
                    ic.start_observed_at,
                    ic.end_observed_at,
                    ic.created_at,
                    ic.updated_at,
                    ST_X(ic.primary_geom) AS primary_lon,
                    ST_Y(ic.primary_geom) AS primary_lat,
                    v.vessel_name,
                    v.vessel_type
                FROM investigation_case ic
                LEFT JOIN vessel v ON v.mmsi = ic.mmsi
                WHERE ic.id = %s
                """,
                (case_id,),
            )
            case_row = cur.fetchone()
            if not case_row:
                raise ValueError(f"Case not found: {case_id}")

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

        zone_label, zone_criticality = _extract_zone_context(alerts)
        behavior_severity = _compute_behavior_severity(alerts)
        cue_corroboration = _compute_cue_corroboration(cues)
        identity_risk = _compute_identity_risk(case_row.get("vessel_type"), cues)
        freshness_reference = case_row.get("updated_at") or case_row.get("end_observed_at") or case_row.get("created_at")
        freshness = _compute_freshness(freshness_reference)
        uncertainty_penalty, missing_evidence = _compute_uncertainty_penalty(case_row, alerts, cues)

        weighted_components = {
            "behavior_severity": _round(behavior_severity * 0.6),
            "zone_criticality": _round(zone_criticality * 0.35),
            "cue_corroboration": _round(cue_corroboration * 0.5),
            "identity_risk": _round(identity_risk * 0.35),
            "freshness": _round(freshness * 0.2),
            "uncertainty_penalty": _round(uncertainty_penalty),
        }
        base_rank = sum(weighted_components.values()) + (float(case_row.get("anomaly_score") or 0.0) * 0.35) + (float(case_row.get("confidence_score") or 0.0) * 0.15)
        rank_score = _round(_clamp(base_rank, 0.0, 2.0))

        why_now = _build_why_now(case_row, alerts, cues, zone_label)
        benign_context = _build_benign_context(case_row.get("vessel_type"), cues, case_row)

        breakdown = {
            "rank_score": rank_score,
            "components": weighted_components,
            "why_now": why_now,
            "top_reasons": _top_reasons(weighted_components),
            "confidence_explainer": _confidence_explainer(case_row, len(alerts), len(cues), len(missing_evidence)),
            "benign_context": benign_context,
            "missing_evidence": missing_evidence,
            "inputs": {
                "case_id": str(case_row["id"]),
                "mmsi": case_row.get("mmsi"),
                "vessel_name": case_row.get("vessel_name"),
                "vessel_type": case_row.get("vessel_type"),
                "zone_context": zone_label,
                "alert_count": len(alerts),
                "cue_count": len(cues),
                "anomaly_score": _round(float(case_row.get("anomaly_score") or 0.0)),
                "confidence_score": _round(float(case_row.get("confidence_score") or 0.0)),
                "evaluated_at": _iso(datetime.now(timezone.utc)),
            },
        }
        return breakdown
    finally:
        conn.close()


def batch_score_cases(case_ids: Optional[List[str]] = None) -> int:
    """Recompute scores for cases. Returns count updated."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    updated = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                ALTER TABLE investigation_case
                ADD COLUMN IF NOT EXISTS score_breakdown jsonb
                """
            )

            if case_ids is None:
                cur.execute(
                    """
                    SELECT id
                    FROM investigation_case
                    WHERE status NOT IN ('resolved', 'dismissed')
                    ORDER BY created_at ASC, id ASC
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT id
                    FROM investigation_case
                    WHERE id = ANY(%s::uuid[])
                    ORDER BY created_at ASC, id ASC
                    """,
                    (case_ids,),
                )
            target_ids = [str(row["id"]) for row in cur.fetchall()]

        for target_id in target_ids:
            breakdown = compute_score_breakdown(target_id)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE investigation_case
                    SET rank_score = %s,
                        score_breakdown = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (breakdown["rank_score"], Json(breakdown), target_id),
                )
                updated += cur.rowcount

        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
