"""Read-only BigQuery tools for the investigation agents.

Every tool:
  - uses parameterized queries (agent input is never pasted into SQL),
  - caps bytes billed per query,
  - never returns label or outcome columns (fraud_flag, fraud_type,
    claim_status, approved_amount), so agents reason from evidence and
    their results can be evaluated against the labels honestly.

Plain functions with type hints and docstrings: ADK turns them into tools.
"""

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from functools import cache
from typing import Any

from google.cloud import bigquery

from fraud_agent.config import DATASET_CLEAN, DATASET_FEATURES, get_settings
from fraud_agent.rules.engine import load_rules

HIDDEN_COLUMNS = {"fraud_flag", "fraud_type", "claim_status", "approved_amount"}
MAX_BYTES_BILLED = 100 * 1024 * 1024
MAX_ROWS = 50


@cache
def _client() -> bigquery.Client:
    settings = get_settings()
    return bigquery.Client(project=settings.project_id, location=settings.location)


@cache
def _rule_descriptions() -> dict[str, str]:
    return {r.id: r.description for r in load_rules().rules}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):  # BigQuery STRUCT
        return {k: _jsonable(v) for k, v in value.items()}
    return value


def _query(sql: str, **params: Any) -> list[dict[str, Any]]:
    query_params = [
        bigquery.ScalarQueryParameter(name, "INT64" if isinstance(v, int) else "STRING", v)
        for name, v in params.items()
    ]
    job = _client().query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=query_params, maximum_bytes_billed=MAX_BYTES_BILLED
        ),
    )
    return [
        {k: _jsonable(v) for k, v in row.items() if k not in HIDDEN_COLUMNS}
        for row in job.result(max_results=MAX_ROWS)
    ]


def _query_all(specs: list[tuple[str, dict[str, Any]]]) -> list[list[dict[str, Any]]]:
    """Run several queries at once: BigQuery jobs start immediately, results are collected after."""
    jobs = []
    for sql, params in specs:
        jobs.append(_client().query(
            sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter(
                        name, "INT64" if isinstance(v, int) else "STRING", v)
                    for name, v in params.items()
                ],
                maximum_bytes_billed=MAX_BYTES_BILLED,
            ),
        ))
    return [
        [{k: _jsonable(v) for k, v in row.items() if k not in HIDDEN_COLUMNS}
         for row in job.result(max_results=MAX_ROWS)]
        for job in jobs
    ]


def _in_parallel(calls: dict[str, tuple]) -> dict[str, Any]:
    """Run several tool functions at once: {key: (fn, *args)} -> {key: result}."""
    with ThreadPoolExecutor(max_workers=min(8, len(calls) or 1)) as pool:
        futures = {key: pool.submit(fn, *args) for key, (fn, *args) in calls.items()}
        return {key: f.result() for key, f in futures.items()}


def _rule_hits(record_table: str, record_ids: list[str]) -> dict[str, list[dict]]:
    if not record_ids:
        return {}
    job = _client().query(
        f"""SELECT record_id, rule_id, severity
            FROM {DATASET_FEATURES}.rule_hits
            WHERE record_table = @t AND record_id IN UNNEST(@ids)
            ORDER BY weight DESC, rule_id""",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("t", "STRING", record_table),
                bigquery.ArrayQueryParameter("ids", "STRING", record_ids),
            ],
            maximum_bytes_billed=MAX_BYTES_BILLED,
        ),
    )
    hits: dict[str, list[dict]] = {}
    for row in job.result():
        hits.setdefault(row.record_id, []).append({
            "rule_id": row.rule_id,
            "severity": row.severity,
            "description": _rule_descriptions().get(row.rule_id, ""),
        })
    return hits


def _attach_rule_hits(rows: list[dict], record_table: str, id_column: str) -> list[dict]:
    hits = _rule_hits(record_table, [r[id_column] for r in rows])
    for r in rows:
        r["rule_hits"] = hits.get(r[id_column], [])
    return rows


def get_claim(claim_id: str) -> dict:
    """Get one claim with its policy, rule hits and ML model score.

    Args:
        claim_id: Claim ID, e.g. "CLM000004".

    Returns:
        The claim fields, data-quality flags (dq_*), the rule hits that fired on
        it, the claims model score (0-1, higher = more likely fraud) and a
        summary of the policy it was made on. {"error": ...} if not found.
    """
    rows = _query(
        f"""WITH hits AS (
              SELECT record_id, ARRAY_AGG(STRUCT(rule_id, severity) ORDER BY weight DESC, rule_id) AS hits
              FROM {DATASET_FEATURES}.rule_hits
              WHERE record_table = 'claims' AND record_id = @claim_id
              GROUP BY record_id)
            SELECT c.*, m.model_score, m.model_version,
                   STRUCT(p.policy_id, p.policy_type, p.issue_date, p.premium_amount,
                          p.sum_insured, p.policy_status, p.channel, p.state) AS policy,
                   COALESCE(h.hits, []) AS hits
            FROM {DATASET_CLEAN}.claims c
            LEFT JOIN {DATASET_FEATURES}.claim_model_scores m USING (claim_id)
            LEFT JOIN {DATASET_CLEAN}.policies p USING (policy_id)
            LEFT JOIN hits h ON h.record_id = c.claim_id
            WHERE c.claim_id = @claim_id""",
        claim_id=claim_id,
    )
    if not rows:
        return {"error": f"claim {claim_id} not found"}
    claim = rows[0]
    claim["rule_hits"] = [
        {**h, "description": _rule_descriptions().get(h["rule_id"], "")}
        for h in claim.pop("hits", [])
    ]
    policy = claim.get("policy") or {}
    if policy.get("sum_insured"):
        claim["claim_to_sum_insured"] = round(claim["claim_amount"] / policy["sum_insured"], 3)
    return claim


