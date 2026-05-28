"""FastAPI app — endpoints for ingest, status, overview, and Q&A."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .agents import answer_stream, generate_overview
from .ingest import stats as graph_stats
from .jobs import get_job, run_ingest
from .neo4j_client import close_driver, init_schema
from .repo import parse_repo_url
from .settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_schema()
    yield
    await close_driver()


app = FastAPI(title="Codebase Explainer", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


class IngestRequest(BaseModel):
    url: str


class AskRequest(BaseModel):
    question: str


@app.post("/api/repos")
async def ingest_repo(req: IngestRequest, bg: BackgroundTasks):
    try:
        ref = parse_repo_url(req.url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    existing = get_job(ref.id)
    if existing and existing.status in {"cloning", "parsing", "ingesting"}:
        return {"id": ref.id, "slug": ref.slug, "status": existing.status}

    bg.add_task(run_ingest, ref)
    return {"id": ref.id, "slug": ref.slug, "status": "pending"}


@app.get("/api/repos/{repo_id}")
async def get_repo(repo_id: str):
    job = get_job(repo_id)
    if job is None:
        # Maybe it was ingested in a previous process — check Neo4j.
        s = await graph_stats(repo_id)
        if s["files"] > 0:
            return {
                "id": repo_id,
                "status": "ready",
                "stats": s,
                "slug": None,
            }
        raise HTTPException(404, "Repo not found")
    return job.to_dict()


@app.get("/api/repos/{repo_id}/overview")
async def get_overview(repo_id: str):
    s = await graph_stats(repo_id)
    if s["files"] == 0:
        raise HTTPException(409, "Repo not ingested yet")
    try:
        return await generate_overview(repo_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"overview failed: {e}")


@app.post("/api/repos/{repo_id}/ask")
async def ask(repo_id: str, req: AskRequest):
    s = await graph_stats(repo_id)
    if s["files"] == 0:
        raise HTTPException(409, "Repo not ingested yet")

    async def event_gen():
        try:
            async for chunk in answer_stream(repo_id, req.question):
                # SSE: each event is a token chunk
                yield {"event": "chunk", "data": chunk}
            yield {"event": "done", "data": ""}
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            yield {"event": "error", "data": str(e)[:400]}

    return EventSourceResponse(event_gen())


@app.get("/api/health")
async def health():
    return {"ok": True}
