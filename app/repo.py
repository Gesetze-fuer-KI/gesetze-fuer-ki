"""The server's clone of the data repository: keeping it current and reading its history.

The clone belongs to the server alone, so updating it is a fetch and a hard
reset, never a merge. The history starts with the data repository's first
commit; older versions of a law are not available.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("repo")


@dataclass
class Change:
    date: str  # ISO 8601, the commit's date
    revision: str
    summary: str  # the law's line from the commit message, or its subject


def _git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def update(repo: Path, url: str, branch: str = "main") -> str:
    """Clone or fast-forward the data repository; returns the current revision."""
    if not (repo / ".git").exists():
        repo.mkdir(parents=True, exist_ok=True)
        log.info("cloning %s", url)
        subprocess.run(["git", "clone", "--branch", branch, url, str(repo)], check=True, capture_output=True)
    else:
        _git(repo, "fetch", "--quiet", "origin", branch)
        _git(repo, "reset", "--quiet", "--hard", f"origin/{branch}")
    return revision(repo)


def revision(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").strip()


def changes(repo: Path, path: str, abk: str, limit: int = 20) -> list[Change]:
    """The commits that changed one law file, newest first."""
    out = _git(repo, "log", f"-n{limit}", "--format=%x1e%H%x1f%cI%x1f%B", "--", path)
    result = []
    for record in out.split("\x1e"):
        if not record.strip():
            continue
        rev, date, message = record.split("\x1f", 2)
        summary = message.strip().splitlines()[0] if message.strip() else ""
        for line in message.splitlines():
            # The sync writes one line per law: "- EStG: zuletzt geändert durch …"
            if line.startswith(f"- {abk}:") or line.startswith(f"- neu: {abk} "):
                summary = line[2:]
                break
        result.append(Change(date=date, revision=rev, summary=summary))
    return result


def file_at(repo: Path, path: str, date: str) -> tuple[str, str] | None:
    """(revision, content) of a file as it was at the end of the given day, or None if it did not exist yet."""
    rev = _git(repo, "rev-list", "-n1", f"--before={date}T23:59:59", "HEAD", "--", path).strip()
    if not rev:
        return None
    content = _git(repo, "show", f"{rev}:{path}", check=False)
    return (rev, content) if content else None


def first_date(repo: Path) -> str | None:
    out = _git(repo, "log", "--reverse", "--format=%cI", check=False).splitlines()
    return out[0] if out else None
