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
import states
import store

DATA_REPO_URL = os.environ.get("GESETZE_REPO_URL", "https://github.com/Gesetze-fuer-KI/gesetze.git")
DATA_REPO_BRANCH = os.environ.get("GESETZE_REPO_BRANCH", "main")
# One data repository per integrated state; "{code}" is the lower-case state code. Empty: no state law.
STATE_REPO_URL = os.environ.get("STATE_REPO_URL", "https://github.com/Gesetze-fuer-KI/landesrecht-{code}.git")
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", "3600"))
SITE_DIR = Path(os.environ.get("SITE_DIR", "/app/site"))
PORT = int(os.environ.get("PORT", "8081"))
# Only one part of a very long provision is returned at a time (EStG § 52 is ~90,000 characters).
PART_CHARS = 30_000

log = logging.getLogger("gesetze")


def join_names(names: list[str]) -> str:
    """German enumeration: "A", "A und B", "A, B und C"."""
    return " und ".join([", ".join(names[:-1]), names[-1]]) if len(names) > 1 else "".join(names)


INTEGRATED = join_names(sorted(s.name for s in states.STATES.values() if s.integrated))

INSTRUCTIONS = f"""\
Aktuelles Bundesrecht von gesetze-im-internet.de: die amtlichen Texte des
Bundesministeriums der Justiz, jede Nacht abgeglichen.

Nutze diese Werkzeuge, sobald eine Frage deutsches Recht berührt: Steuern,
Gewerbeanmeldung, Arbeit, Miete, Verträge, Datenschutz, Verkehr und so weiter.
Antworte aus dem abgerufenen Wortlaut, nicht aus dem Gedächtnis, denn Gesetze ändern sich.
Die Nutzer sind meist keine Juristen: Erkläre einfach und auf Deutsch.

- gesetze_durchsuchen findet Vorschriften zu einem Thema. Es vergleicht Wörter, nicht
  Bedeutungen: Suche mit den Wörtern, die das Gesetz selbst benutzt
  („Informationspflichten Diensteanbieter“, nicht „Impressum“; „Kleinunternehmer
  Umsatz“, nicht „Umsatzgrenze kleine Firma“). Probiere zwei oder drei Formulierungen
  und schränke mit `law` ein, sobald du das Gesetz kennst.
- Wenn du schon weißt, wo eine Regel steht (§ 19 UStG, § 14 GewO), rufe
  vorschrift_lesen direkt auf, statt zu suchen.
- vorschrift_lesen liefert den vollständigen Wortlaut eines § oder Artikels. Lies ihn,
  bevor du dich darauf stützt, und folge den Verweisen, auf die es ankommt
  („§ 4 Nummer 8 gilt entsprechend“).
- Zitiere, was du benutzt hast, als „§ 19 UStG“ und nenne Stand und Link aus der Antwort.
- Enthalten: Bundesrecht und Landesrecht aus {INTEGRATED};
  keine EU-Verordnungen, keine Gerichtsentscheidungen. Kennt der Nutzer sein Bundesland
  oder seinen Ort, `land` setzen und Bund und Land getrennt abfragen.
- Das ist eine Auskunft, keine Rechtsberatung. Bei Entscheidungen mit Folgen auf
  Steuerberater, Rechtsanwalt oder die zuständige Behörde verweisen.
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


def clone_for(law: dict) -> Path:
    """The clone that holds a law's file: the federal data repository or its state's."""
    land = law.get("land")
    return DATA_DIR / "gesetze" if land is None else DATA_DIR / f"landesrecht-{land.lower()}"


def _update_states() -> tuple[dict[str, Path], list[str]]:
    """Clone or update every integrated state's repository: (code -> clone, revisions).

    A state repository that cannot be fetched keeps its existing clone; one that was never
    cloned (not created yet, or gone) is left out, so it never blocks the federal index.
    """
    clones: dict[str, Path] = {}
    revisions: list[str] = []
    if not STATE_REPO_URL:
        return clones, revisions
    for code in sorted(c for c, s in states.STATES.items() if s.integrated):
        clone = clone_for({"land": code})
        try:
            revisions.append(repo.update(clone, STATE_REPO_URL.format(code=code.lower())))
        except Exception as exc:
            if not (clone / ".git").exists():
                log.warning("state repository %s not available: %s", code, exc)
                continue
            # A failed fetch is usually passing: keep serving what the clone already has.
            log.warning("state repository %s not updated, keeping the clone: %s", code, exc)
            revisions.append(repo.revision(clone))
        clones[code] = clone
    return clones, revisions


def refresh_once() -> None:
    clone = DATA_DIR / "gesetze"
    db_path = DATA_DIR / "index.sqlite"
    rev = repo.update(clone, DATA_REPO_URL, DATA_REPO_BRANCH)
    state_clones, state_revs = _update_states()
    # Any repository moving changes the revision, and so triggers a rebuild.
    rev = "+".join([rev, *state_revs])
    if INDEX.revision == rev:
        return
    if db_path.exists():
        existing = store.Store(db_path)
        if existing.meta("revision") == rev and existing.meta("schema") == store.SCHEMA_VERSION:
            INDEX.swap(existing, rev)
            log.info("index at %s is current", rev[:10])
            return
        existing.close()
    started = time.monotonic()
    count = store.build(clone, db_path, rev, states=state_clones)
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
    """The provision's own page on gesetze-im-internet.de, or the law's page (always, for state law)."""
    base = law["quelle"]
    if not enbez or _land(law):
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
    label = f"{law['abk']} ({law['titel']})" if law["abk"] != law["titel"] else law["titel"]
    land = _land(law)
    return f"{label} – Landesrecht {states.STATES[land].name}" if land else label


def _land(law) -> str | None:
    """A law's state code, None for federal law; `law` is a row or a dict, possibly without the column."""
    return law["land"] if "land" in law.keys() else None


