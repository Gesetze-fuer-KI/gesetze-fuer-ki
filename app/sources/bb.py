"""Brandenburg: BRAVORS (bravors.brandenburg.de), run by the Landesregierung Brandenburg.

The texts are "nichtamtlich"; the authentic ones are in the GVBl at landesrecht.brandenburg.de.
There is no licence statement. robots.txt asks for `Crawl-delay: 20`, which is kept for every
request (crawl_delay = 20, one worker). Its sitemap lists three Verwaltungsvorschriften only.

No change signal: no listing tells when a law last changed. The search and the
Fundstellennachweis give the original date ("vom …") only, a law keeps its document id across
amendments, and "zuletzt geändert durch …" appears on the law page alone. So every Entry has
lastmod None and the runner refetches every law once per pass: about 1,800 laws at 20 s are
about ten hours, so a pass spans about two nightly runs and a law is at most about two days
stale. A change feed or a sitemap with lastmod from BRAVORS would allow an incremental sync.

Listing: the Fundstellennachweis "Gesetze und Verordnungen", sachgebietlich: nine pages
(Sachgebiete 1–9) that list every law in force with its document id ("<!-- 212792 -->") and
link. Verträge in it are left out by their link ("/de/vertraege-…"). The Fundstellennachweis
announces no count, so the listing checks itself against the extended search's total for
"Gesetze und Verordnungen" (one form post): the two differ by a few laws (1,785 and 1,780 on
2026-10-20), so up to MAX_MISMATCH is accepted, less than the smallest Sachgebiet (42 laws);
and every Sachgebiet page must parse. The Fundstellennachweis lists a new law only after a few
days, so the ten newest laws from the search's first page are added. Entries are
ordered by id, so that passes progress evenly. Slug: "bb-" + the document id.

Law: /gesetze/<name>, /verordnungen/<name> or /de/gesetze-<id> is the current version
("Aktuelle Fassung"): a head with the title, "vom …" and "zuletzt geändert durch …" (the Stand),
then flat HTML: an optional Eingangsformel, a table of contents (skipped), headings for
Gliederungen ("Abschnitt 1", "1. Hauptteil:", "Erster Abschnitt") and §§/Artikel (<a name="…"> anchors), and
footnotes to the title after <a name="0">. Unit ids come from the designations ("art7a",
"2hauptteil-1abschnitt"); a Gliederung's level follows the order its kind first appears in.
Anlagen published only as attachments are not part of the text.

Versions: the portal serves the version in force only ("Aktuelle Fassung"); older ones sit in
the Änderungshistorie, expired laws in an Archiv. No future version is shown, so
next_version_from is always None. A page showing an archived (expired) law is skipped.
"""

from __future__ import annotations

import datetime
import re

import httpx

from convert import _escape_list_marker, footnote_block
from sources.html import HEADINGS, ORDINAL, Node, Renderer, designation_slug, line, parse_html
from state_markdown import render
from state_sync import Entry, Fetched
from store import Unit

BASE = "https://bravors.brandenburg.de"
FNA = f"{BASE}/de/vorschriften_fundstellennachweis_gesetzte_und_verordnungen_sachgebietlich/sachgebiet"
SEARCH = f"{BASE}/de/vorschriften_erweiterte_suche"
SACHGEBIETE = range(1, 10)
# The Fundstellennachweis and the search disagree slightly (1,785 and 1,780 on 2026-10-20);
# the smallest Sachgebiet holds 42 laws, so a missing page still fails the check.
MAX_MISMATCH = 10
MIN_TEXT_WITHOUT_NORMS = 2000  # a longer text without any § or Artikel is a layout this parser does not know
SKIPPED = "kein Gesetz und keine Verordnung"  # cache value for a document that is neither

_HIT_COUNT = re.compile(r"wurde in (\d[\d.]*) Treffern gefunden")
_ENTRY = re.compile(r'<!-- (\d+) -->\s*<a href="([^"]+)"')
_HIT = re.compile(r'<!-- (\d+)-->\s*<div class="count">\d+</div>\s*<div class="link"><a href="([^"]+)"')
# Link kinds in the Fundstellennachweis: laws (kept) and Verträge (left out).
_LAW_LINK = re.compile(r"/(?:gesetze|verordnungen)/[^/]+|/de/(?:gesetze|verordnungen)-\d+")
_TREATY_LINK = re.compile(r"/de/vertraege-\d+|/vertraege/[^/]+")
# An abbreviation at the end of the title: "(Sorben/Wenden-Gesetz - SWG)", "(StAngZustG)".
_TITLE_ABK = re.compile(r"\(([^()]+)\)\s*$")

