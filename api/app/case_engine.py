"""Case Engine: clusters vessel alerts into incident-based investigation cases."""

import json
import os
from collections import defaultdict
from datetime import timedelta

import psycopg2
from psycopg2.extras import Json, execute_values

DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://cue2case:cue2case_dev@localhost:5433/cue2case",
)

INCIDENT_GAP = timedelta(hours=2)
MIN_SUSTAINED_DURATION = timedelta(minutes=30)
MIN_CASE_SCORE = 0.05
TIMELINE_EVENT_LIMIT = 5

ALERT_WEIGHTS = {
    "identity_anomaly": 0.40,
    "kinematic_anomaly": 0.20,
    "abnormal_approach": 0.25,
    "spoofing": 0.20,
    "ais_silence": 0.10,
    "loitering": 0.05,
}

RECOMMENDATIONS = {
    "identity_anomaly": (
        "Verify vessel identity through registry, AIS, and historical track cross-checks. "
        "Investigate duplicate MMSI usage and confirm which broadcast source is legitimate."
    ),
    "kinematic_anomaly": (
        "Review vessel motion replay for impossible jumps, GPS spikes, or implausible speed changes. "
        "Validate sensor quality and compare against nearby track data."
    ),
    "abnormal_approach": (
        "Review vessel track replay for approach corridor compliance. "
        "Cross-reference with port authority approach instructions."
    ),
    "ais_silence": (
        "Investigate gap period. Check if vessel was in port blind spot or intentionally went dark. "
        "Request imagery for the AIS silence window."
    ),
    "loitering": (
        "Check vessel purpose and authorization for extended anchorage. "
        "Verify whether the vessel is awaiting berth assignment or exhibiting suspicious behavior."
    ),
    "spoofing": (
        "Investigate potential GPS manipulation or AIS spoofing. "
        "Cross-reference position data with radar or satellite imagery. "
        "Check for impossible speed jumps or position teleportation."
    ),
}

DEFAULT_RECOMMENDATION = "Review vessel activity, source alerts, and nearby operational context."


def priority_for_score(anomaly_score):
    """Map anomaly score to low/medium/high priority values."""
    if anomaly_score >= 0.7:
        return 3
    if anomaly_score >= 0.4:
        return 2
    return 1


def normalize_details(details):
    """Return alert details as a dictionary when possible."""
    if isinstance(details, dict):
        return details
    if details is None:
        return {}
    if isinstance(details, str):
        try:
            parsed = json.loads(details)
            return parsed if isinstance(parsed, dict) else {"raw": details}
        except json.JSONDecodeError:
            return {"raw": details}
    return {"raw": details}


def round_to_nearest_hour(timestamp):
    """Round datetimes to the nearest hour for stable case signatures."""
    if timestamp is None:
        return None

    rounded = timestamp.replace(minute=0, second=0, microsecond=0)
    if timestamp - rounded >= timedelta(minutes=30):
        rounded += timedelta(hours=1)
    return rounded


def case_signature(mmsi, alert_types, start_observed_at):
    """Build a deterministic signature that survives case rebuilds."""
    rounded_start = round_to_nearest_hour(start_observed_at)
    return (
        str(mmsi),
        tuple(sorted(alert_types)),
        rounded_start.isoformat() if rounded_start is not None else None,
    )


def build_recommendation(alert_counts, max_severity_by_type):
    """Build a context-sensitive recommendation based on all alert types present."""
    ordered_types = sorted(
        alert_counts.keys(),
        key=lambda t: (
            -(max_severity_by_type.get(t, 0.0) * ALERT_WEIGHTS.get(t, 0.0)),
            -alert_counts[t],
            t,
        ),
    )
    if len(ordered_types) <= 1:
        return RECOMMENDATIONS.get(
            ordered_types[0] if ordered_types else "",
            DEFAULT_RECOMMENDATION,
        )

    parts = []
    for alert_type in ordered_types:
        rec = RECOMMENDATIONS.get(alert_type)
        if rec:
            parts.append(rec)

    if not parts:
        return DEFAULT_RECOMMENDATION

    type_labels = ", ".join(t.replace("_", " ") for t in ordered_types)
    return f"Multiple anomaly types detected ({type_labels}). " + " Additionally: ".join(parts[:3])


def dominant_alert_type(max_severity_by_type, alert_counts):
    """Choose the dominant alert type using weighted contribution, then count, then severity."""
    return max(
        max_severity_by_type,
        key=lambda alert_type: (
            max_severity_by_type[alert_type] * ALERT_WEIGHTS.get(alert_type, 0),
            alert_counts.get(alert_type, 0),
            max_severity_by_type[alert_type],
            alert_type,
        ),
    )


