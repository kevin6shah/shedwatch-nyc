from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import DecisionRequest, DecisionResponse, ReviewCase, ScanSnapshot
from app.state import SnapshotStore


app = FastAPI(
    title="Shedwatch NYC",
    description="Human-reviewed sidewalk-shed permit intelligence from NYC DOT cameras.",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
settings.evidence_dir.mkdir(parents=True, exist_ok=True)
app.mount("/evidence", StaticFiles(directory=settings.evidence_dir), name="evidence")
store = SnapshotStore(settings.snapshot_path)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(settings.static_dir / "index.html")


@app.get("/healthz")
@app.get("/api/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "shedwatch-nyc"}


@app.get("/api/scan-status")
async def scan_status() -> dict:
    screen_path = settings.checkpoint_dir / "citywide-screen.json"
    confirmation_path = settings.checkpoint_dir / "citywide-confirmations.json"
    try:
        screen = json.loads(screen_path.read_text())
        rows = list(screen.get("results", {}).values())
    except (OSError, ValueError):
        screen, rows = {}, []
    try:
        confirmations = json.loads(confirmation_path.read_text()).get("results", {})
    except (OSError, ValueError):
        confirmations = {}
    counts = {"no_shed": 0, "possible_shed": 0, "likely_shed": 0}
    for row in rows:
        classification = row.get("classification")
        if classification in counts:
            counts[classification] += 1
    latest = store.get_snapshot()
    if latest.scope == "citywide" and len(rows) >= 957:
        stage = "complete"
    elif len(rows) >= 957:
        stage = "verifying candidates"
    else:
        stage = "screening"
    return {
        "stage": stage,
        "screened": len(rows),
        "total": 957,
        "confirmations": len(confirmations) if len(rows) >= 957 else 0,
        "classifications": counts,
        "updated_at": screen.get("updated_at"),
    }


@app.get("/api/snapshot", response_model=ScanSnapshot)
async def snapshot() -> ScanSnapshot:
    return store.get_snapshot()


@app.get("/api/cases/{case_id}", response_model=ReviewCase)
async def case(case_id: str) -> ReviewCase:
    result = store.get_case(case_id)
    if not result:
        raise HTTPException(status_code=404, detail="case not found")
    return result


@app.post("/api/cases/{case_id}/decision", response_model=DecisionResponse)
async def decide(case_id: str, request: DecisionRequest) -> DecisionResponse:
    try:
        return store.decide(case_id, request)
    except KeyError:
        raise HTTPException(status_code=404, detail="case not found") from None
