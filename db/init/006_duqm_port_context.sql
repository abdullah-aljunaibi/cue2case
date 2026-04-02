-- Add Duqm-oriented port context tables and case zone context support.

CREATE TABLE IF NOT EXISTS port_profile (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_key VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    label_en VARCHAR(255),
    label_ar VARCHAR(255),
    center_geom GEOMETRY(Point, 4326),
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS operational_zone (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_id UUID NOT NULL REFERENCES port_profile(id),
    name VARCHAR(255) NOT NULL,
    zone_type VARCHAR(50) NOT NULL CHECK (
        zone_type IN (
            'approach',
            'anchorage',
            'restricted',
            'harbor',
            'commercial',
            'government',
            'liquid_bulk',
            'critical'
        )
    ),
    geom GEOMETRY(Polygon, 4326) NOT NULL,
    label_en VARCHAR(255),
    label_ar VARCHAR(255),
    sensitivity INTEGER DEFAULT 1 CHECK (sensitivity >= 1 AND sensitivity <= 5),
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS approach_corridor (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_id UUID NOT NULL REFERENCES port_profile(id),
    name VARCHAR(255) NOT NULL,
    expected_heading_min REAL NOT NULL CHECK (expected_heading_min >= 0 AND expected_heading_min < 360),
    expected_heading_max REAL NOT NULL CHECK (expected_heading_max >= 0 AND expected_heading_max < 360),
    geom GEOMETRY(Polygon, 4326) NOT NULL,
    label_en VARCHAR(255),
    label_ar VARCHAR(255),
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS critical_area (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_id UUID NOT NULL REFERENCES port_profile(id),
    name VARCHAR(255) NOT NULL,
    area_type VARCHAR(50) NOT NULL CHECK (
        area_type IN ('government_berth', 'military', 'energy', 'environmental', 'vts_monitored')
    ),
    geom GEOMETRY(Polygon, 4326) NOT NULL,
    sensitivity INTEGER DEFAULT 3 CHECK (sensitivity >= 1 AND sensitivity <= 5),
    label_en VARCHAR(255),
    label_ar VARCHAR(255),
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_operational_zone_geom ON operational_zone USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_approach_corridor_geom ON approach_corridor USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_critical_area_geom ON critical_area USING GIST(geom);
CREATE INDEX IF NOT EXISTS idx_operational_zone_profile ON operational_zone(profile_id);
CREATE INDEX IF NOT EXISTS idx_approach_corridor_profile ON approach_corridor(profile_id);
CREATE INDEX IF NOT EXISTS idx_critical_area_profile ON critical_area(profile_id);

ALTER TABLE investigation_case
ADD COLUMN zone_context JSONB DEFAULT '{}';
