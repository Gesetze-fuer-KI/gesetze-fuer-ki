"""gesetze-fuer-ki.de: an MCP server that lets AI agents search German federal law.

The laws come from the data repository (Markdown files mirrored nightly from
gesetze-im-internet.de, see sync.py). The server keeps a clone of it, rebuilds
its search index when the clone changes, and serves:

- /mcp     the MCP endpoint (streamable HTTP), no login: the data is public law
- /health  liveness plus the state of the index
- /        the documentation site, if it was built into SITE_DIR
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles

import repo
import store

DATA_REPO_URL = os.environ.get("GESETZE_REPO_URL", "https://github.com/Marceltov/gesetze.git")
DATA_REPO_BRANCH = os.environ.get("GESETZE_REPO_BRANCH", "main")
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", "3600"))
SITE_DIR = Path(os.environ.get("SITE_DIR", "/app/site"))
PORT = int(os.environ.get("PORT", "8081"))
# Only one part of a very long provision is returned at a time (EStG § 52 is ~90,000 characters).
PART_CHARS = 30_000

log = logging.getLogger("gesetze")

INSTRUCTIONS = """\
Current German federal law (Bundesrecht) from gesetze-im-internet.de, the official
consolidated texts of the Federal Ministry of Justice, updated nightly.

Use these tools whenever a question touches German law: taxes, trade registration
(Gewerbe), employment, tenancy, contracts, data protection, traffic and so on.
Answer from the text you retrieved, not from memory, because laws change.

- search_laws finds provisions by topic. It matches words, not meaning: search in
  the words the law itself uses ("Informationspflichten Diensteanbieter", not
  "Impressum"; "Kleinunternehmer Umsatz", not "small business VAT limit"). Try
  two or three phrasings, and narrow with `law` once you know the law.
- When you already know where a rule is (§ 19 UStG, § 14 GewO), call
  get_provision directly instead of searching.
- get_provision returns the full text of one § or Artikel. Read it before you rely on it,
  and follow the cross-references that matter ("§ 4 Nummer 8 gilt entsprechend").
- Cite what you used as "§ 19 UStG" and give the Stand and link the tool returns.
- Federal law only: no state law (Landesrecht), no EU regulations, no court rulings.
- This is information, not legal advice. For decisions with consequences, point to a
  Steuerberater, Rechtsanwalt or the responsible authority.
