"""Nordrhein-Westfalen: RECHT.NRW (recht.nrw.de), run by the Redaktion der Verkündungsblätter im
Ministerium des Innern NRW, hosted by IT.NRW. The consolidated texts are "nichtamtlich".

robots.txt is Drupal's default: it keeps crawlers out of /admin/, /search/, /user/ and the like,
but not out of /lrgv/ (the law pages) or /search-middleware/ (the search index). There is no
sitemap line and no licence statement.

Listing: the portal's search page queries an OpenSearch index through /search-middleware.
The index holds one document per law, its newest version (Fassung), typed "Gesetz",
"Rechtsverordnung", "Verwaltungsvorschrift", "Bekanntmachung" and so on. The listing asks for
the first two (and "Verordnung", which the search form offers) and for laws in force: in force
since today or earlier (or no date), not out of force, not marked historical, as the search
page's own "in Kraft" filter does, but without its condition that the version applies today, so
that a law whose newest version starts later is not missed. Every hit's version date
("field_effective_from") serves as lastmod.

Law id: a version's URL carries its date and title ("/lrgv/gesetz/16102026-studierendenwerksgesetz-stwg")
and changes with every amendment. The stable id is the law's taxonomy term ("Link zur
aktuellsten Fassung", /taxonomy/term/31127), which the index does not hold. Every version page
names it as its canonical link in the first kilobyte, so the listing reads the first few
kilobytes of each page (an HTTP Range request) to learn it: slug "nw-31127". Two laws (of
1,209 on 2026-10-20) had no term; their page is its own canonical link, and the slug is the
last part of its URL.

Law: the version page has the whole text: a preamble (Eingangsformel, the Inhaltsübersicht),
nested <section>s for the Gliederung (legaldoc-part, -chapter, -section, -subsection) and the
§§/Artikel (legaldoc-article, with field_num and field_headline), footnotes per article as
a collapsible list (the change notes), a Schlussformel, and the Anlagen only as PDF
attachments. Unit ids are derived from the designations ("par5", "kapitel2-abschnitt1").
Abbreviation and short title come from the index, as the page's title does not tell them apart.

Versions: each page lists every version of its law, newest first, with its start date. If the
newest version starts after today, fetch takes the version in force today from that list and
returns the newer one's start as next_version_from; if the law has no version in force yet, it
raises NotYetInForce.
"""

from __future__ import annotations

import datetime
import re
from concurrent.futures import ThreadPoolExecutor

import httpx

from convert import footnote_block
from sources.html import Node, Renderer, designation_slug, line, parse_html
from state_markdown import render
from state_sync import Entry, Fetched, NotYetInForce
from store import Unit

BASE = "https://recht.nrw.de"
SEARCH = f"{BASE}/search-middleware/opensearch_internet/_search"
TYPES = ("Gesetz", "Rechtsverordnung", "Verordnung")  # never Verwaltungsvorschrift or Bekanntmachung
PATH_TYPES = ("gesetz", "rechtsverordnung", "verordnung")  # the same in the page URLs (/lrgv/<type>/…)
MAX_HITS = 10_000  # OpenSearch's default result window; the index holds about 4,100 documents
HEAD_BYTES = 8192  # the canonical link sits in the first kilobyte of the page

_CANONICAL = re.compile(r'<link rel="canonical" href="([^"]+)"')
_DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
# An abbreviation at the end of the title: "(WBVO-Pflege-NRW)", "(ECTS-Statistikverordnung – ECTS-VO)".
_TITLE_ABK = re.compile(r"\(([^()]+)\)\s*$")


def _noon_utc(day: datetime.date) -> int:
    """The index's timestamps are noon UTC of the day they stand for."""
    return int(datetime.datetime(day.year, day.month, day.day, 12, tzinfo=datetime.timezone.utc).timestamp())


def _day(timestamp: list[int] | None) -> str | None:
    if not timestamp:
        return None
    return datetime.datetime.fromtimestamp(timestamp[0], datetime.timezone.utc).date().isoformat()


def listing_query(today: datetime.date) -> dict:
    """Gesetze and Verordnungen in force on `today`, as the search page's "in Kraft" filter asks."""
    now = _noon_utc(today)
    return {
        "query": {"bool": {"filter": [
            {"terms": {"type": ["state_law_and_regulations"]}},
            {"terms": {"field_document_type_name": list(TYPES)}},
            {"bool": {"should": [{"range": {"field_inforce_date": {"lte": now}}},
                                 {"bool": {"must_not": {"exists": {"field": "field_inforce_date"}}}}]}},
            {"bool": {"should": [{"range": {"field_outforce_date": {"gt": now}}},
                                 {"bool": {"must_not": {"exists": {"field": "field_outforce_date"}}}}]}},
            {"bool": {"must_not": {"term": {"field_historically": {"value": True}}}}},
        ]}},
        "size": MAX_HITS,
        "track_total_hits": True,
        "_source": ["url", "field_document_type_name", "field_effective_from"],
    }


