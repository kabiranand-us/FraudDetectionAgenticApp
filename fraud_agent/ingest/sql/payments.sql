CREATE OR REPLACE TABLE fraud_clean.payments AS
SELECT
  * EXCEPT (payment_date, fraud_type),
  PARSE_DATE('%d-%m-%Y', payment_date) AS payment_date,
  NULLIF(fraud_type, 'None') AS fraud_type,
  PARSE_DATE('%d-%m-%Y', payment_date) > CURRENT_DATE() AS dq_future_payment_date
FROM fraud_raw.payments;