def get_policy(policy_id: str) -> dict:
    """Get a policy with its rule hits, all claims on it and all payments for it.

    Args:
        policy_id: Policy ID, e.g. "POL000808".

    Returns:
        Policy fields and rule hits, plus "claims" and "payments" lists (each
        with their own rule hits). {"error": ...} if not found.
    """
    rows = _query(
        f"SELECT * FROM {DATASET_CLEAN}.policies WHERE policy_id = @policy_id",
        policy_id=policy_id,
    )
    if not rows:
        return {"error": f"policy {policy_id} not found"}
    policy = _attach_rule_hits(rows, "policies", "policy_id")[0]
    claims, payments = _query_all([
        (f"""SELECT claim_id, customer_id, agent_id, claim_type, incident_date, claim_date,
                    claim_amount, documents_altered_flag
             FROM {DATASET_CLEAN}.claims WHERE policy_id = @policy_id
             ORDER BY incident_date""", {"policy_id": policy_id}),
        (f"""SELECT payment_id, payment_date, payment_amount, payment_mode, payment_status,
                    receipt_number, premium_remitted_to_insurer, remittance_delay_days
             FROM {DATASET_CLEAN}.payments WHERE policy_id = @policy_id
             ORDER BY payment_date""", {"policy_id": policy_id}),
    ])
    policy["claims"] = _attach_rule_hits(claims, "claims", "claim_id")
    policy["payments"] = _attach_rule_hits(payments, "payments", "payment_id")
    return policy


def get_customer_history(customer_id: str) -> dict:
    """Get everything on file for a customer: policies, claims and payments.

    Args:
        customer_id: Customer ID, e.g. "CUST001966".

    Returns:
        "policies", "claims" and "payments" lists (up to 50 each, with rule
        hits), and counts per list.
    """
    policies = _attach_rule_hits(_query(
        f"""SELECT policy_id, agent_id, policy_type, issue_date, premium_amount, sum_insured,
                   policy_status, channel
            FROM {DATASET_CLEAN}.policies WHERE customer_id = @customer_id
            ORDER BY issue_date""",
        customer_id=customer_id,
    ), "policies", "policy_id")
    claims = _attach_rule_hits(_query(
        f"""SELECT claim_id, policy_id, agent_id, claim_type, incident_date, claim_date,
                   claim_amount, days_policy_to_incident, witness_count, police_report_filed,
                   documents_altered_flag
            FROM {DATASET_CLEAN}.claims WHERE customer_id = @customer_id
            ORDER BY incident_date""",
        customer_id=customer_id,
    ), "claims", "claim_id")
    payments = _attach_rule_hits(_query(
        f"""SELECT payment_id, policy_id, agent_id, payment_date, payment_amount,
                   payment_mode, payment_status
            FROM {DATASET_CLEAN}.payments WHERE customer_id = @customer_id
            ORDER BY payment_date""",
        customer_id=customer_id,
    ), "payments", "payment_id")
    return {
        "customer_id": customer_id,
        "counts": {"policies": len(policies), "claims": len(claims), "payments": len(payments)},
        "policies": policies,
        "claims": claims,
        "payments": payments,
    }