_NORM_DESIGNATION = re.compile(r"(?:§§?|Art\.|Artikel|Anlagen?|Anhang)\s*(?:\d+[a-z]*\b)?(?:\s+bis\s+\d+[a-z]*\b)?")
_GLIEDERUNG = re.compile(
    rf"(?:[IVXLC\d]+\.\s*|{ORDINAL})?(Hauptteil|Teil|Buch|Kapitel|Unterkapitel|Abschnitt|Unterabschnitt|Titel|Untertitel)\b"
    r"(?:\s+[IVXLC\d]+[a-z]?\b\.?)?")


class BbSource:
    code = "BB"
    crawl_delay = 20.0  # robots.txt: Crawl-delay: 20
    workers = 1
    # 1,785 listed on 2026-10-20 (the search counted 1,780: 515 Gesetze, 1,265 Verordnungen); about 90 %.
    min_entries = 1600

    def __init__(self) -> None:
        # Document id -> SKIPPED for documents found to be no Gesetz or Verordnung, kept by
        # the runner across runs, so that they are never fetched again.
        self.cache: dict[str, str] = {}

    def list_laws(self, client: httpx.Client) -> list[Entry]:
        total, newest = search(client)
        found: dict[str, str] = {}
        for n in SACHGEBIETE:
            response = client.get(f"{FNA}/{n}")
            response.raise_for_status()
            for doc_id, url in parse_fna(response.text, n):
                found.setdefault(doc_id, url)  # a law listed under two Sachgebiete counts once
        # The Fundstellennachweis takes a few days to list a new law; the search's first page
        # (the ten newest) fills that gap. Its link is used only for laws missing there.
        for doc_id, url in newest:
            found.setdefault(doc_id, url)
        if abs(len(found) - total) > MAX_MISMATCH:
            raise ValueError(f"search announces {total} Gesetze and Verordnungen, Fundstellennachweis lists {len(found)}")
        return [Entry(slug_for(doc_id), url) for doc_id, url in sorted(found.items(), key=lambda x: int(x[0]))
                if self.cache.get(doc_id) != SKIPPED]

    def fetch(self, client: httpx.Client, entry: Entry, today: datetime.date) -> Fetched | None:
        doc_id = entry.slug.removeprefix("bb-")
        response = client.get(entry.url)
        response.raise_for_status()
        url = str(response.url)  # classified by where a link ends up, after redirects
        if _kind(url) is None:
            self.cache[doc_id] = SKIPPED
            return None
        return parse_law(response.text, url, doc_id)


def slug_for(doc_id: str) -> str:
    """The portal's document id as a slug: "212792" -> "bb-212792"."""
    return "bb-" + re.sub(r"[^a-z0-9_-]", "_", doc_id.lower())


def search(client: httpx.Client) -> tuple[int, list[tuple[str, str]]]:
    """How many Gesetze and Verordnungen the extended search finds, and (document id, URL) of the
    ten newest on its first page. The form posts, then redirects to the result."""
    client.cookies.clear()  # the result lives in the session: start a new one
    response = client.post(SEARCH, data={
        "search[title]": "", "search[fulltext]": "", "search[art_vorschrift][]": "landesrecht",
        "search[sachgebietsnr_1]": "", "search[gliederungsnr]": "",
        "search[ausfertigungsdatum_von]": "", "search[ausfertigungsdatum_bis]": "",
        "search[inkrafttreten_von]": "", "search[inkrafttreten_bis]": "",
        "search[fundstelle_medium]": "0", "search[fundstelle_jahr]": "",
        "search[fundstelle_nr]": "", "search[fundstelle_seite]": "", "suchen": "Suchen",
    })
    response.raise_for_status()
    m = _HIT_COUNT.search(response.text)
    if not m or "Gesetze und Verordnungen" not in response.text:
        raise ValueError("search result without a count of Gesetze und Verordnungen")
    hits = [_law_link(h[1], h[2], "search") for h in _HIT.finditer(response.text)]
    return int(m[1].replace(".", "")), [h for h in hits if h]


def parse_fna(page: str, sachgebiet: int) -> list[tuple[str, str]]:
    """(document id, URL) of every Gesetz and Verordnung on one Sachgebiet page of the Fundstellennachweis."""
    if not re.search(rf"<h3>{sachgebiet} [^<]+</h3>", page):
        raise ValueError(f"Sachgebiet {sachgebiet}: not a Fundstellennachweis page")
    blocks = page.split("<dt>")[1:]
    if not blocks:
        raise ValueError(f"Sachgebiet {sachgebiet}: no entries")
    out = []
    for block in blocks:
        m = _ENTRY.search(block)
        if not m:
            raise ValueError(f"Sachgebiet {sachgebiet}: entry without id and link")
        entry = _law_link(m[1], m[2], f"Sachgebiet {sachgebiet}")
        if entry:
            out.append(entry)
    return out


