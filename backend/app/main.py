from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.snapshot import SnapshotRepository, SnapshotUnavailable


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    app.state.settings = settings
    app.state.snapshots = SnapshotRepository(settings)
    yield


app = FastAPI(
    title="YouTube Video Analytics API",
    description="Serves persisted dashboard analytics computed by PySpark on YARN.",
    version="1.0.0",
    lifespan=lifespan,
)
settings = Settings.from_env()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/dashboard")
def dashboard(
    request: Request,
    region: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
) -> dict[str, Any]:
    repository: SnapshotRepository = request.app.state.snapshots
    try:
        payload = repository.load()
    except SnapshotUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    selected_region = region.upper() if region else None
    if selected_region and selected_region not in payload["metadata"]["regions"]:
        raise HTTPException(
            status_code=404, detail=f"No analytics are available for region {selected_region}."
        )
    if selected_region is None:
        return payload

    result = dict(payload)
    result["metadata"] = dict(payload["metadata"])
    result["metadata"]["selected_region"] = selected_region
    for key in ("countries", "categories", "channels", "videos", "trends"):
        result[key] = [row for row in payload[key] if row.get("region") == selected_region]

    country = result["countries"][0]
    result["overview"] = {
        "video_count": country["video_count"],
        "observation_count": country["observation_count"],
        "views": country["views"],
        "likes": country["likes"],
        "comments": country["comments"],
        "engagement_rate": country["engagement_rate"],
    }
    return result
