-- claim_status and approved_amount are investigation outcomes: keep them here,
-- but they must never be used as model features (label leakage).
CREATE OR REPLACE TABLE fraud_clean.claims AS
SELECT
  * EXCEPT (incident_date, claim_date, fraud_type),
  PARSE_DATE('%d-%m-%Y', incident_date) AS incident_date,
  PARSE_DATE('%d-%m-%Y', claim_date) AS claim_date,
  NULLIF(fraud_type, 'None') AS fraud_type,
  PARSE_DATE('%d-%m-%Y', incident_date) > CURRENT_DATE() AS dq_future_incident_date,
  PARSE_DATE('%d-%m-%Y', claim_date) > CURRENT_DATE() AS dq_future_claim_date,
  PARSE_DATE('%d-%m-%Y', claim_date) < PARSE_DATE('%d-%m-%Y', incident_date) AS dq_claim_before_incident
FROM fraud_raw.claims;
