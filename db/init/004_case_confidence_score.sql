-- Add explicit confidence_score support to investigation cases
ALTER TABLE investigation_case
ADD COLUMN IF NOT EXISTS confidence_score REAL NOT NULL DEFAULT 0.5;

ALTER TABLE investigation_case
DROP CONSTRAINT IF EXISTS investigation_case_confidence_score_check;

ALTER TABLE investigation_case
ADD CONSTRAINT investigation_case_confidence_score_check CHECK (
  confidence_score >= 0 AND confidence_score <= 1
);
