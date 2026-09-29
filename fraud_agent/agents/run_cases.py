"""Investigate alerts end to end (orchestrator -> case writer -> reviewer); print or save cases.

    uv run fraud-case claims CLM000593              # one alert, print the case file
    uv run fraud-case --top 8                       # top alerts, spread across the four tables
    uv run fraud-case --top 8 --save                # also append to fraud_cases.case_files

With --top, each case is also shown next to its label (fraud_flag, fraud_type),
which the agents' tools never see.
"""

import argparse
import asyncio
import json
from collections.abc import Callable
from datetime import datetime, timezone

from google.adk.runners import InMemoryRunner
from google.cloud import bigquery
from google.genai import types

from fraud_agent.agents.fraud_investigation.agent import case_writer, fraud_investigation, reviewer
from fraud_agent.agents.schemas import CaseFile, ReviewReport
from fraud_agent.config import DATASET_CASES, DATASET_CLEAN, DATASET_FEATURES, get_settings
from fraud_agent.ingest.schemas import RAW_TABLES

APP_NAME = "fraud_investigation"
USER_ID = "investigator"
RETRY_WAIT_S = 90
# Vertex AI quota (429) and transient server errors, both worth one retry.
RETRYABLE = ("RESOURCE_EXHAUSTED", "500 INTERNAL", "503 UNAVAILABLE", "UNAVAILABLE")
TABLES = {t.name: t for t in RAW_TABLES}


def _parse(model, output):
    if isinstance(output, str):
        return model.model_validate_json(output)
    return model.model_validate(output)


STAGE_NAMES = {
    "orchestrator": "Gathering the evidence",
    "claims_agent": "Claims specialist investigating",
    "policy_agent": "Policy specialist investigating",
    "payment_agent": "Payment specialist investigating",
    "ghost_broking_agent": "Ghost-broking specialist investigating",
    "network_agent": "Checking the agent's network",
    "case_writer": "Writing the case file",
    "reviewer": "Reviewer checking every fact",
}


def _progress_from(event) -> tuple[str, str] | None:
    """(stage, detail) for one ADK event, or None when it says nothing new."""
    stage = STAGE_NAMES.get(getattr(event, "author", ""), None)
    if stage is None:
        return None
    parts = getattr(getattr(event, "content", None), "parts", None) or []
    for part in parts:
        call = getattr(part, "function_call", None)
        if call is None:
            continue
        # Specialists are called as tools, so their events never reach this loop;
        # name them here instead.
        if call.name in STAGE_NAMES:
            return STAGE_NAMES[call.name], ""
        return stage, f"looking up {call.name}"
    return stage, ""


async def investigate(
    runner: InMemoryRunner, record_table: str, record_id: str,
    on_progress: Callable[[str, str], None] | None = None,
) -> tuple[CaseFile, ReviewReport]:
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
    message = types.Content(
        role="user", parts=[types.Part(text=f"Investigate alert: {record_table} {record_id}.")]
    )
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session.id, new_message=message
    ):
        if on_progress:
            update = _progress_from(event)
            if update:
                on_progress(*update)
    session = await runner.session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session.id
    )
    case = session.state.get(case_writer.output_key)
    review = session.state.get(reviewer.output_key)
    if case is None or review is None:
        raise RuntimeError(f"{record_table} {record_id}: pipeline did not finish "
                           f"(case file: {case is not None}, review: {review is not None})")
    return _parse(CaseFile, case), _parse(ReviewReport, review)


async def run(
    alerts: list[tuple[str, str]],
    on_progress: Callable[[str, str], None] | None = None,
) -> dict[tuple[str, str], tuple[CaseFile, ReviewReport]]:
    runner = InMemoryRunner(agent=fraud_investigation, app_name=APP_NAME)
    cases = {}
    for alert in alerts:
        for attempt in (1, 2):
            try:
                cases[alert] = await investigate(runner, *alert, on_progress=on_progress)
                case, review = cases[alert]
                print(f"  {alert[0]}:{alert[1]}: {case.risk_assessment} -> review "
                      f"{review.verdict} ({review.final_risk_assessment})", flush=True)
                break
            except Exception as e:  # keep going; report the failure
                if attempt == 1 and any(m in str(e) for m in RETRYABLE):
                    print(f"  {alert[0]}:{alert[1]}: model error, retrying in {RETRY_WAIT_S}s",
                          flush=True)
                    await asyncio.sleep(RETRY_WAIT_S)
                    continue
                print(f"  {alert[0]}:{alert[1]}: FAILED {type(e).__name__}: {str(e)[:200]}",
                      flush=True)
                break
    return cases


def top_alerts(client: bigquery.Client, n: int) -> list[tuple[str, str]]:
    """Highest-priority alerts, an equal share from each table."""
    per_table = max(1, n // len(TABLES))
    rows = client.query(f"""
        SELECT record_table, record_id FROM {DATASET_FEATURES}.alerts
        QUALIFY ROW_NUMBER() OVER (
          PARTITION BY record_table
          ORDER BY priority DESC, FARM_FINGERPRINT(record_id)) <= {per_table}
        ORDER BY record_table, record_id
    """).result()
    return [(r.record_table, r.record_id) for r in rows]


def labels_for(client: bigquery.Client, alerts: list[tuple[str, str]]) -> dict:
    selects = " UNION ALL ".join(
        f"SELECT '{t.name}' AS record_table, {t.id_column} AS record_id, fraud_flag, fraud_type "
        f"FROM {DATASET_CLEAN}.{t.name}"
        for t in RAW_TABLES
    )
    keys = [f"{t}:{i}" for t, i in alerts]
    rows = client.query(
        f"SELECT * FROM ({selects}) WHERE CONCAT(record_table, ':', record_id) IN UNNEST(@keys)",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ArrayQueryParameter("keys", "STRING", keys)]
        ),
    ).result()
    return {(r.record_table, r.record_id): (r.fraud_flag, r.fraud_type) for r in rows}


