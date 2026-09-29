import typing

from fraud_agent.agents.claims_agent.agent import root_agent
from fraud_agent.agents.schemas import ClaimFindings, ClaimFraudType
from fraud_agent.tools import bigquery_tools
from fraud_agent.tools.bigquery_tools import CLAIM_TOOLS, HIDDEN_COLUMNS, _jsonable

CLAIM_FRAUD_TYPES = {
    "Multiple/Duplicate Claims", "Staged Accident", "Fake Supporting Documents",
    "Exaggerated Claim Amount", "Early Claim Fraud",
}


def test_labels_hidden_from_tools():
    assert {"fraud_flag", "fraud_type", "claim_status", "approved_amount"} <= HIDDEN_COLUMNS


def test_query_filters_hidden_columns(monkeypatch):
    class FakeJob:
        def result(self, max_results=None):
            return [{"claim_id": "CLM1", "fraud_flag": True, "fraud_type": "x",
                     "claim_status": "Rejected", "approved_amount": 1}]

    class FakeClient:
        def query(self, sql, job_config=None):
            return FakeJob()

    monkeypatch.setattr(bigquery_tools, "_client", lambda: FakeClient())
    assert bigquery_tools._query("SELECT 1") == [{"claim_id": "CLM1"}]


def test_fraud_type_enum_matches_data_labels():
    assert set(typing.get_args(ClaimFraudType)) == CLAIM_FRAUD_TYPES


def test_agent_wiring():
    assert root_agent.output_schema is ClaimFindings
    assert root_agent.output_key == "claim_findings"
    assert len(root_agent.tools) == len(CLAIM_TOOLS)
    for tool in CLAIM_TOOLS:
        assert tool.__doc__, f"{tool.__name__} needs a docstring (it is the tool description)"


def test_jsonable_converts_bigquery_types():
    import datetime as dt
    from decimal import Decimal
    assert _jsonable(Decimal("1.5")) == 1.5
    assert _jsonable(dt.date(2024, 1, 2)) == "2024-01-02"
    assert _jsonable([Decimal("2")]) == [2.0]
