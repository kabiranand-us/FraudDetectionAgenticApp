"""Raw table schemas for the four source CSVs.

Dates are DD-MM-YYYY in the source files, which BigQuery cannot parse on load,
so they land as STRING in fraud_raw and are converted in the clean SQL.
Column order must match the CSV header (checked by tests/test_schemas.py).
"""

from dataclasses import dataclass

from google.cloud.bigquery import SchemaField


@dataclass(frozen=True)
class RawTable:
    name: str
    csv_file: str
    id_column: str
    columns: tuple[tuple[str, str], ...]

    @property
    def schema(self) -> list[SchemaField]:
        return [SchemaField(col, typ) for col, typ in self.columns]


CLAIMS = RawTable(
    name="claims",
    id_column="claim_id",
    csv_file="claims.csv",
    columns=(
        ("claim_id", "STRING"),
        ("policy_id", "STRING"),
        ("customer_id", "STRING"),
        ("agent_id", "STRING"),
        ("claim_type", "STRING"),
        ("incident_date", "STRING"),
        ("claim_date", "STRING"),
        ("days_policy_to_incident", "INT64"),
        ("claim_amount", "NUMERIC"),
        ("approved_amount", "NUMERIC"),
        ("claim_status", "STRING"),
        ("num_claims_filed_by_customer", "INT64"),
        ("police_report_filed", "BOOL"),
        ("witness_count", "INT64"),
        ("documents_altered_flag", "BOOL"),
        ("fraud_flag", "BOOL"),
        ("fraud_type", "STRING"),
    ),
)

PAYMENTS = RawTable(
    name="payments",
    id_column="payment_id",
    csv_file="payments_bad_payments.csv",
    columns=(
        ("payment_id", "STRING"),
        ("policy_id", "STRING"),
        ("customer_id", "STRING"),
        ("agent_id", "STRING"),
        ("payment_date", "STRING"),
        ("payment_amount", "NUMERIC"),
        ("payment_mode", "STRING"),
        ("payment_status", "STRING"),
        ("receipt_number", "STRING"),
        ("is_duplicate_receipt", "BOOL"),
        ("premium_remitted_to_insurer", "BOOL"),
        ("remittance_delay_days", "INT64"),
        ("fraud_flag", "BOOL"),
        ("fraud_type", "STRING"),
    ),
)

GHOST_BROKING = RawTable(
    name="ghost_broking",
    id_column="record_id",
    csv_file="ghost_broking.csv",
    columns=(
        ("record_id", "STRING"),
        ("agent_id", "STRING"),
        ("agent_name", "STRING"),
        ("customer_id", "STRING"),
        ("policy_id", "STRING"),
        ("license_status", "STRING"),
        ("license_expiry_date", "STRING"),
        ("premium_collected", "NUMERIC"),
        ("premium_deposited_with_insurer", "BOOL"),
        ("customer_aware_of_agent_status", "BOOL"),
        ("complaint_count", "INT64"),
        ("agent_office_city", "STRING"),
        ("fraud_flag", "BOOL"),
        ("fraud_type", "STRING"),
    ),
)

POLICIES = RawTable(
    name="policies",
    id_column="policy_id",
    csv_file="policies_free_insurance.csv",
    columns=(
        ("policy_id", "STRING"),
        ("customer_id", "STRING"),
        ("agent_id", "STRING"),
        ("policy_type", "STRING"),
        ("issue_date", "STRING"),
        ("premium_amount", "NUMERIC"),
        ("sum_insured", "NUMERIC"),
        ("policy_status", "STRING"),
        ("channel", "STRING"),
        ("state", "STRING"),
        ("free_look_period_days", "INT64"),
        ("free_look_cancelled", "BOOL"),
        ("backdated_flag", "BOOL"),
        ("premium_actually_collected", "BOOL"),
        ("fraud_flag", "BOOL"),
        ("fraud_type", "STRING"),
    ),
)

RAW_TABLES = (POLICIES, CLAIMS, PAYMENTS, GHOST_BROKING)
