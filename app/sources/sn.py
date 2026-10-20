"""Sachsen: REVOSax (revosax.sachsen.de), run by the Sächsische Staatskanzlei with SV SAXONIA Verlag.

robots.txt only names one other crawler and points to a sitemap. The sitemap lists every
document (about 6,400, without lastmod) but not its type, and REVOSax also holds
Verwaltungsvorschriften, Förderrichtlinien, Staatsverträge, Bekanntmachungen and amending acts.

Listing: the portal's extended search, restricted to the Vorschriftentypen "G" (Gesetz) and
"VO" (Verordnung), without Mantelvorschriften (acts that only enact or amend others), valid
today. The search is posted once with the form's CSRF token; the hit list then lives in the
session (a cookie) and is paged five hits at a time with GET /suche?seite=N. Every hit names
its type, which is checked, and the date its current version applies from ("Fassung gültig
ab"), which serves as lastmod.

Law: /vorschrift/<id> is the version in force today ("Aktuelle Fassung") with the whole text
on one page: a header (Eingangsformel), one flat <section> per Gliederung, § / Artikel or
Anlage (nesting in data-level), and the footnotes in a footer. The portal's section ids
("abs2uabs1", "x96") are positional and not always consistent, so unit ids are derived from
the designations instead ("par5", "abschnitt2-unterabschnitt1").

Versions: the page lists all versions with their dates, including one that starts after
today. Its start is returned as next_version_from; on that date lastmod changes and the law is
fetched again. Should the page ever show a text that only applies after today, fetch raises
NotYetInForce.
"""

from __future__ import annotations

import datetime
import math
import re

import httpx

from convert import footnote_block
from sources.html import HEADINGS, Node, Renderer, designation_slug, line, parse_html
from state_markdown import render
from state_sync import Entry, Fetched, NotYetInForce
from store import Unit

BASE = "https://www.revosax.sachsen.de"
CATEGORIES = ("G", "VO")
TYPES = {"Gesetz", "Verordnung"}  # how the portal names CATEGORIES in hit lists and page metadata

_MONTHS = {m: i for i, m in enumerate(("januar", "februar", "märz", "april", "mai", "juni", "juli", "august",
                                       "september", "oktober", "november", "dezember"), 1)}
_DATE = re.compile(r"(\d{1,2})\.\s*([A-Za-zäÄ]+)\s+(\d{4})")
_TOKEN = re.compile(r'name="authenticity_token" value="([^"]+)"')
_COUNT = re.compile(r"<h2>\s*(\d[\d.]*) Treffer")
_HIT_LINK = re.compile(r'href="/vorschrift/(\d+)[^"]*"')
_HIT_TYPE = re.compile(r"Vorschriftentyp:\s*([^<\n]+)")
_HIT_VALID = re.compile(r"Fassung gültig ab:([^<]+)")
_VERSION_DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")

# A norm's designation at the start of its heading, and a Gliederung's ("1. Abschnitt", "Teil 2").
_NORM_DESIGNATION = re.compile(r"(?:§§?|Art\.|Artikel|Anlagen?|Anhang)\s*(?:\d+[a-z]*\b)?(?:\s+bis\s+\d+[a-z]*\b)?")
_GLIEDERUNG_DESIGNATION = re.compile(
    r"(?:[IVXLC\d]+\.\s*)?(?:Teil|Buch|Kapitel|Unterkapitel|Abschnitt|Unterabschnitt|Titel|Untertitel)\b"
    r"(?:\s+[IVXLC\d]+[a-z]?\b\.?)?")


