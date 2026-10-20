"""Mirror gesetze-im-internet.de into a directory of Markdown files.

Run nightly by the data repository's GitHub Action:

    python sync.py --out /path/to/bundesrecht

For every law in gii-toc.xml the XML zip is requested with the ETag of the last
run, so an unchanged law costs one "304 Not Modified". Changed laws are converted
(see convert.py) and written to `<out>/<first two letters>/<slug>.md`; laws that left
the table of contents are deleted. The ETags live in `<out>/.sync/etags.json`,
and `<out>/.sync/commit-message.txt` describes the run for the commit.
"""

from __future__ import annotations

import argparse
import datetime
import io
import json
import logging
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from convert import SOURCE_BASE, convert

TOC_URL = f"{SOURCE_BASE}/gii-toc.xml"
USER_AGENT = "gesetze-fuer-ki.de sync (+https://github.com/Gesetze-fuer-KI/gesetze-fuer-ki)"
# A table of contents with fewer entries than this is treated as broken, never as
# thousands of repealed laws.
MIN_TOC_ENTRIES = 5000
# From GitHub's runners the first connection to gesetze-im-internet.de often times out; the table of contents is worth
# waiting for (15 s, 30 s, … between six attempts), a single law is not.
TOC_ATTEMPTS = 6
TOC_RETRY_DELAY = 15.0

log = logging.getLogger("sync")


def law_path(out: Path, slug: str) -> Path:
    """Laws are sharded by their first two characters: GitHub lists at most 1,000 entries per directory."""
    if not slug[0].isalpha():
        return out / "0-9" / f"{slug}.md"
    shard = re.sub(r"[^a-z0-9]", "_", slug[:2].lower())
    return out / shard / f"{slug}.md"


def fetch_toc(client: httpx.Client) -> list[tuple[str, str]]:
    """(slug, title) for every law in the table of contents."""
    resp = _get(client, TOC_URL, None, attempts=TOC_ATTEMPTS, delay=TOC_RETRY_DELAY)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    laws = []
    for item in root.iter("item"):
        link = item.findtext("link") or ""
        m = re.search(r"gesetze-im-internet\.de/([^/]+)/xml\.zip", link)
        if m:
            laws.append((m.group(1), (item.findtext("title") or "").strip()))
    return laws


def _get(
    client: httpx.Client, url: str, etag: str | None, attempts: int = 4, delay: float = 1.0
) -> httpx.Response:
    headers = {"If-None-Match": etag} if etag else {}
    for attempt in range(attempts):
        try:
            resp = client.get(url, headers=headers)
            if resp.status_code < 500:
                return resp
        except httpx.TransportError:
            if attempt == attempts - 1:
                raise
        if attempt < attempts - 1:
            time.sleep(delay * 2**attempt)
    return resp


def sync_law(client: httpx.Client, out: Path, slug: str, etag: str | None) -> tuple[str, str | None, dict | None]:
    """Return (status, new etag, front matter if written). status: unchanged|written|missing."""
    resp = _get(client, f"{SOURCE_BASE}/{slug}/xml.zip", etag)
    if resp.status_code == 304:
        return "unchanged", etag, None
    if resp.status_code == 404:
        return "missing", None, None
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        if not names:
            raise ValueError(f"{slug}: zip without XML")
        xml_bytes = zf.read(names[0])
    markdown, front = convert(xml_bytes, slug)
    path = law_path(out, slug)
    previous = path.read_text(encoding="utf-8") if path.exists() else None
    if previous == markdown:
        return "unchanged", resp.headers.get("etag"), None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    front["_new"] = previous is None
    return "written", resp.headers.get("etag"), front


def run(out: Path, only: list[str] | None, workers: int) -> int:
    state_dir = out / ".sync"
    state_dir.mkdir(parents=True, exist_ok=True)
    etag_file = state_dir / "etags.json"
    etags: dict[str, str] = json.loads(etag_file.read_text()) if etag_file.exists() else {}

    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True) as client:
        toc = fetch_toc(client)
        full_run = not only
        if full_run and len(toc) < MIN_TOC_ENTRIES:
            log.error("table of contents has only %d entries, refusing to sync", len(toc))
            return 2
        slugs = [s for s, _ in toc if not only or s in only]

        changed: list[dict] = []
        failed: list[str] = []

        def one(slug: str):
            try:
                return slug, sync_law(client, out, slug, etags.get(slug))
            except Exception as exc:  # one broken law must not stop the others
                log.warning("%s: %s", slug, exc)
                return slug, None

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for i, (slug, result) in enumerate(pool.map(one, slugs), 1):
                if i % 500 == 0:
                    log.info("%d/%d", i, len(slugs))
                if result is None:
                    failed.append(slug)
                    continue
                status, etag, front = result
                if etag:
                    etags[slug] = etag
                if status == "written":
                    changed.append({"slug": slug, **front})

    removed: list[str] = []
    if full_run:
        listed = {s for s, _ in toc}
        for path in sorted(out.glob("*/*.md")):
            if path.stem not in listed and not path.name.startswith("README"):
                path.unlink()
                removed.append(path.stem)
                etags.pop(path.stem, None)

    etag_file.write_text(json.dumps(dict(sorted(etags.items())), indent=0, ensure_ascii=False) + "\n")
    (state_dir / "commit-message.txt").write_text(commit_message(changed, removed, failed), encoding="utf-8")
    log.info("%d changed, %d removed, %d failed of %d", len(changed), len(removed), len(failed), len(slugs))

    # A few failures are the source having a bad night; many mean something is wrong here.
    if failed and len(failed) > max(10, len(slugs) // 50):
        return 1
    return 0


def commit_message(changed: list[dict], removed: list[str], failed: list[str]) -> str:
    return "\n".join(commit_lines(f"Stand {time.strftime('%Y-%m-%d')}", changed, removed, failed)) + "\n"


def commit_lines(prefix: str, changed: list[dict], removed: list[str], failed: list[str]) -> list[str]:
    """Subject and one line per law; repo.changes parses these lines (shared with state_sync)."""
    new = [c for c in changed if c.get("_new")]
    updated = [c for c in changed if not c.get("_new")]
    subject = f"{prefix}: {len(updated)} geändert, {len(new)} neu, {len(removed)} entfernt"
    lines = [subject, ""]
    for c in updated:
        lines.append(f"- {c.get('abkuerzung', c['slug'])}: {c.get('stand', 'geändert')}")
    for c in new:
        lines.append(f"- neu: {c.get('abkuerzung', c['slug'])} ({c.get('titel', '')})")
    for slug in removed:
        lines.append(f"- entfernt: {slug}")
    if failed:
        lines.append("")
        lines.append(f"Nicht abrufbar ({len(failed)}): " + ", ".join(failed[:50]))
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="the data repository's working tree")
    parser.add_argument("--only", nargs="*", help="sync just these slugs (no deletions)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--land", help="sync one state's law (Landesrecht) instead, e.g. BY")
    parser.add_argument("--max-minutes", type=float, default=330,
                        help="with --land: stop starting new fetches after this many minutes")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not args.land:
        sys.exit(run(args.out, args.only, args.workers))

    import sources  # imports this module (through state_sync), so not at the top
    import state_sync

    factory = sources.SOURCES.get(args.land.lower())
    if factory is None:
        log.error("no source for state %r (known: %s)", args.land, ", ".join(sorted(sources.SOURCES)) or "none")
        sys.exit(2)
    sys.exit(state_sync.run(args.out, factory(), args.only, args.max_minutes, datetime.date.today()))


if __name__ == "__main__":
    main()