def state_notes(law: dict) -> list[str]:
    """The lines every response with a state law's text carries: unofficial version, attribution."""
    if not _land(law):
        return []
    attribution = states.STATES[law["land"]].attribution
    return ["Nichtamtliche Fassung des Landesportals.", *([attribution] if attribution else [])]


def coverage(s: store.Store) -> str:
    """The footer of every "not found" text: which law is in the index, and who to ask for more."""
    status = s.state_status()
    integrated = sorted((st for st in states.STATES.values() if st.integrated), key=lambda st: st.name)
    complete = [st.name for st in integrated if status.get(st.code)]
    building = [st.name for st in integrated if not status.get(st.code)]
    if complete:
        text = f"Enthalten: Bundesrecht und Landesrecht aus {join_names(complete)}."
        if building:
            text += f" Im Aufbau: {join_names(building)}."
    else:
        text = f"Enthalten: nur Bundesrecht; Landesrecht aus {join_names(building)} ist im Aufbau."
    return f"{text}\nAndere Länder fehlen noch ({states.CONTACT})."


def land_scope(s: store.Store, land: str | None) -> tuple[str | None, str | None]:
    """(state code, None) for a state whose law is in the index, else (None, a German notice).

    Without `land` it is (None, None): the caller decides what "no state" means.
    """
    if not land:
        return None, None
    state = states.find(land)
    if state is None:
        return None, states.unknown_text(land)
    if not state.integrated:
        return None, states.not_integrated_text(state)
    if not s.state_status().get(state.code):
        return None, (
            f"{state.name} wird gerade zum ersten Mal abgeglichen und ist bald verfügbar. "
            f"Bis dahin stehen die Texte auf {state.portal}."
        )
    return state.code, None


def _names(row, law: str) -> bool:
    """Whether `law` is exactly this law's abbreviation or slug."""
    return row["abk_norm"] == store.abk_key(law) or row["slug"] == law.strip().lower()