class NwSource:
    code = "NW"
    crawl_delay = 0.0
    workers = 2
    # 1,209 listed on 2026-10-20 (480 Gesetze, 729 Rechtsverordnungen); about 90 %.
    min_entries = 1088

    def list_laws(self, client: httpx.Client) -> list[Entry]:
        response = client.post(SEARCH, json=listing_query(datetime.date.today()))
        response.raise_for_status()
        hits = response.json()["hits"]
        total = hits["total"]["value"]
        found = hits["hits"]
        if hits["total"].get("relation", "eq") != "eq" or total >= MAX_HITS:
            raise ValueError(f"index announces {total} hits, more than one page holds")
        if len(found) != total:
            raise ValueError(f"{total} hits announced, {len(found)} returned")
        versions = []
        for hit in found:
            source = hit["_source"]
            kind = (source.get("field_document_type_name") or [None])[0]
            if kind not in TYPES:
                raise ValueError(f"{source.get('url')}: unexpected type {kind!r}")
            versions.append((f"{BASE}{source['url'][0]}", _day(source.get("field_effective_from"))))
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            terms = list(pool.map(lambda v: law_id(client, v[0]), versions))
        entries: dict[str, Entry] = {}
        for term, (url, lastmod) in zip(terms, versions):
            entry = Entry(slug_for(term), url, lastmod)
            known = entries.get(entry.slug)
            # Two indexed versions of one law: the newer one leads to all others.
            if known is None or (entry.lastmod or "", entry.url) > (known.lastmod or "", known.url):
                entries[entry.slug] = entry
        return list(entries.values())

    def fetch(self, client: httpx.Client, entry: Entry, today: datetime.date) -> Fetched | None:
        meta = index_entry(client, entry.url)
        if meta.get("field_document_type_name", [None])[0] not in TYPES:
            return None
        page = _get(client, entry.url)
        newest = _valid_from(page)
        if entry.lastmod and newest.isoformat() != entry.lastmod:
            # The index and the page disagree (one was updated in between): try again next run.
            raise ValueError(f"page valid from {newest}, listing says {entry.lastmod}")
        url = entry.url
        versions = _versions(page, entry.url)
        later = sorted(d for d, _ in versions if d > today)
        if newest > today:
            current = max(((d, u) for d, u in versions if d <= today), default=None)
            if current is None:
                raise NotYetInForce(later[0].isoformat() if later else newest.isoformat())
            url = current[1]
            page = _get(client, url)
        next_version = later[0].isoformat() if later else None
        return parse_law(page, url, meta, entry.slug.removeprefix("nw-"), next_version)


def slug_for(term: str) -> str:
    """The law's taxonomy term id as a slug: "31127" -> "nw-31127"."""
    return "nw-" + re.sub(r"[^a-z0-9_-]", "_", term.lower())


def law_id(client: httpx.Client, url: str) -> str:
    """The law's id from the canonical link in the first bytes of a version page.

    That is the law's taxonomy term ("31127"). A few laws have none yet; their page names
    itself, and the id is the last part of its URL ("01072022-verordnung-ueber-…").
    """
    response = client.get(url + "/", headers={"Range": f"bytes=0-{HEAD_BYTES - 1}"})
    response.raise_for_status()
    m = _CANONICAL.search(response.text)
    if not m:
        raise ValueError(f"{url}: no canonical link")
    if m[1] == url:
        return url.rsplit("/", 1)[1]
    term = re.fullmatch(rf"{re.escape(BASE)}/taxonomy/term/(\d+)", m[1])
    if not term:
        raise ValueError(f"{url}: canonical link {m[1]} is neither the law nor the page")
    return term[1]


def index_entry(client: httpx.Client, url: str) -> dict:
    """The index document of one version (abbreviation, short title, type)."""
    path = url.removeprefix(BASE)
    response = client.post(SEARCH, json={
        "query": {"bool": {"filter": [{"term": {"url": path}}]}},
        "size": 2,
        "_source": ["url", "field_document_type_name", "field_abbreviation", "field_short_title",
                    "field_long_title"],
    })
    response.raise_for_status()
    found = response.json()["hits"]["hits"]
    if len(found) != 1:
        raise ValueError(f"{url}: {len(found)} index documents")
    return found[0]["_source"]


def _get(client: httpx.Client, url: str) -> Node:
    response = client.get(url + "/")
    response.raise_for_status()
    # Some texts carry a doubly escaped "&amp;nbsp;" that would show as "&nbsp;".
    return parse_html(response.text.replace("&amp;nbsp;", "&#160;"))


