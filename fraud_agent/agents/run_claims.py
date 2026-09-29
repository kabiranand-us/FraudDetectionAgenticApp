"""Run the claims agent on one or more claims, optionally scoring it against labels.

    uv run fraud-investigate CLM000004 CLM000017     # print findings
    uv run fraud-investigate --sample 20             # stratified sample (tune split) + evaluation
    uv run fraud-investigate --sample 20 --split test   # held-out split, for final numbers
    uv run fraud-investigate --sample 20 --save      # also append to fraud_cases.claim_findings

Evaluation uses the labels (fraud_flag, fraud_type), which the agent's tools never see.
Claims are split in half by a fixed hash: tune prompts on "tune", report on "test".
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone

from google.adk.runners import InMemoryRunner
from google.cloud import bigquery
from google.genai import types

from fraud_agent.agents.claims_agent.agent import claims_agent
from fraud_agent.agents.schemas import ClaimFindings
from fraud_agent.config import DATASET_CASES, DATASET_CLEAN, DATASET_FEATURES, get_settings

APP_NAME = "fraud_claims"
SPLITS = {"tune": 0, "test": 1}
RETRY_WAIT_S = 90
# Vertex AI quota (429) and transient server errors, both worth one retry.
RETRYABLE = ("RESOURCE_EXHAUSTED", "500 INTERNAL", "503 UNAVAILABLE", "UNAVAILABLE")
USER_ID = "investigator"


async def investigate(runner: InMemoryRunner, claim_id: str) -> ClaimFindings:
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
    message = types.Content(role="user", parts=[types.Part(text=f"Investigate claim {claim_id}.")])
    async for _ in runner.run_async(user_id=USER_ID, session_id=session.id, new_message=message):
        pass
    session = await runner.session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session.id
    )
    output = session.state.get(claims_agent.output_key)
    if output is None:
        raise RuntimeError(f"{claim_id}: agent returned no findings")
    if isinstance(output, str):
        return ClaimFindings.model_validate_json(output)
    return ClaimFindings.model_validate(output)


def sample_claims(client: bigquery.Client, n: int, split: str) -> list[str]:
    """Stratified within a split: critical-rule hits, high model scores, medium-only rule hits, no hits."""
    per_group = max(1, n // 4)
    rows = client.query(f"""
        WITH s AS (
          SELECT c.claim_id,
            CASE
              WHEN r.rule_score >= 1.0 THEN 'critical_rule'
              WHEN m.model_score >= 0.6 THEN 'high_model'
              WHEN r.rule_score > 0 THEN 'medium_rule'
              ELSE 'no_hits'
            END AS grp
          FROM {DATASET_CLEAN}.claims c
          JOIN {DATASET_FEATURES}.rule_scores r
            ON r.record_table = 'claims' AND r.record_id = c.claim_id
          JOIN {DATASET_FEATURES}.claim_model_scores m USING (claim_id)
          WHERE MOD(ABS(FARM_FINGERPRINT(CONCAT('split:', c.claim_id))), 2) = {SPLITS[split]}
        )
        SELECT claim_id FROM s
        QUALIFY ROW_NUMBER() OVER (PARTITION BY grp ORDER BY FARM_FINGERPRINT(claim_id)) <= {per_group}
        ORDER BY claim_id
    """).result()
    return [r.claim_id for r in rows]


def labels_for(client: bigquery.Client, claim_ids: list[str]) -> dict[str, tuple[bool, str | None, float]]:
    rows = client.query(
        f"""SELECT c.claim_id, c.fraud_flag, c.fraud_type, r.rule_score
            FROM {DATASET_CLEAN}.claims c
            JOIN {DATASET_FEATURES}.rule_scores r
              ON r.record_table = 'claims' AND r.record_id = c.claim_id
            WHERE c.claim_id IN UNNEST(@ids)""",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ArrayQueryParameter("ids", "STRING", claim_ids)]
        ),
    ).result()
    return {r.claim_id: (r.fraud_flag, r.fraud_type, r.rule_score) for r in rows}


def _pr(flags: list[bool], truth: list[bool]) -> str:
    tp = sum(f and t for f, t in zip(flags, truth))
    n = sum(flags)
    precision = f"{tp / n:.0%}" if n else "-"
    return f"flagged {n:>2}   precision {precision:>4}   recall {tp / sum(truth):.0%}"


def evaluate(results: dict[str, ClaimFindings], labels: dict[str, tuple[bool, str | None, float]]) -> None:
    print(f"\n{'claim':<11}{'label':<30}{'agent risk':<12}{'agent types'}")
    for claim_id, f in results.items():
        fraud_type = labels[claim_id][1]
        print(f"{claim_id:<11}{(fraud_type or 'not fraud'):<30}{f.risk_level:<12}"
              f"{', '.join(f.suspected_fraud_types) or '-'}")

    ids = list(results)
    truth = [labels[i][0] for i in ids]
    if not any(truth):
        print("\nNo fraud in this sample; nothing to score.")
        return
    print(f"\n{len(ids)} claims, {sum(truth)} fraud")
    print("  by agent risk level:")
    for level in ("critical", "high", "medium", "low"):
        in_level = [i for i in ids if results[i].risk_level == level]
        fraud = sum(labels[i][0] for i in in_level)
        print(f"    {level:<9}{len(in_level):>3} claims, {fraud:>2} fraud")
    print("  on the same claims:")
    rows = [
        ("agent: critical", [results[i].risk_level == "critical" for i in ids]),
        ("agent: high or critical", [results[i].risk_level in ("high", "critical") for i in ids]),
        ("rules: critical only", [labels[i][2] >= 1.0 for i in ids]),
        ("rules: any hit", [labels[i][2] > 0 for i in ids]),
    ]
    for name, flags in rows:
        print(f"    {name:<26}{_pr(flags, truth)}")
    named = sum(1 for i in ids if labels[i][0] and labels[i][1] in results[i].suspected_fraud_types)
    print(f"  correct fraud type named: {named}/{sum(truth)}")


def save(client: bigquery.Client, results: dict[str, ClaimFindings], model: str) -> None:
    table = f"{client.project}.{DATASET_CASES}.claim_findings"
    schema = [
        bigquery.SchemaField("claim_id", "STRING"),
        bigquery.SchemaField("risk_level", "STRING"),
        bigquery.SchemaField("suspected_fraud_types", "STRING", mode="REPEATED"),
        bigquery.SchemaField("recommended_action", "STRING"),
        bigquery.SchemaField("findings_json", "JSON"),
        bigquery.SchemaField("agent_model", "STRING"),
        bigquery.SchemaField("created_at", "TIMESTAMP"),
    ]
    now = datetime.now(timezone.utc).isoformat()
    rows = [{
        "claim_id": f.claim_id,
        "risk_level": f.risk_level,
        "suspected_fraud_types": list(f.suspected_fraud_types),
        "recommended_action": f.recommended_action,
        "findings_json": f.model_dump(mode="json"),
        "agent_model": model,
        "created_at": now,
    } for f in results.values()]
    job = client.load_table_from_json(
        rows, table,
        job_config=bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_APPEND"),
    )
    job.result()
    print(f"\nAppended {len(rows)} rows to {DATASET_CASES}.claim_findings")


async def run(claim_ids: list[str]) -> dict[str, ClaimFindings]:
    runner = InMemoryRunner(agent=claims_agent, app_name=APP_NAME)
    results = {}
    for claim_id in claim_ids:
        for attempt in (1, 2):
            try:
                results[claim_id] = await investigate(runner, claim_id)
                print(f"  {claim_id}: {results[claim_id].risk_level}", flush=True)
                break
            except Exception as e:  # keep going; report the failure
                if attempt == 1 and any(m in str(e) for m in RETRYABLE):
                    print(f"  {claim_id}: model error, retrying in {RETRY_WAIT_S}s", flush=True)
                    await asyncio.sleep(RETRY_WAIT_S)
                    continue
                print(f"  {claim_id}: FAILED {type(e).__name__}: {str(e)[:200]}", flush=True)
                break
    return results


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("claim_ids", nargs="*")
    parser.add_argument("--sample", type=int, help="stratified sample size, with evaluation")
    parser.add_argument("--split", choices=SPLITS, default="tune",
                        help="which half of the claims to sample from (default tune)")
    parser.add_argument("--save", action="store_true", help="append findings to BigQuery")
    args = parser.parse_args()
    if not args.claim_ids and not args.sample:
        parser.error("give claim IDs or --sample N")

    client = bigquery.Client(project=settings.project_id, location=settings.location)
    claim_ids = args.claim_ids or sample_claims(client, args.sample, args.split)
    print(f"Investigating {len(claim_ids)} claims with {settings.agent_model}")
    results = asyncio.run(run(claim_ids))

    if args.sample:
        evaluate(results, labels_for(client, list(results)))
    else:
        for f in results.values():
            print(json.dumps(f.model_dump(), indent=2))
    if args.save and results:
        save(client, results, settings.agent_model)


if __name__ == "__main__":
    main()
