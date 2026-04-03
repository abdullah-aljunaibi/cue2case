-- Add spoofing to alert_type CHECK constraint
ALTER TABLE alert DROP CONSTRAINT IF EXISTS alert_alert_type_check;
ALTER TABLE alert ADD CONSTRAINT alert_alert_type_check 
  CHECK (alert_type IN ('abnormal_approach', 'ais_silence', 'loitering', 'kinematic_anomaly', 'identity_anomaly', 'spoofing'));
