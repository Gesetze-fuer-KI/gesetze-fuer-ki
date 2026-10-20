"""Mirror one state's law portal into a directory of Markdown files, politely and resumably.

Run nightly by each state data repository's GitHub Action:

    python sync.py --land BY --out /path/to/landesrecht-by

A source (one per state portal, see SOURCES) lists the laws and fetches one at a time.
State portals are slower and stricter than gesetze-im-internet.de, so the first full pass
may take several nights: a run stops starting new fetches after `--max-minutes`, saves
which laws this pass has done in `<out>/.sync/state.json`, and the next run carries on.
Only after a full pass are laws that left the listing deleted, and `complete` (read by
the server) turns true. Later passes refetch a law only when the portal's lastmod
changes, its file is missing, or a known future version has come into force.
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

import states
from sync import USER_AGENT, commit_lines, law_path

log = logging.getLogger("state_sync")


@dataclass
class Entry:
    slug: str  # "<code lower>-<id>", e.g. "by-baybo"
    url: str
    lastmod: str | None = None


@dataclass
class Fetched:
    markdown: str
    front: dict
    next_version_from: str | None  # ISO date of the next known version, None if none


class Source(Protocol):
    code: str
    crawl_delay: float  # seconds between requests; > 0 requires workers == 1
    workers: int
    min_entries: int  # a shorter listing is treated as broken

    def list_laws(self, client: httpx.Client) -> list[Entry]: ...

    def fetch(self, client: httpx.Client, entry: Entry, today: datetime.date) -> Fetched | None:
        """None means the entry is no Gesetz or Verordnung and is skipped."""
        ...


# Filled by the source modules, keyed by lower-case state code.
SOURCES: dict[str, Callable[[], Source]] = {}


def state_law_path(out: Path, slug: str) -> Path:
    """Sharded like federal laws, by the part after the state prefix; the file keeps the full slug."""
    return law_path(out, slug.split("-", 1)[1]).with_name(f"{slug}.md")


def _client(source: Source, sleep: Callable[[float], None], transport: httpx.BaseTransport | None) -> httpx.Client:
    """A client that waits crawl_delay before every request but the first, whoever sends it."""
    lock = threading.Lock()
    sent = False

    def throttle(request: httpx.Request) -> None:
        nonlocal sent
        with lock:
            if sent and source.crawl_delay > 0:
                sleep(source.crawl_delay)
            sent = True

    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True,
                        event_hooks={"request": [throttle]}, transport=transport)


def _load_state(path: Path) -> dict:
    state = json.loads(path.read_text()) if path.exists() else {}
    return {"complete": state.get("complete", False), "pass_done": state.get("pass_done", []),
            "laws": state.get("laws", {})}


def run(out: Path, source: Source, only: list[str] | None, max_minutes: float, today: datetime.date,
        clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None) -> int:
    if source.crawl_delay > 0 and source.workers != 1:
        raise ValueError(f"{source.code}: a crawl delay needs workers == 1")
    deadline = clock() + max_minutes * 60
    state_dir = out / ".sync"
    state_file = state_dir / "state.json"
    state = _load_state(state_file)
    laws: dict[str, dict] = state["laws"]
    pass_done: set[str] = set(state["pass_done"])

    with _client(source, sleep, transport) as client:
        entries = source.list_laws(client)
        if not only and len(entries) < source.min_entries:
            log.error("listing has only %d entries, refusing to sync", len(entries))
            return 2
        listed = {e.slug for e in entries}
        if only:
            missing = sorted(set(only) - listed)
            if missing:
                log.warning("not in the listing: %s", ", ".join(missing))

        def due(e: Entry) -> bool:
            if only:
                return e.slug in only
            known = laws.get(e.slug, {})
            nvf = known.get("next_version_from")
            if nvf and nvf <= today.isoformat():
                return True
            if known.get("skip"):
                return e.slug not in pass_done and (e.lastmod is None or e.lastmod != known.get("lastmod"))
            if not state_law_path(out, e.slug).exists():
                return True
            if e.slug in pass_done:
                return False
            return e.lastmod is None or known.get("lastmod") is None or e.lastmod != known["lastmod"]

        todo = [e for e in entries if due(e)]
        if not only:
            # Unchanged laws count as done for this pass without a request.
            pass_done |= {e.slug for e in entries} - {e.slug for e in todo}

        def one(e: Entry) -> tuple[Entry, str, Fetched | None]:
            if clock() > deadline:
                return e, "postponed", None
            try:
                return e, "fetched", source.fetch(client, e, today)
            except Exception as exc:  # one broken law must not stop the others
                log.warning("%s: %s", e.slug, exc)
                return e, "failed", None

        changed: list[dict] = []
        failed: list[str] = []
        with ThreadPoolExecutor(max_workers=source.workers) as pool:
            for i, (e, status, fetched) in enumerate(pool.map(one, todo), 1):
                if i % 500 == 0:
                    log.info("%d/%d", i, len(todo))
                if status == "failed":
                    failed.append(e.slug)
                    continue
                if status == "postponed":
                    continue
                if not only:
                    pass_done.add(e.slug)
                if fetched is None:
                    laws[e.slug] = {"lastmod": e.lastmod, "next_version_from": None, "skip": True}
                    continue
                laws[e.slug] = {"lastmod": e.lastmod, "next_version_from": fetched.next_version_from}
                path = state_law_path(out, e.slug)
                previous = path.read_text(encoding="utf-8") if path.exists() else None
                if previous != fetched.markdown:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(fetched.markdown, encoding="utf-8")
                    changed.append({**fetched.front, "slug": e.slug, "_new": previous is None})

    removed: list[str] = []
    finished = not only and listed <= pass_done
    if finished:
        keep = {s for s in listed if not laws.get(s, {}).get("skip")}
        for path in sorted(out.glob("*/*.md")):
            if path.stem not in keep and not path.name.startswith("README"):
                path.unlink()
                removed.append(path.stem)
        for slug in set(laws) - listed:
            del laws[slug]
        state["complete"] = True
        pass_done = set()

    state_dir.mkdir(parents=True, exist_ok=True)
    state["pass_done"] = sorted(pass_done)
    state["laws"] = dict(sorted(laws.items()))
    state_file.write_text(json.dumps(state, indent=1, ensure_ascii=False) + "\n")

    lines = commit_lines(f"{states.STATES[source.code.upper()].name} Stand {today.isoformat()}",
                         changed, removed, failed)
    if not only and not finished:
        lines += ["", f"Abgleich läuft noch: {len(pass_done & listed)} von {len(listed)}"]
    (state_dir / "commit-message.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("%d changed, %d removed, %d failed; pass %s",
             len(changed), len(removed), len(failed), "finished" if finished else f"{len(pass_done)}/{len(listed)}")

    # A few failures are the portal having a bad night; many mean something is wrong here.
    if failed and len(failed) > max(10, len(listed) // 50):
        return 1
    return 0
