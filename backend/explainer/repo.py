"""Clone a public GitHub repo into a temp dir with bounded depth."""
from __future__ import annotations

import asyncio
import hashlib
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .settings import settings

_GH_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[\w.-]+)/(?P<name>[\w.-]+?)(?:\.git)?/?$"
)


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str
    url: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def id(self) -> str:
        return hashlib.sha1(self.slug.lower().encode()).hexdigest()[:16]


def parse_repo_url(url: str) -> RepoRef:
    m = _GH_RE.match(url.strip())
    if not m:
        raise ValueError(f"Not a valid GitHub repo URL: {url}")
    owner, name = m["owner"], m["name"]
    canonical = f"https://github.com/{owner}/{name}.git"
    return RepoRef(owner=owner, name=name, url=canonical)


async def shallow_clone(ref: RepoRef) -> Path:
    """Clone --depth=1 into a temp dir. Caller is responsible for cleanup."""
    tmp = Path(tempfile.mkdtemp(prefix="cbx-"))

    url = ref.url
    if settings.github_token:
        url = url.replace("https://", f"https://{settings.github_token}@", 1)

    proc = await asyncio.create_subprocess_exec(
        "git",
        "clone",
        "--depth=1",
        "--filter=blob:limit=2m",
        url,
        str(tmp),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError(f"git clone failed: {stderr.decode(errors='ignore')[:400]}")
    return tmp


def iter_source_files(root: Path) -> list[Path]:
    """Walk the cloned repo, return source files within size + ext limits."""
    exts = settings.extensions
    out: list[Path] = []
    skip_dirs = {
        "node_modules", ".git", "dist", "build", ".next", "venv", ".venv",
        "__pycache__", "target", "out", ".turbo", "coverage", ".pytest_cache",
    }
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in skip_dirs for part in p.parts):
            continue
        if p.suffix.lstrip(".") not in exts:
            continue
        try:
            if p.stat().st_size > settings.max_file_bytes:
                continue
        except OSError:
            continue
        out.append(p)
        if len(out) >= settings.max_repo_files:
            break
    return out