def cluster_alerts_by_incident(alerts_list):
    """Cluster a vessel's alerts into incidents using a rolling time-gap threshold."""
    if not alerts_list:
        return []

    ordered_alerts = sorted(
        alerts_list,
        key=lambda alert: (alert["observed_at"], alert["id"]),
    )

    incidents = [[ordered_alerts[0]]]
    for alert in ordered_alerts[1:]:
        previous_alert = incidents[-1][-1]
        if alert["observed_at"] - previous_alert["observed_at"] <= INCIDENT_GAP:
            incidents[-1].append(alert)
        else:
            incidents.append([alert])

    return incidents


def format_zone_context(zone_context):
    """Convert zone context payloads into concise user-facing text."""
    if not zone_context:
        return None

    zones = zone_context.get("zones") if isinstance(zone_context, dict) else None
    if not zones:
        return None

    zone_names = [
        zone.get("name")
        for zone in zones
        if isinstance(zone, dict) and zone.get("name")
    ]
    if not zone_names:
        return None

    return f"zones: {', '.join(zone_names)}"


def summarize_key_events(alerts_list):
    """Build short incident timeline highlights from alerts."""
    distinct_events = []
    seen_signatures = set()

    for alert in alerts_list:
        timestamp = alert["observed_at"].strftime("%H:%M")
        alert_type = alert["alert_type"].replace("_", " ")
        details = alert["details"]

        context_parts = []
        formatted_zone_context = format_zone_context(details.get("zone_context"))
        if formatted_zone_context:
            context_parts.append(formatted_zone_context)

        explanation = alert.get("explanation")
        if explanation:
            cleaned = " ".join(str(explanation).split())
            if len(cleaned) > 100:
                cleaned = f"{cleaned[:97]}..."
            context_parts.append(cleaned)

        event_text = f"{timestamp} {alert_type}"
        if context_parts:
            event_text = f"{event_text} ({'; '.join(context_parts)})"

        signature = (alert["alert_type"], timestamp, tuple(context_parts))
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        distinct_events.append(event_text)

        if len(distinct_events) >= TIMELINE_EVENT_LIMIT:
            break

    if len(alerts_list) > len(distinct_events):
        distinct_events.append(f"+{len(alerts_list) - len(distinct_events)} more alerts")

    return distinct_events


def score_incident(alerts_list):
    """Compute anomaly and confidence scores for an incident."""
    max_severity_by_type = {}
    alert_counts = defaultdict(int)
    has_zone_context = False

    for alert in alerts_list:
        alert_type = alert["alert_type"]
        alert_counts[alert_type] += 1
        max_severity_by_type[alert_type] = max(
            max_severity_by_type.get(alert_type, 0.0),
            float(alert["severity"]),
        )
        if alert["details"].get("zone_context"):
            has_zone_context = True

    distinct_types = len(max_severity_by_type)
    alert_count = len(alerts_list)
    duration = alerts_list[-1]["observed_at"] - alerts_list[0]["observed_at"]

    base_score = sum(
        max_severity_by_type.get(alert_type, 0.0) * ALERT_WEIGHTS.get(alert_type, 0.0)
        for alert_type in ALERT_WEIGHTS
    )
    corroboration_bonus = 0.1 * max(0, distinct_types - 1)
    frequency_bonus = min(0.15, alert_count * 0.02)
    anomaly_score = min(base_score + corroboration_bonus + frequency_bonus, 1.0)
    anomaly_score = round(max(anomaly_score, 0.0), 4)

    confidence_score = 0.5
    if alert_count > 10:
        confidence_score += 0.15
    if distinct_types > 1:
        confidence_score += 0.15
    if duration > MIN_SUSTAINED_DURATION:
        confidence_score += 0.1
    if has_zone_context:
        confidence_score += 0.1
    confidence_score = round(min(confidence_score, 1.0), 4)

    return {
        "max_severity_by_type": max_severity_by_type,
        "alert_counts": dict(alert_counts),
        "base_score": round(base_score, 4),
        "corroboration_bonus": round(corroboration_bonus, 4),
        "frequency_bonus": round(frequency_bonus, 4),
        "anomaly_score": anomaly_score,
        "confidence_score": confidence_score,
        "duration": duration,
        "has_zone_context": has_zone_context,
    }


