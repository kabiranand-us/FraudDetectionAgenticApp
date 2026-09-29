-- One row per claim. Labels (fraud_flag, fraud_type) and investigation outcomes
-- (claim_status, approved_amount) are deliberately excluded.
-- policy_status is excluded too: a cancellation can be the result of a fraud finding.
-- Depends on fraud_features.rule_hits (run `fraud-rules` first).
CREATE OR REPLACE TABLE fraud_features.claim_features AS
WITH
agent_gb AS (
  SELECT agent_id,
    COUNTIF(license_status != 'Valid') AS agent_nonvalid_license_rows,
    SUM(complaint_count) AS agent_complaints
  FROM fraud_clean.ghost_broking GROUP BY agent_id
),
-- Critical red flags on the same agent/customer in the *other* tables.
agent_flags AS (
  SELECT agent_id, COUNT(*) AS agent_critical_hits_other
  FROM fraud_features.rule_hits
  WHERE severity = 'critical' AND record_table != 'claims'
  GROUP BY agent_id
),
customer_flags AS (
  SELECT customer_id, COUNT(*) AS customer_critical_hits_other
  FROM fraud_features.rule_hits
  WHERE severity = 'critical' AND record_table != 'claims'
  GROUP BY customer_id
),
agent_policies AS (
  SELECT agent_id, COUNT(*) AS agent_policies FROM fraud_clean.policies GROUP BY agent_id
),
customer_policies AS (
  SELECT customer_id, COUNT(*) AS customer_policies FROM fraud_clean.policies GROUP BY customer_id
)
SELECT
  c.claim_id,
  c.agent_id,
  c.customer_id,
  c.policy_id,
  -- claim
  c.claim_type,
  CAST(c.claim_amount AS FLOAT64) AS claim_amount,
  c.days_policy_to_incident,
  DATE_DIFF(c.claim_date, c.incident_date, DAY) AS report_lag_days,
  c.num_claims_filed_by_customer,
  c.witness_count,
  CAST(c.police_report_filed AS INT64) AS police_report_filed,
  CAST(c.documents_altered_flag AS INT64) AS documents_altered,
  -- policy
  p.policy_type,
  p.channel,
  p.state,
  CAST(p.sum_insured AS FLOAT64) AS sum_insured,
  CAST(p.premium_amount AS FLOAT64) AS premium_amount,
  SAFE_DIVIDE(c.claim_amount, p.sum_insured) AS claim_to_sum_insured,
  SAFE_DIVIDE(c.claim_amount, p.premium_amount) AS claim_to_premium,
  CAST(p.backdated_flag AS INT64) AS policy_backdated,
  CAST(NOT p.premium_actually_collected AS INT64) AS policy_premium_not_collected,
  CAST(p.free_look_cancelled AS INT64) AS policy_free_look_cancelled,
  -- claim history
  COUNT(*) OVER (PARTITION BY c.policy_id) AS claims_on_policy,
  COUNT(*) OVER (PARTITION BY c.customer_id) AS customer_claims,
  COUNT(*) OVER (PARTITION BY c.agent_id) AS agent_claims,
  DATE_DIFF(c.incident_date,
    LAG(c.incident_date) OVER (PARTITION BY c.policy_id ORDER BY c.incident_date, c.claim_id),
    DAY) AS days_since_prev_claim_policy,
  DATE_DIFF(c.incident_date,
    LAG(c.incident_date) OVER (PARTITION BY c.customer_id ORDER BY c.incident_date, c.claim_id),
    DAY) AS days_since_prev_claim_customer,
  -- agent / customer, across files
  COALESCE(ap.agent_policies, 0) AS agent_policies,
  COALESCE(cp.customer_policies, 0) AS customer_policies,
  COALESCE(ag.agent_nonvalid_license_rows, 0) AS agent_nonvalid_license_rows,
  COALESCE(ag.agent_complaints, 0) AS agent_complaints,
  COALESCE(af.agent_critical_hits_other, 0) AS agent_critical_hits_other,
  COALESCE(cf.customer_critical_hits_other, 0) AS customer_critical_hits_other
FROM fraud_clean.claims c
JOIN fraud_clean.policies p ON p.policy_id = c.policy_id
LEFT JOIN agent_gb ag ON ag.agent_id = c.agent_id
LEFT JOIN agent_flags af ON af.agent_id = c.agent_id
LEFT JOIN customer_flags cf ON cf.customer_id = c.customer_id
LEFT JOIN agent_policies ap ON ap.agent_id = c.agent_id
LEFT JOIN customer_policies cp ON cp.customer_id = c.customer_id;