def get_agent_profile(agent_id: str) -> dict:
    """Get an insurance agent's (sales agent's) risk profile across all data.

    Args:
        agent_id: Agent ID, e.g. "AGT00340".

    Returns:
        Name, office city and license statuses from ghost-broking records,
        total complaints, record counts per table, rule hits per table and
        severity, and the agent's average claims-model score.
    """
    license_rows = _query(
        f"""SELECT ANY_VALUE(agent_name) AS agent_name,
                   ARRAY_AGG(DISTINCT agent_office_city) AS office_cities,
                   ARRAY_AGG(DISTINCT license_status) AS license_statuses,
                   MAX(license_expiry_date) AS latest_license_expiry,
                   SUM(complaint_count) AS total_complaints,
                   COUNTIF(NOT customer_aware_of_agent_status) AS customers_unaware,
                   COUNT(*) AS ghost_broking_records
            FROM {DATASET_CLEAN}.ghost_broking WHERE agent_id = @agent_id""",
        agent_id=agent_id,
    )
    counts = _query(
        f"""SELECT
              (SELECT COUNT(*) FROM {DATASET_CLEAN}.policies WHERE agent_id = @agent_id) AS policies,
              (SELECT COUNT(*) FROM {DATASET_CLEAN}.claims WHERE agent_id = @agent_id) AS claims,
              (SELECT COUNT(*) FROM {DATASET_CLEAN}.payments WHERE agent_id = @agent_id) AS payments,
              (SELECT ROUND(AVG(m.model_score), 3)
                 FROM {DATASET_CLEAN}.claims c
                 JOIN {DATASET_FEATURES}.claim_model_scores m USING (claim_id)
                 WHERE c.agent_id = @agent_id) AS avg_claim_model_score""",
        agent_id=agent_id,
    )[0]
    hits = _query(
        f"""SELECT record_table, severity, COUNT(*) AS hits,
                   ARRAY_AGG(DISTINCT rule_id) AS rule_ids
            FROM {DATASET_FEATURES}.rule_hits WHERE agent_id = @agent_id
            GROUP BY record_table, severity ORDER BY record_table, severity""",
        agent_id=agent_id,
    )
    baseline = _query(
        f"""SELECT
              ROUND(AVG(IF(g.agent_id IS NOT NULL, 1, 0)), 2)
                AS share_of_claims_with_agent_license_issue
            FROM {DATASET_CLEAN}.claims c
            LEFT JOIN (SELECT DISTINCT agent_id FROM {DATASET_CLEAN}.ghost_broking
                       WHERE license_status != 'Valid') g USING (agent_id)"""
    )[0]
    profile = {
        "agent_id": agent_id,
        "record_counts": counts,
        "rule_hits": hits,
        "baseline": {
            **baseline,
            "note": "Share of ALL claims handled by an agent with a non-valid license "
                    "record. A license issue alone is a weak, common signal.",
        },
    }
    if license_rows and license_rows[0]["ghost_broking_records"]:
        profile.update(license_rows[0])
    else:
        profile["ghost_broking_records"] = 0
    return profile


def find_related_claims(claim_id: str, window_days: int = 180) -> dict:
    """Find claims that may duplicate or be linked to a given claim.

    Looks for other claims by the same customer, on the same policy, or with
    the same claim type through the same agent, with an incident within
    `window_days` of this claim's incident.

    Args:
        claim_id: The claim to compare against.
        window_days: Max days between incident dates (default 180).

    Returns:
        "related" list with each claim's link reasons (same_customer,
        same_policy, same_agent_same_type), days apart, and whether the amount
        or incident date matches exactly.
    """
    related = _query(
        f"""WITH target AS (SELECT * FROM {DATASET_CLEAN}.claims WHERE claim_id = @claim_id)
            SELECT c.claim_id, c.customer_id, c.policy_id, c.agent_id, c.claim_type,
                   c.incident_date, c.claim_amount,
                   c.customer_id = t.customer_id AS same_customer,
                   c.policy_id = t.policy_id AS same_policy,
                   c.agent_id = t.agent_id AND c.claim_type = t.claim_type AS same_agent_same_type,
                   ABS(DATE_DIFF(c.incident_date, t.incident_date, DAY)) AS days_apart,
                   c.claim_amount = t.claim_amount AS same_amount,
                   c.incident_date = t.incident_date AS same_incident_date
            FROM {DATASET_CLEAN}.claims c CROSS JOIN target t
            WHERE c.claim_id != t.claim_id
              AND (c.customer_id = t.customer_id OR c.policy_id = t.policy_id
                   OR (c.agent_id = t.agent_id AND c.claim_type = t.claim_type))
              AND ABS(DATE_DIFF(c.incident_date, t.incident_date, DAY)) <= @window_days
            ORDER BY days_apart""",
        claim_id=claim_id,
        window_days=window_days,
    )
    baseline = _query(
        f"""SELECT ROUND(AVG(IF(n > 0, 1, 0)), 2) AS share_of_all_claims_with_related
            FROM (
              SELECT a.claim_id, COUNT(b.claim_id) AS n
              FROM {DATASET_CLEAN}.claims a
              LEFT JOIN {DATASET_CLEAN}.claims b
                ON b.claim_id != a.claim_id
               AND (b.customer_id = a.customer_id OR b.policy_id = a.policy_id
                    OR (b.agent_id = a.agent_id AND b.claim_type = a.claim_type))
               AND ABS(DATE_DIFF(b.incident_date, a.incident_date, DAY)) <= @window_days
              GROUP BY a.claim_id)""",
        window_days=window_days,
    )[0]
    return {
        "claim_id": claim_id,
        "window_days": window_days,
        "related": _attach_rule_hits(related, "claims", "claim_id"),
        "exact_duplicate_signals": sum(
            1 for r in related if r["same_amount"] or r["same_incident_date"]
        ),
        "baseline": {
            **baseline,
            "note": "Share of ALL claims that have at least one related claim in this "
                    "window. Having related claims is only unusual if this share is low.",
        },
    }


