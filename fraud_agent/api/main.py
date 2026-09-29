
import argparse
import asyncio
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from fraud_agent.api import store
from fraud_agent.config import ROOT, get_settings

FRONTEND_DIST = ROOT / "frontend" / "dist"

app = FastAPI(title="Fraud investigations", docs_url="/api/docs", openapi_url="/api/openapi.json")

# job_id -> {"state": running|done|failed, "kind", "target", "detail"}
JOBS: dict[str, dict[str, Any]] = {}


class DecisionIn(BaseModel):
    decision: Literal["confirmed_fraud", "not_fraud", "needs_more_info"]
    fraud_type: str | None = None
    note: str = ""
    investigator: str = ""


class JobOut(BaseModel):
    job_id: str
    state: Literal["running", "done", "failed"]
    kind: str
    target: str
    detail: str = Field("", description="Error message when the job failed.")
    stage: str = Field("", description="What the agents are doing right now.")
    step: str = Field("", description="The lookup in progress, when there is one.")
    started_at: float = 0.0


def _jsonable(v):
    """BigQuery arrays arrive as numpy arrays, numbers as numpy scalars."""
    if isinstance(v, np.ndarray):
        return [_jsonable(x) for x in v.tolist()]
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    if v is pd.NaT or (isinstance(v, float) and pd.isna(v)):
        return None
    return v


def _records(df) -> list[dict]:
    rows = df.astype(object).where(df.notna(), None).to_dict("records")
    return [{k: _jsonable(v) for k, v in row.items()} for row in rows]


def _split(alert_id: str) -> tuple[str, str]:
    table, _, record_id = alert_id.partition(":")
    if not record_id:
        raise HTTPException(400, "alert_id must look like claims:CLM000001")
    return table, record_id


def _start_job(kind: str, target: str, coro_factory) -> JobOut:
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {
        "state": "running", "kind": kind, "target": target, "detail": "",
        "stage": "Starting", "step": "", "started_at": time.time(),
    }

    def on_progress(stage: str, step: str) -> None:
        JOBS[job_id].update(stage=stage, step=step)

    async def runner():
        try:
            await coro_factory(on_progress)
            JOBS[job_id].update(state="done", stage="Done", step="")
        except Exception as e:  # surfaced to the UI, not swallowed
            JOBS[job_id].update(state="failed", stage="Failed", step="",
                                detail=f"{type(e).__name__}: {e}"[:400])

    asyncio.get_running_loop().create_task(runner())
    return JobOut(job_id=job_id, **JOBS[job_id])


@app.on_event("startup")
async def _startup() -> None:
    await asyncio.to_thread(store.ensure_tables)


@app.get("/api/alerts")
async def alerts() -> list[dict]:
    return await asyncio.to_thread(lambda: _records(store.alert_queue()))


@app.get("/api/alerts/{alert_id}")
async def alert(alert_id: str) -> dict:
    from fraud_agent.tools.bigquery_tools import get_alert, get_record
    table, record_id = _split(alert_id)

    def load() -> dict:
        detail = get_alert(table, record_id)
        if "error" in detail:
            raise HTTPException(404, detail["error"])
        found = store.latest_case(alert_id)
        return {
            "alert": detail,
            "record": get_record(table, record_id),
            "case": found["case"] if found else None,
            "review": found["review"] if found else None,
            "case_created_at": found["created_at"].isoformat() if found else None,
            "agent_model": found["agent_model"] if found else None,
            "decisions": _records(store.decisions_for(alert_id)),
        }

    return await asyncio.to_thread(load)


@app.post("/api/alerts/{alert_id}/investigate")
async def investigate(alert_id: str) -> JobOut:
    from fraud_agent.agents.run_cases import run, save
    table, record_id = _split(alert_id)

    async def job(on_progress):
        cases = await run([(table, record_id)], on_progress=on_progress)
        if not cases:
            raise RuntimeError("the agents did not finish (often a Vertex AI quota limit)")
        await asyncio.to_thread(save, store.client(), cases, get_settings().agent_model)

    return _start_job("investigate", alert_id, job)


@app.get("/api/networks")
async def networks(entity_type: str = "agent", limit: int = 50) -> list[dict]:
    return await asyncio.to_thread(lambda: _records(store.hubs(entity_type, limit)))


@app.get("/api/networks/{entity_id}")
async def network(entity_id: str) -> dict:
    from fraud_agent.tools.bigquery_tools import get_entity_network

    def load() -> dict:
        net = get_entity_network(entity_id)
        if "error" in net:
            raise HTTPException(404, net["error"])
        found = store.latest_network_findings(entity_id)
        return {
            "network": net,
            "findings": found["findings"] if found else None,
            "findings_created_at": found["created_at"].isoformat() if found else None,
        }

    return await asyncio.to_thread(load)


@app.post("/api/networks/{entity_id}/analyse")
async def analyse_network(entity_id: str) -> JobOut:
    from fraud_agent.agents.run_network import run, save

    async def job(on_progress):
        results = await run([entity_id], on_progress=on_progress)
        if not results:
            raise RuntimeError("the agent did not finish (often a Vertex AI quota limit)")
        await asyncio.to_thread(save, store.client(), results, get_settings().agent_model)

    return _start_job("network", entity_id, job)


@app.get("/api/jobs/{job_id}")
async def job(job_id: str) -> JobOut:
    if job_id not in JOBS:
        raise HTTPException(404, "unknown job")
    return JobOut(job_id=job_id, **JOBS[job_id])


@app.get("/api/decisions")
async def decisions() -> list[dict]:
    return await asyncio.to_thread(lambda: _records(store.all_decisions()))


@app.post("/api/alerts/{alert_id}/decision", status_code=201)
async def decide(alert_id: str, body: DecisionIn) -> dict:
    table, record_id = _split(alert_id)
    if body.decision == "confirmed_fraud" and not body.fraud_type:
        raise HTTPException(400, "choose the fraud type you are confirming")
    found = await asyncio.to_thread(store.latest_case, alert_id)
    await asyncio.to_thread(
        store.save_decision, alert_id, table, record_id, body.decision, body.fraud_type,
        body.note, body.investigator, found["created_at"] if found else None,
    )
    return {"saved": True}


@app.get("/api/fraud-types")
async def fraud_types() -> dict[str, list[str]]:
    from fraud_agent.agents.schemas import FRAUD_TYPES_BY_TABLE
    return {t: list(types) for t, types in FRAUD_TYPES_BY_TABLE.items()}


if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str) -> FileResponse:
        """Serve the React app; unknown paths fall back to index.html."""
        candidate = FRONTEND_DIST / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")


def main() -> None:
    import uvicorn
    parser = argparse.ArgumentParser(description=(__doc__ or "Investigator API").splitlines()[0])
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    if not FRONTEND_DIST.is_dir():
        print(f"No built frontend at {FRONTEND_DIST}: serving the API only. "
              "Run 'npm run build' in frontend/, or 'npm run dev' for development.")
    uvicorn.run("fraud_agent.api.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
