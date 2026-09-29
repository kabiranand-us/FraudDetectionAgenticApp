-- Source data has agents with conflicting license_status across rows and
-- "Valid" licenses whose expiry date has passed; both are flagged, not fixed.
CREATE OR REPLACE TABLE fraud_clean.ghost_broking AS
SELECT
  * EXCEPT (license_expiry_date, policy_id, fraud_type),
  NULLIF(policy_id, '') AS policy_id,
  PARSE_DATE('%d-%m-%Y', license_expiry_date) AS license_expiry_date,
  NULLIF(fraud_type, 'None') AS fraud_type,
  license_status = 'Valid'
    AND PARSE_DATE('%d-%m-%Y', license_expiry_date) < CURRENT_DATE() AS dq_valid_license_expired,
  COUNT(DISTINCT license_status) OVER (PARTITION BY agent_id) > 1 AS dq_agent_license_conflict
FROM fraud_raw.ghost_broking;
