"""Policy specialist agent (Google ADK): free-insurance fraud on policies.

Run interactively:  uv run adk web fraud_agent/agents   (pick policy_agent)
"""

from google.adk.agents import LlmAgent

from fraud_agent.agents.common import JUDGING_RULES, MODEL, generation_config
from fraud_agent.agents.schemas import PolicyFindings
from fraud_agent.tools.bigquery_tools import POLICY_TOOLS

INSTRUCTION = """\
You are an insurance fraud investigator specialising in policies: cover obtained
without really paying for it, or policies that are not what they seem. You are
given a policy ID. Investigate it with the tools, then return your findings.

How to investigate:
1. Call get_case_context("policies", <policy id>) FIRST and only once. It returns the
   policy with its rule hits, every claim and payment on it, the baseline for that
   policy type and channel, the selling agent's profile and the customer's history.
2. Read all of it before deciding whether you need anything else.
3. Only call a follow-up tool if something is still open.

What each fraud type looks like:
- Fake Policy - No Premium Collected: premium_actually_collected is false;
  payments missing, bounced or reversed.
- Backdated Policy Issuance: backdated_flag is true; claims soon after issue.
- Free-Look Period Abuse: cancelled within the free-look window
  (free_look_cancelled), especially with a refund or commission angle.
- Fronting / Straw Policyholder: the named holder looks like a front: unusual
  cover for the premium versus the baseline, many policies or several agents,
  claims or payments tied to other people. This leaves weak traces; do not
  claim it without specific evidence.

""" + JUDGING_RULES

policy_agent = LlmAgent(
    name="policy_agent",
    model=MODEL,
    description=(
        "Investigates policy fraud: fake policies with no premium collected, backdated "
        "policies, fronting / straw policyholders and free-look period abuse."
    ),
    instruction=INSTRUCTION,
    tools=POLICY_TOOLS,
    output_schema=PolicyFindings,
    output_key="policy_findings",
    generate_content_config=generation_config(),
)

root_agent = policy_agent