def get_alert(record_table: str, record_id: str) -> dict:
    """Get the alert for a flagged record: why it was flagged and who is involved.

    Args:
        record_table: One of "claims", "policies", "payments", "ghost_broking".
        record_id: The record's ID, e.g. "CLM000593", "POL000391", "PAY000053", "GB000001".

    Returns:
        Alert source (rule, model, or both), priority (0-1), rule hits with
        descriptions, claims model score (claims only), the agent_id,
        customer_id and policy_id involved, and whether that agent or customer is
        a network hub (agent_is_hub, customer_is_hub). {"error": ...} if the record is not
        in the alert queue.
    """
    rows = _query(
        f"""SELECT a.alert_id, a.record_table, a.record_id, a.agent_id, a.customer_id,
                   a.policy_id, a.alert_source, a.priority, a.max_severity, a.model_score,
                   COALESCE(ag.is_hub, FALSE) AS agent_is_hub,
                   COALESCE(cu.is_hub, FALSE) AS customer_is_hub
            FROM {DATASET_FEATURES}.alerts a
            LEFT JOIN {DATASET_FEATURES}.entity_risk ag
              ON ag.entity_type = 'agent' AND ag.entity_id = a.agent_id
            LEFT JOIN {DATASET_FEATURES}.entity_risk cu
              ON cu.entity_type = 'customer' AND cu.entity_id = a.customer_id
            WHERE a.record_table = @record_table AND a.record_id = @record_id""",
        record_table=record_table,
        record_id=record_id,
    )
    if not rows:
        return {"error": f"no alert for {record_table} {record_id}"}
    return _attach_rule_hits(rows, record_table, "record_id")[0]


def get_payment(payment_id: str) -> dict:
    """Get one premium payment with its rule hits and a summary of its policy.

    Args:
        payment_id: Payment ID, e.g. "PAY000053".

    Returns:
        Payment fields (date, amount, mode, status, receipt, remittance),
        rule hits, and the policy summary. {"error": ...} if not found.
    """
    rows = _query(
        f"SELECT * FROM {DATASET_CLEAN}.payments WHERE payment_id = @payment_id",
        payment_id=payment_id,
    )
    if not rows:
        return {"error": f"payment {payment_id} not found"}
    payment = _attach_rule_hits(rows, "payments", "payment_id")[0]
    policy = _query(
        f"""SELECT policy_id, policy_type, issue_date, premium_amount, sum_insured,
                   policy_status, channel
            FROM {DATASET_CLEAN}.policies WHERE policy_id = @policy_id""",
        policy_id=payment["policy_id"],
    )
    payment["policy"] = policy[0] if policy else None
    return payment


def get_ghost_broking_record(record_id: str) -> dict:
    """Get one agent-sale record from the ghost-broking data, with its rule hits.

    Args:
        record_id: Ghost-broking record ID, e.g. "GB000001".

    Returns:
        Agent name and ID, license status and expiry, premium collected and
        whether it was deposited with the insurer, customer awareness,
        complaints, office city, data-quality flags and rule hits.
        {"error": ...} if not found.
    """
    rows = _query(
        f"SELECT * FROM {DATASET_CLEAN}.ghost_broking WHERE record_id = @record_id",
        record_id=record_id,
    )
    if not rows:
        return {"error": f"ghost-broking record {record_id} not found"}
    return _attach_rule_hits(rows, "ghost_broking", "record_id")[0]


_ID_TABLES = {
    "CLM": ("claims", "claim_id"),
    "POL": ("policies", "policy_id"),
    "PAY": ("payments", "payment_id"),
    "GB": ("ghost_broking", "record_id"),
}


def get_record(record_table: str, record_id: str) -> dict:
    """Get one raw record from any of the four tables, exactly as stored.

    Args:
        record_table: One of "claims", "policies", "payments", "ghost_broking".
        record_id: The record's ID (CLM..., POL..., PAY... or GB...).

    Returns:
        Every stored field of the record (labels and outcomes excluded), its
        rule hits, and for claims the ML model score. {"error": ...} if the
        table or record does not exist.
    """
    tables = {t: col for t, col in _ID_TABLES.values()}
    if record_table not in tables:
        return {"error": f"unknown table {record_table}; use one of {sorted(tables)}"}
    id_col = tables[record_table]
    rows = _query(
        f"SELECT * FROM {DATASET_CLEAN}.{record_table} WHERE {id_col} = @record_id",
        record_id=record_id,
    )
    if not rows:
        return {"error": f"{record_table} {record_id} not found"}
    record = _attach_rule_hits(rows, record_table, id_col)[0]
    if record_table == "claims":
        score = _query(
            f"""SELECT model_score, model_version FROM {DATASET_FEATURES}.claim_model_scores
                WHERE claim_id = @record_id""",
            record_id=record_id,
        )
        record.update(score[0] if score else {"model_score": None})
    return record


