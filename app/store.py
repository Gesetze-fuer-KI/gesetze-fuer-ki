"""The search index: the data repository's Markdown files in one SQLite database.

Each law file (see convert.py) is split at its marker comments into units: the
Gliederung headings and the norms (§§, Artikel, Anlagen). Norms go into an FTS5
table for full-text search; the laws' titles and abbreviations into another.
The index is a cache: it is rebuilt from the files whenever they change.

Federal laws have `land` NULL; state laws (from one data repository per state, see
state_sync.py) carry the state's code. A state is only indexed once its sync has
completed a full pass, so the index never shows a half-mirrored state.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import yaml

MARKER = re.compile(
    r'^<!-- (?P<kind>norm|gliederung) id="(?P<id>[^"]*)"(?: ebene="(?P<ebene>\d+)")? -->\n'
    r"(?P<hashes>#+) (?P<heading>.*)$",
    re.M,
)

SCHEMA = """
CREATE TABLE laws (
    slug TEXT PRIMARY KEY,
    abk TEXT NOT NULL,
    abk_norm TEXT NOT NULL,
    titel TEXT NOT NULL,
    kurztitel TEXT,
    stand TEXT,
    quelle TEXT NOT NULL,
    path TEXT NOT NULL,
    norm_count INTEGER NOT NULL,
    land TEXT
);
CREATE INDEX laws_abk ON laws(abk_norm);
CREATE TABLE states (code TEXT PRIMARY KEY, complete INTEGER NOT NULL);
CREATE TABLE units (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL,
    ord INTEGER NOT NULL,
    kind TEXT NOT NULL,
    unit_id TEXT NOT NULL,
    ebene INTEGER,
    enbez TEXT,
    enbez_norm TEXT,
    heading TEXT NOT NULL,
    breadcrumb TEXT NOT NULL,
    law TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE INDEX units_lookup ON units(slug, enbez_norm);
CREATE INDEX units_order ON units(slug, ord);
CREATE VIRTUAL TABLE units_fts USING fts5(
    heading, breadcrumb, law, body,
    content='units', content_rowid='id',
    tokenize="unicode61 remove_diacritics 0"
);
CREATE VIRTUAL TABLE laws_fts USING fts5(
    abk, titel, kurztitel,
    content='laws',
    tokenize="unicode61 remove_diacritics 0"
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""

# Stored in meta as "schema"; an index built with another version is rebuilt, never reused.
SCHEMA_VERSION = "2"

log = logging.getLogger("store")

# The `land` value that means federal law only.
BUND = "BUND"

# "§ 19", "§§ 19", "Art 3", "Artikel 3", "Art. 3" -> the bare designation, lower case, without spaces.
_DESIGNATION = re.compile(r"^(?:§§?|art(?:ikel|\.)?)\s*", re.I)


def norm_key(designation: str) -> str:
    key = designation.strip()
    key = _DESIGNATION.sub("", key)
    return re.sub(r"[\s.]+", "", key).lower()


def abk_key(abk: str) -> str:
    return re.sub(r"[\s.\-_]+", "", abk).lower()


@dataclass
class Unit:
    kind: str
    unit_id: str
    ebene: int | None
    heading: str
    body: str


def split_law(markdown: str) -> tuple[dict, str, list[Unit]]:
    """(front matter, text before the first unit, units) of one law file."""
    front: dict = {}
    text = markdown
    if text.startswith("---\n"):
        end = text.index("\n---\n", 4)
        front = yaml.safe_load(text[4:end]) or {}
        text = text[end + 5 :]
    matches = list(MARKER.finditer(text))
    preamble = text[: matches[0].start()] if matches else text
    units = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        units.append(
            Unit(
                kind=m["kind"],
                unit_id=m["id"],
                ebene=int(m["ebene"]) if m["ebene"] else None,
                heading=m["heading"].strip(),
                body=text[m.end() : end].strip(),
            )
        )
    return front, preamble.strip(), units


def split_enbez(heading: str) -> str | None:
    """The designation at the start of a norm heading ("§ 19a", "Art 3", "Anlage 2"), if any."""
    m = re.match(r"^((?:§§?|Art(?:ikel)?\.?)\s*\d+[a-z]*|Anlage\s*\d*[a-z]*|Anhang\s*\d*[a-z]*)", heading, re.I)
    return m.group(1) if m else None


def build(data_dir: Path, db_path: Path, revision: str = "", states: dict[str, Path] | None = None) -> int:
    """Index every law under data_dir into a new database at db_path; returns the number of laws.

    `states` maps a state code to its data repository's clone. Every clone gets a row in the
    states table; its laws are indexed only if its sync state says `complete`.
    """
    tmp = db_path.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)
    count = _index_dir(db, data_dir, None)
    for code, clone in sorted((states or {}).items()):
        # A broken state repository must not take the federal index down with it: its
        # half-written rows are rolled back and the state counts as incomplete.
        db.execute("SAVEPOINT state")
        try:
            complete = _state_complete(clone)
            if complete:
                count += _index_dir(db, clone, code)
        except Exception as exc:
            log.warning("state %s not indexed: %s", code, exc)
            db.execute("ROLLBACK TO state")
            complete = False
        db.execute("RELEASE state")
        db.execute("INSERT INTO states VALUES (?, ?)", (code, int(complete)))
    db.execute("INSERT INTO meta VALUES ('schema', ?)", (SCHEMA_VERSION,))
    db.execute("INSERT INTO meta VALUES ('revision', ?)", (revision,))
    db.execute("INSERT INTO meta VALUES ('laws', ?)", (str(count),))
    db.commit()
    db.close()
    tmp.replace(db_path)
    return count


def _state_complete(clone: Path) -> bool:
    """Whether a state's sync has finished a full pass; a clone without a state file has not."""
    path = clone / ".sync" / "state.json"
    if not path.exists():
        return False
    return bool(json.loads(path.read_text(encoding="utf-8")).get("complete"))


def law_files(data_dir: Path) -> list[Path]:
    """The law files of a data repository: not READMEs, nothing in a dot directory (.github, .sync)."""
    return [p for p in sorted(data_dir.glob("*/*.md"))
            if not p.name.startswith("README") and not any(x.startswith(".") for x in p.relative_to(data_dir).parts)]


def _index_dir(db: sqlite3.Connection, data_dir: Path, land: str | None) -> int:
    """Index the law files of one repository; paths are stored relative to it."""
    count = 0
    for path in law_files(data_dir):
        front, _, units = split_law(path.read_text(encoding="utf-8"))
        slug = path.stem
        abk = str(front.get("abkuerzung") or slug)
        titel = str(front.get("titel") or abk)
        breadcrumb: list[str] = []
        norms = 0
        for ord_, u in enumerate(units):
            enbez = None
            if u.kind == "gliederung":
                depth = u.ebene or 1
                breadcrumb = breadcrumb[: depth - 1] + [u.heading]
            else:
                enbez = split_enbez(u.heading)
                norms += 1
            crumb = " › ".join(breadcrumb if u.kind == "norm" else breadcrumb[:-1])
            cur = db.execute(
                "INSERT INTO units (slug, ord, kind, unit_id, ebene, enbez, enbez_norm, heading, breadcrumb, law, body)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (slug, ord_, u.kind, u.unit_id, u.ebene, enbez, norm_key(enbez) if enbez else None,
                 u.heading, crumb, f"{abk} {titel}", u.body),
            )
            if u.kind == "norm" and (u.body or u.heading):
                db.execute(
                    "INSERT INTO units_fts (rowid, heading, breadcrumb, law, body) VALUES (?,?,?,?,?)",
                    (cur.lastrowid, u.heading, crumb, f"{abk} {titel}", u.body),
                )
        cur = db.execute(
            "INSERT INTO laws VALUES (?,?,?,?,?,?,?,?,?,?)",
            (slug, abk, abk_key(abk), titel, front.get("kurztitel"), front.get("stand"),
             front.get("quelle") or "", str(path.relative_to(data_dir)), norms, land),
        )
        db.execute(
            "INSERT INTO laws_fts (rowid, abk, titel, kurztitel) VALUES (?,?,?,?)",
            (cur.lastrowid, abk, titel, front.get("kurztitel") or ""),
        )
        count += 1
    return count


