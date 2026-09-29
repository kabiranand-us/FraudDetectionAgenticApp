"""Run the network agent on agents or customers, and score its review suggestions.

    uv run fraud-network AGT00340                  # one entity, print findings
    uv run fraud-network --top 5                   # the 5 agents with the most alerts
    uv run fraud-network --top 5 --save            # also append to fraud_cases.network_findings

With --top, the records the agent recommends for review (records no rule or model
flagged) are checked against the labels, which its tools never see, and compared
with the fraud rate of all unflagged records.
"""

import argparse
import asyncio
import json
from collections.abc import Callable
from datetime import datetime, timezone

from google.adk.runners import InMemoryRunner
from google.cloud import bigquery
from google.genai import types

from fraud_agent.agents.network_agent.agent import network_agent
from fraud_agent.agents.schemas import NetworkFindings
from fraud_agent.config import DATASET_CASES, DATASET_CLEAN, DATASET_FEATURES, get_settings
from fraud_agent.ingest.schemas import RAW_TABLES

APP_NAME = "fraud_network"
USER_ID = "investigator"
RETRY_WAIT_S = 90
# Vertex AI quota (429) and transient server errors, both worth one retry.
RETRYABLE = ("RESOURCE_EXHAUSTED", "500 INTERNAL", "503 UNAVAILABLE", "UNAVAILABLE")


async def investigate(
    runner: InMemoryRunner, entity_id: str,
    on_progress: Callable[[str, str], None] | None = None,
) -> NetworkFindings:
    kind = "agent" if entity_id.startswith("AGT") else "customer"
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
    message = types.Content(role="user", parts=[types.Part(text=f"Investigate {kind} {entity_id}.")])
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session.id, new_message=message
    ):
        if on_progress:
            for part in getattr(getattr(event, "content", None), "parts", None) or []:
                call = getattr(part, "function_call", None)
                if call is not None:
                    on_progress("Checking the network", f"looking up {call.name}")
    session = await runner.session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session.id
    )
    output = session.state.get(network_agent.output_key)
    if output is None:
        raise RuntimeError(f"{entity_id}: agent returned no findings")
    if isinstance(output, str):
        return NetworkFindings.model_validate_json(output)
    return NetworkFindings.model_validate(output)


async def run(
    entity_ids: list[str], on_progress: Callable[[str, str], None] | None = None,
) -> dict[str, NetworkFindings]:
    runner = InMemoryRunner(agent=network_agent, app_name=APP_NAME)
    results = {}
    for entity_id in entity_ids:
        for attempt in (1, 2):
            try:
                f = results[entity_id] = await investigate(runner, entity_id, on_progress=on_progress)
                print(f"  {entity_id}: {f.pattern}, {f.risk_level}, "
                      f"{len(f.records_to_review)} records to review", flush=True)
                break
            except Exception as e:  # keep going; report the failure
                if attempt == 1 and any(m in str(e) for m in RETRYABLE):
                    print(f"  {entity_id}: model error, retrying in {RETRY_WAIT_S}s", flush=True)
                    await asyncio.sleep(RETRY_WAIT_S)
                    continue
                print(f"  {entity_id}: FAILED {type(e).__name__}: {str(e)[:200]}", flush=True)
                break
    return results


def top_agents(client: bigquery.Client, n: int) -> list[str]:
    rows = client.query(f"""
        SELECT entity_id FROM {DATASET_FEATURES}.entity_risk
        WHERE entity_type = 'agent'
        ORDER BY alerts DESC, critical_alerts DESC, entity_id LIMIT {int(n)}
    """).result()
    return [r.entity_id for r in rows]


def _labels_sql() -> str:
    return " UNION ALL ".join(
        f"SELECT {t.id_column} AS record_id, agent_id, customer_id, fraud_flag "
        f"FROM {DATASET_CLEAN}.{t.name}"
        for t in RAW_TABLES
    )


