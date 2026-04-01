-- Add trust-oriented case/evidence columns and pipeline run tracking metadata.
ALTER TABLE case_evidence
ADD COLUMN observed_at TIMESTAMPTZ;

ALTER TABLE case_evidence
ADD COLUMN timeline_order INTEGER DEFAULT 0;

ALTER TABLE investigation_case
ADD COLUMN primary_geom GEOMETRY(Point, 4326);

ALTER TABLE investigation_case
ADD COLUMN start_observed_at TIMESTAMPTZ;

ALTER TABLE investigation_case
ADD COLUMN end_observed_at TIMESTAMPTZ;

ALTER TABLE investigation_case
ADD COLUMN rank_score REAL NOT NULL DEFAULT 0.0 CHECK (rank_score >= 0 AND rank_score <= 2);

CREATE INDEX idx_case_rank_score ON investigation_case(rank_score DESC);
CREATE INDEX idx_case_primary_geom ON investigation_case USING GIST(primary_geom);
CREATE INDEX idx_case_observed_window ON investigation_case(start_observed_at, end_observed_at);
CREATE INDEX idx_case_evidence_timeline ON case_evidence(case_id, timeline_order, observed_at);

CREATE TABLE pipeline_run (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_type VARCHAR(50) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
    stats JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_pipeline_run_type ON pipeline_run(run_type);
CREATE INDEX idx_pipeline_run_status_started_at ON pipeline_run(status, started_at DESC);

ALTER TABLE alert
ADD COLUMN run_id UUID REFERENCES pipeline_run(id);

ALTER TABLE investigation_case
ADD COLUMN run_id UUID REFERENCES pipeline_run(id);

CREATE INDEX idx_alert_run_id ON alert(run_id);
CREATE INDEX idx_case_run_id ON investigation_case(run_id);
