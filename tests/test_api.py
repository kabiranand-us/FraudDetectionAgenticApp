import inspect
import re

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from fraud_agent.api import main, store


@pytest.fixture
def client(monkeypatch):
    """A client with BigQuery replaced by small fixtures."""
    alerts = pd.DataFrame([{
        "alert_id": "claims:CLM000001", "record_table": "claims", "record_id": "CLM000001",
        "priority": 1.0, "max_severity": "critical", "alert_source": "rule",
        "rule_ids": ["CLM_DOCUMENTS_ALTERED"], "model_score": 0.9, "agent_id": "AGT00001",
        "customer_id": "CUST000001", "policy_id": "POL000001", "agent_is_hub": True,
        "customer_is_hub": False, "case_risk": None, "review_verdict": None, "decision": None,
        "status": "open",
    }])
    monkeypatch.setattr(store, "ensure_tables", lambda: None)
    monkeypatch.setattr(store, "alert_queue", lambda: alerts)
    monkeypatch.setattr(store, "all_decisions", lambda: pd.DataFrame(
        columns=["decided_at", "alert_id", "decision", "fraud_type", "note", "investigator"]))
    monkeypatch.setattr(store, "hubs", lambda t="agent", limit=50: pd.DataFrame([{
        "entity_id": "AGT00001", "records": 10, "alerts": 6, "critical_alerts": 2,
        "tables_with_alerts": 2, "alert_tables": ["claims", "payments"],
        "flagged_counterparts": 3, "alert_rate": 0.6, "is_hub": True}]))
    monkeypatch.setattr(store, "latest_case", lambda alert_id: None)
    monkeypatch.setattr(store, "decisions_for", lambda alert_id: pd.DataFrame(
        columns=["decided_at", "decision", "fraud_type", "note", "investigator"]))
    with TestClient(main.app) as c:
        yield c


def test_alerts_are_json_serialisable(client):
    rows = client.get("/api/alerts").json()
    assert rows[0]["rule_ids"] == ["CLM_DOCUMENTS_ALTERED"]
    assert rows[0]["status"] == "open"


def test_networks_and_fraud_types(client):
    assert client.get("/api/networks").json()[0]["entity_id"] == "AGT00001"
    assert set(client.get("/api/fraud-types").json()) == {
        "claims", "policies", "payments", "ghost_broking"}


def test_confirmed_fraud_needs_a_type(client):
    r = client.post("/api/alerts/claims:CLM000001/decision", json={"decision": "confirmed_fraud"})
    assert r.status_code == 400


def test_decision_is_saved_with_the_case_timestamp(client, monkeypatch):
    saved = {}
    monkeypatch.setattr(store, "save_decision", lambda *a: saved.update(args=a))
    r = client.post("/api/alerts/claims:CLM000001/decision",
                    json={"decision": "not_fraud", "note": "checked", "investigator": "A"})
    assert r.status_code == 201 and saved["args"][0] == "claims:CLM000001"


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope").status_code == 404


def test_bad_alert_id_is_rejected(client):
    assert client.get("/api/alerts/justthis").status_code == 400


def test_api_never_reads_labels():
    src = inspect.getsource(store).replace(store.__doc__, "")
    assert not re.search(r"\bfraud_flag\b", src)
    assert "DATASET_CLEAN" not in src