def compute_rank_score(anomaly_score, confidence_score, corroboration_bonus):
    """Compute the capped trust-oriented rank score for a case."""
    cue_linkage_bonus = 0.0
    recency_decay = 0.0
    rank_score = (
        anomaly_score
        + (confidence_score * 0.3)
        + (corroboration_bonus * 0.5)
        + cue_linkage_bonus
        + recency_decay
    )
    return round(min(rank_score, 2.0), 4)


def build_case_record(mmsi, incident_index, alerts_list, vessel_info):
    """Build a case payload and evidence rows for a single incident."""
    incident_alerts = sorted(alerts_list, key=lambda alert: (alert["observed_at"], alert["id"]))
    scores = score_incident(incident_alerts)
    if scores["anomaly_score"] < MIN_CASE_SCORE:
        return None

    dominant_type = dominant_alert_type(
        scores["max_severity_by_type"],
        scores["alert_counts"],
    )
    vessel_meta = vessel_info.get(mmsi, {})
    vessel_name = vessel_meta.get("name") or "Unknown Vessel"
    vessel_type = vessel_meta.get("type")
    incident_start = incident_alerts[0]["observed_at"]
    incident_end = incident_alerts[-1]["observed_at"]
    primary_alert = max(
        incident_alerts,
        key=lambda alert: (float(alert["severity"]), alert["observed_at"], alert["id"]),
    )
    rank_score = compute_rank_score(
        scores["anomaly_score"],
        scores["confidence_score"],
        scores["corroboration_bonus"],
    )

    title = (
        f"[{mmsi}] {vessel_name} — Incident at "
        f"{incident_start.strftime('%H:%M')} ({dominant_type})"
    )

    ordered_types = sorted(
        scores["alert_counts"],
        key=lambda alert_type: (
            -(scores["max_severity_by_type"].get(alert_type, 0.0) * ALERT_WEIGHTS.get(alert_type, 0.0)),
            -scores["alert_counts"][alert_type],
            alert_type,
        ),
    )
    type_summary = ", ".join(
        f"{scores['alert_counts'][alert_type]} {alert_type.replace('_', ' ')}"
        for alert_type in ordered_types
    )

    vessel_label = f"{vessel_name} (MMSI: {mmsi})"
    if vessel_type:
        vessel_label = f"{vessel_label}, type {vessel_type}"

    timeline_events = summarize_key_events(incident_alerts)
    summary_lines = [
        (
            f"Incident {incident_index} for vessel {vessel_label} spans "
            f"{incident_start.isoformat()} to {incident_end.isoformat()} "
            f"({scores['duration']})."
        ),
        (
            f"Observed {len(incident_alerts)} alert(s) across {len(scores['alert_counts'])} detector type(s): "
            f"{type_summary}. Dominant concern: {dominant_type.replace('_', ' ')}."
        ),
        (
            f"Anomaly score {scores['anomaly_score']:.3f} "
            f"(base {scores['base_score']:.3f} + corroboration {scores['corroboration_bonus']:.3f} "
            f"+ frequency {scores['frequency_bonus']:.3f}); "
            f"confidence score {scores['confidence_score']:.3f}."
        ),
        "Evidence timeline: " + " -> ".join(timeline_events),
    ]
    if scores["has_zone_context"]:
        summary_lines.append("Geofence context present in incident evidence.")
    summary = " ".join(summary_lines)

    evidence_rows = []
    for order_index, alert in enumerate(incident_alerts, start=1):
        evidence_rows.append(
            (
                "alert",
                alert["id"],
                Json(
                    {
                        "alert_type": alert["alert_type"],
                        "severity": alert["severity"],
                        "observed_at": alert["observed_at"].isoformat(),
                        "location": {"lon": alert["lon"], "lat": alert["lat"]},
                        "details": alert["details"],
                        "explanation": alert["explanation"],
                        "incident_index": incident_index,
                        "timeline_order": order_index,
                        "anomaly_score": scores["anomaly_score"],
                        "confidence_score": scores["confidence_score"],
                    }
                ),
                (
                    f"Incident {incident_index} evidence #{order_index}: "
                    f"{alert['alert_type']} at {alert['observed_at'].isoformat()}"
                ),
                alert["observed_at"],
                order_index,
            )
        )

    return {
        "mmsi": mmsi,
        "title": title,
        "anomaly_score": scores["anomaly_score"],
        "confidence_score": scores["confidence_score"],
        "status": "new",
        "assigned_to": None,
        "priority": priority_for_score(scores["anomaly_score"]),
        "summary": summary,
        "recommended_action": build_recommendation(
            scores["alert_counts"],
            scores["max_severity_by_type"],
        ),
        "evidence_rows": evidence_rows,
        "incident_start": incident_start,
        "incident_end": incident_end,
        "start_observed_at": incident_start,
        "end_observed_at": incident_end,
        "primary_lon": primary_alert["lon"],
        "primary_lat": primary_alert["lat"],
        "rank_score": rank_score,
        "signature": case_signature(mmsi, scores["alert_counts"].keys(), incident_start),
    }