def evaluate(client: bigquery.Client, results: dict[str, NetworkFindings]) -> None:
    suggested = sorted({rid for f in results.values() for rid in f.records_to_review})
    entities = list(results)
    rows = client.query(
        f"""WITH lab AS ({_labels_sql()}),
                unflagged AS (
                  SELECT lab.* FROM lab
                  LEFT JOIN {DATASET_FEATURES}.alerts a ON a.record_id = lab.record_id
                  WHERE a.record_id IS NULL)
            SELECT
              (SELECT COUNTIF(fraud_flag) FROM lab WHERE record_id IN UNNEST(@suggested)) AS sug_fraud,
              (SELECT COUNT(*) FROM lab WHERE record_id IN UNNEST(@suggested)) AS sug_n,
              (SELECT COUNTIF(fraud_flag) FROM unflagged
                 WHERE agent_id IN UNNEST(@entities) OR customer_id IN UNNEST(@entities)) AS ent_fraud,
              (SELECT COUNT(*) FROM unflagged
                 WHERE agent_id IN UNNEST(@entities) OR customer_id IN UNNEST(@entities)) AS ent_n,
              (SELECT COUNTIF(fraud_flag) FROM unflagged) AS all_fraud,
              (SELECT COUNT(*) FROM unflagged) AS all_n""",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ArrayQueryParameter("suggested", "STRING", suggested),
            bigquery.ArrayQueryParameter("entities", "STRING", entities),
        ]),
    ).result()
    r = next(iter(rows))
    rate = lambda f, n: f"{f}/{n} = {f / n:.1%}" if n else "-"
    print("\nFraud rate among unflagged records (labels, report only):")
    print(f"  recommended for review by the agent   {rate(r.sug_fraud, r.sug_n)}")
    print(f"  all unflagged records of these entities {rate(r.ent_fraud, r.ent_n)}")
    print(f"  all unflagged records in the data     {rate(r.all_fraud, r.all_n)}")


def save(client: bigquery.Client, results: dict[str, NetworkFindings], model: str) -> None:
    table = f"{client.project}.{DATASET_CASES}.network_findings"
    schema = [
        bigquery.SchemaField("entity_id", "STRING"),
        bigquery.SchemaField("entity_type", "STRING"),
        bigquery.SchemaField("pattern", "STRING"),
        bigquery.SchemaField("risk_level", "STRING"),
        bigquery.SchemaField("records_to_review", "STRING", mode="REPEATED"),
        bigquery.SchemaField("findings_json", "JSON"),
        bigquery.SchemaField("agent_model", "STRING"),
        bigquery.SchemaField("created_at", "TIMESTAMP"),
    ]
    now = datetime.now(timezone.utc).isoformat()
    rows = [{
        "entity_id": f.entity_id,
        "entity_type": f.entity_type,
        "pattern": f.pattern,
        "risk_level": f.risk_level,
        "records_to_review": list(f.records_to_review),
        "findings_json": f.model_dump(mode="json"),
        "agent_model": model,
        "created_at": now,
    } for f in results.values()]
    client.load_table_from_json(
        rows, table,
        job_config=bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_APPEND"),
    ).result()
    print(f"\nAppended {len(rows)} rows to {DATASET_CASES}.network_findings")


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("entity_ids", nargs="*", help="agent (AGT...) or customer (CUST...) IDs")
    parser.add_argument("--top", type=int, help="investigate the N agents with the most alerts")
    parser.add_argument("--save", action="store_true", help="append findings to BigQuery")
    args = parser.parse_args()
    if not args.entity_ids and not args.top:
        parser.error("give entity IDs or --top N")

    client = bigquery.Client(project=settings.project_id, location=settings.location)
    entity_ids = args.entity_ids or top_agents(client, args.top)
    print(f"Investigating {len(entity_ids)} entities with {settings.agent_model}")
    results = asyncio.run(run(entity_ids))

    if args.top:
        evaluate(client, results)
    else:
        for f in results.values():
            print(json.dumps(f.model_dump(mode="json"), indent=2))
    if args.save and results:
        save(client, results, settings.agent_model)


if __name__ == "__main__":
    main()
