from __future__ import annotations

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
store = SnapshotStore(settings.snapshot_path)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(settings.static_dir / "index.html")


@app.get("/healthz")
@app.get("/api/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "shedwatch-nyc"}


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
