-- Update alert type taxonomy after detector hardening
ALTER TABLE alert DROP CONSTRAINT IF EXISTS alert_alert_type_check;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'alert_alert_type_check'
      AND conrelid = 'alert'::regclass
  ) THEN
    ALTER TABLE alert
    ADD CONSTRAINT alert_alert_type_check CHECK (
      alert_type IN (
        'abnormal_approach',
        'ais_silence',
        'loitering',
        'kinematic_anomaly',
        'identity_anomaly'
      )
    );
  END IF;
END
$$;