def build_cases():
    """Build investigation cases from alerts using temporal incident clustering."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    run_id = None
    cases_created = 0
    evidence_created = 0
    alerts_processed = 0

    try:
        cur.execute(
            """
            INSERT INTO pipeline_run (run_type)
            VALUES (%s)
            RETURNING id
            """,
            ("case_build",),
        )
        run_id = cur.fetchone()[0]
        conn.commit()

        cur.execute(
            """
            SELECT
                id,
                mmsi,
                title,
                start_observed_at,
                end_observed_at,
                status,
                assigned_to
            FROM investigation_case
            """
        )
        existing_cases = cur.fetchall()

        existing_case_ids = [row[0] for row in existing_cases]
        existing_notes_by_case_id = defaultdict(list)
        existing_alert_types_by_case_id = defaultdict(set)
        if existing_case_ids:
            cur.execute(
                """
                SELECT id, case_id, author, content, created_at
                FROM analyst_note
                WHERE case_id = ANY(%s::uuid[])
                ORDER BY created_at ASC, id ASC
                """,
                (existing_case_ids,),
            )
            for note_row in cur.fetchall():
                existing_notes_by_case_id[note_row[1]].append(note_row)

            cur.execute(
                """
                SELECT case_id, data->>'alert_type' AS alert_type
                FROM case_evidence
                WHERE case_id = ANY(%s::uuid[])
                  AND data ? 'alert_type'
                """,
                (existing_case_ids,),
            )
            for case_id, alert_type in cur.fetchall():
                if alert_type:
                    existing_alert_types_by_case_id[case_id].add(alert_type)

        preserved_cases_by_signature = {}
        for row in existing_cases:
            case_id, mmsi, title, start_observed_at, end_observed_at, status, assigned_to = row
            signature = case_signature(
                mmsi,
                existing_alert_types_by_case_id.get(case_id, ()),
                start_observed_at,
            )
            preserved_cases_by_signature[signature] = {
                "status": status,
                "assigned_to": assigned_to,
                "notes": existing_notes_by_case_id.get(case_id, []),
            }

        if existing_case_ids:
            cur.execute("DELETE FROM analyst_note WHERE case_id = ANY(%s::uuid[])", (existing_case_ids,))
        cur.execute("DELETE FROM case_evidence")
        cur.execute("DELETE FROM investigation_case")
        conn.commit()

        cur.execute(
            """
            SELECT
                id,
                mmsi,
                alert_type,
                severity,
                observed_at,
                ST_X(geom) AS lon,
                ST_Y(geom) AS lat,
                details,
                explanation
            FROM alert
            ORDER BY mmsi, observed_at, id
            """
        )
        alerts = cur.fetchall()
        alerts_processed = len(alerts)
        print(f"Processing {alerts_processed} alerts...")

        vessel_alerts = defaultdict(list)
        for row in alerts:
            vessel_alerts[row[1]].append(
                {
                    "id": row[0],
                    "mmsi": row[1],
                    "alert_type": row[2],
                    "severity": float(row[3]),
                    "observed_at": row[4],
                    "lon": row[5],
                    "lat": row[6],
                    "details": normalize_details(row[7]),
                    "explanation": row[8],
                }
            )

        cur.execute("SELECT mmsi, vessel_name, vessel_type FROM vessel")
        vessel_info = {
            row[0]: {"name": row[1], "type": row[2]}
            for row in cur.fetchall()
        }

        case_records = []
        for mmsi, alerts_list in vessel_alerts.items():
            incidents = cluster_alerts_by_incident(alerts_list)
            for incident_index, incident_alerts in enumerate(incidents, start=1):
                case_record = build_case_record(
                    mmsi,
                    incident_index,
                    incident_alerts,
                    vessel_info,
                )
                if case_record is not None:
                    preserved_case = preserved_cases_by_signature.get(case_record["signature"])
                    if preserved_case is not None:
                        case_record["status"] = preserved_case["status"] or case_record["status"]
                        case_record["assigned_to"] = preserved_case["assigned_to"]
                    case_records.append(case_record)

        case_records.sort(
            key=lambda record: (
                -record["anomaly_score"],
                -record["confidence_score"],
                str(record["mmsi"]),
                record["incident_start"],
            )
        )

        for case_record in case_records:
            cur.execute(
                """
                INSERT INTO investigation_case (
                    title,
                    mmsi,
                    anomaly_score,
                    confidence_score,
                    status,
                    priority,
                    summary,
                    recommended_action,
                    primary_geom,
                    start_observed_at,
                    end_observed_at,
                    rank_score,
                    assigned_to,
                    run_id
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                RETURNING id
                """,
                (
                    case_record["title"],
                    case_record["mmsi"],
                    case_record["anomaly_score"],
                    case_record["confidence_score"],
                    case_record["status"],
                    case_record["priority"],
                    case_record["summary"],
                    case_record["recommended_action"],
                    case_record["primary_lon"],
                    case_record["primary_lat"],
                    case_record["start_observed_at"],
                    case_record["end_observed_at"],
                    case_record["rank_score"],
                    case_record["assigned_to"],
                    run_id,
                ),
            )
            case_id = cur.fetchone()[0]
            cases_created += 1

            preserved_case = preserved_cases_by_signature.get(case_record["signature"])
            if preserved_case and preserved_case["notes"]:
                execute_values(
                    cur,
                    """
                    INSERT INTO analyst_note (
                        case_id,
                        author,
                        content,
                        created_at
                    )
                    VALUES %s
                    """,
                    [
                        (
                            case_id,
                            author,
                            content,
                            created_at,
                        )
                        for (_, _, author, content, created_at) in preserved_case["notes"]
                    ],
                )

            if case_record["evidence_rows"]:
                execute_values(
                    cur,
                    """
                    INSERT INTO case_evidence (
                        case_id,
                        evidence_type,
                        evidence_ref,
                        data,
                        provenance,
                        observed_at,
                        timeline_order
                    )
                    VALUES %s
                    """,
                    [
                        (
                            case_id,
                            evidence_type,
                            evidence_ref,
                            data,
                            provenance,
                            observed_at,
                            timeline_order,
                        )
                        for (
                            evidence_type,
                            evidence_ref,
                            data,
                            provenance,
                            observed_at,
                            timeline_order,
                        ) in case_record["evidence_rows"]
                    ],
                )
                evidence_created += len(case_record["evidence_rows"])

        conn.commit()

        cur.execute(
            """
            UPDATE pipeline_run
            SET status = %s,
                finished_at = NOW(),
                stats = %s
            WHERE id = %s
            """,
            (
                "completed",
                Json(
                    {
                        "alerts_processed": alerts_processed,
                        "cases_created": cases_created,
                        "evidence_created": evidence_created,
                    }
                ),
                run_id,
            ),
        )
        conn.commit()

        cur.execute(
            """
            SELECT
                title,
                anomaly_score,
                priority,
                confidence_score,
                evidence_count
            FROM (
                SELECT
                    title,
                    anomaly_score,
                    priority,
                    confidence_score,
                    (
                        SELECT COUNT(*)
                        FROM case_evidence
                        WHERE case_id = investigation_case.id
                    ) AS evidence_count,
                    id
                FROM investigation_case
            ) ranked_cases
            ORDER BY anomaly_score DESC, id ASC
            LIMIT 10
            """
        )
        top_cases = cur.fetchall()

        print(f"\nCreated {cases_created} cases with {evidence_created} evidence links.")
        print("\nTop 10 cases:")
        print("-" * 100)
        for row in top_cases:
            title, anomaly_score, priority, confidence_score, evidence_count = row
            score_text = (
                f"Anomaly: {anomaly_score:.3f} | Confidence: {confidence_score:.3f}"
            )
            print(
                f"  {score_text} | Priority: {priority} | "
                f"Evidence: {evidence_count} | {title}"
            )
    except Exception:
        conn.rollback()
        if run_id is not None:
            try:
                cur.execute(
                    """
                    UPDATE pipeline_run
                    SET status = %s,
                        finished_at = NOW(),
                        stats = %s
                    WHERE id = %s
                    """,
                    (
                        "failed",
                        Json(
                            {
                                "alerts_processed": alerts_processed,
                                "cases_created": cases_created,
                                "evidence_created": evidence_created,
                            }
                        ),
                        run_id,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    build_cases()