"""

mcp = FastMCP("gesetze-fuer-ki", instructions=INSTRUCTIONS, website_url="https://gesetze-fuer-ki.de")

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


class Index:
    """The current Store, swapped atomically when a rebuild finishes."""

    def __init__(self) -> None:
        self._store: store.Store | None = None
        self._lock = threading.Lock()
        self.revision: str | None = None
        self.error: str | None = None

    def get(self) -> store.Store:
        with self._lock:
            if self._store is None:
                raise NotReady()
            return self._store

    def swap(self, new: store.Store, revision: str) -> None:
        with self._lock:
            old, self._store, self.revision = self._store, new, revision
        if old is not None:
            # Give calls still using the old connection a moment to finish.
            threading.Timer(60, old.close).start()


class NotReady(Exception):
    pass


INDEX = Index()


def refresh_once() -> None:
    clone = DATA_DIR / "gesetze"
    db_path = DATA_DIR / "index.sqlite"
    rev = repo.update(clone, DATA_REPO_URL, DATA_REPO_BRANCH)
    if INDEX.revision == rev:
        return
    if db_path.exists():
        existing = store.Store(db_path)
        if existing.meta("revision") == rev:
            INDEX.swap(existing, rev)
            log.info("index at %s is current", rev[:10])
            return
        existing.close()
    started = time.monotonic()
    count = store.build(clone, db_path, rev)
    INDEX.swap(store.Store(db_path), rev)
    log.info("indexed %d laws at %s in %.0fs", count, rev[:10], time.monotonic() - started)


def refresh_loop() -> None:
    while True:
        try:
            refresh_once()
            INDEX.error = None
        except Exception as exc:  # keep serving the last good index
            INDEX.error = str(exc)
            log.exception("refresh failed")
        time.sleep(REFRESH_SECONDS)


# ---- formatting -------------------------------------------------------------------------------


def provision_url(law: dict, enbez: str | None) -> str:
    """The provision's own page on gesetze-im-internet.de, or the law's page."""
    base = law["quelle"]
    if not enbez:
        return base
    m = re.match(r"^§\s*(\d+[a-z]*)$", enbez)
    if m:
        return f"{base}__{m.group(1)}.html"
    m = re.match(r"^Art(?:ikel|\.)?\s*(\d+[a-z]*)$", enbez, re.I)
    if m:
        return f"{base}art_{m.group(1)}.html"
    m = re.match(r"^Anlage\s*(\d+[a-z]*)$", enbez, re.I)
    if m:
        return f"{base}anlage_{m.group(1)}.html"
    return base


def law_label(law: dict) -> str:
    return f"{law['abk']} ({law['titel']})" if law["abk"] != law["titel"] else law["titel"]


def resolve(s: store.Store, law: str) -> tuple[dict | None, str | None]:
    """The one law meant by `law`, or an error text that lists the candidates."""
    rows = s.resolve_law(law)
    if not rows:
        return None, f"Kein Gesetz zu „{law}“ gefunden. Mit find_law nach dem Namen suchen."
    exact = [r for r in rows if r["abk_norm"] == store.abk_key(law) or r["slug"] == law.strip().lower()]
    if len(exact) == 1:
        return dict(exact[0]), None
    candidates = exact or rows
    if len(candidates) == 1:
        return dict(candidates[0]), None
    lines = [f"„{law}“ ist mehrdeutig. Bitte mit der Kennung (slug) erneut aufrufen:"]
    lines += [f"- `{r['slug']}`: {law_label(r)}" for r in candidates[:10]]
    return None, "\n".join(lines)


def split_parts(body: str, size: int = PART_CHARS) -> list[str]:
    """Split a long text at paragraph boundaries into parts of about `size` characters."""
    if len(body) <= size:
        return [body]
    parts, current = [], ""
    for block in body.split("\n\n"):
        if current and len(current) + len(block) > size:
            parts.append(current)
            current = ""
        current = f"{current}\n\n{block}" if current else block
    if current:
        parts.append(current)
    return parts


def _not_ready() -> str:
    return "Der Suchindex wird gerade aufgebaut. Bitte in einer Minute erneut versuchen."


# ---- tools ------------------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
def search_laws(
    query: Annotated[str, Field(description="Search terms in German legal language, e.g. 'Kleinunternehmer Umsatzgrenze' or 'Gewerbe anzeigen'")],
    law: Annotated[str | None, Field(description="Restrict to one law: abbreviation like 'UStG', 'GewO', 'BGB', or a slug from find_law")] = None,
    limit: Annotated[int, Field(ge=1, le=25)] = 8,
) -> str:
    """Full-text search over all provisions (§§, Artikel, Anlagen) of current German federal law.

    Returns the best-matching provisions with law, designation, heading and a text
    snippet. Then call get_provision for the full text of the ones that matter.
    """
    try:
        s = INDEX.get()
    except NotReady:
        return _not_ready()
    slug = None
    if law:
        found, error = resolve(s, law)
        if error:
            return error
        slug = found["slug"]
    rows = s.search(query, slug, limit)
    if not rows:
        return f"Keine Treffer für „{query}“. Andere, juristischere Begriffe oder weniger Wörter versuchen."
    lines = [f"Treffer für „{query}“:", ""]
    for r in rows:
        snippet = re.sub(r"\s+", " ", r["snippet"] or "").strip()
        where = f" — {r['breadcrumb']}" if r["breadcrumb"] else ""
        lines.append(f"### {r['heading']} {r['abk']}")
        lines.append(f"law: `{r['slug']}`, provision: `{r['enbez'] or r['heading']}`{where}")
        lines.append(f"> {snippet}")
        lines.append("")
    return "\n".join(lines).rstrip()


@mcp.tool(annotations=READ_ONLY)
def find_law(
    query: Annotated[str, Field(description="Name, part of the title or abbreviation, e.g. 'Gewerbeordnung', 'Mindestlohn', 'DSGVO-Anpassung', 'AO'")],
    limit: Annotated[int, Field(ge=1, le=25)] = 10,
) -> str:
    """Find laws and regulations (Gesetze, Verordnungen) by name or abbreviation.

    Use this to get the right abbreviation or slug when a law's exact name is unknown.
    """
    try:
        s = INDEX.get()
    except NotReady:
        return _not_ready()
    exact = s.resolve_law(query)
    rows = list(exact)
    for r in s.find_laws(query, limit):
        if all(r["slug"] != e["slug"] for e in rows):
            rows.append(r)
    if not rows:
        return f"Kein Gesetz zu „{query}“ gefunden."
    lines = []
    for r in rows[:limit]:
        stand = f" — Stand: {r['stand']}" if r["stand"] else ""
        lines.append(f"- **{r['abk']}** `{r['slug']}`: {r['titel']}{stand}")
    return "\n".join(lines)


@mcp.tool(annotations=READ_ONLY)
def get_provision(
    law: Annotated[str, Field(description="Abbreviation like 'UStG' or a slug like 'ustg_1980'")],
    provision: Annotated[str, Field(description="The § or Artikel, e.g. '§ 19', '19a', 'Art 3', 'Anlage 2'")],
    date: Annotated[str | None, Field(description="Optional YYYY-MM-DD: the wording in force in this mirror on that day. Omit for the current text.")] = None,
    part: Annotated[int, Field(ge=1, description="For very long provisions: which part to return")] = 1,
) -> str:
    """The full text of one provision of a German federal law, with its Stand and official link."""
    try:
        s = INDEX.get()
    except NotReady:
        return _not_ready()
    found, error = resolve(s, law)
    if error:
        return error
    if date:
        return _provision_at(found, provision, date, part)
    unit = s.norm(found["slug"], provision)
    if unit is None:
        return (
            f"{provision} {found['abk']} nicht gefunden. "
            f"Mit get_law_outline('{found['slug']}') die Gliederung ansehen."
        )
    return _format_provision(found, dict(unit), part, stand=found["stand"])


def _format_provision(law: dict, unit: dict, part: int, stand: str | None, note: str = "") -> str:
    parts = split_parts(unit["body"] or "(kein Text)")
    if part > len(parts):
        return f"Diese Vorschrift hat nur {len(parts)} Teil(e)."
    lines = [f"## {unit['heading']} {law['abk']}", f"{law_label(law)}"]
    if unit.get("breadcrumb"):
        lines.append(unit["breadcrumb"])
    lines.append(f"Stand: {stand or 'unbekannt'}{note}")
    lines.append(f"Quelle: {provision_url(law, unit.get('enbez'))}")
    lines.append("")
    lines.append(parts[part - 1])
    if len(parts) > 1:
        more = f" Weiter mit part={part + 1}." if part < len(parts) else ""
        lines.append(f"\n[Teil {part} von {len(parts)}.{more}]")
    return "\n".join(lines)


def _provision_at(law: dict, provision: str, date: str, part: int) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return "date bitte als JJJJ-MM-TT angeben."
    clone = DATA_DIR / "gesetze"
    found = repo.file_at(clone, law["path"], date)
    if found is None:
        first = (repo.first_date(clone) or "")[:10]
        return (
            f"Für {date} liegt keine Fassung vor. Die Historie dieses Spiegels beginnt am {first}; "
            "ältere Fassungen sind hier nicht verfügbar."
        )
    rev, content = found
    front, _, units = store.split_law(content)
    key = store.norm_key(provision)
    breadcrumb: list[str] = []
    for u in units:
        if u.kind == "gliederung":
            breadcrumb = breadcrumb[: (u.ebene or 1) - 1] + [u.heading]
            continue
        enbez = store.split_enbez(u.heading)
        if enbez and store.norm_key(enbez) == key:
            unit = {"heading": u.heading, "body": u.body, "enbez": enbez, "breadcrumb": " › ".join(breadcrumb)}
            return _format_provision(law, unit, part, stand=front.get("stand"), note=f" (Fassung vom {date})")
    return f"{provision} {law['abk']} gab es am {date} in diesem Spiegel nicht."


@mcp.tool(annotations=READ_ONLY)
def get_law_outline(
    law: Annotated[str, Field(description="Abbreviation like 'GewO' or a slug")],
) -> str:
    """The structure of a law: its parts, sections and all provisions with their headings."""
    try:
        s = INDEX.get()
    except NotReady:
        return _not_ready()
    found, error = resolve(s, law)
    if error:
        return error
    lines = [f"# {law_label(found)}", f"Stand: {found['stand'] or 'unbekannt'}", f"Quelle: {found['quelle']}", ""]
    for r in s.outline(found["slug"]):
        if r["kind"] == "gliederung":
            lines.append("  " * ((r["ebene"] or 1) - 1) + f"**{r['heading']}**")
        else:
            depth = 0
            for prev in reversed(lines):
                if prev.lstrip().startswith("**"):
                    depth = (len(prev) - len(prev.lstrip())) // 2 + 1
                    break
            lines.append("  " * depth + f"- {r['heading']}")
    return "\n".join(lines)


@mcp.tool(annotations=READ_ONLY)
def get_law_changes(
    law: Annotated[str, Field(description="Abbreviation like 'EStG' or a slug")],
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
) -> str:
    """When a law's text changed in this mirror, newest first, with the official amendment note.

    Use with get_provision(date=...) to compare wordings before and after a change.
    """
    try:
        s = INDEX.get()
    except NotReady:
        return _not_ready()
    found, error = resolve(s, law)
    if error:
        return error
    clone = DATA_DIR / "gesetze"
    entries = repo.changes(clone, found["path"], found["abk"], limit)
    first = (repo.first_date(clone) or "")[:10]
    lines = [f"Änderungen an {law_label(found)} in diesem Spiegel (Historie ab {first}):", ""]
    lines += [f"- {c.date[:10]}: {c.summary}" for c in entries]
    return "\n".join(lines)


# ---- HTTP -------------------------------------------------------------------------------------


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    try:
        s = INDEX.get()
        laws = int(s.meta("laws") or 0)
    except NotReady:
        laws = 0
    return JSONResponse(
        {"status": "ok", "ready": laws > 0, "laws": laws, "revision": INDEX.revision, "error": INDEX.error}
    )


def create_app():
    allowed_hosts = [h for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h] or None
    app = mcp.http_app(path="/mcp", allowed_hosts=allowed_hosts)
    if SITE_DIR.is_dir():
        app.mount("/", StaticFiles(directory=SITE_DIR, html=True), name="site")
    return app


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=refresh_loop, name="refresh", daemon=True).start()
    # proxy_headers: Caddy in front sets X-Forwarded-*; the access log is Caddy's.
    uvicorn.run(create_app(), host="0.0.0.0", port=PORT, access_log=False, proxy_headers=True)


if __name__ == "__main__":
    main()
