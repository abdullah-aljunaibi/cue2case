-- Add explicit confidence_score support to investigation cases
ALTER TABLE investigation_case
ADD COLUMN IF NOT EXISTS confidence_score REAL NOT NULL DEFAULT 0.5;

ALTER TABLE investigation_case
DROP CONSTRAINT IF EXISTS investigation_case_confidence_score_check;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'investigation_case_confidence_score_check'
      AND conrelid = 'investigation_case'::regclass
  ) THEN
    ALTER TABLE investigation_case
    ADD CONSTRAINT investigation_case_confidence_score_check CHECK (
      confidence_score >= 0 AND confidence_score <= 1
    );
  END IF;
END
$$;