def _land_filter(land: str | None) -> tuple[str, list]:
    """An SQL condition on laws.land: None means all sources, BUND federal law, else that state's code."""
    if land is None:
        return "", []
    if land == BUND:
        return " AND laws.land IS NULL", []
    return " AND laws.land = ?", [land]


# Words that say nothing about which provision is meant.
STOPWORDS = set(
    "der die das den dem des ein eine einen einem einer eines und oder aber für fuer mit ohne von vom zu zum zur"
    " im in am an auf aus bei bis nach über ueber unter vor als wie wenn ob ich mich mein meine meinen meiner wir"
    " uns unser sie er es ihr man ist sind war wird werden wurde muss müssen kann können darf dürfen soll sollen"
    " brauche brauchen habe haben hat gibt was wer wo wann warum welche welcher welches nicht kein keine auch noch"
    " so sich da dass daß gilt eigentlich bitte beim vom ans".split()
)
_SUFFIXES = ("ungen", "ung", "en", "er", "es", "e", "n", "s")


def _stem(word: str) -> str:
    """A light German stem, used as an FTS5 prefix: "anzeigen" -> "anzeig" finds Anzeige, Anzeigepflicht."""
    lower = word.lower()
    for suffix in _SUFFIXES:
        if len(lower) - len(suffix) >= 5 and lower.endswith(suffix):
            return lower[: -len(suffix)]
    return lower


def query_terms(text: str) -> list[str]:
    words = re.findall(r"[\wäöüÄÖÜß]+", text)
    terms = []
    for w in words:
        if w.lower() in STOPWORDS or (len(w) < 2 and not w.isdigit()):
            continue
        t = _stem(w)
        if t not in terms:
            terms.append(t)
    return terms