def resolve(s: store.Store, law: str, land: str | None = None) -> tuple[dict | None, str | None]:
    """The one law meant by `law` (in all sources, or in one state's), or an error text with the candidates.

    With `land`, a federal law named exactly is still found: the instructions say to set land whenever
    the user's state is known, so "BGB" with land="Bayern" must not fail.
    """
    rows = s.resolve_law(law, land)
    if land and not any(_names(r, law) for r in rows):
        federal = [r for r in s.resolve_law(law, store.BUND) if _names(r, law)]
        if len(federal) == 1:
            return dict(federal[0]), None
    if not rows:
        where = f" im Landesrecht {states.STATES[land].name}" if land else ""
        return None, (
            f"Kein Gesetz zu „{law}“{where} gefunden. Mit gesetz_finden nach dem Namen suchen.\n\n{coverage(s)}"
        )
    # A slug is unique and is what the "mehrdeutig" list asks for, so one given exactly (slugs are
    # lower case) wins: "minig" is the federal law, while "MiniG" stays ambiguous with Bavaria's MiniG.
    by_slug = [r for r in rows if r["slug"] == law.strip()]
    if by_slug:
        return dict(by_slug[0]), None
    exact = [r for r in rows if r["abk_norm"] == store.abk_key(law)]
    if len(exact) == 1:
        return dict(exact[0]), None
    candidates = exact or rows
    if len(candidates) == 1:
        return dict(candidates[0]), None
    # Federal and state law can share an abbreviation; then every line says where it is from.
    mixed = any(r["land"] for r in candidates)
    lines = [f"„{law}“ ist mehrdeutig. Bitte mit der Kennung (slug) erneut aufrufen:"]
    lines += [
        f"- `{r['slug']}`: {law_label(r)}{' – Bundesrecht' if mixed and not r['land'] else ''}"
        for r in candidates[:10]
    ]
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


# Tool names, titles and descriptions are what users see in their client, so they are German; the Python
# names and docstrings stay English.

# ---- tools ------------------------------------------------------------------------------------

LAND_DESCRIPTION = "Optional: Bundesland, z. B. „Bayern“, „BY“, „NRW“. Weglassen für Bundesrecht."
# For the tools that read one law: they find it in all sources, so land only picks among namesakes.
LAND_PICK_DESCRIPTION = "Optional: Bundesland, z. B. „Bayern“, „BY“, „NRW“. Nur nötig, wenn die Abkürzung mehrdeutig ist."


@mcp.tool(
    name="gesetze_durchsuchen",
    title="Gesetze durchsuchen",
    description=(
        "Volltextsuche in allen Paragrafen, Artikeln und Anlagen des aktuellen Bundesrechts; "
        "mit land im Landesrecht eines Bundeslandes. "
        "Liefert die passendsten Vorschriften mit Gesetz, Überschrift und einem Textausschnitt. "
        "Danach mit vorschrift_lesen den vollständigen Wortlaut der wichtigen Vorschriften holen."
    ),
    annotations=READ_ONLY,
)
def search_laws(
    query: Annotated[str, Field(description="Suchbegriffe in der Sprache des Gesetzes, z. B. „Kleinunternehmer Umsatzgrenze“ oder „Gewerbe anzeigen“")],
    law: Annotated[str | None, Field(description="Nur in einem Gesetz suchen: Abkürzung wie „UStG“, „GewO“, „BGB“, auch Landesrecht wie „BayBO“, oder eine Kennung aus gesetz_finden")] = None,
    limit: Annotated[int, Field(ge=1, le=25, description="Höchstzahl der Treffer")] = 8,
    land: Annotated[str | None, Field(description=LAND_DESCRIPTION)] = None,
) -> str:
    """Full-text search over all provisions of current federal law, or of one state's law."""
    try:
        s = INDEX.get()
    except NotReady:
        return _not_ready()
    code, notice = land_scope(s, land)
    if notice:
        return notice
    slug = None
    if law:
        # The law may come from any source (federal even with land set); the search stays inside it.
        found, error = resolve(s, law, code)
        if error:
            return error
        slug = found["slug"]
    # A law is its own scope: with land set it may still be federal (see resolve).
    rows = s.search(query, slug, limit, land=None if slug else (code or store.BUND))
    hint = ""
    if not land and not law:
        counts = s.count_by_land(query)
        if counts:
            ranked = sorted(counts.items(), key=lambda kv: (-kv[1], states.STATES[kv[0]].name))
            found_in = ", ".join(f"{states.STATES[c].name} ({n})" for c, n in ranked)
            hint = f"\n\nAuch im Landesrecht gibt es Treffer: {found_in}. Mit land gezielt suchen."
    if not rows:
        # State hits are the better pointer; without them, say what the index holds.
        footer = hint or f"\n\n{coverage(s)}"
        where = f" im Landesrecht {states.STATES[code].name}" if code and not slug else ""
        return f"Keine Treffer für „{query}“{where}. Andere, juristischere Begriffe oder weniger Wörter versuchen.{footer}"
    lines = [f"Treffer für „{query}“:", ""]
    sources = set()
    for r in rows:
        snippet = re.sub(r"\s+", " ", r["snippet"] or "").strip()
        where = f" — {r['breadcrumb']}" if r["breadcrumb"] else ""
        tag = f" [{states.STATES[r['land']].name}]" if r["land"] else ""
        sources.add(r["land"])
        lines.append(f"### {r['heading']} {r['abk']}{tag}")
        lines.append(f"law: `{r['slug']}`, provision: `{r['enbez'] or r['heading']}`{where}")
        lines.append(f"> {snippet}")
        lines.append("")
    attributions = (states.STATES[c].attribution for c in sorted(c for c in sources if c))
    lines += [a for a in attributions if a]
    return "\n".join(lines).rstrip() + hint


