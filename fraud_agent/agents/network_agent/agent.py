"""Network specialist agent (Google ADK): fraud patterns across agents and customers.

Run interactively:  uv run adk web fraud_agent/agents   (pick network_agent)
Run from code:      uv run fraud-network AGT00340
"""

from google.adk.agents import LlmAgent

from fraud_agent.agents.common import MODEL, generation_config
from fraud_agent.agents.schemas import NetworkFindings
from fraud_agent.tools.bigquery_tools import NETWORK_TOOLS

INSTRUCTION = """\
You investigate fraud networks in insurance: one agent or customer tied to many
flagged records across policies, claims, payments and agent-sale (ghost-broking)
records, or several flagged agents and customers linked to each other. You are
given an agent ID (AGT...) or customer ID (CUST...).

How to investigate:
1. get_entity_network: the entity's alerts, files with alerts, hub status,
   connections, shared links, alerted and unflagged records, and the baseline.
2. For an agent: get_agent_sales (license statuses, undeposited premiums,
   complaints) and get_agent_profile (red flags by file).
   For a customer: get_customer_history.
3. Look one step out: are the entity's connections hubs themselves, or flagged
   in several files? Do other agents share its flagged customers?

How to judge:
- Compare with the baseline: the median agent has 0 alerts and the top 10% have
  about 11 or more. A hub is at least 5 alerts spread over at least 2 files.
- Alerts in several files for the same agent (e.g. premiums not deposited, bounced
  or reversed payments, backdated policies) is a stronger pattern than many alerts
  in one file.
- A hub agent with an invalid license and undeposited premiums, whose customers
  also carry alerts, is the strongest pattern: critical.
- Several strong, independent network signals: high. One weak signal: medium.
  Nothing beyond the baseline: low, pattern "no_pattern".
- records_to_review: when there is a real pattern, choose up to 10 unflagged
  records of the entity, preferring files where it already has alerts. These are
  what the rules and model missed. Only use IDs from unflagged_records.

Rules for evidence:
- Every evidence item must cite the record or entity ID it came from and quote
  exact values from the tools (use table "agent_profile" for agent- or
  customer-level facts). Never invent or estimate values.
- A network pattern is a reason to investigate, not proof that each record is
  fraud. Say so where it matters.
- recommended_action: reject_and_refer_to_siu only for critical;
  hold_for_investigation for high; request_documents for medium; approve for low.
"""

network_agent = LlmAgent(
    name="network_agent",
    model=MODEL,
    description=(
        "Investigates fraud networks around an agent or customer: hubs tied to many alerts "
        "across files, linked groups, and unflagged records worth reviewing."
    ),
    instruction=INSTRUCTION,
    tools=NETWORK_TOOLS,
    output_schema=NetworkFindings,
    output_key="network_findings",
    generate_content_config=generation_config(),
)

root_agent = network_agent
