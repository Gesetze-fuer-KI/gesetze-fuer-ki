"""Bremen: Transparenzportal Bremen (transparenz.bremen.de), run by Der Senator für Finanzen.

robots.txt is empty. The portal's terms put each document under the licence given for it; the
Impressum puts the law texts under "Creative Commons Namensnennung - Nicht kommerziell - Keine
Bearbeitung" (the portal's licence list: CC BY-NC-ND 3.0), for the publisher's editorial
additions. So the text is converted as for every state but never reworded; the attribution in
states.py heads every file. The texts come from juris and have its layout.

Listing: the Vorschriften search, filtered to the type "Gesetze und Rechtsverordnungen" and
"In Kraft", sorted by title and paged 50 hits at a time (the portal's maximum). It announces a
count, which the unique hits must match. Each hit is one version of a law: its id changes with
every new version, and the listing shows its Stand (the day the portal updated it), which
together with the id serves as lastmod. The filter also returns non-laws (Prüfungsordnungen,
overviews) and Ortsgesetze of the Stadtgemeinden Bremen and Bremerhaven (municipal law, like
Satzungen elsewhere); fetch skips them by the juris Dokumenttyp and logs the type, so a full run
shows what was left out. The 33 listing pages are slow (about 2.5 minutes).

Slug: a version id is no stable law id, so each law's page is read once per version to find
the juris document key ("jlr-TariftVergabeGBRrahmen" -> "hb-tariftvergabegbr"), which stays
the same across versions. The cache keeps version id -> slug across runs, so a night only reads
the pages of new versions, and the page read while listing is kept for fetch: a new version
costs one request. A document without juris key (an overview) gets its version id. The first
run thus reads all ~1,600 pages while listing (two at a time, before the runner's time budget
applies), holding them compressed for fetch; with the cache, later nights read only new versions.

Law: /metainformationen/<title>-<version id>?template=20_gp_ifg_meta_detail_d is the whole
text: a header (abbreviation, juris Dokumenttyp: only Gesetz and Verordnung are kept), the title,
the period of this version, the Stand ("letzte berücksichtigte Änderung"),
then one block per unit: Eingangsformel, table of contents (skipped), Gliederungen (heading
level h3, h4, … is their depth) and §§/Artikel/Anlagen with their footnotes. Unit ids come from
the designations ("par5", "zweiterhauptteil-1abschnitt").

Versions: the page names the period of its version ("Gesamtausgabe in der Gültigkeit vom
02.10.2026 bis 31.12.2029"); if it ends, the next version (listed under "Zukünftige Fassungen")
starts the day after, which is next_version_from. A version starting after today raises
NotYetInForce.
"""

from __future__ import annotations

import datetime
import html
import logging
import re
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx

from convert import footnote_block
from sources.html import HEADINGS, ORDINAL, Node, Renderer, designation_slug, line, parse_html
from state_markdown import render
from state_sync import Entry, Fetched, NotYetInForce
from store import Unit

log = logging.getLogger("sources.hb")

BASE = "https://www.transparenz.bremen.de"
LISTING = f"{BASE}/vorschriften-72741"
LISTING_TYPE = "Gesetze und Rechtsverordnungen"
LISTING_PARAMS = {
    "id": "72743", "gsid": "kogis_tp_berlin01.c.60176.de", "_article_id": "72741", "fulltext": "",
    "vorschriften[0]": LISTING_TYPE, "gltigkeit[0]": "In Kraft", "sort": "titel", "order": "asc",
}
PAGE_SIZE = 50  # the most the portal shows per page
RETRY_DELAY = 5.0  # seconds before the one retry of a request that failed on the server's side
KINDS = {"Gesetz", "Verordnung", "Rechtsverordnung"}  # juris Dokumenttyp of the laws kept
MIN_TEXT_WITHOUT_NORMS = 2000  # a longer text without any § or Artikel is a layout this parser does not know

_COUNT = re.compile(r"Ergebnisse\s+[\d.]+\s*-\s*[\d.]+\s+von\s+\(([\d.]+)\)")
_HIT = re.compile(r'<li class="search-result-item" data-id="(\d+)">(.*?)</li>', re.DOTALL)
_HIT_TYPES = re.compile(r"<b>Dokumententyp:</b>\s*((?:<span>[^<]*</span>)+)")
_HIT_STAND = re.compile(r"Stand: (\d{2})\.(\d{2})\.(\d{4})")
_HIT_INKRAFT = re.compile(r"Inkrafttreten: (\d{2}\.\d{2}\.\d{4})")
_HIT_LINK = re.compile(r'<a class="more" href="([^"]+)"[^>]*><b>Vorschrift direkt aufrufen</b>')
_VERSION = re.compile(r"-(\d+)\?")
_DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
_PERIOD = re.compile(r"Gültigkeit vom (\d{2}\.\d{2}\.\d{4})(?: bis (\d{2}\.\d{2}\.\d{4}))?")
_TITLE_END = re.compile(r"(?:Vom|vom|In der Fassung|in der Fassung)\b")

