#!/usr/bin/env python3
"""Seed an approximate Duqm port profile and related port-context geometry."""

import os
from typing import Iterable

import psycopg2
from psycopg2.extras import Json

DEFAULT_DATABASE_URL = "postgresql://cue2case:cue2case_dev@localhost:5433/cue2case"


def polygon_wkt(points: Iterable[tuple[float, float]]) -> str:
    coords = list(points)
    if len(coords) < 4:
        raise ValueError("polygon requires at least 4 points")
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return "POLYGON(({}))".format(
        ", ".join(f"{lon:.6f} {lat:.6f}" for lon, lat in coords)
    )


def point_wkt(lon: float, lat: float) -> str:
    return f"POINT({lon:.6f} {lat:.6f})"


def main() -> None:
    database_url = os.getenv("DATABASE_URL_SYNC", DEFAULT_DATABASE_URL)

    # Approximate demo geometry from public materials for Port of Duqm / SEZAD references.
    port_center = (57.680000, 21.650000)

    operational_zones = [
        {
            "name": "commercial_wharf",
            "zone_type": "commercial",
            "label_en": "Commercial Wharf",
            "label_ar": "الرصيف التجاري",
            "sensitivity": 2,
            "geom": polygon_wkt(
                [
                    (57.662000, 21.651500),
                    (57.669500, 21.651500),
                    (57.669500, 21.661500),
                    (57.662000, 21.661500),
                ]
            ),
            "metadata": {
                "source": "approximate demo geometry from public materials",
                "notes": "Western-side commercial berth footprint.",
            },
        },
        {
            "name": "government_berth",
            "zone_type": "government",
            "label_en": "Government Berth",
            "label_ar": "مرسى حكومي",
            "sensitivity": 4,
            "geom": polygon_wkt(
                [
                    (57.688500, 21.651500),
                    (57.696500, 21.651500),
                    (57.696500, 21.660500),
                    (57.688500, 21.660500),
                ]
            ),
            "metadata": {
                "source": "approximate demo geometry from public materials",
                "notes": "Eastern-side government berth footprint.",
            },
        },
        {
            "name": "liquid_bulk_terminal",
            "zone_type": "liquid_bulk",
            "label_en": "Liquid Bulk Terminal",
            "label_ar": "محطة السوائل السائبة",
            "sensitivity": 4,
            "geom": polygon_wkt(
                [
                    (57.672000, 21.638500),
                    (57.681500, 21.638500),
                    (57.681500, 21.647000),
                    (57.672000, 21.647000),
                ]
            ),
            "metadata": {
                "source": "approximate demo geometry from public materials",
                "notes": "Southern liquid bulk handling area.",
            },
        },
        {
            "name": "outer_anchorage",
            "zone_type": "anchorage",
            "label_en": "Outer Anchorage",
            "label_ar": "المخطاف الخارجي",
            "sensitivity": 1,
            "geom": polygon_wkt(
                [
                    (57.712000, 21.596000),
                    (57.744000, 21.596000),
                    (57.744000, 21.626000),
                    (57.712000, 21.626000),
                ]
            ),
            "metadata": {
                "source": "approximate demo geometry from public materials",
                "notes": "Approx. 5nm southeast of the port entrance for waiting vessels.",
            },
        },
        {
            "name": "inner_harbor",
            "zone_type": "harbor",
            "label_en": "Inner Harbor",
            "label_ar": "الميناء الداخلي",
            "sensitivity": 2,
            "geom": polygon_wkt(
                [
                    (57.666000, 21.646000),
                    (57.692500, 21.646000),
                    (57.692500, 21.666500),
                    (57.666000, 21.666500),
                ]
            ),
            "metadata": {
                "source": "approximate demo geometry from public materials",
                "notes": "General harbor basin and maneuvering area.",
            },
        },
    ]

    approach_corridors = [
        {
            "name": "main_approach",
            "expected_heading_min": 290.0,
            "expected_heading_max": 350.0,
            "label_en": "Main Approach Corridor",
            "label_ar": "ممر الاقتراب الرئيسي",
            "geom": polygon_wkt(
                [
                    (57.700000, 21.632000),
                    (57.744000, 21.586000),
                    (57.758000, 21.600000),
                    (57.704000, 21.650000),
                ]
            ),
            "metadata": {
                "source": "approximate demo geometry from public materials",
                "notes": "Primary southeast-to-northwest inbound corridor from open sea.",
            },
        },
        {
            "name": "secondary_approach",
            "expected_heading_min": 300.0,
            "expected_heading_max": 20.0,
            "label_en": "Secondary Approach Corridor",
            "label_ar": "ممر اقتراب ثانوي",
            "geom": polygon_wkt(
                [
                    (57.684000, 21.628000),
                    (57.718000, 21.612000),
                    (57.726000, 21.626000),
                    (57.688000, 21.644000),
                ]
            ),
            "metadata": {
                "source": "approximate demo geometry from public materials",
                "notes": "Secondary feeder approach for vessels aligning closer to the breakwater entrance.",
            },
        },
    ]

    critical_areas = [
        {
            "name": "government_berth",
            "area_type": "government_berth",
            "label_en": "Government Berth Critical Area",
            "label_ar": "منطقة المرسي الحكومي الحرجة",
            "sensitivity": 5,
            "geom": polygon_wkt(
                [
                    (57.689000, 21.652000),
                    (57.696000, 21.652000),
                    (57.696000, 21.659500),
                    (57.689000, 21.659500),
                ]
            ),
            "metadata": {
                "source": "approximate demo geometry from public materials",
                "notes": "Highest-sensitivity government berth envelope.",
            },
        },
        {
            "name": "vts_zone",
            "area_type": "vts_monitored",
            "label_en": "VTS Monitored Zone",
            "label_ar": "منطقة مراقبة VTS",
            "sensitivity": 3,
            "geom": polygon_wkt(
                [
                    (57.640000, 21.610000),
                    (57.760000, 21.610000),
                    (57.760000, 21.690000),
                    (57.640000, 21.690000),
                ]
            ),
            "metadata": {
                "source": "approximate demo geometry from public materials",
                "notes": "Wider VTS oversight area around the port and outer approach.",
            },
        },
        {
            "name": "energy_terminal",
            "area_type": "energy",
            "label_en": "Energy Terminal",
            "label_ar": "محطة الطاقة",
            "sensitivity": 4,
            "geom": polygon_wkt(
                [
                    (57.673000, 21.639000),
                    (57.681000, 21.639000),
                    (57.681000, 21.646500),
                    (57.673000, 21.646500),
                ]
            ),
            "metadata": {
                "source": "approximate demo geometry from public materials",
                "notes": "Energy and liquid bulk-adjacent terminal security envelope.",
            },
        },
    ]

    seeded_counts = {
        "port_profile": 0,
        "operational_zone": 0,
        "approach_corridor": 0,
        "critical_area": 0,
    }

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM port_profile WHERE profile_key = %s",
                ("duqm",),
            )
            existing = cur.fetchone()

            if existing:
                profile_id = existing[0]
                cur.execute("DELETE FROM critical_area WHERE profile_id = %s", (profile_id,))
                cur.execute("DELETE FROM approach_corridor WHERE profile_id = %s", (profile_id,))
                cur.execute("DELETE FROM operational_zone WHERE profile_id = %s", (profile_id,))
                cur.execute(
                    "DELETE FROM port_profile WHERE id = %s",
                    (profile_id,),
                )

            cur.execute(
                """
                INSERT INTO port_profile (
                    profile_key,
                    name,
                    label_en,
                    label_ar,
                    center_geom,
                    metadata
                )
                VALUES (%s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s)
                RETURNING id
                """,
                (
                    "duqm",
                    "Port of Duqm",
                    "Port of Duqm",
                    "ميناء الدقم",
                    point_wkt(*port_center),
                    Json(
                        {
                            "source": "approximate demo geometry from public materials",
                            "notes": "Seed profile for Duqm-focused anomaly context.",
                            "approach_heading_reference": [290, 350],
                        }
                    ),
                ),
            )
            profile_id = cur.fetchone()[0]
            seeded_counts["port_profile"] = 1

            for zone in operational_zones:
                cur.execute(
                    """
                    INSERT INTO operational_zone (
                        profile_id,
                        name,
                        zone_type,
                        geom,
                        label_en,
                        label_ar,
                        sensitivity,
                        metadata
                    )
                    VALUES (%s, %s, %s, ST_GeomFromText(%s, 4326), %s, %s, %s, %s)
                    """,
                    (
                        profile_id,
                        zone["name"],
                        zone["zone_type"],
                        zone["geom"],
                        zone["label_en"],
                        zone["label_ar"],
                        zone["sensitivity"],
                        Json(zone["metadata"]),
                    ),
                )
                seeded_counts["operational_zone"] += 1

            for corridor in approach_corridors:
                cur.execute(
                    """
                    INSERT INTO approach_corridor (
                        profile_id,
                        name,
                        expected_heading_min,
                        expected_heading_max,
                        geom,
                        label_en,
                        label_ar,
                        metadata
                    )
                    VALUES (%s, %s, %s, %s, ST_GeomFromText(%s, 4326), %s, %s, %s)
                    """,
                    (
                        profile_id,
                        corridor["name"],
                        corridor["expected_heading_min"],
                        corridor["expected_heading_max"],
                        corridor["geom"],
                        corridor["label_en"],
                        corridor["label_ar"],
                        Json(corridor["metadata"]),
                    ),
                )
                seeded_counts["approach_corridor"] += 1

            for area in critical_areas:
                cur.execute(
                    """
                    INSERT INTO critical_area (
                        profile_id,
                        name,
                        area_type,
                        geom,
                        sensitivity,
                        label_en,
                        label_ar,
                        metadata
                    )
                    VALUES (%s, %s, %s, ST_GeomFromText(%s, 4326), %s, %s, %s, %s)
                    """,
                    (
                        profile_id,
                        area["name"],
                        area["area_type"],
                        area["geom"],
                        area["sensitivity"],
                        area["label_en"],
                        area["label_ar"],
                        Json(area["metadata"]),
                    ),
                )
                seeded_counts["critical_area"] += 1

    print("Seeded Duqm port context successfully.")
    print(f"Database URL: {database_url}")
    print(f"Port profile: {seeded_counts['port_profile']}")
    print(f"Operational zones: {seeded_counts['operational_zone']}")
    print(f"Approach corridors: {seeded_counts['approach_corridor']}")
    print(f"Critical areas: {seeded_counts['critical_area']}")
    print("Operational zone names: commercial_wharf, government_berth, liquid_bulk_terminal, outer_anchorage, inner_harbor")
    print("Approach corridor names: main_approach, secondary_approach")
    print("Critical area names: government_berth, vts_zone, energy_terminal")


if __name__ == "__main__":
    main()