def get_records(record_ids: list[str]) -> dict:
    """Get several records at once, for checking a case's evidence in one call.

    Args:
        record_ids: Up to 20 IDs of any type: claims (CLM...), policies (POL...),
            payments (PAY...), ghost-broking records (GB...), agents (AGT...).

    Returns:
        "records": {record_id: the record with its rule hits, or agent profile for
        AGT ids}, and "not_found": IDs that do not exist.
    """
    wanted = list(dict.fromkeys(record_ids))[:20]
    calls: dict[str, tuple] = {}
    for rid in wanted:
        if rid.startswith("AGT"):
            calls[rid] = (get_agent_profile, rid)
            continue
        prefix = next((p for p in _ID_TABLES if rid.startswith(p)), None)
        if prefix:
            calls[rid] = (get_record, _ID_TABLES[prefix][0], rid)
    results = _in_parallel(calls) if calls else {}
    found = {k: v for k, v in results.items() if "error" not in v}
    missing = [r for r in wanted if r not in found]
    return {"records": found, "not_found": missing}


def check_record_ids(record_ids: list[str]) -> dict:
    """Check that record IDs cited in a case actually exist in the data.

    Args:
        record_ids: IDs to check: claims (CLM...), policies (POL...), payments
            (PAY...), ghost-broking records (GB...), agents (AGT...) or
            customers (CUST...).

    Returns:
        {"results": [{"record_id", "exists", "table"}], "missing": [...]}.
    """
    results = []
    for rid in dict.fromkeys(record_ids):
        if rid.startswith("AGT") or rid.startswith("CUST"):
            col = "agent_id" if rid.startswith("AGT") else "customer_id"
            found = _query(
                f"""SELECT COUNT(*) AS n FROM (
                      SELECT {col} FROM {DATASET_CLEAN}.policies UNION ALL
                      SELECT {col} FROM {DATASET_CLEAN}.claims UNION ALL
                      SELECT {col} FROM {DATASET_CLEAN}.payments UNION ALL
                      SELECT {col} FROM {DATASET_CLEAN}.ghost_broking)
                    WHERE {col} = @rid""",
                rid=rid,
            )[0]["n"] > 0
            results.append({"record_id": rid, "exists": found,
                            "table": "agent" if col == "agent_id" else "customer"})
            continue
        prefix = next((p for p in _ID_TABLES if rid.startswith(p)), None)
        if prefix is None:
            results.append({"record_id": rid, "exists": False, "table": None})
            continue
        table, col = _ID_TABLES[prefix]
        found = _query(
            f"SELECT COUNT(*) AS n FROM {DATASET_CLEAN}.{table} WHERE {col} = @rid", rid=rid
        )[0]["n"] > 0
        results.append({"record_id": rid, "exists": found, "table": table})
    return {"results": results, "missing": [r["record_id"] for r in results if not r["exists"]]}


def find_related_payments(payment_id: str) -> dict:
    """Find payments linked to a given payment: same policy, same customer or same receipt.

    Args:
        payment_id: The payment to compare against, e.g. "PAY000707".

    Returns:
        "related" payments (date, amount, mode, status, remittance, rule hits,
        link reasons), counts of reversed and bounced payments among them, days
        between this payment and its policy's issue date, and a "baseline" with
        how common these patterns are across all payments.
    """
    related = _attach_rule_hits(_query(
        f"""WITH t AS (SELECT * FROM {DATASET_CLEAN}.payments WHERE payment_id = @payment_id)
            SELECT p.payment_id, p.policy_id, p.customer_id, p.agent_id, p.payment_date,
                   p.payment_amount, p.payment_mode, p.payment_status, p.receipt_number,
                   p.premium_remitted_to_insurer, p.remittance_delay_days,
                   p.policy_id = t.policy_id AS same_policy,
                   p.customer_id = t.customer_id AS same_customer,
                   p.receipt_number = t.receipt_number AS same_receipt,
                   DATE_DIFF(p.payment_date, t.payment_date, DAY) AS days_from_this_payment
            FROM {DATASET_CLEAN}.payments p CROSS JOIN t
            WHERE p.payment_id != t.payment_id
              AND (p.policy_id = t.policy_id OR p.customer_id = t.customer_id
                   OR p.receipt_number = t.receipt_number)
            ORDER BY p.payment_date""",
        payment_id=payment_id,
    ), "payments", "payment_id")
    timing = _query(
        f"""SELECT DATE_DIFF(pay.payment_date, pol.issue_date, DAY) AS days_after_policy_issue
            FROM {DATASET_CLEAN}.payments pay
            JOIN {DATASET_CLEAN}.policies pol USING (policy_id)
            WHERE pay.payment_id = @payment_id""",
        payment_id=payment_id,
    )
    baseline = _query(
        f"""SELECT
              ROUND(AVG(IF(payment_status = 'Reversed', 1, 0)), 3) AS share_reversed,
              ROUND(AVG(IF(payment_status = 'Bounced', 1, 0)), 3) AS share_bounced,
              ROUND(AVG(IF(payment_mode = 'Cash', 1, 0)), 3) AS share_cash,
              ROUND(AVG(IF(pay.payment_date < pol.issue_date, 1, 0)), 3)
                AS share_paid_before_policy_issue,
              (SELECT COUNT(*) FROM (SELECT receipt_number FROM {DATASET_CLEAN}.payments
                                     GROUP BY receipt_number HAVING COUNT(*) > 1))
                AS receipt_numbers_used_twice
            FROM {DATASET_CLEAN}.payments pay
            JOIN {DATASET_CLEAN}.policies pol USING (policy_id)"""
    )[0]
    return {
        "payment_id": payment_id,
        "days_after_policy_issue": timing[0]["days_after_policy_issue"] if timing else None,
        "related": related,
        "related_reversed": sum(r["payment_status"] == "Reversed" for r in related),
        "related_bounced": sum(r["payment_status"] == "Bounced" for r in related),
        "baseline": {
            **baseline,
            "note": "Shares across ALL payments. A pattern most payments share is not evidence. "
                    "is_duplicate_receipt is set by the payments system; receipt numbers in this "
                    "data are otherwise unique.",
        },
    }