_NORM_DESIGNATION = re.compile(
    r"(?:§§?|Art\.|(?:Artikel|Anlagen?|Anhang)\b)\s*(?:\d+[a-z]*\b)?(?:\s+bis\s+\d+[a-z]*\b)?")
_GLIEDERUNG = re.compile(
    rf"(?:[IVXLC\d]+\.\s*|{ORDINAL})?"
    r"(?:Hauptteil|Teil|Buch|Kapitel|Unterkapitel|Abschnitt|Unterabschnitt|Titel|Untertitel)\b"
    r"(?:\s+[IVXLC\d]+[a-z]?\b\.?)?")


@dataclass
class _Hit:
    version: str
    url: str
    lastmod: str
    inkraft: datetime.date


class HbSource:
    code = "HB"
    crawl_delay = 0.0
    workers = 2
    # 1,611 listed on 2026-10-20 (non-laws among them are skipped when fetched); about 90 %.
    min_entries = 1450

    def __init__(self) -> None:
        # Version id -> slug, kept by the runner across runs: a version's page is read once.
        self.cache: dict[str, str] = {}
        self._pages: dict[str, bytes] = {}  # version id -> page read while listing (compressed), for fetch

    def list_laws(self, client: httpx.Client) -> list[Entry]:
        hits = listing(client)
        listed = {h.version for h in hits}
        self.cache = {k: v for k, v in self.cache.items() if k in listed}  # earlier versions are not needed
        todo = [h for h in hits if h.version not in self.cache]
        pool = ThreadPoolExecutor(max_workers=self.workers)
        try:
            for hit, page in zip(todo, pool.map(lambda h: _get(client, h.url), todo)):
                # Saved one by one: a listing that breaks off keeps what it has resolved.
                self.cache[hit.version] = _resolve(page, hit.version)
                self._pages[hit.version] = zlib.compress(page.encode())
        finally:
            pool.shutdown(cancel_futures=True)  # after a failure, request no more pages
        chosen: dict[str, _Hit] = {}
        for h in hits:
            slug = self.cache[h.version]
            if slug in chosen:
                # Two listed versions of one law (the portal lagging): the later one applies.
                log.warning("%s listed twice (versions %s and %s)", slug, chosen[slug].version, h.version)
                h = _later(chosen[slug], h)
            chosen[slug] = h
        return [Entry(slug, h.url, h.lastmod) for slug, h in chosen.items()]

    def fetch(self, client: httpx.Client, entry: Entry, today: datetime.date) -> Fetched | None:
        m = _VERSION.search(entry.url)
        kept = self._pages.pop(m[1], None) if m else None
        page = zlib.decompress(kept).decode() if kept is not None else _get(client, entry.url)
        return parse_law(page, entry.url, entry.slug, today)


def _get(client: httpx.Client, url: str) -> str:
    """A page's text; a network error or a 5xx is retried once after RETRY_DELAY."""
    try:
        response = client.get(url)
        if response.status_code < 500:
            response.raise_for_status()
            return response.text
    except httpx.TransportError:
        pass
    time.sleep(RETRY_DELAY)
    response = client.get(url)
    response.raise_for_status()
    return response.text


def _later(a: _Hit, b: _Hit) -> _Hit:
    """The version that applies later; on the same day the one with the higher id."""
    return max(a, b, key=lambda h: (h.inkraft, int(h.version)))


def _resolve(page: str, version: str) -> str:
    """The slug for a version from its page: the juris key, or the version id for an overview.

    Any other page (an error page, a truncated response, a new template) raises: a made-up slug
    would be cached for good, and the law's file deleted at the end of the pass.
    """
    key = law_key(page)
    if key:
        return slug_for(key)
    _, _, fields = _document(page, version)
    if "Dokumenttyp" not in fields:
        return slug_for(version)
    raise ValueError(f"{version}: a juris document without key")