def _law_link(doc_id: str, href: str, where: str) -> tuple[str, str] | None:
    """(document id, URL) of a Gesetz or Verordnung, None for a Vertrag; anything else is an error."""
    if _TREATY_LINK.fullmatch(href):
        return None
    if not _LAW_LINK.fullmatch(href):
        raise ValueError(f"{where}: unexpected link {href}")
    return doc_id, BASE + href


def _kind(url: str) -> str | None:
    """ "Gesetz" or "Verordnung" from a law page's URL, None for anything else."""
    path = url.removeprefix(BASE)
    if path.startswith(("/gesetze/", "/de/gesetze-")):
        return "Gesetz"
    if path.startswith(("/verordnungen/", "/de/verordnungen-")):
        return "Verordnung"
    return None


# -- the law page


def parse_law(page: str, url: str, doc_id: str) -> Fetched | None:
    """The Markdown file for one law from its page; None if it is no Gesetz or Verordnung in force."""
    if _kind(url) is None:
        return None
    root = parse_html(page)
    if root.find("h2", id="archive_head") is not None:
        return None  # expired ("ARCHIV"): skipped this pass, not cached, as the listing should drop it
    title_node = root.find("h2", id="norm_title")
    head = next((n for n in root.iter() if n.tag == "div" and "reiterbox_innen_kopf" in n.classes()), None)
    body = next((n for n in root.iter() if n.tag == "div" and "reiterbox_innen_text" in n.classes()), None)
    if title_node is None or head is None or body is None:
        raise ValueError(f"{url}: no law text")
    titel = line(title_node.text())

    kurz, abk = None, None
    m = _TITLE_ABK.search(titel)
    if m:
        kurz_part, _, abk_part = m[1].rpartition(" - ")
        abk = abk_part.strip()
        kurz = kurz_part.strip() or None
        titel = titel[:m.start()].strip()
    if not abk:
        abk = doc_id  # no abbreviation in the title

    head_lines = _Law().heading_lines(head.find("p") or head)
    stand = _stand(head_lines)
    front = {
        "land": "BB",
        "abkuerzung": abk,
        "titel": titel,
        "kurztitel": kurz,
        "stand": stand,
        "gilt_ab": None,
        "naechste_fassung_ab": None,
        "quelle": url,
    }
    law = _Law()
    law.walk(body)
    if not any(u.kind == "norm" and _NORM_DESIGNATION.match(u.heading) for u in law.units) and \
            sum(len(u.body) for u in law.units) > MIN_TEXT_WITHOUT_NORMS:
        # A changed page layout must not turn a whole law into one Eingangsformel.
        raise ValueError(f"{url}: no § or Artikel in {sum(len(u.body) for u in law.units)} characters of text")
    return Fetched(markdown=render(front, law.units), front=front, next_version_from=None)


def _stand(head: list[str]) -> str | None:
    """ "zuletzt geändert durch … (GVBl.…)" from the head, else the date of the original text."""
    for prefix in ("zuletzt geändert", "vom ", "In der Fassung"):
        i = next((i for i, x in enumerate(head) if x.startswith(prefix)), None)
        if i is None:
            continue
        text = head[i] + (f" {head[i + 1]}" if i + 1 < len(head) and head[i + 1].startswith("(") else "")
        return f"Ursprüngliche Fassung {text}" if prefix == "vom " else text
    return None


def _is_link_list(el: Node) -> bool:
    """A paragraph of the table of contents: nothing but in-page links (and line breaks)."""
    links = False
    for child in el.children:
        if isinstance(child, str):
            if child.strip():
                return False
        elif child.tag == "a" and child.attrs.get("href", "").startswith("#"):
            links = True
        elif child.tag != "br":
            return False
    return links