def _date(text: str) -> datetime.date | None:
    m = _DATE.search(text)
    return datetime.date(int(m[3]), int(m[2]), int(m[1])) if m else None


def _valid_from(root: Node) -> datetime.date:
    """The "Gültig ab" date in the page's info box (under "Fassung")."""
    box = root.find("div", id="block-rnrw-legal-document-info-box")
    for item in (n for n in box.iter() if "info-box-item" in n.classes()) if box is not None else ():
        label = next((n for n in item.elements() if "field__label" in n.classes()), None)
        value = next((n for n in item.elements() if "field__item" in n.classes()), None)
        if label is not None and value is not None and line(label.text()) == "Gültig ab":
            day = _date(value.text())
            if day:
                return day
    raise ValueError("page without a Gültig ab date")


def _versions(root: Node, url: str) -> list[tuple[datetime.date, str]]:
    """(start date, URL) of every version the page lists; the page itself without a link."""
    box = root.find("div", id="versions")
    out = []
    for li in (n for n in box.iter() if n.tag == "li") if box is not None else ():
        day = _date(li.text())
        if day is None:
            continue
        link = li.find("a")
        out.append((day, BASE + link.attrs["href"].rstrip("/") if link is not None else url))
    return out


def _abbreviation(meta: dict, title: str, term: str) -> str:
    """The index's abbreviation, else one in parentheses at the end of the title, else the law id."""
    abk = line((meta.get("field_abbreviation") or [""])[0])
    if abk:
        return abk
    m = _TITLE_ABK.search(title)
    if m:
        candidate = re.split(r"\s+[–-]\s+", m[1])[-1].strip()
        if len(candidate) <= 30 and re.search(r"[A-ZÄÖÜ]{2}", candidate):
            return candidate
    return term


# -- the law page


def parse_law(root: Node, url: str, meta: dict, term: str, next_version: str | None) -> Fetched:
    """The Markdown file for the version at `url` from its page and its law's index document."""
    valid = _valid_from(root)
    title_block = root.find("div", id="block-rnrw-page-title")
    h1 = title_block.find("h1") if title_block is not None else None
    titel = line("".join(c if isinstance(c, str) else c.text() for c in h1.children
                         if isinstance(c, str) or "title-additions" not in c.classes())) if h1 is not None else ""
    titel = titel or line((meta.get("field_long_title") or [""])[0])
    kurz = line((meta.get("field_short_title") or [""])[0])
    front = {
        "land": "NW",
        "abkuerzung": _abbreviation(meta, titel, term),
        "titel": titel or kurz or term,
        "kurztitel": kurz if kurz and kurz != titel else None,
        "stand": f"Fassung gültig ab {valid.strftime('%d.%m.%Y')}",
        "gilt_ab": valid.isoformat(),
        "naechste_fassung_ab": next_version,
        "quelle": url,
    }

    content = root.find("div", id="block-rnrw-content")
    if content is None:
        raise ValueError(f"{url}: no law text")
    law = _Law()
    article = content.find("article") or content
    holder = next((n for n in article.elements() if n.tag == "div"), article)
    for part in holder.elements():
        classes = part.classes()
        if "footnote-container" in classes:
            law.notes += law.footnotes(part)  # notes on the law as a whole
        elif "field--name-field-preamble" in classes:
            law.preamble(part)
        elif "field--field_body" in classes:
            law.flush_preamble()
            law.body(part, [])
        elif "field--name-field-conclusions" in classes:
            law.flush_preamble()
            law.formula(part, "schlussformel", "Schlussformel")
    law.flush_preamble()
    law.attachments(root.find("div", id="block-rnrw-attachments"))
    return Fetched(markdown=render(front, law.units), front=front, next_version_from=next_version)


def _escape_numbering(block: str) -> str:
    """ "1. die Errichtung …" at the start of a line would become a Markdown ordered list."""
    return re.sub(r"(?m)^(\d+[a-z]?)\.(?=\s)", r"\1\\.", block)