def fts_query(text: str, mode: str = "AND") -> str:
    """Turn a free-text question into an FTS5 query of prefix terms.

    German compounds make prefixes worth it: "Kleinunternehmer" also finds
    "Kleinunternehmerregelung". Quotes keep FTS5 syntax characters literal.
    """
    return f" {mode} ".join(f'"{t}"*' for t in query_terms(text))


class Store:
    """Read access to one built index. Open a new Store after a rebuild."""

    def __init__(self, db_path: Path):
        self.db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.create_function("ln", 1, math.log, deterministic=True)

    def close(self) -> None:
        self.db.close()

    def meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def state_status(self) -> dict[str, bool]:
        """Every state with a data repository: whether its laws are complete and indexed."""
        return {r["code"]: bool(r["complete"]) for r in self.db.execute("SELECT * FROM states ORDER BY code")}

    def resolve_law(self, law: str, land: str | None = None) -> list[sqlite3.Row]:
        """Laws matching an abbreviation, a slug or a title; exact matches first.

        `land`: None for all sources, BUND for federal law only, a state code for that state only.
        """
        where, args = _land_filter(land)
        rows = self.db.execute(
            f"SELECT * FROM laws WHERE (abk_norm = ? OR slug = ?){where} ORDER BY land IS NOT NULL, length(titel)",
            (abk_key(law), law.strip().lower(), *args),
        ).fetchall()
        if rows:
            return rows
        return self.find_laws(law, limit=5, land=land)

    def find_laws(self, query: str, limit: int = 10, land: str | None = None) -> list[sqlite3.Row]:
        q = fts_query(query, "OR")
        if not q:
            return []
        where, args = _land_filter(land)
        return self.db.execute(
            "SELECT laws.* FROM laws_fts JOIN laws ON laws.rowid = laws_fts.rowid"
            f" WHERE laws_fts MATCH ?{where} ORDER BY bm25(laws_fts, 10.0, 3.0, 3.0) LIMIT ?",
            (q, *args, limit),
        ).fetchall()

    def search(
        self, query: str, slug: str | None = None, limit: int = 10, land: str | None = BUND
    ) -> list[sqlite3.Row]:
        """Norms matching all terms first; if those are too few, norms matching any term.

        `land` as in resolve_law, but federal law only by default.
        """
        rows: list[sqlite3.Row] = []
        seen: set[int] = set()
        for mode in ("AND", "OR"):
            q = fts_query(query, mode)
            if not q:
                return []
            for row in self._search(q, slug, limit, land):
                if row["id"] not in seen:
                    seen.add(row["id"])
                    rows.append(row)
            if len(rows) >= limit or len(query_terms(query)) < 2:
                break
        return rows[:limit]

    def count_by_land(self, query: str) -> dict[str, int]:
        """Matching norms per state, federal law left out: all terms, or any term if none match all."""
        counts: dict[str, int] = {}
        for mode in ("AND", "OR"):
            q = fts_query(query, mode)
            if not q:
                return {}
            counts = {
                r["land"]: r["n"]
                for r in self.db.execute(
                    "SELECT laws.land, count(*) AS n FROM units_fts JOIN units ON units.id = units_fts.rowid"
                    " JOIN laws ON laws.slug = units.slug WHERE units_fts MATCH ? AND laws.land IS NOT NULL"
                    " GROUP BY laws.land ORDER BY laws.land",
                    (q,),
                )
            }
            if counts or len(query_terms(query)) < 2:
                break
        return counts

    def _search(self, q: str, slug: str | None, limit: int, land: str | None = BUND) -> list[sqlite3.Row]:
        sql = (
            "SELECT units.*, laws.abk, laws.titel AS law_titel, laws.stand, laws.quelle, laws.land,"
            " snippet(units_fts, 3, '**', '**', ' … ', 24) AS snippet"
            " FROM units_fts JOIN units ON units.id = units_fts.rowid JOIN laws ON laws.slug = units.slug"
            " WHERE units_fts MATCH ?"
        )
        args: list = [q]
        if slug:
            sql += " AND units.slug = ?"
            args.append(slug)
        where, land_args = _land_filter(land)
        sql += where
        args += land_args
        # Larger laws are the ones people mean more often (BGB over a Verordnung on cattle trading),
        # so they get a gentle boost; bm25 is negative, more negative is better.
        sql += " ORDER BY bm25(units_fts, 8.0, 2.0, 3.0, 1.0) * (1 + 0.15 * ln(max(laws.norm_count, 1))) LIMIT ?"
        args.append(limit)
        return self.db.execute(sql, args).fetchall()

    def law(self, slug: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM laws WHERE slug = ?", (slug,)).fetchone()

    def norm(self, slug: str, designation: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM units WHERE slug = ? AND kind = 'norm' AND enbez_norm = ? ORDER BY ord LIMIT 1",
            (slug, norm_key(designation)),
        ).fetchone()

    def outline(self, slug: str) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT kind, ebene, heading, enbez FROM units WHERE slug = ? ORDER BY ord", (slug,)
        ).fetchall()