class _Law(Renderer):
    """Collects the units of one law from the flat sequence of headings and blocks."""

    def __init__(self) -> None:
        self.units: list[Unit] = []
        self.used: set[str] = set()
        self.path: list[tuple[str, str]] = []  # (kind, id part) of the enclosing Gliederungen
        self.kinds: list[str] = []  # Gliederung kinds in the order they first appear: their level
        self.current: tuple[str, str, int | None, str] | None = None  # kind, id, ebene, heading
        self.blocks_: list[str] = []
        self.notes: list[str] = []

    def unit_id(self, base: str) -> str:
        """A unique id: a repeated designation gets "-2", "-3" in document order."""
        candidate, n = base, 1
        while candidate in self.used:
            n += 1
            candidate = f"{base}-{n}"
        self.used.add(candidate)
        return candidate

    def flush(self) -> None:
        blocks = self.blocks_ + ([footnote_block(self.notes)] if self.notes else [])
        if self.current is None:
            if blocks:
                self.units.append(Unit("norm", self.unit_id("eingangsformel"), None, "Eingangsformel",
                                       "\n\n".join(blocks)))
        else:
            kind, base, ebene, heading = self.current
            self.units.append(Unit(kind, self.unit_id(base), ebene, heading, "\n\n".join(blocks)))
        self.blocks_, self.notes = [], []

    def walk(self, body: Node) -> None:
        children = [c for c in body.children if isinstance(c, Node) or c.strip()]
        # A <p> wrapping the whole Eingangsformel ("<p><p>…</p></p>") is unwrapped.
        flat: list[Node | str] = []
        for c in children:
            if isinstance(c, Node) and c.tag == "p" and self.has_blocks(c):
                flat.extend(x for x in c.children if isinstance(x, Node) or x.strip())
            else:
                flat.append(c)
        skip = self._toc(flat)
        footnotes = False
        for i, el in enumerate(flat):
            if i in skip:
                continue
            if isinstance(el, Node) and not footnotes and any(
                    n.tag == "a" and n.attrs.get("name") == "0" for n in el.iter()):
                # The footnotes to the title follow the last provision.
                self.flush()
                self.current = ("norm", "fussnoten", None, "Fußnoten")
                footnotes = True
            if isinstance(el, Node) and el.tag in HEADINGS and not footnotes:
                self.heading(el)
                continue
            wrapper = Node("div", {})
            wrapper.children.append(el)
            self.blocks_.extend(self.blocks(wrapper))
        self.flush()

    def _toc(self, flat: list[Node | str]) -> set[int]:
        """Indexes of the table of contents: its heading ("Inhaltsübersicht") to its last list of links."""
        start = next((i for i, el in enumerate(flat) if isinstance(el, Node) and el.tag in HEADINGS
                      and line(el.text()).lower().startswith("inhalt")), None)
        if start is None:
            return set()
        end = start
        for i in range(start + 1, len(flat)):
            el = flat[i]
            if isinstance(el, Node) and el.tag in HEADINGS:
                continue
            if isinstance(el, Node) and el.tag == "p" and _is_link_list(el):
                end = i
                continue
            break
        return set(range(start, end + 1))

    def heading(self, el: Node) -> None:
        self.flush()
        lines = self.heading_lines(el)
        heading = " ".join(lines) or "(ohne Bezeichnung)"
        anchor = any(n.tag == "a" and n.attrs.get("name") for n in el.iter())
        norm = _NORM_DESIGNATION.match(heading)
        g = _GLIEDERUNG.match(heading)
        if norm or anchor or not g:
            designation = norm[0] if norm else (lines[0] if lines else heading)
            self.current = ("norm", designation_slug(designation) or "vorschrift", None, heading)
            return
        kind = g[1].lower()
        if kind not in self.kinds:
            self.kinds.append(kind)
        level = self.kinds.index(kind)
        while self.path and self.kinds.index(self.path[-1][0]) >= level:
            self.path.pop()
        self.path.append((kind, designation_slug(g[0]) or "gliederung"))
        heading = g[0] + heading[len(g[0]):].removeprefix(":")  # "1. Hauptteil: Grundlagen"
        self.current = ("gliederung", "-".join(p for _, p in self.path), len(self.path), heading)

    def ul(self, el: Node, depth: int) -> list[str]:
        """Numbered items of an <ol> keep their numbers ("1\\."), as in the printed text."""
        if el.tag != "ol":
            return super().ul(el, depth)
        lines: list[str] = []
        indent = "  " * depth
        start = el.attrs.get("start", "1")
        n = int(start) if start.isdigit() else 1
        for li in el.elements():
            if li.tag == "li":
                head, nested = self.item(li, depth)
                lines.append(f"{indent}- {_escape_list_marker(f'{n}.')} {head}".rstrip())
                lines.extend(nested)
                n += 1
        return lines

    def inline_child(self, el: Node) -> str:
        if el.tag == "sup" and self.plain(el) == "*":
            return ""  # the marker before the title's footnote, which stands under its own heading
        return super().inline_child(el)

    def is_footnote(self, el: Node) -> bool:
        # In-page links are the title's footnote marker (<a href="#0"><sup>*</sup></a>); the
        # notes themselves follow the last provision, so the marker is dropped.
        return el.tag == "a" and el.attrs.get("href", "").startswith("#")
