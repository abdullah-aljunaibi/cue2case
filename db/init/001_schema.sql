-- Enable extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Vessel identity
CREATE TABLE vessel (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mmsi VARCHAR(9) NOT NULL,
    vessel_name VARCHAR(255),
    vessel_type INTEGER,
    length REAL,
    width REAL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(mmsi)
);

-- Raw AIS positions
CREATE TABLE ais_position (
    id BIGSERIAL PRIMARY KEY,
    mmsi VARCHAR(9) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    geom GEOMETRY(Point, 4326) NOT NULL,
    sog REAL,
    cog REAL,
    heading REAL,
    nav_status INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ais_position_mmsi ON ais_position(mmsi);
CREATE INDEX idx_ais_position_timestamp ON ais_position(timestamp);
CREATE INDEX idx_ais_position_geom ON ais_position USING GIST(geom);

-- Track segments
CREATE TABLE track_segment (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mmsi VARCHAR(9) NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    geom GEOMETRY(LineString, 4326),
    point_count INTEGER,
    avg_sog REAL,
    max_sog REAL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_track_segment_mmsi ON track_segment(mmsi);
CREATE INDEX idx_track_segment_geom ON track_segment USING GIST(geom);

-- Geofences
CREATE TABLE geofence (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    zone_type VARCHAR(50) NOT NULL, -- 'approach', 'anchorage', 'restricted', 'harbor'
    geom GEOMETRY(Polygon, 4326) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_geofence_geom ON geofence USING GIST(geom);

-- Anomaly alerts
CREATE TABLE alert (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mmsi VARCHAR(9) NOT NULL,
    alert_type VARCHAR(50) NOT NULL, -- 'abnormal_approach', 'ais_silence', 'loitering', 'identity_inconsistency'
    severity REAL NOT NULL, -- 0.0 to 1.0
    timestamp TIMESTAMPTZ NOT NULL,
    geom GEOMETRY(Point, 4326),
    details JSONB NOT NULL DEFAULT '{}',
    explanation TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alert_mmsi ON alert(mmsi);
CREATE INDEX idx_alert_type ON alert(alert_type);
CREATE INDEX idx_alert_severity ON alert(severity DESC);

-- Investigation cases
CREATE TABLE investigation_case (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    mmsi VARCHAR(9) NOT NULL,
    anomaly_score REAL NOT NULL, -- composite score
    status VARCHAR(20) NOT NULL DEFAULT 'new', -- 'new', 'in_review', 'escalated', 'resolved', 'dismissed'
    priority INTEGER NOT NULL DEFAULT 0,
    summary TEXT,
    recommended_action TEXT,
    assigned_to VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_case_status ON investigation_case(status);
CREATE INDEX idx_case_score ON investigation_case(anomaly_score DESC);

-- Case evidence
CREATE TABLE case_evidence (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id UUID NOT NULL REFERENCES investigation_case(id),
    evidence_type VARCHAR(50) NOT NULL, -- 'alert', 'track', 'external_cue', 'screenshot'
    evidence_ref UUID,
    data JSONB NOT NULL DEFAULT '{}',
    provenance TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- External cues
CREATE TABLE external_cue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source VARCHAR(255) NOT NULL,
    cue_type VARCHAR(50) NOT NULL, -- 'rf_detection', 'imagery', 'tip', 'other'
    timestamp TIMESTAMPTZ,
    geom GEOMETRY(Point, 4326),
    data JSONB NOT NULL DEFAULT '{}',
    case_id UUID REFERENCES investigation_case(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_external_cue_geom ON external_cue USING GIST(geom);

-- Analyst notes
CREATE TABLE analyst_note (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id UUID NOT NULL REFERENCES investigation_case(id),
    author VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Audit log (immutable)
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    actor VARCHAR(255) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_log_entity ON audit_log(entity_type, entity_id);

-- RBAC users
CREATE TABLE app_user (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'analyst', -- 'analyst', 'admin'
    created_at TIMESTAMPTZ DEFAULT NOW()
);
