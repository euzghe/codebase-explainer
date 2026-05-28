"""Neo4j driver wrapper. Schema-aware: knows our File/Function/Class node model."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from neo4j import AsyncDriver, AsyncGraphDatabase

from .settings import settings

_driver: AsyncDriver | None = None


def get_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _driver


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


@asynccontextmanager
async def session() -> AsyncIterator[Any]:
    driver = get_driver()
    async with driver.session(database=settings.neo4j_database) as s:
        yield s


async def init_schema() -> None:
    """Idempotent: constraints + indexes."""
    statements = [
        # Repos
        "CREATE CONSTRAINT repo_id IF NOT EXISTS FOR (r:Repo) REQUIRE r.id IS UNIQUE",
        # Files keyed by (repo_id, path)
        "CREATE CONSTRAINT file_key IF NOT EXISTS FOR (f:File) REQUIRE (f.repo_id, f.path) IS UNIQUE",
        # Symbols keyed by (repo_id, qualified_name)
        "CREATE CONSTRAINT symbol_key IF NOT EXISTS FOR (s:Symbol) REQUIRE (s.repo_id, s.qname) IS UNIQUE",
        # Indexes for symbol lookup by name
        "CREATE INDEX symbol_name IF NOT EXISTS FOR (s:Symbol) ON (s.repo_id, s.name)",
        "CREATE INDEX file_repo IF NOT EXISTS FOR (f:File) ON (f.repo_id)",
    ]
    async with session() as s:
        for stmt in statements:
            await s.run(stmt)


async def wipe_repo(repo_id: str) -> None:
    """Delete all nodes belonging to a repo. Used on re-ingest."""
    async with session() as s:
        await s.run(
            "MATCH (n {repo_id: $rid}) DETACH DELETE n",
            rid=repo_id,
        )
