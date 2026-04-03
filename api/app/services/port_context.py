"""Port context service.

Provides zone/corridor/critical-area lookup for detectors and API.
Replaces hardcoded heading assumptions with profile-driven logic.
"""

import json
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from api.app.db import get_database_url

DATABASE_URL = get_database_url()


def _normalize_heading(heading: float) -> float:
    return float(heading) % 360.0


def _heading_in_range(heading: float, minimum: float, maximum: float) -> bool:
    heading = _normalize_heading(heading)
    minimum = _normalize_heading(minimum)
    maximum = _normalize_heading(maximum)
    if minimum <= maximum:
        return minimum <= heading <= maximum
    return heading >= minimum or heading <= maximum


def _heading_span(minimum: float, maximum: float) -> float:
    minimum = _normalize_heading(minimum)
    maximum = _normalize_heading(maximum)
    if minimum <= maximum:
        return maximum - minimum
    return (360.0 - minimum) + maximum


def _decode_geojson(value: Any) -> Any:
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _normalize_record(row: Dict[str, Any], geometry_field: str = "geometry") -> Dict[str, Any]:
    item = dict(row)
    if geometry_field in item:
        item[geometry_field] = _decode_geojson(item[geometry_field])
    return item


def get_active_profile(profile_key: str = "duqm") -> Optional[Dict[str, Any]]:
    """Get port profile with all zones, corridors, and critical areas."""
    with psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    p.id,
                    p.profile_key,
                    p.name,
                    p.label_en,
                    p.label_ar,
                    ST_AsGeoJSON(p.center_geom) AS center_geometry,
                    p.metadata,
                    p.created_at
                FROM port_profile p
                WHERE p.profile_key = %s
                LIMIT 1
                """,
                (profile_key,),
            )
            profile_row = cur.fetchone()
            if not profile_row:
                return None

            profile = dict(profile_row)
            profile_id = profile.pop("id")
            profile["center_geometry"] = _decode_geojson(profile.get("center_geometry"))

            cur.execute(
                """
                SELECT
                    z.id,
                    z.name,
                    z.zone_type,
                    z.label_en,
                    z.label_ar,
                    z.sensitivity,
                    z.metadata,
                    z.created_at,
                    ST_AsGeoJSON(z.geom) AS geometry
                FROM operational_zone z
                WHERE z.profile_id = %s
                ORDER BY z.sensitivity DESC, z.name ASC
                """,
                (profile_id,),
            )
            profile["zones"] = [_normalize_record(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                    c.id,
                    c.name,
                    c.expected_heading_min,
                    c.expected_heading_max,
                    c.label_en,
                    c.label_ar,
                    c.metadata,
                    c.created_at,
                    ST_AsGeoJSON(c.geom) AS geometry
                FROM approach_corridor c
                WHERE c.profile_id = %s
                ORDER BY c.name ASC
                """,
                (profile_id,),
            )
            profile["corridors"] = [_normalize_record(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                    a.id,
                    a.name,
                    a.area_type,
                    a.sensitivity,
                    a.label_en,
                    a.label_ar,
                    a.metadata,
                    a.created_at,
                    ST_AsGeoJSON(a.geom) AS geometry
                FROM critical_area a
                WHERE a.profile_id = %s
                ORDER BY a.sensitivity DESC, a.name ASC
                """,
                (profile_id,),
            )
            profile["critical_areas"] = [_normalize_record(row) for row in cur.fetchall()]

            return profile


def get_zones_for_point(lon: float, lat: float, profile_key: str = "duqm") -> List[Dict[str, Any]]:
    """Find which operational zones contain the given point."""
    with psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    z.id,
                    z.name,
                    z.zone_type,
                    z.label_en,
                    z.label_ar,
                    z.sensitivity,
                    z.metadata,
                    z.created_at,
                    ST_AsGeoJSON(z.geom) AS geometry
                FROM operational_zone z
                JOIN port_profile p ON p.id = z.profile_id
                WHERE p.profile_key = %s
                  AND ST_Contains(z.geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                ORDER BY z.sensitivity DESC, z.name ASC
                """,
                (profile_key, lon, lat),
            )
            return [_normalize_record(row) for row in cur.fetchall()]


def get_corridor_for_heading(heading: float, lon: float, lat: float, profile_key: str = "duqm") -> Optional[Dict[str, Any]]:
    """Find which approach corridor matches the vessel's heading and position."""
    if heading is None:
        return None

    with psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.id,
                    c.name,
                    c.expected_heading_min,
                    c.expected_heading_max,
                    c.label_en,
                    c.label_ar,
                    c.metadata,
                    c.created_at,
                    ST_AsGeoJSON(c.geom) AS geometry
                FROM approach_corridor c
                JOIN port_profile p ON p.id = c.profile_id
                WHERE p.profile_key = %s
                  AND ST_Contains(c.geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                ORDER BY c.name ASC
                """,
                (profile_key, lon, lat),
            )
            candidates = [_normalize_record(row) for row in cur.fetchall()]

    matching = [
        candidate
        for candidate in candidates
        if _heading_in_range(
            heading,
            float(candidate["expected_heading_min"]),
            float(candidate["expected_heading_max"]),
        )
    ]
    if not matching:
        return None

    matching.sort(
        key=lambda item: (
            _heading_span(float(item["expected_heading_min"]), float(item["expected_heading_max"])),
            item["name"],
        )
    )
    return matching[0]


def get_zone_criticality(lon: float, lat: float, profile_key: str = "duqm") -> float:
    """Get maximum sensitivity score for a point across all zones and critical areas."""
    with psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH point AS (
                    SELECT ST_SetSRID(ST_MakePoint(%s, %s), 4326) AS geom
                ),
                zone_scores AS (
                    SELECT z.sensitivity::float AS sensitivity
                    FROM operational_zone z
                    JOIN port_profile p ON p.id = z.profile_id
                    CROSS JOIN point
                    WHERE p.profile_key = %s
                      AND ST_Contains(z.geom, point.geom)
                ),
                area_scores AS (
                    SELECT a.sensitivity::float AS sensitivity
                    FROM critical_area a
                    JOIN port_profile p ON p.id = a.profile_id
                    CROSS JOIN point
                    WHERE p.profile_key = %s
                      AND ST_Contains(a.geom, point.geom)
                )
                SELECT COALESCE(MAX(sensitivity), 0.0) AS max_sensitivity
                FROM (
                    SELECT sensitivity FROM zone_scores
                    UNION ALL
                    SELECT sensitivity FROM area_scores
                ) scores
                """,
                (lon, lat, profile_key, profile_key),
            )
            row = cur.fetchone()

    max_sensitivity = float((row or {}).get("max_sensitivity") or 0.0)
    return round(max_sensitivity / 5.0, 4)


def enrich_case_zone_context(case_id: str, lon: float, lat: float, profile_key: str = "duqm") -> Dict[str, Any]:
    """Compute and store zone context for a case."""
    with psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    z.id,
                    z.name,
                    z.zone_type,
                    z.label_en,
                    z.label_ar,
                    z.sensitivity,
                    z.metadata,
                    z.created_at,
                    ST_AsGeoJSON(z.geom) AS geometry
                FROM operational_zone z
                JOIN port_profile p ON p.id = z.profile_id
                WHERE p.profile_key = %s
                  AND ST_Contains(z.geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                ORDER BY z.sensitivity DESC, z.name ASC
                """,
                (profile_key, lon, lat),
            )
            zones = [_normalize_record(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                    c.id,
                    c.name,
                    c.expected_heading_min,
                    c.expected_heading_max,
                    c.label_en,
                    c.label_ar,
                    c.metadata,
                    c.created_at,
                    ST_AsGeoJSON(c.geom) AS geometry
                FROM approach_corridor c
                JOIN port_profile p ON p.id = c.profile_id
                WHERE p.profile_key = %s
                  AND ST_Contains(c.geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                ORDER BY c.name ASC
                """,
                (profile_key, lon, lat),
            )
            corridors = [_normalize_record(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                    a.id,
                    a.name,
                    a.area_type,
                    a.sensitivity,
                    a.label_en,
                    a.label_ar,
                    a.metadata,
                    a.created_at,
                    ST_AsGeoJSON(a.geom) AS geometry
                FROM critical_area a
                JOIN port_profile p ON p.id = a.profile_id
                WHERE p.profile_key = %s
                  AND ST_Contains(a.geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                ORDER BY a.sensitivity DESC, a.name ASC
                """,
                (profile_key, lon, lat),
            )
            critical_areas = [_normalize_record(row) for row in cur.fetchall()]

            max_sensitivity = 0
            if zones:
                max_sensitivity = max(max_sensitivity, max(int(zone["sensitivity"] or 0) for zone in zones))
            if critical_areas:
                max_sensitivity = max(
                    max_sensitivity,
                    max(int(area["sensitivity"] or 0) for area in critical_areas),
                )

            context = {
                "profile_key": profile_key,
                "point": {"lon": lon, "lat": lat},
                "zones": zones,
                "corridors": corridors,
                "critical_areas": critical_areas,
                "max_sensitivity": max_sensitivity,
                "criticality": round(max_sensitivity / 5.0, 4),
            }

            cur.execute(
                """
                UPDATE investigation_case
                SET zone_context = %s::jsonb
                WHERE id = %s
                RETURNING id
                """,
                (Json(context), case_id),
            )
            updated = cur.fetchone()
            if not updated:
                raise ValueError(f"Case '{case_id}' not found")

        conn.commit()

    return context