class SnSource:
    code = "SN"
    crawl_delay = 0.0
    workers = 2
    # 887 listed on 2026-10-20 (267 Gesetze, 620 Verordnungen); about 90 %.
    min_entries = 798

    def list_laws(self, client: httpx.Client) -> list[Entry]:
        client.cookies.clear()  # the hit list is per session: start a new one
        form = client.get(f"{BASE}/vorschriftensuche")
        form.raise_for_status()
        token = _TOKEN.search(form.text)
        if not token:
            raise ValueError("search form without a CSRF token")
        response = client.post(f"{BASE}/suche", data={
            "authenticity_token": token[1],
            "search_request[mode]": "fullsearch",
            "search_request[search_text]": "",
            "search_request[title_search]": "0",
            "search_request[categories][]": list(CATEGORIES),
            "search_request[include_envelopes]": "0",
            "search_request[valid_day_de]": datetime.date.today().strftime("%d.%m.%Y"),
        })
        response.raise_for_status()
        total, found = parse_hitlist(response.text)
        if total and not found:
            raise ValueError(f"{total} hits announced, none on the first page")
        pages = math.ceil(total / len(found)) if total else 0
        for n in range(2, pages + 1):
            response = client.get(f"{BASE}/suche", params={"seite": n})
            response.raise_for_status()
            page_total, page_found = parse_hitlist(response.text)
            if page_total != total:
                raise ValueError(f"page {n}: {page_total} hits announced instead of {total}")
            found += page_found
        entries = {e.slug: e for e in found}
        if len(entries) != total:
            raise ValueError(f"{total} hits announced, {len(entries)} listed")
        return list(entries.values())

    def fetch(self, client: httpx.Client, entry: Entry, today: datetime.date) -> Fetched | None:
        response = client.get(entry.url)
        response.raise_for_status()
        fetched = parse_law(response.text, entry.url, today)
        if fetched is not None and entry.lastmod and fetched.front["gilt_ab"] != entry.lastmod:
            # The page and the listing disagree (one was updated in between): try again next run
            # rather than store this text under the listing's lastmod.
            raise ValueError(f"page valid from {fetched.front['gilt_ab']}, listing says {entry.lastmod}")
        return fetched


def slug_for(doc_id: str) -> str:
    """The portal's numeric document id as a slug: "20111" -> "sn-20111"."""
    return "sn-" + re.sub(r"[^a-z0-9_-]", "_", doc_id.lower())


def german_date(text: str) -> datetime.date | None:
    """ "1. Januar 2025" -> 2025-01-01."""
    m = _DATE.search(text)
    if not m or m[2].lower() not in _MONTHS:
        return None
    return datetime.date(int(m[3]), _MONTHS[m[2].lower()], int(m[1]))


def parse_hitlist(page: str) -> tuple[int, list[Entry]]:
    """(announced number of hits, the entries on this page) of one hit list page."""
    m = _COUNT.search(page)
    if not m:
        raise ValueError("hit list page without a hit count")
    entries = []
    for block in page.split('<div class="result_hit">')[1:]:
        link = _HIT_LINK.search(block)
        if not link:
            continue
        kind = _HIT_TYPE.search(block)
        if not kind or kind[1].strip() not in TYPES:
            raise ValueError(f"{link[1]}: unexpected type {kind[1].strip() if kind else None!r}")
        valid = _HIT_VALID.search(block)
        start = german_date(valid[1]) if valid else None
        entries.append(Entry(slug_for(link[1]), f"{BASE}/vorschrift/{link[1]}", start.isoformat() if start else None))
    return int(m[1].replace(".", "")), entries


# -- the law page


def parse_law(page: str, url: str, today: datetime.date) -> Fetched | None:
    """The Markdown file for one law from its page; None if it is no Gesetz or Verordnung."""
    root = parse_html(page)
    description = next((n.attrs.get("content", "") for n in root.iter()
                        if n.tag == "meta" and n.attrs.get("name") == "description"), "")
    kind, _, long_title = description.removeprefix("Sächsisches Landesrecht ").partition(":")
    if kind.strip() not in TYPES:
        return None
    article = root.find("article", id="lesetext")
    if article is None:
        raise ValueError(f"{url}: no law text")
    valid = next((n for n in root.iter() if n.tag == "div" and "box" in n.classes()
                  and "Gültigkeitszeitraum" in n.text()), None)
    gilt_ab = german_date(valid.text()) if valid is not None else None
    if gilt_ab is None:
        raise ValueError(f"{url}: no Fassung gültig ab")
    if gilt_ab > today:
        raise NotYetInForce(gilt_ab.isoformat())
    next_version = _next_version(root, today)

    # <title>: "REVOSax Landesrecht Sachsen - <Kurztitel> – <Abkürzung>", or only one of the two.
    title_node = root.find("title")
    short = line(title_node.text()) if title_node is not None else ""
    short = short.removeprefix("REVOSax Landesrecht Sachsen").strip().removeprefix("-").strip()
    h1 = root.find("h1")
    kurz = line(h1.text()) if h1 is not None else ""
    if " – " in short:
        kurz, abk = (x.strip() for x in short.rsplit(" – ", 1))
    elif short and " " not in short:
        abk = short  # an abbreviation without Kurztitel ("SächsWG") or a one-word name ("Verfassung")
    else:
        abk = url.rsplit("/", 1)[1]
    titel = line(long_title) or kurz or abk
    front = {
        "land": "SN",
        "abkuerzung": abk,
        "titel": titel,
        "kurztitel": kurz if kurz and kurz != titel else None,
        "stand": f"Fassung gültig ab {gilt_ab.strftime('%d.%m.%Y')}",
        "gilt_ab": gilt_ab.isoformat(),
        "naechste_fassung_ab": next_version,
        "quelle": url,
    }

    law = _Law(article)
    header = next((n for n in article.elements() if n.tag == "header"), None)
    if header is not None:
        law.eingangsformel(header)
    for section in (n for n in article.iter() if n.tag == "section"):
        law.section(section)
    return Fetched(markdown=render(front, law.units), front=front, next_version_from=next_version)