def slug_for(key: str) -> str:
    """A juris document key (or a version id) as a slug:
    "TariftVergabeGBR" -> "hb-tariftvergabegbr"."""
    return "hb-" + re.sub(r"[^a-z0-9_-]", "_", key.lower())


def listing(client: httpx.Client) -> list[_Hit]:
    """Every hit of the listing, page by page; the number of unique hits must match the announced count."""
    total: int | None = None
    hits: dict[str, _Hit] = {}
    skip = 0
    while total is None or skip < total:
        response = client.get(LISTING, params={**LISTING_PARAMS, "skip": str(skip), "max": str(PAGE_SIZE)})
        response.raise_for_status()
        page_total, page_hits = parse_listing(response.text)
        if total is not None and page_total != total:
            raise ValueError(f"page at {skip}: {page_total} hits announced instead of {total}")
        total = page_total
        if not page_hits:
            break
        for h in page_hits:
            hits.setdefault(h.version, h)
        skip += PAGE_SIZE
    if len(hits) != total:
        raise ValueError(f"{total} hits announced, {len(hits)} listed")
    return list(hits.values())


def parse_listing(page: str) -> tuple[int, list[_Hit]]:
    """(announced number of hits, the hits on this page) of one listing page."""
    m = _COUNT.search(page)
    if not m:
        raise ValueError("listing page without a hit count")
    hits = []
    for version, block in _HIT.findall(page):
        types = _HIT_TYPES.search(block)
        spans = re.findall(r"<span>([^<]*)</span>", types[1]) if types else []
        names = [line(html.unescape(x)).removeprefix("•").strip() for x in spans]
        if LISTING_TYPE not in names:  # an overview carries every type
            raise ValueError(f"{version}: unexpected type {', '.join(names) or None}")
        stand, inkraft, link = _HIT_STAND.search(block), _HIT_INKRAFT.search(block), _HIT_LINK.search(block)
        if not stand or not inkraft or not link:
            raise ValueError(f"{version}: hit without Stand, Inkrafttreten or link")
        url = link[1].replace("&amp;", "&")
        if not url.startswith(f"{BASE}/metainformationen/") or f"-{version}?" not in url:
            raise ValueError(f"{version}: unexpected link {url}")
        hits.append(_Hit(version, url, f"{stand[3]}-{stand[2]}-{stand[1]}/{version}", _date(inkraft[1])))
    return int(m[1].replace(".", "")), hits


def law_key(page: str) -> str | None:
    """The juris document key of a law page ("TariftVergabeGBR"), None for a page without one."""
    m = re.search(r'<a name="jlr-([^"]+)rahmen"', page)
    return m[1] if m else None


def _date(text: str) -> datetime.date:
    m = _DATE.search(text)
    if not m:
        raise ValueError(f"no date in {text!r}")
    return datetime.date(int(m[3]), int(m[2]), int(m[1]))


# -- the law page


