import csv
import typing

from google.adk.tools.agent_tool import AgentTool

from fraud_agent.agents.fraud_investigation.agent import (
    case_writer,
    orchestrator,
    reviewer,
    root_agent,
)
from fraud_agent.agents.schemas import FRAUD_TYPES_BY_TABLE, CaseFile, FraudType, ReviewReport
from fraud_agent.alerts import ALERTS_SQL
from fraud_agent.ingest.schemas import RAW_TABLES
from fraud_agent.rules.engine import load_rules
from fraud_agent.config import RAW_DATA_DIR


def test_pipeline_order():
    assert [a.name for a in root_agent.sub_agents] == ["orchestrator", "case_writer", "reviewer"]


def test_reviewer_is_independent_of_the_notes():
    assert "{case_file}" in reviewer.instruction
    assert "{investigation}" not in reviewer.instruction
    assert reviewer.include_contents == "none"
    assert reviewer.output_schema is ReviewReport
    tool_names = {t.__name__ for t in reviewer.tools}
    assert {"check_record_ids", "get_record"} <= tool_names


def test_orchestrator_can_call_every_specialist():
    agent_tools = [t for t in orchestrator.tools if isinstance(t, AgentTool)]
    assert {t.agent.name for t in agent_tools} == {
        "claims_agent", "policy_agent", "payment_agent", "ghost_broking_agent", "network_agent"
    }
    for name in ("claims_agent", "policy_agent", "payment_agent", "ghost_broking_agent",
                 "network_agent", "agent_is_hub"):
        assert name in orchestrator.instruction


def test_specialists_only_allow_their_own_fraud_types():
    import typing
    from fraud_agent.agents.ghost_broking_agent.agent import ghost_broking_agent
    from fraud_agent.agents.payment_agent.agent import payment_agent
    from fraud_agent.agents.policy_agent.agent import policy_agent
    for agent, table in ((policy_agent, "policies"), (payment_agent, "payments"),
                         (ghost_broking_agent, "ghost_broking")):
        field = agent.output_schema.model_fields["suspected_fraud_types"]
        (literal,) = typing.get_args(field.annotation)
        assert set(typing.get_args(literal)) == set(FRAUD_TYPES_BY_TABLE[table])
        assert agent.tools, agent.name
        for tool in agent.tools:
            assert tool.__doc__, f"{tool.__name__} needs a docstring"


def test_case_writer_reads_orchestrator_notes_only():
    assert "{investigation}" in case_writer.instruction
    assert orchestrator.output_key == "investigation"
    assert case_writer.include_contents == "none"
    assert case_writer.output_schema is CaseFile
    assert not case_writer.tools


def test_fraud_type_enum_covers_every_label_in_data():
    labels = set()
    for table in RAW_TABLES:
        with (RAW_DATA_DIR / table.csv_file).open() as f:
            labels |= {r["fraud_type"] for r in csv.DictReader(f) if r["fraud_type"] != "None"}
    # Labels use an en dash; the enum uses a hyphen so it is easy to type.
    normalised = {l.replace("–", "-") for l in labels}
    assert normalised == set(typing.get_args(FraudType))


def test_alerts_use_high_and_critical_rules_only():
    weights = load_rules().severity_weights
    assert f"rule_score >= {weights['high']}" in ALERTS_SQL


def test_fraud_types_by_table_match_data():
    for table in RAW_TABLES:
        with (RAW_DATA_DIR / table.csv_file).open() as f:
            labels = {r["fraud_type"] for r in csv.DictReader(f) if r["fraud_type"] != "None"}
        assert labels == set(FRAUD_TYPES_BY_TABLE[table.name]), table.name


def test_instructions_carry_the_fraud_type_mapping():
    for agent in (case_writer, reviewer):
        assert "FRAUD_TYPES_BY_TABLE" not in agent.instruction
        assert "ghost_broking: Fake/Cloned Agent Identity" in agent.instruction