def _next_version(root: Node, today: datetime.date) -> str | None:
    """The start of the version after the one shown, from the list of versions, if it lies after today."""
    historic = root.find("li", id="historic")
    if historic is None:
        return None
    links = [n for n in historic.iter() if n.tag == "a" and "law_version_link" in n.classes()]
    active = next((i for i, n in enumerate(links) if "linkactive" in n.classes()), None)
    if active is None or active + 1 >= len(links):
        return None
    m = _VERSION_DATE.search(links[active + 1].text())
    if not m:
        return None
    start = datetime.date(int(m[3]), int(m[2]), int(m[1]))
    return start.isoformat() if start > today else None


class _Law(Renderer):
    """Collects the units of one law; footnotes are gathered per unit."""

    def __init__(self, article: Node) -> None:
        self.units: list[Unit] = []
        self.used: set[str] = set()
        self.notes: list[str] = []
        self.path: list[tuple[int, str]] = []  # (data-level, id part) of the enclosing gliederungen
        footer = next((n for n in article.iter() if n.tag == "footer"), None)
        self.footnotes: dict[str, Node] = {}
        if footer is not None:
            self.footnotes = {n.attrs["id"]: n for n in footer.iter() if n.tag == "dd" and n.attrs.get("id")}

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
        self.units.append(Unit(kind, self.unit_id(base), ebene, heading, "\n\n".join(blocks)))
        self.notes = []

    # -- structure

    def eingangsformel(self, header: Node) -> None:
        """The header without the title (it heads the file) and the "Rechtsbereinigt" line (the Stand says it)."""
        body = Node("div", {})
        title_seen = False
        for child in header.children:
            if isinstance(child, Node) and child.tag in HEADINGS:
                if not title_seen and child.tag == "h3":
                    title_seen = True
                    continue
                if "rechtsbereinigt" in child.classes():
                    continue
            body.children.append(child)
        blocks = self.blocks(body)
        if blocks or self.notes:
            self.add("norm", "eingangsformel", None, "Eingangsformel", blocks)

    def section(self, el: Node) -> None:
        heading_node = next((n for n in el.elements() if n.tag in HEADINGS), None)
        lines = self.heading_lines(heading_node) if heading_node is not None else []
        heading = " ".join(lines) or line(el.attrs.get("title", "")) or "(ohne Bezeichnung)"
        blocks = self.blocks(el, skip=heading_node)
        # Norm or Gliederung by designation and body only: a footnote on a heading changes neither.
        norm = _NORM_DESIGNATION.match(heading)
        g = _GLIEDERUNG_DESIGNATION.match(heading)
        if norm or (blocks and not g):
            designation = norm[0] if norm else (lines[0] if lines else heading)
            self.add("norm", designation_slug(designation) or "vorschrift", None, heading, blocks)
            return
        level_attr = el.attrs.get("data-level", "")
        level = int(level_attr) if level_attr.isdigit() else 1
        while self.path and self.path[-1][0] >= level:
            self.path.pop()
        part = designation_slug(g[0] if g else (lines[0] if lines else heading)) or "gliederung"
        self.path.append((level, part))
        # Text of its own and footnotes on its heading stay with the Gliederung, as its body.
        self.add("gliederung", "-".join(p for _, p in self.path), len(self.path), heading, blocks)

    def is_footnote(self, el: Node) -> bool:
        return el.tag == "a" and el.attrs.get("href", "").startswith("#FNID_")

    def footnote(self, el: Node) -> str:
        """Collect the note behind a footnote link; returns its marker ("1)")."""
        number = line(el.text())
        note = self.footnotes.get(el.attrs["href"][1:])
        text = "\n\n".join(self.blocks(note)) if note is not None else ""
        if text:
            self.notes.append(f"{number}) {text}" if number else text)
        return f"{number})" if number else ""