class _Law(Renderer):
    """Collects the units of one law; footnotes are gathered per unit."""

    def __init__(self) -> None:
        self.units: list[Unit] = []
        self.used: set[str] = set()
        self.notes: list[str] = []
        self.formel: list[str] = []
        self.preamble_done = False

    def unit_id(self, base: str) -> str:
        """A unique id: a repeated designation gets "-2", "-3" in document order."""
        candidate, n = base, 1
        while candidate in self.used:
            n += 1
            candidate = f"{base}-{n}"
        self.used.add(candidate)
        return candidate

    def add(self, kind: str, base: str, ebene: int | None, heading: str, blocks: list[str]) -> None:
        blocks = [_escape_numbering(b) for b in blocks]
        if self.notes:
            blocks = blocks + [footnote_block(self.notes)]
        self.units.append(Unit(kind, self.unit_id(base), ebene, heading, "\n\n".join(blocks)))
        self.notes = []

    def text_blocks(self, el: Node) -> list[str]:
        """The rendered text fields directly inside a paragraph element."""
        out: list[str] = []
        for child in el.elements():
            if "field--name-field-text" in child.classes():
                out.extend(self.blocks(child))
        return out

    def footnotes(self, container: Node) -> list[str]:
        """The notes in a "Fußnoten" box: "<Veröffentlichung>: <text>" each."""
        notes = []
        for item in (n for n in container.iter() if "paragraph--type--footnotes" in n.classes()):
            reference = next((n for n in item.iter() if "field--field_reference" in n.classes()), None)
            ref = ""
            if reference is not None:
                link = reference.find("a")
                ref = line(link.text()) if link is not None else ""
            text = "\n\n".join(b for n in item.iter() if "field--name-field-footnote-description" in n.classes()
                               for b in self.blocks(n))
            if text or ref:
                notes.append(f"{ref}: {text}" if ref and text else text or ref)
        return notes

    # -- structure

    def preamble(self, el: Node) -> None:
        """The Eingangsformel; the Inhaltsübersicht is left out (the units are the outline)."""
        for paragraph in (n for n in el.iter() if "paragraph" in n.classes()):
            if "paragraph--type--formel" in paragraph.classes():
                self.formel += self.text_blocks(paragraph)

    def flush_preamble(self) -> None:
        """The Eingangsformel unit, with the notes on the law as a whole, once, before the body."""
        if self.preamble_done:
            return
        self.preamble_done = True
        if self.formel or self.notes:
            self.add("norm", "eingangsformel", None, "Eingangsformel", self.formel)

    def formula(self, el: Node, base: str, heading: str) -> None:
        blocks = [b for paragraph in el.iter() if "paragraph--type--formel" in paragraph.classes()
                  for b in self.text_blocks(paragraph)]
        if blocks:
            self.add("norm", base, None, heading, blocks)

    def body(self, el: Node, path: list[str]) -> None:
        """Walk the nested sections: legaldoc-article is a norm, any other a Gliederung."""
        for section in el.elements():
            if section.tag != "section":
                self.body(section, path)
                continue
            paragraph = next((n for n in section.elements() if "paragraph" in n.classes()), None)
            if paragraph is None:
                continue
            num, headline = self.designation(paragraph)
            container = next((n for n in paragraph.elements() if "footnote-container" in n.classes()), None)
            if container is not None:
                self.notes += self.footnotes(container)
            blocks = self.text_blocks(paragraph)
            heading = " ".join(x for x in (num, headline) if x)
            if "legaldoc-article" in section.classes():
                if not heading and not blocks and not self.notes:
                    continue  # an empty placeholder
                if not heading and not self.units:
                    # Older texts keep their Eingangsformel in an unnamed first article.
                    self.add("norm", "eingangsformel", None, "Eingangsformel", blocks)
                    continue
                self.add("norm", designation_slug(num or headline) or "ohnebezeichnung", None,
                         heading or "(ohne Bezeichnung)", blocks)
                continue
            part = designation_slug(num or headline) or "gliederung"
            self.add("gliederung", "-".join(path + [part]), len(path) + 1, heading or "(ohne Bezeichnung)", blocks)
            self.body(section, path + [part])

    def designation(self, paragraph: Node) -> tuple[str, str]:
        """(field_num, field_headline) of a section's header."""
        header = next((n for n in paragraph.elements() if "paragraph-header" in n.classes()), None)
        num = headline = ""
        if header is not None:
            for n in header.iter():
                if "field--field_num" in n.classes():
                    num = self.plain(n)
                elif "field--field_headline" in n.classes():
                    headline = self.plain(n)
        return line(num), line(headline)

    def attachments(self, box: Node | None) -> None:
        """The Anlagen: the portal has them only as PDF files, so each unit links its file."""
        if box is None:
            return
        for item in (n for n in box.iter() if "attachment-item" in n.classes()):
            link = item.find("a")
            title = next((n for n in item.iter() if "field--name-field-publictitle" in n.classes()), None)
            if link is None or title is None:
                continue
            label = re.sub(r"\s*\(PDF\)\s*$", "", line(title.text()))
            m = re.fullmatch(r"(Anlage|Anhang)\s*0*(\d+[a-z]?)", label)
            heading = f"{m[1]} {m[2]}" if m else label
            href = link.attrs.get("href", "")
            self.add("norm", designation_slug(heading) or "anlage", None, heading,
                     [f"Nur als PDF veröffentlicht: <{BASE}{href}>" if href.startswith("/") else f"<{href}>"])