def get_agent_sales(agent_id: str) -> dict:
    """Get every ghost-broking sale record for an agent, with a license summary.

    Args:
        agent_id: Agent ID, e.g. "AGT00311".

    Returns:
        "sales": each record (customer, policy, license status and expiry,
        premium collected and deposited, customer awareness, complaints, rule
        hits); a summary (license statuses seen, premiums not deposited,
        customers unaware, total complaints); and a "baseline" across all agents.
    """
    sales = _attach_rule_hits(_query(
        f"""SELECT record_id, agent_name, customer_id, policy_id, license_status,
                   license_expiry_date, premium_collected, premium_deposited_with_insurer,
                   customer_aware_of_agent_status, complaint_count, agent_office_city,
                   dq_valid_license_expired, dq_agent_license_conflict
            FROM {DATASET_CLEAN}.ghost_broking WHERE agent_id = @agent_id
            ORDER BY record_id""",
        agent_id=agent_id,
    ), "ghost_broking", "record_id")
    baseline = _query(
        f"""SELECT
              ROUND(AVG(IF(nonvalid > 0, 1, 0)), 2) AS share_of_agents_with_nonvalid_license,
              ROUND(AVG(not_deposited / n), 3) AS avg_share_not_deposited,
              ROUND(AVG(complaints / n), 2) AS avg_complaints_per_record
            FROM (
              SELECT agent_id, COUNT(*) AS n,
                     COUNTIF(license_status != 'Valid') AS nonvalid,
                     COUNTIF(NOT premium_deposited_with_insurer) AS not_deposited,
                     SUM(complaint_count) AS complaints
              FROM {DATASET_CLEAN}.ghost_broking GROUP BY agent_id)"""
    )[0]
    statuses: dict[str, int] = {}
    for r in sales:
        statuses[r["license_status"]] = statuses.get(r["license_status"], 0) + 1
    return {
        "agent_id": agent_id,
        "summary": {
            "records": len(sales),
            "license_statuses": statuses,
            "premiums_not_deposited": sum(not r["premium_deposited_with_insurer"] for r in sales),
            "customers_unaware": sum(not r["customer_aware_of_agent_status"] for r in sales),
            "total_complaints": sum(r["complaint_count"] for r in sales),
        },
        "sales": sales,
        "baseline": {**baseline, "note": "Averages across ALL agents in the ghost-broking data."},
    }


def get_policy_baseline(policy_type: str, channel: str) -> dict:
    """Get typical figures for policies of a type sold through a channel, for comparison.

    Args:
        policy_type: One of "Auto", "Health", "Life", "Property", "Travel".
        channel: One of "Agent", "Online", "Broker", "Bancassurance".

    Returns:
        Number of such policies, median and 90th-percentile sum-insured-to-premium
        ratio, and the share cancelled, cancelled in the free-look window,
        backdated, and with premium not collected; plus the share of customers
        holding policies through more than one agent (all policies).
    """
    rows = _query(
        f"""SELECT COUNT(*) AS policies,
                   APPROX_QUANTILES(SAFE_DIVIDE(sum_insured, premium_amount), 10)[OFFSET(5)]
                     AS median_sum_insured_to_premium,
                   APPROX_QUANTILES(SAFE_DIVIDE(sum_insured, premium_amount), 10)[OFFSET(9)]
                     AS p90_sum_insured_to_premium,
                   ROUND(AVG(IF(policy_status = 'Cancelled', 1, 0)), 3) AS share_cancelled,
                   ROUND(AVG(IF(free_look_cancelled, 1, 0)), 3) AS share_free_look_cancelled,
                   ROUND(AVG(IF(backdated_flag, 1, 0)), 3) AS share_backdated,
                   ROUND(AVG(IF(NOT premium_actually_collected, 1, 0)), 3)
                     AS share_premium_not_collected
            FROM {DATASET_CLEAN}.policies
            WHERE policy_type = @policy_type AND channel = @channel""",
        policy_type=policy_type,
        channel=channel,
    )[0]
    multi_agent = _query(
        f"""SELECT ROUND(AVG(IF(agents > 1, 1, 0)), 3) AS share_customers_with_multiple_agents
            FROM (SELECT customer_id, COUNT(DISTINCT agent_id) AS agents
                  FROM {DATASET_CLEAN}.policies GROUP BY customer_id)"""
    )[0]
    return {"policy_type": policy_type, "channel": channel, **rows, **multi_agent}