def parse_law(page: str, url: str, slug: str, today: datetime.date) -> Fetched | None:
    """The Markdown file for one law from its page; None if it is no Gesetz or Verordnung."""
    root, text, fields = _document(page, url)
    kind = fields.get("Dokumenttyp")
    key = law_key(page)
    if kind is None:
        if key is None:
            return None  # an overview: the portal's layout for documents that are no juris text
        raise ValueError(f"{url}: no Dokumenttyp in the header")
    if kind not in KINDS:
        log.info("skipped juris Dokumenttyp: %s", kind)
        return None
    if key is None or slug_for(key) != slug:
        raise ValueError(f"{url}: the page of {slug_for(key) if key else 'another document'}, not {slug}")
    units_nodes = [n for n in text.iter() if n.tag == "div" and "jgwsAiZDoc" in n.classes()]
    if not units_nodes:
        raise ValueError(f"{url}: no law text")

    law = _Law(root)
    title_box = next((n for n in text.iter() if n.tag == "div" and "docLayoutTitel" in n.classes()), None)
    title_node = next((n for n in title_box.iter() if n.tag == "div" and "doc" in n.classes()), None) \
        if title_box is not None else None
    titel, kurz, paren = _title(law.heading_lines(title_node) if title_node is not None else [])
    abk = fields.get("Amtliche Abkürzung") or fields.get("juris-Abkürzung") or paren or key
    if kurz == abk:
        kurz = None
    law.title_notes, law.notes = law.notes, []

    period = next((line(n.text()) for n in text.iter()
                   if n.tag == "div" and "docLayoutMarginTopMore" in n.classes()), "")
    m = _PERIOD.search(period)
    if m:
        gilt_ab, until = _date(m[1]), _date(m[2]) if m[2] else None
    else:
        span = next((n for n in root.iter() if n.tag == "div" and "metadaten" in n.classes()), None)
        inkraft = line(span.text()) if span is not None else ""
        if "Inkrafttreten" not in inkraft:
            raise ValueError(f"{url}: no date the version applies from")
        gilt_ab, until = _date(inkraft.split("Inkrafttreten", 1)[1]), None
    if gilt_ab > today:
        raise NotYetInForce(gilt_ab.isoformat())
    next_version = until + datetime.timedelta(days=1) if until else None
    next_version_from = next_version.isoformat() if next_version and next_version > today else None

    for node in units_nodes:
        law.unit(node)
    change = law.change
    if change and change.startswith("letzte berücksichtigte Änderung:"):
        change = change.removeprefix("letzte berücksichtigte Änderung:").strip()
    stand = f"{change}, gültig ab {gilt_ab:%d.%m.%Y}" if change else f"Fassung gültig ab {gilt_ab:%d.%m.%Y}"
    front = {
        "land": "HB",
        "abkuerzung": abk,
        "titel": titel or abk,
        "kurztitel": kurz,
        "stand": stand,
        "gilt_ab": gilt_ab.isoformat(),
        "naechste_fassung_ab": next_version_from,
        "quelle": url,
    }
    units = law.finish()
    if not any(u.kind == "norm" and _NORM_DESIGNATION.match(u.heading) for u in units) and \
            sum(len(u.body) for u in units) > MIN_TEXT_WITHOUT_NORMS:
        # A changed page layout must not turn a whole law into one Eingangsformel.
        raise ValueError(f"{url}: no § or Artikel in {sum(len(u.body) for u in units)} characters of text")
    return Fetched(markdown=render(front, units), front=front, next_version_from=next_version_from)


def _document(page: str, where: str) -> tuple[Node, Node, dict[str, str]]:
    """(tree, text container, header fields) of a document page; anything else raises."""
    root = parse_html(page)
    text = next((n for n in root.iter() if n.tag == "div" and "docLayoutText" in n.classes()), None)
    header = next((n for n in text.iter() if n.tag == "div" and "jgwsHead" in n.classes()), None) \
        if text is not None else None
    if text is None or header is None:
        raise ValueError(f"{where}: unrecognised page (no document text or header)")
    return root, text, _fields(header)


def _fields(header: Node) -> dict[str, str]:
    """The header's label/value pairs ("Dokumenttyp" -> "Gesetz"); the first value of a label wins."""
    fields: dict[str, str] = {}
    for row in (n for n in header.iter() if n.tag == "tr"):
        cells = [c for c in row.elements() if c.tag == "td"]
        if len(cells) == 2 and not any(c.tag == "table" for c in cells[1].iter()):
            label = line(cells[0].text()).rstrip(":").strip()
            if label:
                fields.setdefault(label, line(cells[1].text()))
    return fields


def _title(lines: list[str]) -> tuple[str, str | None, str | None]:
    """(title, short title, abbreviation) from the title's lines: "Bremisches Polizeigesetz",
    "(BremPolG)", "in der Fassung vom …". The date line and what follows are left out."""
    title: list[str] = []
    kurz, abk = None, None
    for x in lines:
        if _TITLE_END.match(x):
            break
        if x.startswith("(") and x.endswith(")"):
            inner = x[1:-1].strip()
            both = re.fullmatch(r"(.+?)\s+[-–]\s+(\S+)", inner)  # "(Bremisches Gesetz – BremG)"
            if both:
                kurz, abk = both[1], both[2]
            elif " " in inner:
                kurz = inner
            else:
                abk = inner
            continue
        title.append(x)
    return " ".join(title), kurz, abk