@mcp.tool(
    name="gesetz_finden",
    title="Gesetz finden",
    description=(
        "Gesetze und Verordnungen des Bundes und der Länder über ihren Namen oder ihre Abkürzung finden. "
        "Liefert die richtige Abkürzung und Kennung, wenn der genaue Name unbekannt ist."
    ),
    annotations=READ_ONLY,
)
def find_law(
    query: Annotated[str, Field(description="Name, Teil des Titels oder Abkürzung, z. B. „Gewerbeordnung“, „Mindestlohn“, „AO“, „BayBO“")],
    limit: Annotated[int, Field(ge=1, le=25, description="Höchstzahl der Treffer")] = 10,
    land: Annotated[str | None, Field(description="Optional: nur in einem Bundesland suchen, z. B. „Bayern“, „BY“, „NRW“. Weglassen für alle.")] = None,
) -> str:
    """Find federal and state laws and regulations by name or abbreviation."""
    try:
        s = INDEX.get()
    except NotReady:
        return _not_ready()
    code, notice = land_scope(s, land)
    if notice:
        return notice
    exact = s.resolve_law(query, code)
    rows = list(exact)
    for r in s.find_laws(query, limit, code):
        if all(r["slug"] != e["slug"] for e in rows):
            rows.append(r)
    if not rows:
        return f"Kein Gesetz zu „{query}“ gefunden.\n\n{coverage(s)}"
    lines = []
    for r in rows[:limit]:
        stand = f" — Stand: {r['stand']}" if r["stand"] else ""
        tag = f" [{states.STATES[r['land']].name}]" if r["land"] else ""
        lines.append(f"- **{r['abk']}** `{r['slug']}`{tag}: {r['titel']}{stand}")
    return "\n".join(lines)


