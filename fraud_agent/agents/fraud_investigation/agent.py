"""Alert investigation pipeline (Google ADK): orchestrator, case writer, reviewer.

    orchestrator  - takes one alert, routes it to the right specialist or tools,
                    and writes investigation notes (state key "investigation")
    case_writer   - turns the notes into a validated CaseFile (state key "case_file")
    reviewer      - independently re-checks every cited fact against BigQuery and the
                    case's calibration; never sees the notes (state key "review")

Run interactively:  uv run adk web fraud_agent/agents   (pick fraud_investigation)
Run from code:      uv run fraud-case claims CLM000593
"""

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools.agent_tool import AgentTool

from fraud_agent.agents.claims_agent.agent import claims_agent
from fraud_agent.agents.ghost_broking_agent.agent import ghost_broking_agent
from fraud_agent.agents.network_agent.agent import network_agent
from fraud_agent.agents.payment_agent.agent import payment_agent
from fraud_agent.agents.policy_agent.agent import policy_agent
from fraud_agent.agents.common import MODEL, generation_config
from fraud_agent.agents.schemas import CaseFile, ReviewReport, fraud_types_by_table_text
from fraud_agent.tools.bigquery_tools import CONTEXT_TOOLS, REVIEW_TOOLS

ORCHESTRATOR_INSTRUCTION = """\
You coordinate insurance fraud investigations. You receive one alert: a record
(claim, policy, payment or ghost-broking record) that rules or an ML model flagged.
The flagging decision is already made. Your job is to gather and weigh the
evidence, so an investigator can decide quickly.

Steps:
1. Call get_case_context(record_table, record_id) once: why it was flagged, the record,
   its related records and the agent's profile, all in one call. Do not re-fetch these
   pieces with other tools.
2. Call the specialist for the record type, with the request
   "Investigate <record type> <id>":
   - claims -> claims_agent
   - policies -> policy_agent
   - payments -> payment_agent
   - ghost_broking -> ghost_broking_agent
   The specialist's findings are the core of your notes.
3. Add context only if the specialist left something open, using at most one extra
   tool call. The same agent behind red flags in several files is worth noting; you
   already have that from step 1. Never repeat the specialist's work.
4. If the alert shows agent_is_hub or customer_is_hub, call network_agent with
   "Investigate agent <agent_id>" (or customer <customer_id>). Put its pattern,
   linked entities and records_to_review under CONTEXT; a network is a reason to
   investigate, not proof that this record is fraud.

Weighing evidence:
- A critical rule hit on the record itself is near-certain evidence.
- High rules are strong (60-75% precise); medium rules are weak (about 1 in 3).
- Tools return "baseline" figures. A signal most records share is not evidence.
- Red flags on related records (the policy, agent, customer) are context, not
  proof about this record. Say so explicitly.
- dq_* fields are data-quality flags, not fraud evidence.

Write your notes as plain text with these headings:
ALERT: record, why it was flagged.
FINDINGS: facts, each with the record ID it came from and the exact values.
CONTEXT: related policy, agent, customer facts, with record IDs and values.
MITIGATING: facts pointing away from fraud.
OPEN QUESTIONS: what the data cannot answer.
ASSESSMENT: critical / high / medium / low, likely fraud types, and why.
Never invent values. If a tool returns an error, say so in the notes.
"""

CASE_WRITER_INSTRUCTION = """\
You write case files for insurance fraud investigators, from an investigator's
notes. Use ONLY facts in the notes below. Do not add facts, values or record IDs
that are not in the notes.

- alert_id is "<record_table>:<record_id>".
- why_flagged: restate the rules and/or model score from the ALERT section.
- risk_assessment: take it from the ASSESSMENT section; lower it if the notes'
  evidence is weaker than the assessment claims (e.g. only context red flags).
- evidence: one item per fact, citing the record ID and quoting exact values.
- entities: the agent, customer and policy involved, each with a one-line note.
- recommended_action: reject_and_refer_to_siu only for critical;
  hold_for_investigation for high; request_documents for medium; approve for low.
- recommended_next_steps: concrete checks, e.g. "Verify the hospital bill with
  the issuing hospital", "Check agent AGT00087's license with the regulator".
- suspected_fraud_types: only fraud committed through THIS record (e.g. a
  reversed payment is refund fraud). Red flags about related entities, such as
  the agent's license, go in entities and evidence, not in this list. Use only
  the types listed for the record's table below. Empty is allowed.

Fraud types allowed for each record table:
FRAUD_TYPES_BY_TABLE

Investigator's notes:
{investigation}
"""

