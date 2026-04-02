#!/usr/bin/env python3
"""Seed three synthetic Duqm-centered investigation scenarios into the Cue2Case v3 database."""

import math
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import psycopg2
from psycopg2.extras import Json, RealDictCursor

DEFAULT_DATABASE_URL = "postgresql://cue2case:cue2case_dev@localhost:5433/cue2case"
BASE_TIME = datetime(2024, 1, 15, 6, 0, tzinfo=timezone.utc)
TARGET_MMSIS = ("470001001", "636092001", "351001001")

Point = Tuple[float, float]


def point_wkt(lon: float, lat: float) -> str:
    return f"POINT({lon:.6f} {lat:.6f})"


def linestring_wkt(points: Sequence[Point]) -> str:
    if len(points) < 2:
        raise ValueError("track segment requires at least two points")
    return "LINESTRING({})".format(
        ", ".join(f"{lon:.6f} {lat:.6f}" for lon, lat in points)
    )


def interpolate_points(start: Point, end: Point, count: int) -> List[Point]:
    if count < 2:
        raise ValueError("interpolate_points requires count >= 2")
    return [
        (
            start[0] + (end[0] - start[0]) * index / (count - 1),
            start[1] + (end[1] - start[1]) * index / (count - 1),
        )
        for index in range(count)
    ]


def loiter_points(center: Point, count: int, lon_radius: float, lat_radius: float) -> List[Point]:
    points: List[Point] = []
    for index in range(count):
        angle = (2.0 * math.pi * index) / count
        wobble = 1.0 + (0.08 if index % 2 == 0 else -0.05)
        lon = center[0] + math.cos(angle) * lon_radius * wobble
        lat = center[1] + math.sin(angle) * lat_radius * wobble
        points.append((round(lon, 6), round(lat, 6)))
    return points


def erratic_points(start: Point, offsets: Sequence[Point]) -> List[Point]:
    return [(round(start[0] + dx, 6), round(start[1] + dy, 6)) for dx, dy in offsets]


def fetch_zone_context(cur: Any, lon: float, lat: float) -> Dict[str, Any]:
    cur.execute(
        """
        SELECT p.profile_key
        FROM port_profile p
        WHERE p.profile_key = 'duqm'
        LIMIT 1
        """
    )
    profile = cur.fetchone()
    if not profile:
        raise RuntimeError("Duqm port profile not found. Seed port context first.")

    point_params = (lon, lat)

    cur.execute(
        """
        SELECT
            z.name,
            z.zone_type,
            z.label_en,
            z.label_ar,
            z.sensitivity,
            z.metadata
        FROM operational_zone z
        JOIN port_profile p ON p.id = z.profile_id
        WHERE p.profile_key = 'duqm'
          AND ST_Contains(z.geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
        ORDER BY z.sensitivity DESC, z.name ASC
        """,
        point_params,
    )
    zones = [dict(row) for row in cur.fetchall()]

    cur.execute(
        """
        SELECT
            c.name,
            c.expected_heading_min,
            c.expected_heading_max,
            c.label_en,
            c.label_ar,
            c.metadata
        FROM approach_corridor c
        JOIN port_profile p ON p.id = c.profile_id
        WHERE p.profile_key = 'duqm'
          AND ST_Contains(c.geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
        ORDER BY c.name ASC
        """,
        point_params,
    )
    corridors = [dict(row) for row in cur.fetchall()]

    cur.execute(
        """
        SELECT
            a.name,
            a.area_type,
            a.label_en,
            a.label_ar,
            a.sensitivity,
            a.metadata
        FROM critical_area a
        JOIN port_profile p ON p.id = a.profile_id
        WHERE p.profile_key = 'duqm'
          AND ST_Contains(a.geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
        ORDER BY a.sensitivity DESC, a.name ASC
        """,
        point_params,
    )
    critical_areas = [dict(row) for row in cur.fetchall()]

    max_sensitivity = 0
    if zones:
        max_sensitivity = max(max_sensitivity, max(int(item["sensitivity"] or 0) for item in zones))
    if critical_areas:
        max_sensitivity = max(max_sensitivity, max(int(item["sensitivity"] or 0) for item in critical_areas))

    return {
        "profile_key": "duqm",
        "point": {"lon": lon, "lat": lat},
        "zones": zones,
        "corridors": corridors,
        "critical_areas": critical_areas,
        "max_sensitivity": max_sensitivity,
        "criticality": round(max_sensitivity / 5.0, 4),
    }


