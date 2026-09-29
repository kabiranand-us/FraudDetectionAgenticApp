"""BigQuery reads and writes for the investigator API.

The API never reads label columns (fraud_flag, fraud_type): an investigator
working on real data would not have them. The only table it writes is
fraud_cases.decisions (plus case_files when an investigation is run from the UI).
"""

import json
import uuid
from datetime import datetime, timezone
from functools import cache

import pandas as pd
from google.cloud import bigquery

from fraud_agent.config import DATASET_CASES, DATASET_FEATURES, get_settings

DECISIONS = ("confirmed_fraud", "not_fraud", "needs_more_info")

_CASE_FILES_COLUMNS = [
    ("alert_id", "STRING"), ("record_table", "STRING"), ("record_id", "STRING"),
    ("risk_assessment", "STRING"), ("suspected_fraud_types", "ARRAY<STRING>"),
    ("recommended_action", "STRING"), ("case_json", "JSON"),
    ("review_verdict", "STRING"), ("final_risk_assessment", "STRING"),
    ("final_recommended_action", "STRING"), ("final_suspected_fraud_types", "ARRAY<STRING>"),
    ("review_json", "JSON"), ("agent_model", "STRING"), ("created_at", "TIMESTAMP"),
]


@cache
def client() -> bigquery.Client:
    settings = get_settings()
    return bigquery.Client(project=settings.project_id, location=settings.location)


def _df(sql: str, **params) -> pd.DataFrame:
    qp = []
    for name, v in params.items():
        if isinstance(v, list):
            qp.append(bigquery.ArrayQueryParameter(name, "STRING", v))
        else:
            qp.append(bigquery.ScalarQueryParameter(name, "INT64" if isinstance(v, int) else "STRING", v))
    job = client().query(sql, job_config=bigquery.QueryJobConfig(query_parameters=qp))
    return job.to_dataframe(create_bqstorage_client=False)


def ensure_tables() -> None:
    """Create the decisions table, and add review columns to older case_files tables."""
    cols = ", ".join(f"{c} {t}" for c, t in _CASE_FILES_COLUMNS)
    client().query(f"CREATE TABLE IF NOT EXISTS {DATASET_CASES}.case_files ({cols})").result()
    adds = ", ".join(f"ADD COLUMN IF NOT EXISTS {c} {t}" for c, t in _CASE_FILES_COLUMNS)
    client().query(f"ALTER TABLE {DATASET_CASES}.case_files {adds}").result()
    client().query(f"""
        CREATE TABLE IF NOT EXISTS {DATASET_CASES}.decisions (
          decision_id STRING, alert_id STRING, record_table STRING, record_id STRING,
          decision STRING, fraud_type STRING, note STRING, investigator STRING,
          case_created_at TIMESTAMP, decided_at TIMESTAMP)
    """).result()


_LATEST = f"""
latest_case AS (
  SELECT * EXCEPT (rn) FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY alert_id ORDER BY created_at DESC) AS rn
    FROM {DATASET_CASES}.case_files) WHERE rn = 1),
latest_decision AS (
  SELECT * EXCEPT (rn) FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY alert_id ORDER BY decided_at DESC) AS rn
    FROM {DATASET_CASES}.decisions) WHERE rn = 1)
"""


def alert_queue() -> pd.DataFrame:
    return _df(f"""
        WITH {_LATEST}
        SELECT
          a.alert_id, a.record_table, a.record_id, a.priority, a.max_severity, a.alert_source,
          a.rule_ids, a.model_score, a.agent_id, a.customer_id, a.policy_id,
          COALESCE(ag.is_hub, FALSE) AS agent_is_hub,
          COALESCE(cu.is_hub, FALSE) AS customer_is_hub,
          COALESCE(c.final_risk_assessment, c.risk_assessment) AS case_risk,
          c.review_verdict,
          d.decision,
          CASE WHEN d.decision IS NOT NULL THEN 'decided'
               WHEN c.alert_id IS NOT NULL THEN 'case ready'
               ELSE 'open' END AS status
        FROM {DATASET_FEATURES}.alerts a
        LEFT JOIN {DATASET_FEATURES}.entity_risk ag
          ON ag.entity_type = 'agent' AND ag.entity_id = a.agent_id
        LEFT JOIN {DATASET_FEATURES}.entity_risk cu
          ON cu.entity_type = 'customer' AND cu.entity_id = a.customer_id
        LEFT JOIN latest_case c USING (alert_id)
        LEFT JOIN latest_decision d USING (alert_id)
        ORDER BY a.priority DESC, a.alert_id
    """)


def _json(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    while isinstance(value, str):  # older rows were double-encoded
        value = json.loads(value)
    return value


def latest_case(alert_id: str) -> dict | None:
    df = _df(f"""
        SELECT case_json, review_json, review_verdict, agent_model, created_at
        FROM {DATASET_CASES}.case_files WHERE alert_id = @alert_id
        ORDER BY created_at DESC LIMIT 1""", alert_id=alert_id)
    if df.empty:
        return None
    row = df.iloc[0]
    return {
        "case": _json(row.case_json),
        "review": _json(row.review_json),
        "agent_model": row.agent_model,
        "created_at": row.created_at,
    }


def decisions_for(alert_id: str) -> pd.DataFrame:
    return _df(f"""
        SELECT decided_at, decision, fraud_type, note, investigator
        FROM {DATASET_CASES}.decisions WHERE alert_id = @alert_id
        ORDER BY decided_at DESC""", alert_id=alert_id)


def all_decisions() -> pd.DataFrame:
    return _df(f"""
        SELECT decided_at, alert_id, decision, fraud_type, note, investigator
        FROM {DATASET_CASES}.decisions ORDER BY decided_at DESC LIMIT 500""")


def latest_network_findings(entity_id: str) -> dict | None:
    exists = _df(f"""
        SELECT COUNT(*) AS n FROM {DATASET_CASES}.INFORMATION_SCHEMA.TABLES
        WHERE table_name = 'network_findings'""")
    if not exists.n.iloc[0]:
        return None
    df = _df(f"""
        SELECT findings_json, created_at FROM {DATASET_CASES}.network_findings
        WHERE entity_id = @entity_id ORDER BY created_at DESC LIMIT 1""", entity_id=entity_id)
    return None if df.empty else {"findings": _json(df.findings_json.iloc[0]),
                                  "created_at": df.created_at.iloc[0]}


def hubs(entity_type: str = "agent", limit: int = 50) -> pd.DataFrame:
    return _df(f"""
        SELECT entity_id, records, alerts, critical_alerts, tables_with_alerts, alert_tables,
               flagged_counterparts, alert_rate, is_hub
        FROM {DATASET_FEATURES}.entity_risk WHERE entity_type = @t
        ORDER BY alerts DESC, critical_alerts DESC, entity_id LIMIT @limit""",
        t=entity_type, limit=limit)


def save_decision(alert_id: str, record_table: str, record_id: str, decision: str,
                  fraud_type: str | None, note: str, investigator: str,
                  case_created_at) -> None:
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}")
    row = {
        "decision_id": uuid.uuid4().hex,
        "alert_id": alert_id,
        "record_table": record_table,
        "record_id": record_id,
        "decision": decision,
        "fraud_type": fraud_type or None,
        "note": note.strip() or None,
        "investigator": investigator.strip() or None,
        "case_created_at": case_created_at.isoformat() if case_created_at is not None else None,
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }
    errors = client().insert_rows_json(f"{client().project}.{DATASET_CASES}.decisions", [row])
    if errors:
        raise RuntimeError(f"could not save decision: {errors}")
