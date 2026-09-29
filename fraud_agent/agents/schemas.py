"""Structured outputs returned by the investigation agents."""

from typing import Literal

from pydantic import BaseModel, Field

ClaimFraudType = Literal[
    "Multiple/Duplicate Claims",
    "Staged Accident",
    "Fake Supporting Documents",
    "Exaggerated Claim Amount",
    "Early Claim Fraud",
]


class Evidence(BaseModel):
    record_id: str = Field(description="ID of the record the fact comes from, e.g. CLM000004 or AGT00340.")
    table: Literal["claims", "policies", "payments", "ghost_broking", "agent_profile"]
    fact: str = Field(description="The fact, quoting exact values returned by the tools.")


class ClaimFindings(BaseModel):
    claim_id: str
    risk_level: Literal["critical", "high", "medium", "low"]
    suspected_fraud_types: list[ClaimFraudType] = Field(
        description="Empty when the evidence does not support fraud."
    )
    evidence: list[Evidence] = Field(description="Facts supporting the risk level; every item cites a record.")
    mitigating_factors: list[str] = Field(description="Facts that point away from fraud.")
    recommended_action: Literal[
        "reject_and_refer_to_siu", "hold_for_investigation", "request_documents", "approve"
    ]
    summary: str = Field(description="Two to four sentences an investigator can read in 20 seconds.")


FraudType = Literal[
    # claims
    "Multiple/Duplicate Claims", "Staged Accident", "Fake Supporting Documents",
    "Exaggerated Claim Amount", "Early Claim Fraud",
    # policies
    "Fake Policy - No Premium Collected", "Backdated Policy Issuance",
    "Fronting / Straw Policyholder", "Free-Look Period Abuse",
    # payments
    "Duplicate/Unauthorized Refund Claimed", "Fake Payment Receipt Submitted",
    "Bounced Cheque Used for Coverage", "Premium Diversion by Agent",
    # ghost broking
    "Fake/Cloned Agent Identity", "Premium Pocketing - No Remittance",
    "Expired License Sales", "Unlicensed Selling",
]


FRAUD_TYPES_BY_TABLE: dict[str, tuple[str, ...]] = {
    "claims": ("Multiple/Duplicate Claims", "Staged Accident", "Fake Supporting Documents",
               "Exaggerated Claim Amount", "Early Claim Fraud"),
    "policies": ("Fake Policy - No Premium Collected", "Backdated Policy Issuance",
                 "Fronting / Straw Policyholder", "Free-Look Period Abuse"),
    "payments": ("Duplicate/Unauthorized Refund Claimed", "Fake Payment Receipt Submitted",
                 "Bounced Cheque Used for Coverage", "Premium Diversion by Agent"),
    "ghost_broking": ("Fake/Cloned Agent Identity", "Premium Pocketing - No Remittance",
                      "Expired License Sales", "Unlicensed Selling"),
}


def fraud_types_by_table_text() -> str:
    """The mapping as prompt text: which fraud types can apply to which record type."""
    return "\n".join(f"  {t}: {'; '.join(types)}" for t, types in FRAUD_TYPES_BY_TABLE.items())


class Entity(BaseModel):
    entity_type: Literal["agent", "customer", "policy"]
    entity_id: str
    note: str = Field(description="Why this entity matters to the case, in one line.")


class CaseFile(BaseModel):
    alert_id: str = Field(description='"<record_table>:<record_id>", e.g. "claims:CLM000593".')
    record_table: Literal["claims", "policies", "payments", "ghost_broking"]
    record_id: str
    why_flagged: str = Field(description="The rules and/or model score that raised the alert.")
    risk_assessment: Literal["critical", "high", "medium", "low"] = Field(
        description="Advisory: how strong the evidence is. The alert itself came from rules/model."
    )
    suspected_fraud_types: list[FraudType]
    entities: list[Entity]
    evidence: list[Evidence]
    mitigating_factors: list[str]
    open_questions: list[str] = Field(
        description="What an investigator should check that the data cannot answer."
    )
    recommended_action: Literal[
        "reject_and_refer_to_siu", "hold_for_investigation", "request_documents", "approve"
    ]
    recommended_next_steps: list[str]
    summary: str = Field(description="Three to five sentences for the investigator.")


class EvidenceCheck(BaseModel):
    record_id: str
    fact: str = Field(description="The evidence item as written in the case file.")
    status: Literal["verified", "contradicted", "unverifiable"]
    note: str = Field(description="What the data actually shows, with exact values.")


class ReviewReport(BaseModel):
    alert_id: str
    missing_record_ids: list[str] = Field(description="Cited IDs that do not exist in the data.")
    evidence_checks: list[EvidenceCheck]
    issues: list[str] = Field(
        description="Calibration or reasoning problems: risk too high/low for the evidence, "
                    "fraud types the evidence does not support, context presented as proof."
    )
    verdict: Literal["approved", "approved_with_corrections", "rejected"]
    final_risk_assessment: Literal["critical", "high", "medium", "low"]
    final_recommended_action: Literal[
        "reject_and_refer_to_siu", "hold_for_investigation", "request_documents", "approve"
    ]
    final_suspected_fraud_types: list[FraudType] = Field(
        description="Corrected fraud types: only those committed through this record."
    )
    reviewer_note: str = Field(description="One to three sentences for the investigator.")


class _SpecialistFindings(BaseModel):
    risk_level: Literal["critical", "high", "medium", "low"]
    evidence: list[Evidence] = Field(description="Facts supporting the risk level; every item cites a record.")
    mitigating_factors: list[str] = Field(description="Facts that point away from fraud.")
    recommended_action: Literal[
        "reject_and_refer_to_siu", "hold_for_investigation", "request_documents", "approve"
    ]
    summary: str = Field(description="Two to four sentences an investigator can read in 20 seconds.")


class PolicyFindings(_SpecialistFindings):
    policy_id: str
    suspected_fraud_types: list[Literal[FRAUD_TYPES_BY_TABLE["policies"]]] = Field(
        description="Empty when the evidence does not support fraud."
    )


class PaymentFindings(_SpecialistFindings):
    payment_id: str
    suspected_fraud_types: list[Literal[FRAUD_TYPES_BY_TABLE["payments"]]] = Field(
        description="Empty when the evidence does not support fraud."
    )


class GhostBrokingFindings(_SpecialistFindings):
    record_id: str
    suspected_fraud_types: list[Literal[FRAUD_TYPES_BY_TABLE["ghost_broking"]]] = Field(
        description="Empty when the evidence does not support fraud."
    )


class NetworkFindings(BaseModel):
    entity_id: str
    entity_type: Literal["agent", "customer"]
    pattern: Literal["hub", "linked_group", "no_pattern"] = Field(
        description="hub: one entity tied to many alerts across files; linked_group: several "
                    "flagged entities sharing customers or agents; no_pattern: nothing unusual."
    )
    risk_level: Literal["critical", "high", "medium", "low"]
    linked_entities: list[Entity] = Field(description="Agents and customers that form the pattern.")
    evidence: list[Evidence]
    records_to_review: list[str] = Field(
        description="Unflagged record IDs (from unflagged_records) that deserve an investigator's "
                    "look because of the network. Empty if there is no pattern."
    )
    mitigating_factors: list[str]
    recommended_action: Literal[
        "reject_and_refer_to_siu", "hold_for_investigation", "request_documents", "approve"
    ]
    summary: str = Field(description="Two to four sentences an investigator can read in 20 seconds.")