@mcp.tool(
    name="vorschrift_lesen",
    title="Vorschrift lesen",
    description=(
        "Der vollständige Wortlaut eines Paragrafen, Artikels oder einer Anlage, mit Stand und "
        "Link zur amtlichen Fassung. Mit date auch die Fassung an einem früheren Tag."
    ),
    annotations=READ_ONLY,
)
def get_provision(
    law: Annotated[str, Field(description="Abkürzung wie „UStG“, auch Landesrecht wie „BayBO“, oder Kennung wie „ustg_1980“")],
    provision: Annotated[str, Field(description="Der Paragraf oder Artikel, z. B. „§ 19“, „19a“, „Art 3“, „Anlage 2“")],
    date: Annotated[str | None, Field(description="Optional, als JJJJ-MM-TT: der Wortlaut, der an diesem Tag galt. Weglassen für den aktuellen Text.")] = None,
    part: Annotated[int, Field(ge=1, description="Bei sehr langen Vorschriften: welcher Teil")] = 1,
    land: Annotated[str | None, Field(description=LAND_PICK_DESCRIPTION)] = None,
) -> str:
    """The full text of one provision, with its Stand and official link."""
    try:
        s = INDEX.get()
    except NotReady:
        return _not_ready()
    code, notice = land_scope(s, land)
    if notice:
        return notice
    found, error = resolve(s, law, code)
    if error:
        return error
    if date:
        return _provision_at(found, provision, date, part)
    unit = s.norm(found["slug"], provision)
    if unit is None:
        return (
            f"{provision} {found['abk']} nicht gefunden. "
            f"Mit gliederung_anzeigen('{found['slug']}') die Gliederung ansehen."
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
    lines += state_notes(law)
    lines.append("")
    lines.append(parts[part - 1])
    if len(parts) > 1:
        more = f" Weiter mit part={part + 1}." if part < len(parts) else ""
        lines.append(f"\n[Teil {part} von {len(parts)}.{more}]")
    return "\n".join(lines)


def _provision_at(law: dict, provision: str, date: str, part: int) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return "date bitte als JJJJ-MM-TT angeben."
    clone = clone_for(law)
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


@mcp.tool(
    name="gliederung_anzeigen",
    title="Gliederung anzeigen",
    description="Der Aufbau eines Gesetzes des Bundes oder eines Landes: Teile, Abschnitte und alle Vorschriften mit ihren Überschriften.",
    annotations=READ_ONLY,
)
def get_law_outline(
    law: Annotated[str, Field(description="Abkürzung wie „GewO“, auch Landesrecht wie „BayBO“, oder eine Kennung")],
    land: Annotated[str | None, Field(description=LAND_PICK_DESCRIPTION)] = None,
) -> str:
    """The structure of a law with all headings."""
    try:
        s = INDEX.get()
    except NotReady:
        return _not_ready()
    code, notice = land_scope(s, land)
    if notice:
        return notice
    found, error = resolve(s, law, code)
    if error:
        return error
    lines = [f"# {law_label(found)}", f"Stand: {found['stand'] or 'unbekannt'}", f"Quelle: {found['quelle']}"]
    lines += [*state_notes(found), ""]
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


@mcp.tool(
    name="aenderungen_anzeigen",
    title="Änderungen anzeigen",
    description=(
        "Wann sich ein Gesetz geändert hat, neueste zuerst, mit dem amtlichen Änderungsvermerk. "
        "Zusammen mit vorschrift_lesen und date lässt sich der Wortlaut vor und nach einer Änderung vergleichen."
    ),
    annotations=READ_ONLY,
)
def get_law_changes(
    law: Annotated[str, Field(description="Abkürzung wie „EStG“, auch Landesrecht wie „BayBO“, oder eine Kennung")],
    limit: Annotated[int, Field(ge=1, le=50, description="Höchstzahl der Einträge")] = 10,
    land: Annotated[str | None, Field(description=LAND_PICK_DESCRIPTION)] = None,
) -> str:
    """When a law changed in this mirror, newest first, with the official amendment note."""
    try:
        s = INDEX.get()
    except NotReady:
        return _not_ready()
    code, notice = land_scope(s, land)
    if notice:
        return notice
    found, error = resolve(s, law, code)
    if error:
        return error
    clone = clone_for(found)
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
        state_status = s.state_status()
    except NotReady:
        laws, state_status = 0, {}
    return JSONResponse(
        {"status": "ok", "ready": laws > 0, "laws": laws, "revision": INDEX.revision, "error": INDEX.error,
         "states": state_status}
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
