"""Write parsed File/Symbol nodes + edges into Neo4j."""
from __future__ import annotations

from .neo4j_client import session
from .parser import FileParse


async def ingest(repo_id: str, repo_slug: str, parses: list[FileParse]) -> dict:
    """Write the parsed repo into Neo4j. Returns ingest stats."""
    files = [
        {"path": p.path, "language": p.language, "bytes": p.bytes_}
        for p in parses
    ]
    symbols = [
        {
            "path": p.path,
            "name": s.name,
            "qname": f"{p.path}::{s.qname}",
            "short_qname": s.qname,
            "kind": s.kind,
            "line_start": s.line_start,
            "line_end": s.line_end,
            "snippet": s.snippet,
        }
        for p in parses
        for s in p.symbols
    ]
    import_edges = [
        {"path": p.path, "target": t}
        for p in parses
        for t in p.imports
    ]
    call_edges = [
        {"src_qname": f"{p.path}::{s.qname}", "callee_name": c}
        for p in parses
        for s in p.symbols
        for c in s.calls
    ]

    async with session() as sess:
        # Repo node
        await sess.run(
            """
            MERGE (r:Repo {id: $rid})
              SET r.slug = $slug, r.ingested_at = timestamp()
            """,
            rid=repo_id, slug=repo_slug,
        )

        # Files
        await sess.run(
            """
            UNWIND $files AS f
            MERGE (file:File {repo_id: $rid, path: f.path})
              SET file.language = f.language, file.bytes = f.bytes
            WITH file
            MATCH (r:Repo {id: $rid})
            MERGE (file)-[:IN_REPO]->(r)
            """,
            rid=repo_id, files=files,
        )

        # Symbols
        await sess.run(
            """
            UNWIND $symbols AS s
            MATCH (file:File {repo_id: $rid, path: s.path})
            MERGE (sym:Symbol {repo_id: $rid, qname: s.qname})
              SET sym.name = s.name,
                  sym.short_qname = s.short_qname,
                  sym.kind = s.kind,
                  sym.line_start = s.line_start,
                  sym.line_end = s.line_end,
                  sym.snippet = s.snippet,
                  sym.file_path = s.path
            MERGE (sym)-[:DEFINED_IN]->(file)
            """,
            rid=repo_id, symbols=symbols,
        )

        # Import edges — best-effort match by suffix path
        await sess.run(
            """
            UNWIND $edges AS e
            MATCH (src:File {repo_id: $rid, path: e.path})
            OPTIONAL MATCH (dst:File {repo_id: $rid})
              WHERE dst.path ENDS WITH e.target
                 OR dst.path ENDS WITH (e.target + '.py')
                 OR dst.path ENDS WITH (e.target + '.ts')
                 OR dst.path ENDS WITH (e.target + '.tsx')
                 OR dst.path ENDS WITH (e.target + '.js')
                 OR dst.path ENDS WITH (replace(e.target, '.', '/') + '.py')
                 OR dst.path ENDS WITH (replace(e.target, '.', '/') + '/__init__.py')
            FOREACH (_ IN CASE WHEN dst IS NULL THEN [] ELSE [1] END |
              MERGE (src)-[:IMPORTS {raw: e.target}]->(dst)
            )
            """,
            rid=repo_id, edges=import_edges,
        )

        # Call edges — resolve by symbol name within the repo
        await sess.run(
            """
            UNWIND $edges AS e
            MATCH (src:Symbol {repo_id: $rid, qname: e.src_qname})
            MATCH (dst:Symbol {repo_id: $rid, name: e.callee_name})
            MERGE (src)-[:CALLS]->(dst)
            """,
            rid=repo_id, edges=call_edges,
        )

    return {
        "files": len(files),
        "symbols": len(symbols),
        "import_edges": len(import_edges),
        "call_edges": len(call_edges),
    }


async def stats(repo_id: str) -> dict:
    """Quick counts for overview/sidebar."""
    async with session() as sess:
        res = await sess.run(
            """
            MATCH (f:File {repo_id: $rid})
            WITH count(f) AS files
            MATCH (s:Symbol {repo_id: $rid})
            WITH files, count(s) AS symbols, count(CASE WHEN s.kind = 'class' THEN 1 END) AS classes,
                 count(CASE WHEN s.kind = 'function' OR s.kind = 'method' THEN 1 END) AS functions
            RETURN files, symbols, classes, functions
            """,
            rid=repo_id,
        )
        row = await res.single()
        if row is None:
            return {"files": 0, "symbols": 0, "classes": 0, "functions": 0}
        return dict(row)


async def top_files_by_in_degree(repo_id: str, limit: int = 20) -> list[dict]:
    """Files most imported by others — likely entry points / shared modules."""
    async with session() as sess:
        res = await sess.run(
            """
            MATCH (f:File {repo_id: $rid})
            OPTIONAL MATCH (other:File)-[:IMPORTS]->(f)
            WITH f, count(other) AS in_deg
            ORDER BY in_deg DESC, f.path ASC
            LIMIT $limit
            RETURN f.path AS path, f.language AS language, in_deg
            """,
            rid=repo_id, limit=limit,
        )
        return [dict(r) async for r in res]


async def find_symbols_by_name(repo_id: str, name: str, limit: int = 20) -> list[dict]:
    """Used by Q&A: when the user mentions a function/class, find it."""
    async with session() as sess:
        res = await sess.run(
            """
            MATCH (s:Symbol {repo_id: $rid})
            WHERE toLower(s.name) CONTAINS toLower($q)
            RETURN s.name AS name, s.short_qname AS qname, s.kind AS kind,
                   s.file_path AS file, s.line_start AS line_start,
                   s.line_end AS line_end, s.snippet AS snippet
            ORDER BY size(s.name) ASC
            LIMIT $limit
            """,
            rid=repo_id, q=name, limit=limit,
        )
        return [dict(r) async for r in res]


async def neighbors(repo_id: str, qname: str, depth: int = 1) -> dict:
    """Pull a small subgraph around a symbol — what it calls + who calls it."""
    async with session() as sess:
        res = await sess.run(
            """
            MATCH (s:Symbol {repo_id: $rid, qname: $qname})
            OPTIONAL MATCH (s)-[:CALLS]->(out:Symbol)
            OPTIONAL MATCH (in:Symbol)-[:CALLS]->(s)
            RETURN s.name AS name, s.short_qname AS qname, s.kind AS kind,
                   s.file_path AS file, s.line_start AS line_start, s.snippet AS snippet,
                   collect(DISTINCT {name: out.name, qname: out.short_qname,
                                     file: out.file_path, line: out.line_start}) AS calls,
                   collect(DISTINCT {name: in.name, qname: in.short_qname,
                                     file: in.file_path, line: in.line_start}) AS called_by
            """,
            rid=repo_id, qname=qname,
        )
        row = await res.single()
        return dict(row) if row else {}
