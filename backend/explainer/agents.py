"""Claude agents: overview synthesizer + graph-grounded Q&A.

Caching design — same trick as the PR reviewer project:

  Both agents share the *same* repo-context system prompt structure:
    [stable system intro]   <- prefix
    [repo facts: stats + top files + symbol index]   <- cached, per-repo
    [task-specific instructions]   <- last block

  Repo facts are the heavy block. They're identical across every Q&A turn
  for the same repo, so prompt caching gives ~0.1x reads on every follow-up.
  First request per repo pays ~1.25x cache write; everything after is cheap.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import anthropic

from .ingest import find_symbols_by_name, neighbors, stats, top_files_by_in_degree
from .settings import settings

MODEL = "claude-opus-4-7"

_BASE_SYSTEM = """You are a senior engineer onboarding a new contributor to a codebase.

You have read-only access to a graph of the repo's files, functions, and classes,
plus retrieved code snippets. Be concrete: cite file paths and line numbers when
you reference code. If something isn't in the retrieved context, say so — do not
invent functions, signatures, or behavior.

Repo facts (cached):
{repo_facts}
"""

_OVERVIEW_INSTRUCTIONS = """Produce a project overview for a new contributor.

Output JSON with these fields:
  - "summary": 2-4 sentence description of what this codebase does and how it's organized.
  - "stack": list of strings — main languages/frameworks/libraries you can infer.
  - "entry_points": list of {{path, why}} — likely entry files (main, server, CLI).
  - "key_modules": list of {{path, role}} — files/modules with the most importers or central role.
  - "mermaid": a mermaid flowchart (string) showing top-level module relationships. Use 'flowchart LR'. Keep it under 15 nodes.
  - "first_questions": list of 4 concrete Q&A starter questions a new contributor would ask.
"""

_OVERVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "stack": {"type": "array", "items": {"type": "string"}},
        "entry_points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "why": {"type": "string"}},
                "required": ["path", "why"],
                "additionalProperties": False,
            },
        },
        "key_modules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "role": {"type": "string"}},
                "required": ["path", "role"],
                "additionalProperties": False,
            },
        },
        "mermaid": {"type": "string"},
        "first_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "summary", "stack", "entry_points", "key_modules", "mermaid", "first_questions",
    ],
    "additionalProperties": False,
}


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def _build_repo_facts(repo_id: str) -> str:
    """Cheap-to-build, large-ish block we cache."""
    s = await stats(repo_id)
    top = await top_files_by_in_degree(repo_id, limit=25)
    # Sample of symbols — give Claude a sense of what's in here.
    sample = await find_symbols_by_name(repo_id, "", limit=80)

    lines = [
        f"Stats: {s['files']} files, {s['symbols']} symbols "
        f"({s['classes']} classes, {s['functions']} functions/methods).",
        "",
        "Top files by inbound imports (likely shared modules):",
    ]
    for row in top:
        lines.append(f"  - {row['path']} ({row['language']}, in_deg={row['in_deg']})")

    lines.append("")
    lines.append("Sample of symbols defined in this repo:")
    for sym in sample[:60]:
        lines.append(
            f"  - [{sym['kind']}] {sym['name']} @ {sym['file']}:{sym['line_start']}"
        )

    return "\n".join(lines)


async def generate_overview(repo_id: str) -> dict:
    repo_facts = await _build_repo_facts(repo_id)
    system = [
        {
            "type": "text",
            "text": _BASE_SYSTEM.format(repo_facts=repo_facts),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    async with _client() as client:
        resp = await client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=system,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {"type": "json_schema", "schema": _OVERVIEW_SCHEMA},
            },
            messages=[{"role": "user", "content": _OVERVIEW_INSTRUCTIONS}],
        )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    return json.loads(text)


# ---------------------------------------------------------------------------
# Q&A
# ---------------------------------------------------------------------------

# Naive symbol-name extraction from the user question — anything that looks
# like an identifier. Filters out common English words via length + context.
import re

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "what", "where", "when",
    "how", "why", "does", "doing", "does", "from", "into", "are", "was",
    "were", "will", "code", "file", "files", "module", "function", "class",
    "method", "repo", "main", "src", "test", "tests", "app", "any", "some",
    "all", "use", "uses", "used", "using", "doesnt", "isnt", "havent",
}


def _extract_candidates(question: str) -> list[str]:
    found = _IDENT_RE.findall(question)
    seen: set[str] = set()
    out: list[str] = []
    for tok in found:
        low = tok.lower()
        if low in _STOPWORDS:
            continue
        if tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out[:8]


async def _retrieve_context(repo_id: str, question: str) -> str:
    """Look up symbols mentioned in the question, pull their neighborhoods."""
    candidates = _extract_candidates(question)
    blocks: list[str] = []

    if not candidates:
        return "(no specific symbols matched in the question — answer from repo facts alone)"

    for cand in candidates:
        matches = await find_symbols_by_name(repo_id, cand, limit=5)
        if not matches:
            continue
        for m in matches[:3]:
            nbr = await neighbors(repo_id, f"{m['file']}::{m['qname']}")
            block = [
                f"### {m['kind']} `{m['name']}` — {m['file']}:{m['line_start']}-{m['line_end']}",
                "```",
                m["snippet"],
                "```",
            ]
            calls = [c for c in nbr.get("calls", []) if c.get("name")]
            called_by = [c for c in nbr.get("called_by", []) if c.get("name")]
            if calls:
                block.append("**Calls:** " + ", ".join(
                    f"{c['name']} ({c['file']}:{c['line']})" for c in calls[:8]
                ))
            if called_by:
                block.append("**Called by:** " + ", ".join(
                    f"{c['name']} ({c['file']}:{c['line']})" for c in called_by[:8]
                ))
            blocks.append("\n".join(block))

    if not blocks:
        return "(no matching symbols found in the graph)"
    return "\n\n".join(blocks)


_ASK_INSTRUCTIONS = """Answer the user's question about this codebase.

Cite file paths and line numbers from the retrieved context below. If the
context does not contain the answer, say so honestly — do not invent.

Retrieved code context for this question:
---
{context}
---

User question: {question}
"""


async def answer_stream(repo_id: str, question: str) -> AsyncIterator[str]:
    """Streaming Q&A. Yields text chunks."""
    repo_facts = await _build_repo_facts(repo_id)
    context = await _retrieve_context(repo_id, question)

    system = [
        {
            "type": "text",
            "text": _BASE_SYSTEM.format(repo_facts=repo_facts),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    user = _ASK_INSTRUCTIONS.format(context=context, question=question)

    async with _client() as client:
        async with client.messages.stream(
            model=MODEL,
            max_tokens=16000,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            messages=[{"role": "user", "content": user}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
