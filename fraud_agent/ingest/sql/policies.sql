CREATE OR REPLACE TABLE fraud_clean.policies AS
SELECT
  * EXCEPT (issue_date, fraud_type),
  PARSE_DATE('%d-%m-%Y', issue_date) AS issue_date,
  NULLIF(fraud_type, 'None') AS fraud_type,
  PARSE_DATE('%d-%m-%Y', issue_date) > CURRENT_DATE() AS dq_future_issue_date
FROM fraud_raw.policies;
