"""Mirror one state's law portal into a directory of Markdown files, politely and resumably.

Run nightly by each state data repository's GitHub Action:

    python sync.py --land BY --out /path/to/landesrecht-by

A source (one per state portal, see sources.SOURCES) lists the laws and fetches one at a time.
State portals are slower and stricter than gesetze-im-internet.de, so the first full pass
may take several nights: a run stops starting new fetches after `--max-minutes`, saves
which laws this pass has done in `<out>/.sync/state.json`, and the next run carries on.
Only after a full pass are laws that left the listing deleted, and `complete` (read by
the server) turns true, unless too many laws failed; a pass that would delete more files
than failures are allowed deletes none and exits 1. A law that fails keeps its old file
and is tried again in the next pass. A run that breaks off still saves its progress and
writes a commit message saying so. Later passes refetch a law only when the portal's
lastmod changes, its file is missing, or a known future version has come into force.
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
import store
from sync import USER_AGENT, commit_lines, law_path

log = logging.getLogger("state_sync")


@dataclass
class Entry:
    slug: str  # "<code lower>-<id>", e.g. "by-baybo"
    url: str
    lastmod: str | None = None


class NotYetInForce(Exception):
    """The portal only has a text that applies from `start` (ISO date) on, not today's.

    Not a failure: the law keeps its file (or stays absent if new) and is fetched again on `start`.
    """

    def __init__(self, start: str):
        super().__init__(f"text applies from {start}")
        self.start = start


@dataclass
class Fetched:
    markdown: str
    front: dict
    next_version_from: str | None  # ISO date of the next known version, None if none


class Source(Protocol):
    """A state portal. A source may also have a `cache` dict attribute: the runner then sets it
    to what the source kept there in the last run before list_laws, and saves it with the state."""

    code: str
    crawl_delay: float  # seconds between requests; > 0 requires workers == 1
    workers: int
    min_entries: int  # a shorter listing is treated as broken

    def list_laws(self, client: httpx.Client) -> list[Entry]: ...

    def fetch(self, client: httpx.Client, entry: Entry, today: datetime.date) -> Fetched | None:
        """None means the entry is no Gesetz or Verordnung and is skipped (its file deleted at the
        end of the pass). Return it only for a document positively recognised as a non-law (a type
        or link the source knows); anything unknown or unrecognised raises, so the law keeps its
        file and is tried again next pass."""
        ...


def state_law_path(out: Path, slug: str) -> Path:
    """Sharded like federal laws, by the part after the state prefix; the file keeps the full slug.

    Numeric ids (Sachsen: "sn-20111") are sharded by their first two digits ("20/"), or they
    would all land in "0-9/", past the 1,000 entries GitHub lists per directory.
    """
    doc_id = slug.split("-", 1)[1]
    if len(doc_id) >= 2 and doc_id[:2].isdigit():
        return out / doc_id[:2] / f"{slug}.md"
    return law_path(out, doc_id).with_name(f"{slug}.md")


RETRY_DELAY = 5.0  # seconds before the one retry of a request that failed on the server's side


class _Polite(httpx.BaseTransport):
    """Waits crawl_delay before every request but the first, whoever sends it, and retries a
    network error or a 5xx once after RETRY_DELAY; the retry waits its turn like any request."""

    def __init__(self, source: Source, sleep: Callable[[float], None], inner: httpx.BaseTransport) -> None:
        self.source, self.sleep, self.inner = source, sleep, inner
        self.lock = threading.Lock()
        self.sent = False

    def throttle(self) -> None:
        with self.lock:
            if self.sent and self.source.crawl_delay > 0:
                self.sleep(self.source.crawl_delay)
            self.sent = True

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.throttle()
        try:
            response = self.inner.handle_request(request)
            if response.status_code < 500:
                return response
            response.close()
        except httpx.TransportError as exc:
            log.info("%s: %s, retrying", request.url, exc)
        self.sleep(RETRY_DELAY)
        self.throttle()
        return self.inner.handle_request(request)

    def close(self) -> None:
        self.inner.close()


def _client(source: Source, sleep: Callable[[float], None], transport: httpx.BaseTransport | None) -> httpx.Client:
    """A client that waits crawl_delay between requests and retries a failed one once."""
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True,
                        transport=_Polite(source, sleep, transport or httpx.HTTPTransport()))


def _load_state(path: Path) -> dict:
    state = json.loads(path.read_text()) if path.exists() else {}
    return {"complete": state.get("complete", False), "pass_done": state.get("pass_done", []),
            "pass_failed": state.get("pass_failed", []), "laws": state.get("laws", {}),
            "cache": state.get("cache", {})}


def _failure_limit(total: int) -> int:
    """A few failures are the portal having a bad night; more mean something is wrong here."""
    return max(10, total // 50)


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
    # Laws this pass has handled: fetched or unchanged (pass_done), or failed (pass_failed, retried next pass).
    pass_done: set[str] = set(state["pass_done"])
    pass_failed: set[str] = set(state["pass_failed"]) - pass_done
    if hasattr(source, "cache"):
        source.cache = state["cache"]  # the source's own memory across runs, saved with the state
    message_file = state_dir / "commit-message.txt"
    message_file.unlink(missing_ok=True)  # a run that ends early must not leave the last run's message
    prefix = f"{states.STATES[source.code.upper()].name} Stand {today.isoformat()}"
    changed: list[dict] = []
    removed: list[str] = []
    failed: list[str] = []
    started = False

    def save() -> None:
        state_dir.mkdir(parents=True, exist_ok=True)
        state["pass_done"] = sorted(pass_done)
        state["pass_failed"] = sorted(pass_failed)
        state["laws"] = dict(sorted(laws.items()))
        state["cache"] = dict(sorted(getattr(source, "cache", state["cache"]).items()))
        tmp = state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1, ensure_ascii=False) + "\n")
        tmp.replace(state_file)

    try:
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
            started = True

            def due(e: Entry) -> bool:
                if only:
                    return e.slug in only
                if e.slug in pass_failed:
                    return False
                known = laws.get(e.slug, {})
                nvf = known.get("next_version_from")
                if nvf and nvf <= today.isoformat():
                    return True
                if nvf and known.get("waiting"):
                    return False  # only a later text exists; nothing to do before its start date
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
                pass_done |= listed - pass_failed - {e.slug for e in todo}

            def one(e: Entry) -> tuple[Entry, str, Fetched | str | None]:
                if clock() > deadline:
                    return e, "postponed", None
                try:
                    fetched = source.fetch(client, e, today)
                    if fetched is not None and not any(u.kind == "norm" for u in store.split_law(fetched.markdown)[2]):
                        # A real law has at least one norm: a changed page template must not wipe the texts.
                        raise ValueError("no norm in the converted text")
                    return e, "fetched", fetched
                except NotYetInForce as exc:
                    return e, "waiting", exc.start
                except Exception as exc:  # one broken law must not stop the others
                    log.warning("%s: %s", e.slug, exc)
                    return e, "failed", None

            pool = ThreadPoolExecutor(max_workers=source.workers)
            try:
                for i, (e, status, fetched) in enumerate(pool.map(one, todo), 1):
                    if i % 500 == 0:
                        log.info("%d/%d", i, len(todo))
                    if i % 25 == 0:
                        save()  # a run killed by the job timeout keeps its progress
                    if status == "postponed":
                        continue
                    if status == "failed":
                        failed.append(e.slug)
                        if not only:
                            pass_failed.add(e.slug)
                        continue
                    if not only:
                        pass_done.add(e.slug)
                    if status == "waiting":
                        # Keep the old lastmod: the law is fetched again on the start date anyway.
                        known = laws.get(e.slug, {})
                        laws[e.slug] = {"lastmod": known.get("lastmod"), "next_version_from": fetched, "waiting": True}
                        continue
                    if fetched is None:
                        laws[e.slug] = {"lastmod": e.lastmod, "next_version_from": None, "skip": True}
                        continue
                    path = state_law_path(out, e.slug)
                    previous = path.read_text(encoding="utf-8") if path.exists() else None
                    if previous != fetched.markdown:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(fetched.markdown, encoding="utf-8")
                        changed.append({**fetched.front, "slug": e.slug, "_new": previous is None})
                    laws[e.slug] = {"lastmod": e.lastmod, "next_version_from": fetched.next_version_from}
            finally:
                pool.shutdown(cancel_futures=True)

        failed_in_pass = sorted(pass_failed)
        finished = not only and listed <= pass_done | pass_failed
        refused = 0  # files a pass would have deleted, had there not been too many
        if finished:
            keep = {s for s in listed if not laws.get(s, {}).get("skip")}
            gone = [p for p in store.law_files(out) if p.stem not in keep]
            if len(gone) > _failure_limit(len(listed)):
                # A source that wrongly skips (or stops listing) many laws must not wipe them.
                log.error("pass would delete %d files, more than %d: deleting none", len(gone),
                          _failure_limit(len(listed)))
                refused = len(gone)
            else:
                for path in gone:
                    path.unlink()
                    removed.append(path.stem)
            for slug in set(laws) - listed:
                del laws[slug]
            if pass_failed:
                log.warning("pass finished, %d failed: %s", len(pass_failed), ", ".join(failed_in_pass))
            if len(pass_failed) <= _failure_limit(len(listed)):
                state["complete"] = True
            pass_done, pass_failed = set(), set()
        save()

        lines = commit_lines(prefix, changed, removed, failed_in_pass if finished else failed)
        if refused:
            lines += ["", f"Nicht gelöscht: {refused} Dateien wären entfernt worden, zu viele für einen Abgleich"]
        if not only and not finished:
            lines += ["", f"Abgleich läuft noch: {len((pass_done | pass_failed) & listed)} von {len(listed)}"]
        message_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log.info("%d changed, %d removed, %d failed; pass %s", len(changed), len(removed), len(failed),
                 "finished" if finished else f"{len(pass_done | pass_failed)}/{len(listed)}")

        if refused or (failed and len(failed) > _failure_limit(len(listed))):
            return 1
        return 0
    finally:
        if started or hasattr(source, "cache"):
            save()  # a listing that breaks off keeps what it has cached
        if started and not message_file.exists():
            # Broken off (job timeout, error): commit what is saved, with a message that says so.
            lines = commit_lines(prefix, changed, removed, failed)
            message_file.write_text("\n".join(lines + ["", "Abgleich abgebrochen, Fortschritt gesichert"]) + "\n",
                                    encoding="utf-8")