def cleanup_demo_data(cur: Any) -> None:
    cur.execute(
        "SELECT id FROM investigation_case WHERE mmsi = ANY(%s)",
        (list(TARGET_MMSIS),),
    )
    case_ids = [str(row["id"]) for row in cur.fetchall()]

    if case_ids:
        cur.execute("DELETE FROM analyst_note WHERE case_id = ANY(%s::uuid[])", (case_ids,))
        cur.execute("DELETE FROM case_evidence WHERE case_id = ANY(%s::uuid[])", (case_ids,))
        cur.execute("DELETE FROM external_cue WHERE case_id = ANY(%s::uuid[])", (case_ids,))
        cur.execute(
            "DELETE FROM audit_log WHERE entity_type = 'case' AND entity_id = ANY(%s::uuid[])",
            (case_ids,),
        )
        cur.execute("DELETE FROM investigation_case WHERE id = ANY(%s::uuid[])", (case_ids,))

    cur.execute("DELETE FROM alert WHERE mmsi = ANY(%s)", (list(TARGET_MMSIS),))
    cur.execute("DELETE FROM track_segment WHERE mmsi = ANY(%s)", (list(TARGET_MMSIS),))
    cur.execute("DELETE FROM ais_position WHERE mmsi = ANY(%s)", (list(TARGET_MMSIS),))
    cur.execute("DELETE FROM vessel WHERE mmsi = ANY(%s)", (list(TARGET_MMSIS),))


def insert_vessel(cur: Any, vessel: Dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO vessel (mmsi, vessel_name, vessel_type, length, width)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (mmsi) DO NOTHING
        """,
        (
            vessel["mmsi"],
            vessel["vessel_name"],
            vessel["vessel_type"],
            vessel["length"],
            vessel["width"],
        ),
    )


def insert_positions(cur: Any, mmsi: str, positions: Sequence[Dict[str, Any]]) -> None:
    for position in positions:
        lon, lat = position["point"]
        cur.execute(
            """
            INSERT INTO ais_position (mmsi, observed_at, geom, sog, cog, heading, nav_status)
            VALUES (
                %s,
                %s,
                ST_GeomFromText(%s, 4326),
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                mmsi,
                position["observed_at"],
                point_wkt(lon, lat),
                position["sog"],
                position["cog"],
                position["heading"],
                position["nav_status"],
            ),
        )


def insert_track_segment(cur: Any, mmsi: str, positions: Sequence[Dict[str, Any]]) -> str:
    points = [position["point"] for position in positions]
    avg_sog = round(sum(float(position["sog"]) for position in positions) / len(positions), 3)
    max_sog = round(max(float(position["sog"]) for position in positions), 3)
    cur.execute(
        """
        INSERT INTO track_segment (mmsi, start_time, end_time, geom, point_count, avg_sog, max_sog)
        VALUES (%s, %s, %s, ST_GeomFromText(%s, 4326), %s, %s, %s)
        RETURNING id
        """,
        (
            mmsi,
            positions[0]["observed_at"],
            positions[-1]["observed_at"],
            linestring_wkt(points),
            len(points),
            avg_sog,
            max_sog,
        ),
    )
    return str(cur.fetchone()["id"])


