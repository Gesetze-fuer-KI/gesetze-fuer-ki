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
import unicodedata
from html.parser import HTMLParser

import httpx

from convert import _SUBSCRIPT, _SUPERSCRIPT, _clean, _escape_list_marker, footnote_block
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
    r"(?:[IVXLC\d]+\.\s*)?(?:Teil|Buch|Kapitel|Unterkapitel|Abschnitt|Unterabschnitt|Titel|Untertitel)"
    r"(?:\s+[IVXLC\d]+[a-z]?\b\.?)?")

_VOID = {"br", "img", "col", "input", "meta", "link", "hr", "wbr", "source"}
_BLOCK = {"p", "div", "dl", "table", "ul", "ol", "pre", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6",
          "section", "header", "footer", "nav", "article"}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


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
        return parse_law(response.text, entry.url, today)


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


# -- a small DOM, since the stdlib has only a streaming HTML parser


class _Node:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: dict[str, str]):
        self.tag = tag
        self.attrs = attrs
        self.children: list[_Node | str] = []

    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def elements(self) -> list[_Node]:
        return [c for c in self.children if isinstance(c, _Node)]

    def iter(self):
        yield self
        for child in self.elements():
            yield from child.iter()

    def find(self, tag: str, **attrs: str) -> _Node | None:
        return next((n for n in self.iter() if n.tag == tag
                     and all(n.attrs.get(k) == v for k, v in attrs.items())), None)

    def text(self) -> str:
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK and self.stack[-1].tag == "p":
            self.stack.pop()  # a block element ends an open paragraph, as in a browser
        node = _Node(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.stack[-1].children.append(_Node(tag, {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def _parse_html(page: str) -> _Node:
    builder = _TreeBuilder()
    builder.feed(page)
    builder.close()
    return builder.root


# -- the law page


def parse_law(page: str, url: str, today: datetime.date) -> Fetched | None:
    """The Markdown file for one law from its page; None if it is no Gesetz or Verordnung."""
    root = _parse_html(page)
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
    short = _line(title_node.text()) if title_node is not None else ""
    short = short.removeprefix("REVOSax Landesrecht Sachsen").strip().removeprefix("-").strip()
    h1 = root.find("h1")
    kurz = _line(h1.text()) if h1 is not None else ""
    if " – " in short:
        kurz, abk = (x.strip() for x in short.rsplit(" – ", 1))
    elif short and " " not in short:
        abk = short  # an abbreviation without Kurztitel ("SächsWG") or a one-word name ("Verfassung")
    else:
        abk = url.rsplit("/", 1)[1]
    titel = _line(long_title) or kurz or abk
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


def _next_version(root: _Node, today: datetime.date) -> str | None:
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


def _line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _text(raw: str) -> str:
    """Inline text with line breaks kept, spaces collapsed within lines."""
    lines = [_clean(line).strip() for line in raw.split("\n")]
    return "  \n".join(line for line in lines if line)


def _slug(text: str) -> str:
    """An id part from a designation: "§ 44a" -> "par44a", "Artikel 3" -> "art3", "1. Abschnitt" -> "1abschnitt"."""
    s = text.lower().replace("§", "par")
    s = re.sub(r"^artikel\b|^art\.", "art", s)
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", s)[:40]


class _Law:
    """Collects the units of one law; footnotes are gathered per unit."""

    def __init__(self, article: _Node) -> None:
        self.units: list[Unit] = []
        self.used: set[str] = set()
        self.notes: list[str] = []
        self.path: list[tuple[int, str]] = []  # (data-level, id part) of the enclosing gliederungen
        footer = next((n for n in article.iter() if n.tag == "footer"), None)
        self.footnotes: dict[str, _Node] = {}
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

    def eingangsformel(self, header: _Node) -> None:
        """The header without the title (it heads the file) and the "Rechtsbereinigt" line (the Stand says it)."""
        body = _Node("div", {})
        title_seen = False
        for child in header.children:
            if isinstance(child, _Node) and child.tag in _HEADINGS:
                if not title_seen and child.tag == "h3":
                    title_seen = True
                    continue
                if "rechtsbereinigt" in child.classes():
                    continue
            body.children.append(child)
        blocks = self.blocks(body)
        if blocks or self.notes:
            self.add("norm", "eingangsformel", None, "Eingangsformel", blocks)

    def section(self, el: _Node) -> None:
        heading_node = next((n for n in el.elements() if n.tag in _HEADINGS), None)
        lines = self.heading_lines(heading_node) if heading_node is not None else []
        heading = " ".join(lines) or _line(el.attrs.get("title", "")) or "(ohne Bezeichnung)"
        blocks = self.blocks(el, skip=heading_node)
        norm = _NORM_DESIGNATION.match(heading)
        if norm or blocks or self.notes:
            designation = norm[0] if norm else (lines[0] if lines else heading)
            self.add("norm", _slug(designation) or "vorschrift", None, heading, blocks)
            return
        level_attr = el.attrs.get("data-level", "")
        level = int(level_attr) if level_attr.isdigit() else 1
        while self.path and self.path[-1][0] >= level:
            self.path.pop()
        g = _GLIEDERUNG_DESIGNATION.match(heading)
        part = _slug(g[0] if g else (lines[0] if lines else heading)) or "gliederung"
        self.path.append((level, part))
        self.add("gliederung", "-".join(p for _, p in self.path), len(self.path), heading, [])

    def heading_lines(self, el: _Node) -> list[str]:
        """The lines of a heading (split at <br>); footnote markers are left out, their notes kept."""
        parts: list[str] = []
        for child in el.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag == "br":
                parts.append("\n")
            elif self.is_footnote(child):
                self.footnote(child)
            else:
                parts.append(self.plain(child))
        return [x for x in (_line(x) for x in "".join(parts).split("\n")) if x]

    # -- blocks

    def blocks(self, el: _Node, skip: _Node | None = None) -> list[str]:
        """Render a container as a list of Markdown blocks."""
        out: list[str] = []
        buffer: list[str] = []

        def flush() -> None:
            text = _text("".join(buffer))
            if text:
                out.append(text)
            buffer.clear()

        for child in el.children:
            if isinstance(child, str):
                buffer.append(_clean(child))
                continue
            tag = child.tag
            if child is skip or tag in ("section", "nav", "footer", "colgroup", "script", "style"):
                continue
            if tag in ("p", "div", "blockquote", "span") and self.has_blocks(child):
                flush()
                out.extend(self.blocks(child))
            elif tag in ("p", "div", "blockquote"):
                flush()
                text = _text(self.inline(child))
                if text:
                    out.append(text)
            elif tag == "dl":
                flush()
                lines = self.dl(child, 0)
                if lines:
                    out.append("\n".join(lines))
            elif tag in ("ul", "ol"):
                flush()
                lines = self.ul(child, 0)
                if lines:
                    out.append("\n".join(lines))
            elif tag == "table":
                flush()
                out.extend(self.table(child))
            elif tag in _HEADINGS:
                flush()
                text = " ".join(self.heading_lines(child))
                if text:
                    out.append(f"**{text}**")
            elif tag == "pre":
                flush()
                text = "\n".join(line.rstrip() for line in child.text().strip("\n").split("\n"))
                if text.strip():
                    out.append("```text\n" + text + "\n```")
            else:
                buffer.append(self.inline_child(child))
        flush()
        return out

    def has_blocks(self, el: _Node) -> bool:
        return any(c.tag in _BLOCK for c in el.elements())

    def dl(self, el: _Node, depth: int) -> list[str]:
        lines: list[str] = []
        indent = "  " * depth
        marker = None
        for child in el.elements():
            if child.tag == "dt":
                if marker:  # a dt without dd
                    lines.append(f"{indent}- {_escape_list_marker(marker)}")
                marker = self.plain(child)
            elif child.tag == "dd":
                head, nested = self.item(child, depth)
                label = _escape_list_marker(marker or "")
                lines.append(f"{indent}- {label} {head}".rstrip() if label else f"{indent}- {head}".rstrip())
                lines.extend(nested)
                marker = None
        if marker:
            lines.append(f"{indent}- {_escape_list_marker(marker)}")
        return lines

    def ul(self, el: _Node, depth: int) -> list[str]:
        lines: list[str] = []
        indent = "  " * depth
        for li in el.elements():
            if li.tag == "li":
                head, nested = self.item(li, depth)
                lines.append(f"{indent}- {head}".rstrip())
                lines.extend(nested)
        return lines

    def item(self, el: _Node, depth: int) -> tuple[str, list[str]]:
        """The text of a list item and the lines of what is nested in it (lists, tables, later text)."""
        indent = "  " * (depth + 1)
        texts: list[str] = []
        nested: list[str] = []

        def text_block(raw: str) -> None:
            text = _text(raw)
            if not text:
                return
            if nested:  # text after a nested list continues the item below it
                nested.append(indent + text.replace("\n", "\n" + indent))
            else:
                texts.append(text)

        inline: list[str] = []
        for child in el.children:
            if isinstance(child, _Node) and child.tag in ("dl", "ul", "ol", "table", "p", "div"):
                text_block("".join(inline))
                inline = []
                if child.tag == "dl":
                    nested.extend(self.dl(child, depth + 1))
                elif child.tag in ("ul", "ol"):
                    nested.extend(self.ul(child, depth + 1))
                elif child.tag == "table":
                    nested.extend(indent + line for block in self.table(child) for line in block.split("\n"))
                else:
                    for block in self.blocks(child):
                        if nested or texts:
                            nested.append(indent + block.replace("\n", "\n" + indent))
                        else:
                            texts.append(block)
            else:
                inline.append(_clean(child) if isinstance(child, str) else self.inline_child(child))
        text_block("".join(inline))
        head = " ".join(texts).replace("\n", "\n" + indent)
        return head, nested

    def table(self, el: _Node) -> list[str]:
        """The caption (bold) and the table as Markdown blocks."""
        out: list[str] = []
        caption = next((c for c in el.elements() if c.tag == "caption"), None)
        if caption is not None:
            text = _line(self.plain(caption))
            if text:
                out.append(f"**{text}**")
        rows: list[list[str]] = []
        header_rows = 0
        sections = [s for s in el.elements() if s.tag in ("thead", "tbody", "tfoot")] or [el]
        for section in sections:
            for row in (r for r in section.elements() if r.tag == "tr"):
                cells: list[str] = []
                for cell in row.elements():
                    if cell.tag not in ("td", "th"):
                        continue
                    text = "<br>".join(b.replace("  \n", "<br>").replace("\n", "<br>") for b in self.blocks(cell))
                    cells.append(text.replace("|", "\\|"))
                    span = cell.attrs.get("colspan", "1")
                    cells.extend([""] * (int(span) - 1 if span.isdigit() and int(span) > 1 else 0))
                rows.append(cells)
                if section.tag == "thead":
                    header_rows += 1
        rows = [r for r in rows if any(c.strip() for c in r)]
        if rows:
            width = max(len(r) for r in rows)
            rows = [r + [""] * (width - len(r)) for r in rows]
            head, body = (rows[0], rows[1:]) if header_rows else ([""] * width, rows)
            lines = ["| " + " | ".join(head) + " |", "|" + "---|" * width]
            lines += ["| " + " | ".join(r) + " |" for r in body]
            out.append("\n".join(lines))
        return out

    # -- inline

    def inline(self, el: _Node) -> str:
        """An element's text with inline markup; line breaks only from <br>."""
        return "".join(_clean(c) if isinstance(c, str) else self.inline_child(c) for c in el.children)

    def plain(self, el: _Node) -> str:
        """One line of text: no emphasis, footnote markers dropped (their notes kept)."""
        parts: list[str] = []
        for child in el.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag == "br":
                parts.append(" ")
            elif self.is_footnote(child):
                self.footnote(child)
            elif child.tag in ("sup", "sub"):
                parts.append(self.inline_child(child))
            else:
                parts.append(self.plain(child))
        return _line("".join(parts))

    def is_footnote(self, el: _Node) -> bool:
        return el.tag == "a" and el.attrs.get("href", "").startswith("#FNID_")

    def footnote(self, el: _Node) -> str:
        """Collect the note behind a footnote link; returns its marker ("1)")."""
        number = _line(el.text())
        note = self.footnotes.get(el.attrs["href"][1:])
        text = "\n\n".join(self.blocks(note)) if note is not None else ""
        if text:
            self.notes.append(f"{number}) {text}" if number else text)
        return f"{number})" if number else ""

    def inline_child(self, el: _Node) -> str:
        tag = el.tag
        if tag == "br":
            return "\n"
        if self.is_footnote(el):
            marker = self.footnote(el)
            return marker.translate(_SUPERSCRIPT).replace(")", "⁾") if marker else ""
        if tag == "sup":
            inner = self.plain(el)
            return inner.translate(_SUPERSCRIPT) if inner.isdigit() else f"^({inner})" if inner else ""
        if tag == "sub":
            inner = self.plain(el)
            return inner.translate(_SUBSCRIPT) if inner.isdigit() else f"_({inner})" if inner else ""
        if tag in ("b", "strong", "i", "em"):
            raw = self.inline(el)
            mark = "**" if tag in ("b", "strong") else "*"
            # Emphasis per line, spaces at the edges outside the markers, or Markdown would not see it.
            out = []
            for line in raw.split("\n"):
                inner = _line(line)
                lead, trail = (" " if line[:1] == " " else ""), (" " if line[-1:] == " " else "")
                out.append(f"{lead}{mark}{inner}{mark}{trail}" if inner else line)
            return "\n".join(out)
        if tag == "img":
            return " *(Abbildung, siehe Originalfassung)* "
        if tag in ("script", "style"):
            return ""
        if tag in _BLOCK:  # a block inside an inline context (rare): flatten it
            return " " + _line(" ".join(self.blocks(el))) + " "
        return self.inline(el)
