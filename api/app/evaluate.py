"""Evaluation report script for demo-friendly Cue2Case system metrics."""

import os

import psycopg2


def resolve_database_url():
    """Resolve a psycopg2-compatible database URL for host or container execution."""
    for env_var in ("DATABASE_URL_SYNC", "DATABASE_URL", "DATABASE_URL_ASYNC"):
        value = os.environ.get(env_var)
        if value:
            return value.replace("postgresql+asyncpg://", "postgresql://")

    # Host fallback first; container-safe override via env vars above is preferred.
    return "postgresql://cue2case:cue2case_dev@localhost:5433/cue2case"


DATABASE_URL = resolve_database_url()


def fetch_scalar(cur, query, params=None):
    """Execute a query and return the first column from the first row."""
    cur.execute(query, params or [])
    row = cur.fetchone()
    return row[0] if row else None


def percentage(part, total):
    """Return a percentage string with one decimal place."""
    if not total:
        return "0.0%"
    return f"{(part / total) * 100:.1f}%"


def print_section(title):
    """Print a report section heading."""
    print(f"\n{title}")
    print("-" * len(title))


def print_key_value(label, value):
    """Print a left-aligned label/value line."""
    print(f"{label:<28} {value}")


def run_evaluation():
    """Connect to Postgres and print a compact evaluation report."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    try:
        print("Cue2Case Evaluation Report")
        print("==========================")

        print_section("1) Dataset summary")
        dataset_counts = [
            ("vessel count", "SELECT COUNT(*) FROM vessel"),
            ("AIS position count", "SELECT COUNT(*) FROM ais_position"),
            ("track segment count", "SELECT COUNT(*) FROM track_segment"),
            ("alert count", "SELECT COUNT(*) FROM alert"),
            ("case count", "SELECT COUNT(*) FROM investigation_case"),
            ("external cue count", "SELECT COUNT(*) FROM external_cue"),
        ]
        for label, query in dataset_counts:
            print_key_value(label, fetch_scalar(cur, query))

        print_section("2) Alert distribution")
        cur.execute(
            """
            SELECT alert_type, COUNT(*) AS count
            FROM alert
            GROUP BY alert_type
            ORDER BY count DESC, alert_type ASC
            """
        )
        alert_rows = cur.fetchall()
        if not alert_rows:
            print("No alerts found.")
        else:
            for alert_type, count in alert_rows:
                print_key_value(alert_type, count)

        print_section("3) Case distribution")
        cur.execute(
            """
            SELECT priority, COUNT(*) AS count
            FROM investigation_case
            GROUP BY priority
            ORDER BY priority DESC
            """
        )
        priority_rows = cur.fetchall()
        if not priority_rows:
            print("No cases found.")
        else:
            print("By priority:")
            for priority, count in priority_rows:
                print_key_value(f"priority {priority}", count)

        avg_anomaly_score = fetch_scalar(
            cur,
            "SELECT ROUND(COALESCE(AVG(anomaly_score), 0)::numeric, 4) FROM investigation_case",
        )
        max_anomaly_score = fetch_scalar(
            cur,
            "SELECT ROUND(COALESCE(MAX(anomaly_score), 0)::numeric, 4) FROM investigation_case",
        )
        print_key_value("avg anomaly_score", avg_anomaly_score)
        print_key_value("max anomaly_score", max_anomaly_score)

        cur.execute(
            """
            SELECT
                ic.title,
                ic.anomaly_score,
                COUNT(ce.id) AS evidence_count
            FROM investigation_case ic
            LEFT JOIN case_evidence ce ON ce.case_id = ic.id
            GROUP BY ic.id, ic.title, ic.anomaly_score
            ORDER BY ic.anomaly_score DESC, ic.title ASC, ic.id ASC
            LIMIT 10
            """
        )
        top_case_rows = cur.fetchall()
        print("Top 10 cases by anomaly_score:")
        if not top_case_rows:
            print("  No cases found.")
        else:
            for index, (title, anomaly_score, evidence_count) in enumerate(top_case_rows, start=1):
                print(
                    f"  {index:>2}. {anomaly_score:.4f} | evidence={evidence_count} | {title}"
                )

        print_section("4) Cue coverage")
        cur.execute(
            """
            SELECT cue_type, COUNT(*) AS count
            FROM external_cue
            GROUP BY cue_type
            ORDER BY count DESC, cue_type ASC
            """
        )
        cue_type_rows = cur.fetchall()
        if not cue_type_rows:
            print("No external cues found.")
        else:
            print("By cue_type:")
            for cue_type, count in cue_type_rows:
                print_key_value(cue_type, count)

        linked_cues = fetch_scalar(
            cur,
            "SELECT COUNT(*) FROM external_cue WHERE case_id IS NOT NULL",
        )
        unlinked_cues = fetch_scalar(
            cur,
            "SELECT COUNT(*) FROM external_cue WHERE case_id IS NULL",
        )
        print_key_value("linked cues", linked_cues)
        print_key_value("unlinked cues", unlinked_cues)

        print_section("5) Explainability coverage")
        total_alerts = fetch_scalar(cur, "SELECT COUNT(*) FROM alert") or 0
        explainability_row_query = """
            SELECT
                COUNT(*) FILTER (
                    WHERE details ? 'reasons_suspicious'
                      AND jsonb_typeof(details->'reasons_suspicious') = 'array'
                      AND jsonb_array_length(details->'reasons_suspicious') > 0
                ) AS suspicious_count,
                COUNT(*) FILTER (
                    WHERE details ? 'reasons_benign'
                      AND jsonb_typeof(details->'reasons_benign') = 'array'
                      AND jsonb_array_length(details->'reasons_benign') > 0
                ) AS benign_count,
                COUNT(*) FILTER (
                    WHERE NULLIF(BTRIM(explanation), '') IS NOT NULL
                ) AS explanation_count
            FROM alert
        """
        cur.execute(explainability_row_query)
        suspicious_count, benign_count, explanation_count = cur.fetchone()
        print_key_value(
            "alerts with suspicious reasons",
            f"{suspicious_count}/{total_alerts} ({percentage(suspicious_count, total_alerts)})",
        )
        print_key_value(
            "alerts with benign reasons",
            f"{benign_count}/{total_alerts} ({percentage(benign_count, total_alerts)})",
        )
        print_key_value(
            "alerts with explanation",
            f"{explanation_count}/{total_alerts} ({percentage(explanation_count, total_alerts)})",
        )

        print_section("6) Geofence context coverage")
        geofence_context_count = fetch_scalar(
            cur,
            """
            SELECT COUNT(*)
            FROM alert
            WHERE (
                details ? 'zone_context'
                AND COALESCE(NULLIF(BTRIM(details->>'zone_context'), ''), '') <> ''
            )
            OR (
                details ? 'zones_before'
                AND jsonb_typeof(details->'zones_before') = 'array'
                AND jsonb_array_length(details->'zones_before') > 0
            )
            OR (
                details ? 'zones_after'
                AND jsonb_typeof(details->'zones_after') = 'array'
                AND jsonb_array_length(details->'zones_after') > 0
            )
            """,
        )
        print_key_value(
            "alerts with zone context",
            f"{geofence_context_count}/{total_alerts} ({percentage(geofence_context_count, total_alerts)})",
        )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    run_evaluation()
