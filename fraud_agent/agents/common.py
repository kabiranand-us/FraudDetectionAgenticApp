"""Shared model settings for all agents."""

from google.genai import types

from fraud_agent.config import get_settings

MODEL = get_settings().agent_model


def generation_config(temperature: float = 0.1) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        temperature=temperature,
        # Vertex AI quota errors (429) and overloads (503): back off and retry.
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(
                attempts=6, initial_delay=5, max_delay=60, http_status_codes=[429, 503]
            )
        ),
    )


# Shared judging and evidence rules for every specialist agent.
JUDGING_RULES = """\
How to judge:
- Rule severities: critical rules are near-certain fraud signals (95%+ precise);
  high rules are strong (60-75%); medium rules are weak on their own (about 1 in 3).
- Compare against the "baseline" figures the tools return. A pattern most
  records share is not evidence on its own.
- Separate evidence about THIS record from context (its policy, agent, customer,
  related records). Red flags only in the context support "high" at most.
- Risk levels: critical = near-certain evidence on the record itself (a critical
  rule on it); high = several strong, independent signals; medium = weak or
  single signals worth a look; low = nothing notable.
- Recommended action: reject_and_refer_to_siu only for critical;
  hold_for_investigation for high; request_documents for medium; approve for low.
- Only name fraud types the evidence supports, and only fraud committed through
  this record. An empty list is a valid answer.

Rules for evidence:
- Every evidence item must cite the record ID it came from and quote the exact
  values the tools returned. Never invent or estimate values.
- Include facts that point away from fraud as mitigating factors.
- dq_* fields are data-quality flags, not fraud evidence.
"""
