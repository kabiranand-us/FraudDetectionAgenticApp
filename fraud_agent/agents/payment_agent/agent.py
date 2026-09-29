"""Payment specialist agent (Google ADK): bad premium payments.

Run interactively:  uv run adk web fraud_agent/agents   (pick payment_agent)
"""

from google.adk.agents import LlmAgent

from fraud_agent.agents.common import JUDGING_RULES, MODEL, generation_config
from fraud_agent.agents.schemas import PaymentFindings
from fraud_agent.tools.bigquery_tools import PAYMENT_TOOLS

INSTRUCTION = """\
You are an insurance fraud investigator specialising in premium payments: money
that never really reached the insurer, or was taken back. You are given a
payment ID. Investigate it with the tools, then return your findings.

How to investigate:
1. Call get_case_context("payments", <payment id>) FIRST and only once. It returns the
   payment with its rule hits and policy, the related payments (reversals, bounces,
   timing versus policy issue, baseline) and the collecting agent's profile.
2. Read all of it before deciding whether you need anything else.
3. Only if something is still open, call get_policy or get_customer_history.

What each fraud type looks like:
- Duplicate/Unauthorized Refund Claimed: payment_status is Reversed; repeated
  reversals by the same customer or on the same policy.
- Fake Payment Receipt Submitted: is_duplicate_receipt is true (set by the
  payments system).
- Bounced Cheque Used for Coverage: payment_status is Bounced while the policy
  stayed active.
- Premium Diversion by Agent: premium_remitted_to_insurer is false, or a long
  remittance_delay_days (normal is 0-2 days).

""" + JUDGING_RULES

payment_agent = LlmAgent(
    name="payment_agent",
    model=MODEL,
    description=(
        "Investigates premium payment fraud: unauthorized refunds, fake receipts, "
        "bounced cheques and premium diversion by agents."
    ),
    instruction=INSTRUCTION,
    tools=PAYMENT_TOOLS,
    output_schema=PaymentFindings,
    output_key="payment_findings",
    generate_content_config=generation_config(),
)

root_agent = payment_agent
