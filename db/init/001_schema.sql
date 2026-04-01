-- Enable extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Vessel identity
CREATE TABLE vessel (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mmsi VARCHAR(9) NOT NULL CHECK (mmsi ~ '^[0-9]{9}$'),
    vessel_name VARCHAR(255),
    vessel_type INTEGER,
    length REAL CHECK (length >= 0),
    width REAL CHECK (width >= 0),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(mmsi)
);

-- Raw AIS positions
CREATE TABLE ais_position (
    id BIGSERIAL PRIMARY KEY,
    mmsi VARCHAR(9) NOT NULL REFERENCES vessel(mmsi),
    observed_at TIMESTAMPTZ NOT NULL,
    geom GEOMETRY(Point, 4326) NOT NULL,
    sog REAL CHECK (sog >= 0),
    cog REAL CHECK (cog >= 0 AND cog < 360),
    heading REAL CHECK (heading >= 0 AND heading < 360),
    nav_status INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ais_position_mmsi ON ais_position(mmsi);
CREATE INDEX idx_ais_position_observed_at ON ais_position(observed_at);
CREATE INDEX idx_ais_position_geom ON ais_position USING GIST(geom);

-- Track segments
CREATE TABLE track_segment (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mmsi VARCHAR(9) NOT NULL REFERENCES vessel(mmsi),
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    geom GEOMETRY(LineString, 4326) NOT NULL CHECK (ST_IsValid(geom)),
    point_count INTEGER CHECK (point_count >= 0),
    avg_sog REAL CHECK (avg_sog >= 0),
    max_sog REAL CHECK (max_sog >= 0),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_track_segment_mmsi ON track_segment(mmsi);
CREATE INDEX idx_track_segment_geom ON track_segment USING GIST(geom);
CREATE INDEX idx_track_segment_time ON track_segment(start_time, end_time);

-- Geofences
CREATE TABLE geofence (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    zone_type VARCHAR(50) NOT NULL CHECK (zone_type IN ('approach', 'anchorage', 'restricted', 'harbor')),
    geom GEOMETRY(Polygon, 4326) NOT NULL CHECK (ST_IsValid(geom)),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_geofence_geom ON geofence USING GIST(geom);

-- Anomaly alerts
CREATE TABLE alert (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mmsi VARCHAR(9) NOT NULL REFERENCES vessel(mmsi),
    alert_type VARCHAR(50) NOT NULL CHECK (alert_type IN ('abnormal_approach', 'ais_silence', 'loitering', 'identity_inconsistency')),
    severity REAL NOT NULL CHECK (severity >= 0 AND severity <= 1),
    observed_at TIMESTAMPTZ NOT NULL,
    geom GEOMETRY(Point, 4326),
    details JSONB NOT NULL DEFAULT '{}',
    explanation TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alert_mmsi ON alert(mmsi);
CREATE INDEX idx_alert_type ON alert(alert_type);
CREATE INDEX idx_alert_severity ON alert(severity DESC);
CREATE INDEX idx_alert_observed_at ON alert(observed_at);

-- Investigation cases
CREATE TABLE investigation_case (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(255) NOT NULL,
    mmsi VARCHAR(9) NOT NULL REFERENCES vessel(mmsi),
    anomaly_score REAL NOT NULL CHECK (anomaly_score >= 0 AND anomaly_score <= 1),
    status VARCHAR(20) NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'in_review', 'escalated', 'resolved', 'dismissed')),
    priority INTEGER NOT NULL DEFAULT 0 CHECK (priority >= 0),
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
    evidence_type VARCHAR(50) NOT NULL CHECK (evidence_type IN ('alert', 'track', 'external_cue', 'screenshot')),
    evidence_ref UUID,
    data JSONB NOT NULL DEFAULT '{}',
    provenance TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_case_evidence_case_id ON case_evidence(case_id);

-- External cues
CREATE TABLE external_cue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source VARCHAR(255) NOT NULL,
    cue_type VARCHAR(50) NOT NULL CHECK (cue_type IN ('rf_detection', 'imagery', 'tip', 'other')),
    observed_at TIMESTAMPTZ,
    geom GEOMETRY(Point, 4326),
    data JSONB NOT NULL DEFAULT '{}',
    case_id UUID REFERENCES investigation_case(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_external_cue_geom ON external_cue USING GIST(geom);
CREATE INDEX idx_external_cue_case_id ON external_cue(case_id);

-- Analyst notes
CREATE TABLE analyst_note (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id UUID NOT NULL REFERENCES investigation_case(id),
    author VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_analyst_note_case_id ON analyst_note(case_id);

-- Audit log (immutable — enforced by trigger)
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

-- Immutability trigger for audit log
CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is immutable';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_log_no_update
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();

-- RBAC users
CREATE TABLE app_user (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'analyst' CHECK (role IN ('analyst', 'admin')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-update updated_at trigger
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_investigation_case_updated_at
BEFORE UPDATE ON investigation_case
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