def _entity_kind(entity_id: str) -> tuple[str, str, str] | None:
    if entity_id.startswith("AGT"):
        return "agent", "agent_id", "customer_id"
    if entity_id.startswith("CUST"):
        return "customer", "customer_id", "agent_id"
    return None


def get_entity_network(entity_id: str) -> dict:
    """Get an agent's or customer's network: alerts, connections and unflagged records.

    Args:
        entity_id: An agent ID (AGT...) or customer ID (CUST...).

    Returns:
        "risk": alert counts, files with alerts, alert rate, percentile and hub
        status; "connections": the customers (for an agent) or agents (for a
        customer) linked to it, with their own alerts and hub status;
        "shared_links": other agents serving the same flagged customers (agents
        only); "alerted_records" and "unflagged_records" (records with no alert,
        up to 50); and a "baseline" for the entity type.
    """
    kind = _entity_kind(entity_id)
    if kind is None:
        return {"error": f"{entity_id} is not an agent (AGT...) or customer (CUST...) ID"}
    entity_type, col, other = kind
    risk = _query(
        f"""SELECT * EXCEPT (built_at) FROM {DATASET_FEATURES}.entity_risk
            WHERE entity_type = @t AND entity_id = @id""",
        t=entity_type, id=entity_id,
    )
    if not risk:
        return {"error": f"{entity_id} not found"}
    records_sql = f"""
        WITH rec AS (
          SELECT 'claims' AS record_table, claim_id AS record_id, agent_id, customer_id FROM {DATASET_CLEAN}.claims
          UNION ALL SELECT 'policies', policy_id, agent_id, customer_id FROM {DATASET_CLEAN}.policies
          UNION ALL SELECT 'payments', payment_id, agent_id, customer_id FROM {DATASET_CLEAN}.payments
          UNION ALL SELECT 'ghost_broking', record_id, agent_id, customer_id FROM {DATASET_CLEAN}.ghost_broking)
        SELECT rec.*, a.max_severity, a.alert_source, a.priority
        FROM rec LEFT JOIN {DATASET_FEATURES}.alerts a USING (record_table, record_id)
        WHERE rec.{col} = @id"""
    alerted = _query(
        records_sql + " AND a.record_id IS NOT NULL ORDER BY a.priority DESC, record_table, record_id",
        id=entity_id,
    )
    unflagged = _query(
        records_sql + " AND a.record_id IS NULL ORDER BY record_table, record_id", id=entity_id
    )
    connections = _query(
        f"""WITH rec AS (
              SELECT agent_id, customer_id FROM {DATASET_CLEAN}.claims
              UNION ALL SELECT agent_id, customer_id FROM {DATASET_CLEAN}.policies
              UNION ALL SELECT agent_id, customer_id FROM {DATASET_CLEAN}.payments
              UNION ALL SELECT agent_id, customer_id FROM {DATASET_CLEAN}.ghost_broking)
            SELECT e.entity_id, e.records, e.alerts, e.tables_with_alerts, e.is_hub
            FROM (SELECT DISTINCT {other} AS entity_id FROM rec WHERE {col} = @id) c
            JOIN {DATASET_FEATURES}.entity_risk e
              ON e.entity_id = c.entity_id AND e.entity_type = @other_type
            ORDER BY e.alerts DESC, e.entity_id""",
        id=entity_id, other_type="customer" if entity_type == "agent" else "agent",
    )
    shared = []
    if entity_type == "agent":
        shared = _query(
            f"""WITH rec AS (
                  SELECT agent_id, customer_id FROM {DATASET_CLEAN}.claims
                  UNION ALL SELECT agent_id, customer_id FROM {DATASET_CLEAN}.policies
                  UNION ALL SELECT agent_id, customer_id FROM {DATASET_CLEAN}.payments
                  UNION ALL SELECT agent_id, customer_id FROM {DATASET_CLEAN}.ghost_broking),
                flagged_customers AS (
                  SELECT DISTINCT a.customer_id FROM {DATASET_FEATURES}.alerts a
                  WHERE a.agent_id = @id)
                SELECT r.agent_id, COUNT(DISTINCT r.customer_id) AS shared_flagged_customers,
                       ANY_VALUE(e.alerts) AS alerts, ANY_VALUE(e.is_hub) AS is_hub
                FROM rec r
                JOIN flagged_customers f USING (customer_id)
                JOIN {DATASET_FEATURES}.entity_risk e
                  ON e.entity_type = 'agent' AND e.entity_id = r.agent_id
                WHERE r.agent_id != @id
                GROUP BY r.agent_id
                ORDER BY shared_flagged_customers DESC, alerts DESC
                LIMIT 15""",
            id=entity_id,
        )
    baseline = _query(
        f"""SELECT APPROX_QUANTILES(alerts, 2)[OFFSET(1)] AS median_alerts,
                   APPROX_QUANTILES(alerts, 10)[OFFSET(9)] AS p90_alerts,
                   ROUND(AVG(IF(is_hub, 1, 0)), 3) AS share_hubs
            FROM {DATASET_FEATURES}.entity_risk WHERE entity_type = @t""",
        t=entity_type,
    )[0]
    return {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "risk": risk[0],
        "connections": connections[:MAX_ROWS],
        "shared_links": shared,
        "alerted_records": alerted,
        "unflagged_records": [
            {k: r[k] for k in ("record_table", "record_id", "agent_id", "customer_id")}
            for r in unflagged
        ],
        "unflagged_total": risk[0]["records"] - risk[0]["alerts"],
        "baseline": {
            **baseline,
            "note": f"Across ALL {entity_type}s. Unflagged records of hub agents are fraud about "
                    "4 times as often as records of other agents.",
        },
    }


