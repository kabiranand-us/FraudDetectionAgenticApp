"""Build the alert queue: records that rules or the claims model flag for investigation.

    uv run fraud-alerts

An alert is a record with a high or critical rule hit (rule_score >= 0.7), or a
claim whose model score is >= 0.42 (about 60% precision out-of-fold). Medium-only
rule hits are not alerts. Priority = the higher of rule score and model score.
Writes fraud_features.alerts. Run after fraud-rules and fraud-train-claims.
"""

import argparse

from google.cloud import bigquery

from fraud_agent.config import DATASET_FEATURES, get_settings

MIN_RULE_SCORE = 0.7
MIN_MODEL_SCORE = 0.42

ALERTS_SQL = f"""
CREATE OR REPLACE TABLE {DATASET_FEATURES}.alerts AS
SELECT
  CONCAT(r.record_table, ':', r.record_id) AS alert_id,
  r.record_table, r.record_id, r.agent_id, r.customer_id, r.policy_id,
  r.rule_score, r.max_severity, r.rule_ids,
  m.model_score,
  GREATEST(r.rule_score, COALESCE(m.model_score, 0)) AS priority,
  CASE
    WHEN r.rule_score >= {MIN_RULE_SCORE} AND m.model_score >= {MIN_MODEL_SCORE}
      THEN 'rule and model'
    WHEN r.rule_score >= {MIN_RULE_SCORE} THEN 'rule'
    ELSE 'model'
  END AS alert_source,
  CURRENT_TIMESTAMP() AS created_at
FROM {DATASET_FEATURES}.rule_scores r
LEFT JOIN {DATASET_FEATURES}.claim_model_scores m
  ON r.record_table = 'claims' AND m.claim_id = r.record_id
WHERE r.rule_score >= {MIN_RULE_SCORE} OR m.model_score >= {MIN_MODEL_SCORE}
"""


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args()
    client = bigquery.Client(project=settings.project_id, location=settings.location)
    client.query(ALERTS_SQL).result()
    rows = client.query(f"""
        SELECT record_table, COUNT(*) AS alerts, COUNTIF(max_severity = 'critical') AS critical
        FROM {DATASET_FEATURES}.alerts GROUP BY record_table ORDER BY alerts DESC
    """).result()
    total = 0
    print(f"{DATASET_FEATURES}.alerts:")
    for r in rows:
        total += r.alerts
        print(f"  {r.record_table:<14}{r.alerts:>5} alerts ({r.critical} critical)")
    print(f"  {'total':<14}{total:>5}")


if __name__ == "__main__":
    main()