class _Law(Renderer):
    """Collects the units of one law, one juris block (div.jgwsAiZDoc) at a time."""

    def __init__(self, root: Node) -> None:
        self.units: list[Unit] = []
        self.used: set[str] = set()
        self.path: list[tuple[int, str]] = []  # (level, id part) of the enclosing Gliederungen
        self.notes: list[str] = []
        self.title_notes: list[str] = []
        self.change: str | None = None  # the Stand line's text
        # Footnote texts by the name of their anchor; the marker links to it ("#_XY_d35177e782_text").
        self.footnotes: dict[str, Node] = {}
        for box in (n for n in root.iter() if n.tag == "div" and "jgwsAiZDocFootnote" in n.classes()):
            name = None
            for el in (n for n in box.iter() if n.tag in ("dt", "dd")):
                if el.tag == "dt":
                    name = next((a.attrs["name"] for a in el.iter() if a.tag == "a" and a.attrs.get("name")), None)
                elif name:
                    self.footnotes[name] = el
                    name = None

    def unit_id(self, base: str) -> str:
        """A unique id: a repeated designation gets "-2", "-3" in document order."""
        candidate, n = base, 1
        while candidate in self.used:
            n += 1
            candidate = f"{base}-{n}"
        self.used.add(candidate)
        return candidate

    def add(self, kind: str, base: str, ebene: int | None, heading: str, blocks: list[str]) -> None:
        if self.notes:
            blocks = blocks + [footnote_block(self.notes)]
            self.notes = []
        self.units.append(Unit(kind, self.unit_id(base), ebene, heading, "\n\n".join(blocks)))

    def append(self, blocks: list[str]) -> None:
        """Text without a heading of its own: the Eingangsformel, or more of the unit before it."""
        if not self.units:
            self.add("norm", "eingangsformel", None, "Eingangsformel", blocks)
            return
        last = self.units[-1]
        if self.notes:
            blocks = blocks + [footnote_block(self.notes)]
            self.notes = []
        if blocks:
            self.units[-1] = Unit(last.kind, last.unit_id, last.ebene, last.heading,
                                  "\n\n".join(([last.body] if last.body else []) + blocks))

    def finish(self) -> list[Unit]:
        if self.title_notes:
            self.notes = self.title_notes
            self.add("norm", "fussnoten", None, "Fußnoten", [])
        return self.units

    def unit(self, node: Node) -> None:
        for box in [n for n in node.iter() if n.tag == "div" and "jgwsAiZDocFootnote" in n.classes()]:
            _detach(node, box)  # the notes are collected where their markers stand
        names = [a.attrs["name"] for a in node.iter() if a.tag == "a" and a.attrs.get("name", "").startswith("jlr-")]
        stand = next((n for n in node.iter() if n.tag == "table" and "standangaben" in n.classes()), None)
        if stand is not None:
            cells = [c for c in stand.iter() if c.tag == "td"]
            self.change = self.plain(cells[-1]) if cells else None
            self.title_notes += self.notes  # a note on the Stand line belongs to the whole law
            self.notes = []
            return
        heading = next((n for n in node.iter() if n.tag in HEADINGS), None)
        if heading is None:
            if any(n.endswith("IVZ") for n in names) or line(node.text()).startswith("Inhalt"):
                return  # the table of contents
            self.append(self.blocks(node))
            return
        lines = self.heading_lines(heading)
        title = " ".join(lines) or "(ohne Bezeichnung)"
        _detach(node, heading)
        blocks = self.blocks(node)
        # Norm or Gliederung by designation and body only: a footnote on a heading changes neither.
        norm = _NORM_DESIGNATION.match(title)
        g = _GLIEDERUNG.match(title)
        if norm or (blocks and not g):
            designation = norm[0] if norm else (lines[0] if lines else title)
            self.add("norm", designation_slug(designation) or "vorschrift", None, title, blocks)
            return
        level = max(1, int(heading.tag[1]) - 2)  # h3 heads the top level
        while self.path and self.path[-1][0] >= level:
            self.path.pop()
        part = designation_slug(g[0] if g else (lines[0] if lines else title)) or "gliederung"
        self.path.append((level, part))
        # Text of its own and footnotes on its heading stay with the Gliederung, as its body.
        self.add("gliederung", "-".join(p for _, p in self.path), len(self.path), title, blocks)

    def is_footnote(self, el: Node) -> bool:
        return el.tag == "a" and "Overl" in el.classes() and el.attrs.get("href", "").endswith("_text")

    def footnote(self, el: Node) -> str:
        """Collect the note behind a footnote link; returns its marker ("*)", "1)")."""
        marker = line(el.text())
        if marker and not marker.endswith(")"):
            marker += ")"
        note = self.footnotes.get(el.attrs["href"][1:])
        text = "\n\n".join(self.blocks(note)) if note is not None else ""
        if text:
            self.notes.append(f"{marker} {text}" if marker else text)
        return marker


def _detach(root: Node, node: Node) -> None:
    """Remove a node from the tree below root."""
    for parent in root.iter():
        if node in parent.children:
            parent.children.remove(node)
            return