REVIEWER_INSTRUCTION = """\
You are the quality reviewer for insurance fraud case files. Nothing reaches an
investigator until you have checked it. Trust nothing in the case: verify it.

1. Call check_record_ids once with every record, agent and customer ID the case
   cites. Any missing ID is a serious error.
2. Call get_records once with all the record and agent IDs cited in the evidence:
   it returns them together, so you do not need one lookup per fact. Use
   get_record or get_agent_profile only for something get_records did not return.
   Then compare every value each fact states with the data:
   - verified: every stated value matches.
   - contradicted: any stated value differs from the data (say what the data shows).
   - unverifiable: the fact cannot be checked with the tools.
3. Check calibration:
   - critical needs near-certain evidence on the record itself (a critical rule
     on it). Red flags only on related records (policy, agent, customer) support
     high at most.
   - Every suspected fraud type needs supporting evidence in the case, and must
     describe fraud committed through THIS record. Types that describe a related
     entity (e.g. an agent's license status on a payment case) must be removed,
     and so must any type not listed for the record's table:
FRAUD_TYPES_BY_TABLE
   - The recommended action must match the risk: reject_and_refer_to_siu only for
     critical; hold_for_investigation for high; request_documents for medium;
     approve for low.
4. Verdict:
   - approved: no missing IDs, no contradicted facts, calibration right.
   - approved_with_corrections: facts hold, but risk, action or fraud types need
     changing; give the corrected final_* values.
   - rejected: any missing ID, or a contradicted fact that the risk depends on.
   final_risk_assessment, final_recommended_action and final_suspected_fraud_types
   are your corrected values (the same as the case's when approved).

Case file to review:
{case_file}
"""

# str.replace, not format(): the instructions contain {state} placeholders for ADK.
CASE_WRITER_INSTRUCTION = CASE_WRITER_INSTRUCTION.replace(
    "FRAUD_TYPES_BY_TABLE", fraud_types_by_table_text())
REVIEWER_INSTRUCTION = REVIEWER_INSTRUCTION.replace(
    "FRAUD_TYPES_BY_TABLE", fraud_types_by_table_text())

orchestrator = LlmAgent(
    name="orchestrator",
    model=MODEL,
    description="Investigates one fraud alert by routing it to specialists and tools.",
    instruction=ORCHESTRATOR_INSTRUCTION,
    tools=[
        AgentTool(claims_agent),
        AgentTool(policy_agent),
        AgentTool(payment_agent),
        AgentTool(ghost_broking_agent),
        AgentTool(network_agent),
        *CONTEXT_TOOLS,
    ],
    output_key="investigation",
    generate_content_config=generation_config(),
)

case_writer = LlmAgent(
    name="case_writer",
    model=MODEL,
    description="Turns investigation notes into a structured case file.",
    instruction=CASE_WRITER_INSTRUCTION,
    include_contents="none",
    output_schema=CaseFile,
    output_key="case_file",
    generate_content_config=generation_config(),
)

reviewer = LlmAgent(
    name="reviewer",
    model=MODEL,
    description="Verifies a case file's evidence and calibration against the data.",
    instruction=REVIEWER_INSTRUCTION,
    include_contents="none",
    tools=REVIEW_TOOLS,
    output_schema=ReviewReport,
    output_key="review",
    generate_content_config=generation_config(),
)

fraud_investigation = SequentialAgent(
    name="fraud_investigation",
    description="Investigates a fraud alert, writes a case file and reviews it.",
    sub_agents=[orchestrator, case_writer, reviewer],
)

root_agent = fraud_investigation