def print_comparison(cases: dict, labels: dict) -> None:
    print(f"\n{'alert':<24}{'label':<36}{'case':<10}{'review':<27}{'final'}")
    for alert, (case, review) in cases.items():
        fraud, fraud_type = labels[alert]
        print(f"{alert[0] + ':' + alert[1]:<24}{(fraud_type or 'not fraud'):<36}"
              f"{case.risk_assessment:<10}{review.verdict:<27}{review.final_risk_assessment}")
    named = sum(1 for a, (c, _) in cases.items()
                if labels[a][0] and labels[a][1] in c.suspected_fraud_types)
    n_fraud = sum(1 for a in cases if labels[a][0])
    print(f"\nCorrect fraud type named in {named} of {n_fraud} fraud alerts.")
    print_review_stats(cases)


def print_review_stats(cases: dict) -> None:
    checks = [ec for _, r in cases.values() for ec in r.evidence_checks]
    by_status = {s: sum(ec.status == s for ec in checks) for s in ("verified", "contradicted", "unverifiable")}
    missing = sum(len(r.missing_record_ids) for _, r in cases.values())
    changed = sum(c.risk_assessment != r.final_risk_assessment for c, r in cases.values())
    pruned = sum(set(c.suspected_fraud_types) != set(r.final_suspected_fraud_types)
                 for c, r in cases.values())
    print(f"Reviewer: {len(checks)} evidence items checked: {by_status['verified']} verified, "
          f"{by_status['contradicted']} contradicted, {by_status['unverifiable']} unverifiable; "
          f"{missing} missing IDs; risk changed on {changed} and fraud types on {pruned} "
          f"of {len(cases)} cases.")
    for alert, (_, review) in cases.items():
        for ec in review.evidence_checks:
            if ec.status != "verified":
                print(f"  {alert[1]} {ec.status}: {ec.fact[:90]} | data: {ec.note[:120]}")
        for issue in review.issues:
            print(f"  {alert[1]} issue: {issue[:200]}")


def save(client: bigquery.Client, cases: dict, model: str) -> None:
    table = f"{client.project}.{DATASET_CASES}.case_files"
    schema = [
        bigquery.SchemaField("alert_id", "STRING"),
        bigquery.SchemaField("record_table", "STRING"),
        bigquery.SchemaField("record_id", "STRING"),
        bigquery.SchemaField("risk_assessment", "STRING"),
        bigquery.SchemaField("suspected_fraud_types", "STRING", mode="REPEATED"),
        bigquery.SchemaField("recommended_action", "STRING"),
        bigquery.SchemaField("case_json", "JSON"),
        bigquery.SchemaField("review_verdict", "STRING"),
        bigquery.SchemaField("final_risk_assessment", "STRING"),
        bigquery.SchemaField("final_recommended_action", "STRING"),
        bigquery.SchemaField("final_suspected_fraud_types", "STRING", mode="REPEATED"),
        bigquery.SchemaField("review_json", "JSON"),
        bigquery.SchemaField("agent_model", "STRING"),
        bigquery.SchemaField("created_at", "TIMESTAMP"),
    ]
    now = datetime.now(timezone.utc).isoformat()
    rows = [{
        "alert_id": c.alert_id,
        "record_table": c.record_table,
        "record_id": c.record_id,
        "risk_assessment": c.risk_assessment,
        "suspected_fraud_types": list(c.suspected_fraud_types),
        "recommended_action": c.recommended_action,
        "case_json": c.model_dump(mode="json"),
        "review_verdict": r.verdict,
        "final_risk_assessment": r.final_risk_assessment,
        "final_recommended_action": r.final_recommended_action,
        "final_suspected_fraud_types": list(r.final_suspected_fraud_types),
        "review_json": r.model_dump(mode="json"),
        "agent_model": model,
        "created_at": now,
    } for c, r in cases.values()]
    client.load_table_from_json(
        rows, table,
        job_config=bigquery.LoadJobConfig(
            schema=schema,
            write_disposition="WRITE_APPEND",
            # Tables created before the reviewer existed lack the review columns.
            schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
        ),
    ).result()
    print(f"\nAppended {len(rows)} case files to {DATASET_CASES}.case_files")


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("record_table", nargs="?", choices=list(TABLES))
    parser.add_argument("record_id", nargs="?")
    parser.add_argument("--top", type=int, help="investigate the top N alerts across tables")
    parser.add_argument("--save", action="store_true", help="append case files to BigQuery")
    args = parser.parse_args()
    if not args.top and not (args.record_table and args.record_id):
        parser.error("give RECORD_TABLE RECORD_ID, or --top N")

    client = bigquery.Client(project=settings.project_id, location=settings.location)
    alerts = top_alerts(client, args.top) if args.top else [(args.record_table, args.record_id)]
    print(f"Investigating {len(alerts)} alert(s) with {settings.agent_model}")
    cases = asyncio.run(run(alerts))

    if args.top:
        print_comparison(cases, labels_for(client, list(cases)))
    else:
        for case, review in cases.values():
            print(json.dumps({"case_file": case.model_dump(mode="json"),
                              "review": review.model_dump(mode="json")}, indent=2))
        print_review_stats(cases)
    if args.save and cases:
        save(client, cases, settings.agent_model)


if __name__ == "__main__":
    main()
