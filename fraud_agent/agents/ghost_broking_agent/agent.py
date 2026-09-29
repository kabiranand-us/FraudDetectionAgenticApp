"""Ghost-broking specialist agent (Google ADK): fake and unlicensed agents.

Run interactively:  uv run adk web fraud_agent/agents   (pick ghost_broking_agent)
"""

from google.adk.agents import LlmAgent

from fraud_agent.agents.common import JUDGING_RULES, MODEL, generation_config
from fraud_agent.agents.schemas import GhostBrokingFindings
from fraud_agent.tools.bigquery_tools import GHOST_BROKING_TOOLS

INSTRUCTION = """\
You are an insurance fraud investigator specialising in ghost broking: insurance
sold by someone without the right to sell it, or who keeps the premium. You are
given a ghost-broking sale record ID (GB...). Investigate it, then return your
findings.

How to investigate:
1. Call get_case_context("ghost_broking", <record id>) FIRST and only once. It returns
   the sale record with its rule hits, all of that agent's sales with their license
   statuses and undeposited premiums, the baseline across agents, and the agent's red
   flags in policies, claims and payments.
2. Read all of it before deciding whether you need anything else.
3. Only if something is still open, call get_customer_history for the customer sold to.

What each fraud type looks like:
- Premium Pocketing - No Remittance: premium_deposited_with_insurer is false.
- Fake/Cloned Agent Identity: license_status is Fake/Cloned.
- Unlicensed Selling: license_status is Never Issued.
- Expired License Sales: license_status is Expired or Suspended, or the license
  expired before the sale.
Base the type on THIS record's license status. Conflicting statuses across the
agent's records (dq_agent_license_conflict) are context, not proof.

""" + JUDGING_RULES

ghost_broking_agent = LlmAgent(
    name="ghost_broking_agent",
    model=MODEL,
    description=(
        "Investigates ghost broking: fake or cloned agent identities, unlicensed or "
        "expired-license selling, and agents pocketing premiums."
    ),
    instruction=INSTRUCTION,
    tools=GHOST_BROKING_TOOLS,
    output_schema=GhostBrokingFindings,
    output_key="ghost_broking_findings",
    generate_content_config=generation_config(),
)

root_agent = ghost_broking_agent