def insert_alerts(cur: Any, mmsi: str, alerts: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    inserted: List[Dict[str, Any]] = []
    for alert in alerts:
        lon, lat = alert["point"]
        cur.execute(
            """
            INSERT INTO alert (mmsi, alert_type, severity, observed_at, geom, details, explanation, run_id)
            VALUES (%s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s, %s, NULL)
            RETURNING id, alert_type, observed_at
            """,
            (
                mmsi,
                alert["alert_type"],
                alert["severity"],
                alert["observed_at"],
                point_wkt(lon, lat),
                Json(alert["details"]),
                alert["explanation"],
            ),
        )
        row = dict(cur.fetchone())
        row["severity"] = alert["severity"]
        inserted.append(row)
    return inserted


def insert_case(cur: Any, case: Dict[str, Any], mmsi: str, primary_point: Point, start_at: datetime, end_at: datetime) -> str:
    zone_context = fetch_zone_context(cur, primary_point[0], primary_point[1])
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
            zone_context,
            rank_score,
            primary_geom,
            start_observed_at,
            end_observed_at,
            run_id
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, ST_GeomFromText(%s, 4326), %s, %s, NULL
        )
        RETURNING id
        """,
        (
            case["title"],
            mmsi,
            case["anomaly_score"],
            case["confidence_score"],
            case.get("status", "new"),
            case["priority"],
            case["summary"],
            case["recommended_action"],
            Json(zone_context),
            case["rank_score"],
            point_wkt(primary_point[0], primary_point[1]),
            start_at,
            end_at,
        ),
    )
    return str(cur.fetchone()["id"])


def insert_external_cue(cur: Any, case_id: str, cue: Dict[str, Any]) -> str:
    lon, lat = cue["point"]
    cur.execute(
        """
        INSERT INTO external_cue (source, cue_type, observed_at, geom, data, case_id)
        VALUES (%s, %s, %s, ST_GeomFromText(%s, 4326), %s, %s)
        RETURNING id
        """,
        (
            cue["source"],
            cue["cue_type"],
            cue["observed_at"],
            point_wkt(lon, lat),
            Json(cue["data"]),
            case_id,
        ),
    )
    return str(cur.fetchone()["id"])


def insert_case_evidence(
    cur: Any,
    case_id: str,
    alert_rows: Sequence[Dict[str, Any]],
    cue_id: str,
    cue: Dict[str, Any],
    track_segment_id: str,
) -> None:
    timeline_order = 1
    cur.execute(
        """
        INSERT INTO case_evidence (case_id, evidence_type, evidence_ref, data, provenance, observed_at, timeline_order)
        VALUES (%s, 'track', %s, %s, %s, %s, %s)
        """,
        (
            case_id,
            track_segment_id,
            Json({"kind": "track_segment", "point_count": cue.get("track_point_count")}),
            "synthetic Duqm scenario seeder",
            cue["track_observed_at"],
            timeline_order,
        ),
    )
    timeline_order += 1

    for alert in sorted(alert_rows, key=lambda item: item["observed_at"]):
        cur.execute(
            """
            INSERT INTO case_evidence (case_id, evidence_type, evidence_ref, data, provenance, observed_at, timeline_order)
            VALUES (%s, 'alert', %s, %s, %s, %s, %s)
            """,
            (
                case_id,
                alert["id"],
                Json({"alert_type": alert["alert_type"], "severity": alert["severity"]}),
                "detector output (demo seeded)",
                alert["observed_at"],
                timeline_order,
            ),
        )
        timeline_order += 1

    cur.execute(
        """
        INSERT INTO case_evidence (case_id, evidence_type, evidence_ref, data, provenance, observed_at, timeline_order)
        VALUES (%s, 'external_cue', %s, %s, %s, %s, %s)
        """,
        (
            case_id,
            cue_id,
            Json(cue["data"]),
            cue["source"],
            cue["observed_at"],
            timeline_order,
        ),
    )


def insert_analyst_note(cur: Any, case_id: str, author: str, content: str) -> None:
    cur.execute(
        """
        INSERT INTO analyst_note (case_id, author, content)
        VALUES (%s, %s, %s)
        """,
        (case_id, author, content),
    )


def build_scenarios() -> List[Dict[str, Any]]:
    scenario_1_points = interpolate_points((57.75, 21.58), (57.6932, 21.6568), 20)
    scenario_1_times = [BASE_TIME + timedelta(minutes=6 * index) for index in range(20)]
    scenario_1_positions: List[Dict[str, Any]] = []
    for index, point in enumerate(scenario_1_points):
        scenario_1_positions.append(
            {
                "point": point,
                "observed_at": scenario_1_times[index],
                "sog": round(13.8 - (index * 0.18), 2),
                "cog": 322.0,
                "heading": 321.0 + (0.2 if index % 3 == 0 else -0.2),
                "nav_status": 0,
            }
        )
    reappear_start = scenario_1_times[-1] + timedelta(minutes=45)
    for offset, point in enumerate([(57.6944, 21.6574), (57.6951, 21.6582), (57.6958, 21.6589)]):
        scenario_1_positions.append(
            {
                "point": point,
                "observed_at": reappear_start + timedelta(minutes=5 * offset),
                "sog": round(5.2 - (offset * 0.7), 2),
                "cog": 334.0,
                "heading": 336.0,
                "nav_status": 0,
            }
        )

    scenario_2_points = loiter_points((57.72, 21.60), 15, 0.0065, 0.0048)
    scenario_2_positions = [
        {
            "point": point,
            "observed_at": BASE_TIME + timedelta(hours=4, minutes=10 * index),
            "sog": round(4.6 + (0.5 if index % 5 == 0 else -0.2), 2),
            "cog": round((index * 24.0) % 360.0, 1),
            "heading": round(((index * 24.0) + 12.0) % 360.0, 1),
            "nav_status": 1,
        }
        for index, point in enumerate(scenario_2_points)
    ]

    scenario_3_offsets = [
        (-0.018, -0.010), (-0.015, -0.008), (-0.012, -0.005), (-0.009, -0.001),
        (-0.006, 0.002), (-0.003, 0.004), (0.000, 0.006), (0.004, 0.008),
        (0.008, 0.009), (0.012, 0.007), (0.010, 0.003), (0.006, 0.000),
        (0.002, -0.002), (-0.002, -0.001), (0.003, 0.003), (0.007, 0.006),
        (0.011, 0.010), (0.015, 0.011), (0.017, 0.008), (0.013, 0.004),
        (0.009, 0.001), (0.005, 0.003), (0.001, 0.007), (-0.002, 0.010),
        (0.002, 0.012),
    ]
    scenario_3_points = erratic_points((57.688, 21.635), scenario_3_offsets)
    scenario_3_headings = [308, 312, 319, 326, 341, 8, 26, 44, 63, 71, 128, 154, 201, 223, 184, 139, 91, 57, 31, 346, 318, 302, 18, 55, 102]
    scenario_3_cogs = [304, 309, 317, 323, 336, 5, 22, 41, 59, 68, 121, 149, 196, 217, 180, 135, 87, 52, 27, 342, 314, 298, 14, 51, 98]
    scenario_3_positions = [
        {
            "point": point,
            "observed_at": BASE_TIME + timedelta(hours=7, minutes=5 * index),
            "sog": round(8.7 + ((index % 4) * 0.6) - (0.9 if index % 6 == 0 else 0.0), 2),
            "cog": float(scenario_3_cogs[index]),
            "heading": float(scenario_3_headings[index]),
            "nav_status": 0,
        }
        for index, point in enumerate(scenario_3_points)
    ]

    return [
        {
            "name": "Scenario 1",
            "vessel": {
                "mmsi": "470001001",
                "vessel_name": "SHADOW TRADER",
                "vessel_type": 70,
                "length": 185,
                "width": 28,
            },
            "positions": scenario_1_positions,
            "alerts": [
                {
                    "alert_type": "ais_silence",
                    "severity": 0.85,
                    "observed_at": scenario_1_positions[-1]["observed_at"],
                    "point": (57.6948, 21.6579),
                    "details": {"gap_minutes": 45, "last_seen_context": "approach corridor", "reappeared_near": "government berth"},
                    "explanation": "Vessel stopped transmitting AIS for 45 minutes while inbound, then reappeared adjacent to the government berth.",
                },
                {
                    "alert_type": "abnormal_approach",
                    "severity": 0.72,
                    "observed_at": scenario_1_positions[-2]["observed_at"],
                    "point": scenario_1_positions[-2]["point"],
                    "details": {"corridor": "main_approach", "destination": "government_berth", "note": "Approach tightened toward a sensitive berth before AIS gap."},
                    "explanation": "Approach profile placed the vessel on an unusually direct path toward the government berth.",
                },
            ],
            "case": {
                "title": "AIS silence near government berth — SHADOW TRADER",
                "anomaly_score": 0.82,
                "confidence_score": 0.88,
                "rank_score": 1.44,
                "priority": 4,
                "summary": "Cargo vessel approached Duqm from the southeast, went dark for 45 minutes, then reappeared near the government berth.",
                "recommended_action": "Escalate to VTS and harbor security for berth-side verification and sensor cross-checks.",
            },
            "cue": {
                "source": "SIGINT Demo Sensor",
                "cue_type": "rf_detection",
                "observed_at": scenario_1_positions[-1]["observed_at"] + timedelta(minutes=3),
                "point": (57.6952, 21.6585),
                "data": {"subtype": "rf_detection", "band": "VHF", "signal_strength_dbm": -54.2, "note": "RF emission detected near government berth during AIS silence window."},
            },
            "primary_point": (57.6952, 21.6585),
        },
        {
            "name": "Scenario 2",
            "vessel": {
                "mmsi": "636092001",
                "vessel_name": "PACIFIC ENDURANCE",
                "vessel_type": 80,
                "length": 245,
                "width": 42,
            },
            "positions": scenario_2_positions,
            "alerts": [
                {
                    "alert_type": "loitering",
                    "severity": 0.55,
                    "observed_at": scenario_2_positions[10]["observed_at"],
                    "point": scenario_2_positions[10]["point"],
                    "details": {"zone": "outer_anchorage", "duration_minutes": 140, "behavior": "slow circular holding pattern"},
                    "explanation": "Tanker remained in a slow circular holding pattern near the approach corridor instead of entering port directly.",
                }
            ],
            "case": {
                "title": "Loitering near approach corridor — PACIFIC ENDURANCE",
                "anomaly_score": 0.48,
                "confidence_score": 0.65,
                "rank_score": 0.73,
                "priority": 2,
                "summary": "Tanker loitered in the outer anchorage, but a public marine weather advisory provides plausible mitigation context.",
                "recommended_action": "Monitor only; defer escalation unless loitering persists after weather conditions improve.",
            },
            "cue": {
                "source": "Open-Meteo Marine — public source",
                "cue_type": "other",
                "observed_at": scenario_2_positions[9]["observed_at"] - timedelta(minutes=5),
                "point": (57.7200, 21.6000),
                "data": {"subtype": "marine_weather", "advisory": "tropical storm advisory", "sea_state": "rough", "mitigating_context": True},
            },
            "primary_point": (57.7200, 21.6000),
        },
        {
            "name": "Scenario 3",
            "vessel": {
                "mmsi": "351001001",
                "vessel_name": "NEPTUNE GRACE",
                "vessel_type": 70,
                "length": 165,
                "width": 25,
            },
            "positions": scenario_3_positions,
            "alerts": [
                {
                    "alert_type": "kinematic_anomaly",
                    "severity": 0.78,
                    "observed_at": scenario_3_positions[16]["observed_at"],
                    "point": scenario_3_positions[16]["point"],
                    "details": {"zone": "vts_zone", "erratic_turns": 7, "heading_spread_deg": 250},
                    "explanation": "Cargo vessel made repeated abrupt heading shifts inside the VTS-monitored zone.",
                },
                {
                    "alert_type": "identity_anomaly",
                    "severity": 0.90,
                    "observed_at": scenario_3_positions[18]["observed_at"],
                    "point": scenario_3_positions[18]["point"],
                    "details": {"watchlist_context": "name/MMSI mismatch review", "registry_flag": "Panama", "risk_marker": "watchlist-adjacent identity inconsistency"},
                    "explanation": "Identity metadata and movement behavior jointly indicate elevated risk requiring compliance review.",
                },
            ],
            "case": {
                "title": "Identity anomaly + erratic kinematics — NEPTUNE GRACE",
                "anomaly_score": 0.91,
                "confidence_score": 0.92,
                "rank_score": 1.67,
                "priority": 5,
                "summary": "Watchlist-linked cargo vessel showed erratic kinematics near the VTS zone with identity anomalies inconsistent with expected traffic behavior.",
                "recommended_action": "Escalate immediately to compliance and port security; validate registry, cargo declarations, and movement intent.",
            },
            "cue": {
                "source": "OFAC SDN List — public source",
                "cue_type": "other",
                "observed_at": scenario_3_positions[18]["observed_at"] + timedelta(minutes=2),
                "point": scenario_3_positions[18]["point"],
                "data": {"subtype": "watchlist_hit", "watchlist_hit": True, "list": "OFAC SDN", "confidence": "high"},
            },
            "analyst_note": {
                "author": "system",
                "content": "Flagged for escalation — OFAC match requires compliance review",
            },
            "primary_point": scenario_3_positions[18]["point"],
        },
    ]


def main() -> None:
    database_url = os.getenv("DATABASE_URL_SYNC", DEFAULT_DATABASE_URL)
    scenarios = build_scenarios()
    seeded = Counter()

    with psycopg2.connect(database_url, cursor_factory=RealDictCursor) as conn:
        with conn.cursor() as cur:
            cleanup_demo_data(cur)

            for scenario in scenarios:
                vessel = scenario["vessel"]
                positions = scenario["positions"]
                cue = dict(scenario["cue"])
                cue["track_observed_at"] = positions[-1]["observed_at"]
                cue["track_point_count"] = len(positions)

                insert_vessel(cur, vessel)
                seeded["vessels"] += 1

                insert_positions(cur, vessel["mmsi"], positions)
                seeded["ais_positions"] += len(positions)

                track_segment_id = insert_track_segment(cur, vessel["mmsi"], positions)
                seeded["track_segments"] += 1

                alert_rows = insert_alerts(cur, vessel["mmsi"], scenario["alerts"])
                seeded["alerts"] += len(alert_rows)

                case_id = insert_case(
                    cur,
                    scenario["case"],
                    vessel["mmsi"],
                    scenario["primary_point"],
                    positions[0]["observed_at"],
                    positions[-1]["observed_at"],
                )
                seeded["cases"] += 1

                cue_id = insert_external_cue(cur, case_id, cue)
                seeded["external_cues"] += 1

                insert_case_evidence(cur, case_id, alert_rows, cue_id, cue, track_segment_id)
                seeded["case_evidence"] += len(alert_rows) + 2

                analyst_note = scenario.get("analyst_note")
                if analyst_note:
                    insert_analyst_note(cur, case_id, analyst_note["author"], analyst_note["content"])
                    seeded["analyst_notes"] += 1

        conn.commit()

    print("Seeded Duqm synthetic investigation scenarios.")
    print(f"Database URL: {database_url}")
    print(f"Vessels: {seeded['vessels']}")
    print(f"AIS positions: {seeded['ais_positions']}")
    print(f"Track segments: {seeded['track_segments']}")
    print(f"Alerts: {seeded['alerts']}")
    print(f"Investigation cases: {seeded['cases']}")
    print(f"External cues: {seeded['external_cues']}")
    print(f"Case evidence rows: {seeded['case_evidence']}")
    print(f"Analyst notes: {seeded['analyst_notes']}")
    print("Seeded MMSIs: 470001001, 636092001, 351001001")


if __name__ == "__main__":
    main()
