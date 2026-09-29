import re

from fraud_agent.agents.network_agent.agent import network_agent
from fraud_agent.agents.schemas import NetworkFindings
from fraud_agent.graph.build import ENTITY_RISK_SQL
from fraud_agent.tools.bigquery_tools import NETWORK_TOOLS, _entity_kind


def test_entity_risk_is_built_without_labels():
    for col in ("fraud_flag", "fraud_type", "claim_status", "approved_amount"):
        assert not re.search(rf"\b{col}\b", ENTITY_RISK_SQL), col


def test_network_agent_wiring():
    assert network_agent.output_schema is NetworkFindings
    assert network_agent.output_key == "network_findings"
    names = {t.__name__ for t in network_agent.tools}
    assert {"get_entity_network", "list_hub_entities"} <= names
    for tool in NETWORK_TOOLS:
        assert tool.__doc__, tool.__name__


def test_entity_kind():
    assert _entity_kind("AGT00340")[0] == "agent"
    assert _entity_kind("CUST000001")[0] == "customer"
    assert _entity_kind("POL000001") is None