def list_hub_entities(entity_type: str, limit: int = 20) -> dict:
    """List the agents or customers most strongly tied to alerts.

    Args:
        entity_type: "agent" or "customer".
        limit: How many to return (default 20, max 50).

    Returns:
        "entities": ID, records, alerts, critical alerts, files with alerts,
        flagged counterparts and hub status, highest alert count first.
    """
    if entity_type not in ("agent", "customer"):
        return {"error": 'entity_type must be "agent" or "customer"'}
    rows = _query(
        f"""SELECT entity_id, records, alerts, critical_alerts, tables_with_alerts, alert_tables,
                   flagged_counterparts, is_hub
            FROM {DATASET_FEATURES}.entity_risk WHERE entity_type = @t
            ORDER BY alerts DESC, critical_alerts DESC, entity_id
            LIMIT @limit""",
        t=entity_type, limit=min(max(limit, 1), MAX_ROWS),
    )
    return {"entity_type": entity_type, "entities": rows}


def get_case_context(record_table: str, record_id: str) -> dict:
    """Get everything usually needed to investigate one record, in a single call.

    Fetches the record, its rule hits and model score, the related records, the
    agent's profile and the baselines together, instead of one tool call each.

    Args:
        record_table: One of "claims", "policies", "payments", "ghost_broking".
        record_id: The record's ID, e.g. "CLM000263".

    Returns:
        "alert" (why it was flagged, if it is in the queue), "record" (with rule
        hits), and the context for its type: related claims or payments, the
        agent's profile or sales, the customer's history, and policy baselines.
        {"error": ...} if the record does not exist.
    """
    loaders = {
        "claims": get_claim, "policies": get_policy,
        "payments": get_payment, "ghost_broking": get_ghost_broking_record,
    }
    if record_table not in loaders:
        return {"error": f"unknown table {record_table}; use one of {sorted(loaders)}"}

    first = _in_parallel({
        "record": (loaders[record_table], record_id),
        "alert": (get_alert, record_table, record_id),
    })
    record = first["record"]
    if "error" in record:
        return record
    alert = first["alert"]
    context: dict[str, Any] = {
        "record_table": record_table,
        "record_id": record_id,
        "alert": None if "error" in alert else alert,
        "record": record,
    }

    agent_id, customer_id = record.get("agent_id"), record.get("customer_id")
    calls: dict[str, tuple] = {}
    if agent_id:
        calls["agent_profile"] = (get_agent_profile, agent_id)
    if record_table == "claims":
        calls["related_claims"] = (find_related_claims, record_id)
    elif record_table == "payments":
        calls["related_payments"] = (find_related_payments, record_id)
    elif record_table == "ghost_broking" and agent_id:
        calls["agent_sales"] = (get_agent_sales, agent_id)
    elif record_table == "policies":
        if customer_id:
            calls["customer_history"] = (get_customer_history, customer_id)
        if record.get("policy_type") and record.get("channel"):
            calls["policy_baseline"] = (get_policy_baseline, record["policy_type"], record["channel"])
    context.update(_in_parallel(calls))
    return context


CLAIM_TOOLS = [get_case_context, get_claim, get_policy, get_customer_history,
               get_agent_profile, find_related_claims]
CONTEXT_TOOLS = [
    get_case_context, get_alert, get_policy, get_payment, get_ghost_broking_record,
    get_customer_history, get_agent_profile,
]
REVIEW_TOOLS = [check_record_ids, get_records, get_record, get_agent_profile, find_related_claims]
POLICY_TOOLS = [get_case_context, get_policy, get_policy_baseline, get_customer_history, get_agent_profile]
PAYMENT_TOOLS = [get_case_context, get_payment, find_related_payments, get_policy, get_agent_profile,
                 get_customer_history]
GHOST_BROKING_TOOLS = [get_case_context, get_ghost_broking_record, get_agent_sales, get_agent_profile,
                       get_customer_history]
NETWORK_TOOLS = [get_entity_network, list_hub_entities, get_agent_profile, get_agent_sales,
                 get_customer_history]
