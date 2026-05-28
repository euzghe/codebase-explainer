"""In-memory job tracker for ingestion runs.

For a single-node MVP this is fine. If we deploy multi-instance, swap for
Redis. The job model is intentionally tiny — just enough for the frontend
to render a status line and unblock the overview/ask routes.
"""
from __future__ import annotations

import asyncio
import shutil
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from .ingest import ingest as ingest_to_neo4j
from .neo4j_client import wipe_repo
from .parser import parse_repo
from .repo import RepoRef, iter_source_files, shallow_clone


@dataclass
class Job:
    repo_id: str
    slug: str
    status: str = "pending"  # pending | cloning | parsing | ingesting | ready | error
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    error: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


_JOBS: dict[str, Job] = {}
_LOCK = asyncio.Lock()


def get_job(repo_id: str) -> Job | None:
    return _JOBS.get(repo_id)


async def run_ingest(ref: RepoRef) -> None:
    """Owns the full pipeline. Stores progress in _JOBS."""
    job = Job(repo_id=ref.id, slug=ref.slug, status="cloning")
    async with _LOCK:
        _JOBS[ref.id] = job

    clone_dir = None
    try:
        await wipe_repo(ref.id)
        clone_dir = await shallow_clone(ref)

        job.status = "parsing"
        files = iter_source_files(clone_dir)
        if not files:
            raise RuntimeError(
                "No source files matched the allowed extensions. "
                "This repo may not have Python/TS/JS code, or its source lives outside the cloned root."
            )
        parses = parse_repo(clone_dir, files)

        job.status = "ingesting"
        stats = await ingest_to_neo4j(ref.id, ref.slug, parses)

        job.stats = stats
        job.status = "ready"
        job.finished_at = time.time()
    except Exception as e:  # noqa: BLE001 — surface to client
        job.status = "error"
        job.error = str(e)[:500]
        job.finished_at = time.time()
    finally:
        if clone_dir is not None:
            shutil.rmtree(clone_dir, ignore_errors=True)
