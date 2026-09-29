"""Entity network features: how strongly each agent and customer is tied to alerts.

    uv run fraud-graph

Writes fraud_features.entity_risk: one row per agent and per customer, built only
from the alert queue (rules + model), never from labels. An entity is a "hub" when
it is linked to at least HUB_MIN_ALERTS alerts spread over at least
HUB_MIN_TABLES files. The printed report then checks, using the labels, whether
records handled by hub agents are more often fraud. Run after fraud-alerts.
"""

import argparse

from google.cloud import bigquery

from fraud_agent.config import DATASET_CLEAN, DATASET_FEATURES, get_settings

HUB_MIN_ALERTS = 5
HUB_MIN_TABLES = 2

RECORDS_SQL = f"""
  SELECT 'claims' AS record_table, claim_id AS record_id, agent_id, customer_id FROM {DATASET_CLEAN}.claims
  UNION ALL SELECT 'policies', policy_id, agent_id, customer_id FROM {DATASET_CLEAN}.policies
  UNION ALL SELECT 'payments', payment_id, agent_id, customer_id FROM {DATASET_CLEAN}.payments
  UNION ALL SELECT 'ghost_broking', record_id, agent_id, customer_id FROM {DATASET_CLEAN}.ghost_broking
"""


def _entity_select(entity: str, counterpart: str) -> str:
    return f"""
  SELECT
    '{entity.removesuffix("_id")}' AS entity_type,
    {entity} AS entity_id,
    COUNT(*) AS records,
    COUNTIF(alerted) AS alerts,
    COUNTIF(critical) AS critical_alerts,
    COUNT(DISTINCT IF(alerted, record_table, NULL)) AS tables_with_alerts,
    ARRAY_AGG(DISTINCT IF(alerted, record_table, NULL) IGNORE NULLS) AS alert_tables,
    COUNT(DISTINCT {counterpart}) AS counterparts,
    COUNT(DISTINCT IF(alerted, {counterpart}, NULL)) AS flagged_counterparts
  FROM r
  WHERE {entity} IS NOT NULL
  GROUP BY {entity}"""


ENTITY_RISK_SQL = f"""
CREATE OR REPLACE TABLE {DATASET_FEATURES}.entity_risk AS
WITH rec AS ({RECORDS_SQL}),
r AS (
  SELECT rec.*, a.record_id IS NOT NULL AS alerted,
         COALESCE(a.max_severity = 'critical', FALSE) AS critical
  FROM rec
  LEFT JOIN {DATASET_FEATURES}.alerts a USING (record_table, record_id)
),
e AS (
  {_entity_select("agent_id", "customer_id")}
  UNION ALL
  {_entity_select("customer_id", "agent_id")}
)
SELECT
  e.*,
  ROUND(SAFE_DIVIDE(alerts, records), 3) AS alert_rate,
  ROUND(PERCENT_RANK() OVER (PARTITION BY entity_type ORDER BY alerts), 3) AS alerts_percentile,
  alerts >= {HUB_MIN_ALERTS} AND tables_with_alerts >= {HUB_MIN_TABLES} AS is_hub,
  CURRENT_TIMESTAMP() AS built_at
FROM e
"""

REPORT_SQL = f"""
WITH rec AS (
  SELECT 'claims' AS record_table, claim_id AS record_id, agent_id, fraud_flag FROM {DATASET_CLEAN}.claims
  UNION ALL SELECT 'policies', policy_id, agent_id, fraud_flag FROM {DATASET_CLEAN}.policies
  UNION ALL SELECT 'payments', payment_id, agent_id, fraud_flag FROM {DATASET_CLEAN}.payments
  UNION ALL SELECT 'ghost_broking', record_id, agent_id, fraud_flag FROM {DATASET_CLEAN}.ghost_broking
),
r AS (
  SELECT rec.*, a.record_id IS NOT NULL AS alerted, COALESCE(er.is_hub, FALSE) AS hub_agent
  FROM rec
  LEFT JOIN {DATASET_FEATURES}.alerts a USING (record_table, record_id)
  LEFT JOIN {DATASET_FEATURES}.entity_risk er
    ON er.entity_type = 'agent' AND er.entity_id = rec.agent_id
)
SELECT hub_agent, alerted, COUNT(*) AS records, COUNTIF(fraud_flag) AS fraud
FROM r GROUP BY hub_agent, alerted ORDER BY hub_agent DESC, alerted DESC
"""


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args()
    client = bigquery.Client(project=settings.project_id, location=settings.location)
    client.query(ENTITY_RISK_SQL).result()

    print(f"{DATASET_FEATURES}.entity_risk:")
    for r in client.query(f"""
        SELECT entity_type, COUNT(*) AS n, COUNTIF(is_hub) AS hubs, MAX(alerts) AS max_alerts
        FROM {DATASET_FEATURES}.entity_risk GROUP BY entity_type ORDER BY entity_type
    """).result():
        print(f"  {r.entity_type:<9}{r.n:>5} entities, {r.hubs:>3} hubs "
              f"(>= {HUB_MIN_ALERTS} alerts over >= {HUB_MIN_TABLES} files), max {r.max_alerts} alerts")

    print("\nDo hub agents' records carry more fraud? (uses labels, report only)")
    print(f"  {'agent':<11}{'record':<14}{'records':>8}{'fraud':>7}{'rate':>8}")
    for r in client.query(REPORT_SQL).result():
        print(f"  {'hub' if r.hub_agent else 'other':<11}{'alerted' if r.alerted else 'not alerted':<14}"
              f"{r.records:>8}{r.fraud:>7}{r.fraud / r.records:>8.1%}")


if __name__ == "__main__":
    main()
