"""Bayern: BAYERN.RECHT (gesetze-bayern.de), run by the Bayerische Staatskanzlei with C.H.Beck.

The Nutzungshinweise allow reuse without restriction; robots.txt allows everything.

Listing: the portal's search, filtered by Normtyp "ges" (Gesetze) and "rv"
(Rechtsverordnungen). Verwaltungsvorschriften ("vv") and Verträge ("vertr") are never
asked for. The hit list lives in the server session (a cookie) and is paged ten hits at a
time, so each Normtyp starts a fresh session. Every hit carries the law's "Rechtsstand",
the date its current text applies from, which serves as lastmod.

Law: the per-law ZIP (/Content/Zip/<id>) holds one XML file in the portal's own schema
(byrecht-norm): `kopf` with the metadata, `rumpf` with gliederung/einzelnorm, then one
`annex` per Anlage. Its element ids (G_1, P_45) are positions, so unit ids are derived
from the designations instead ("art44a", "ersterteil-1abschnitt").

The portal only serves the version in force ("in aktueller Fassung", Hilfe), so there is no
future version to announce and next_version_from is always None. A text that only applies
after today is refused rather than mirrored early.
"""

from __future__ import annotations

import codecs
import datetime
import html
import io
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

import httpx

from state_markdown import render
from state_sync import Entry, Fetched
from store import Unit

BASE = "https://www.gesetze-bayern.de"
NORMTYPES = ("ges", "rv")
MAX_XML_BYTES = 50_000_000

_COUNT = re.compile(r'<p id="readable">\s*(\d+) Treffer')
_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
# Rendered as blocks of their own (their content is walked), not as inline text.
_CONTAINERS = {"p", "absatz.text", "annex.text", "annex.koerper", "einleitungssatz", "einleitungssatz.text"}
# Rendered as headings, or not at all.
_SKIP = {"para.nr", "para.titel", "gliederung.nr", "gliederung.titel", "absatz.nr", "annex.nummer",
         "annex.titel", "colgroup", "aenderungsverlauf", "normzitat"}


class BySource:
    code = "BY"
    crawl_delay = 0.0
    workers = 2
    # 727 listed on 2026-10-20 (241 Gesetze, 486 Rechtsverordnungen); about 90 %.
    min_entries = 654

    def list_laws(self, client: httpx.Client) -> list[Entry]:
        entries: dict[str, Entry] = {}
        for normtyp in NORMTYPES:
            client.cookies.clear()  # the hit list is per session: start a new one
            response = client.get(f"{BASE}/Search/Filter/NORMTYP/{normtyp}")
            response.raise_for_status()
            total, found = parse_hitlist(response.text)
            if total and not found:
                raise ValueError(f"{normtyp}: {total} hits announced, none on the first page")
            page_size = len(found)
            pages = -(-total // page_size) if total else 0
            for page in range(2, pages + 1):
                response = client.get(f"{BASE}/Search/Page/{page}")
                response.raise_for_status()
                found += parse_hitlist(response.text)[1]
            slugs = {e.slug for e in found}
            if len(slugs) != total:
                raise ValueError(f"{normtyp}: {total} hits announced, {len(slugs)} listed")
            for e in found:
                entries.setdefault(e.slug, e)
        return list(entries.values())

    def fetch(self, client: httpx.Client, entry: Entry, today: datetime.date) -> Fetched | None:
        doc_id = entry.url.rsplit("/", 1)[1]
        response = client.get(f"{BASE}/Content/Zip/{doc_id}")
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            members = [i for i in z.infolist() if i.filename.startswith("bayportalnorm/")
                       and i.filename.endswith(".xml")]
            if len(members) != 1:
                raise ValueError(f"{doc_id}: expected one XML file in the ZIP, found {len(members)}")
            if members[0].file_size > MAX_XML_BYTES:
                raise ValueError(f"{doc_id}: XML file too large")
            xml = z.read(members[0])
        return parse_law(xml, entry.url, today)


def slug_for(doc_id: str) -> str:
    """The portal's document id, lower case, as a slug: "BayBO" -> "by-baybo"."""
    return "by-" + re.sub(r"[^a-z0-9_-]", "_", doc_id.lower())


def parse_hitlist(page: str) -> tuple[int, list[Entry]]:
    """(announced number of hits, the entries on this page) of one hit list page."""
    m = _COUNT.search(page)
    if not m:
        raise ValueError("hit list page without a hit count")
    entries = []
    for block in page.split('<li class="hitlistItem">')[1:]:
        link = re.search(r'href="/Content/Document/([^"?#]+)', block)
        if not link:
            continue
        doc_id = html.unescape(link[1])
        stand = re.search(r"Rechtsstand:\s*(\d{2})\.(\d{2})\.(\d{4})", block)
        lastmod = f"{stand[3]}-{stand[2]}-{stand[1]}" if stand else None
        entries.append(Entry(slug_for(doc_id), f"{BASE}/Content/Document/{doc_id}", lastmod))
    return int(m[1]), entries


def parse_law(xml: bytes, url: str, today: datetime.date) -> Fetched:
    """The Markdown file for one law from the portal's XML."""
    root = ET.fromstring(xml.removeprefix(codecs.BOM_UTF8))
    head = root.find("kopf/angaben.versabh")
    doc = root.find("kopf/angaben.versunabh/dokumentation")
    if head is None or doc is None:
        raise ValueError(f"{url}: no kopf metadata")
    doc_id = doc.get("dokid") or url.rsplit("/", 1)[1]
    inkraft = datetime.date.fromisoformat((head.findtext("inkraft") or "").strip())
    if inkraft > today:
        raise ValueError(f"{doc_id}: the portal's text applies from {inkraft.isoformat()}, after {today.isoformat()}")

    law = _Law()
    abk = law.plain(head.find("amtlicheAbk"))
    kurz = law.plain(head.find("kurzbezeichnung"))
    titelangaben = head.find("titelangaben")
    titel = _line(titelangaben.text or "") if titelangaben is not None else ""
    front = {
        "land": "BY",
        "abkuerzung": abk or doc_id,
        "titel": titel or kurz or abk or doc_id,
        "kurztitel": kurz or None,
        "stand": f"Text gilt ab: {inkraft.strftime('%d.%m.%Y')}",
        "gilt_ab": inkraft.isoformat(),
        "quelle": url,
    }
    law.notes = []  # footnotes in the metadata have no unit to go to
    rumpf = root.find("rumpf")
    if rumpf is not None:
        law.walk(rumpf, [], 1)
    for annex in root.findall("annex"):
        law.annex(annex)
    return Fetched(markdown=render(front, law.units), front=front, next_version_from=None)


def _ws(text: str | None) -> str:
    """Collapse the XML's layout whitespace (line breaks come from <br/> only)."""
    return re.sub(r"\s+", " ", text or "")


def _line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _text(raw: str) -> str:
    """Inline text with line breaks kept, spaces collapsed within lines."""
    lines = [re.sub(r" +", " ", line).strip() for line in raw.split("\n")]
    return "  \n".join(line for line in lines if line)


def _slug(text: str) -> str:
    """An id part from a designation: "Art. 44a" -> "art44a", "Erster Teil" -> "ersterteil"."""
    s = text.lower().replace("§", "par")
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", s)[:40]


def _escape_list_marker(marker: str) -> str:
    # "1." at the start of a list item would become a Markdown ordered list.
    return re.sub(r"^(\d+[a-z]?)\.", r"\1\\.", marker)


def _footnotes(notes: list[str]) -> str:
    quoted = ["\n".join("> " + line if line else ">" for line in note.split("\n")) for note in notes]
    return "> **Fußnote**\n>\n" + "\n>\n".join(quoted)


class _Law:
    """Collects the units of one law; footnotes are gathered per unit."""

    def __init__(self) -> None:
        self.units: list[Unit] = []
        self.used: set[str] = set()
        self.notes: list[str] = []

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
            blocks = blocks + [_footnotes(self.notes)]
        self.units.append(Unit(kind, self.unit_id(base), ebene, heading, "\n\n".join(blocks)))
        self.notes = []

    # -- structure

    def walk(self, el: ET.Element, path: list[str], depth: int) -> None:
        for child in el:
            if child.tag == "gliederung":
                heading, designation = self.gliederung_heading(child)
                sub = path + [_slug(designation) or "gliederung"]
                self.add("gliederung", "-".join(sub), depth, heading or "(ohne Überschrift)", [])
                self.walk(child, sub, depth + 1)
            elif child.tag == "einzelnorm":
                nr, titel = self.norm_heading(child)
                heading = " ".join(x for x in (nr, titel) if x) or "(ohne Bezeichnung)"
                blocks = self.blocks(child)
                self.add("norm", _slug(nr) or _slug(titel) or "einzelnorm", None, heading, blocks)
            elif child.tag == "einleitungssatz":
                self.add("norm", "eingangsformel", None, "Eingangsformel", self.blocks(child))
            elif child.tag == "annex":
                self.annex(child)

    def gliederung_heading(self, el: ET.Element) -> tuple[str, str]:
        """(heading, designation): the designation is the gliederung.nr or the title's first line."""
        nr = self.plain(el.find("gliederung.nr"))
        titel_el = el.find("gliederung.titel")
        raw_lines = [_line(x) for x in "".join(titel_el.itertext()).split("\n")] if titel_el is not None else []
        raw_lines = [x for x in raw_lines if x]
        titel = self.plain(titel_el)
        heading = " ".join(x for x in (nr, titel) if x)
        return heading, nr or (raw_lines[0] if raw_lines else "")

    def norm_heading(self, el: ET.Element) -> tuple[str, str]:
        return self.plain(el.find("para.nr")), self.plain(el.find("para.titel"))

    def annex(self, el: ET.Element) -> None:
        body = el.find("annex.koerper")
        if body is None:
            body = el
        nummern = body.findall("annex.nummer")
        display = self.plain(nummern[0]) if nummern else "Anlage"
        short = next((self.plain(n) for n in nummern if n.get("int")), display)
        titel = self.plain(body.find("annex.titel"))
        heading = " ".join(x for x in (display, titel) if x)
        blocks = self.blocks(body)
        self.add("norm", _slug(short) or "anlage", None, heading, blocks)

    # -- blocks

    def blocks(self, el: ET.Element) -> list[str]:
        """Render a container as a list of Markdown blocks."""
        out: list[str] = []
        buffer: list[str] = [_ws(el.text)]

        def flush() -> None:
            text = _text("".join(buffer))
            if text:
                out.append(text)
            buffer.clear()

        for child in el:
            tag = child.tag
            if tag in _SKIP:
                pass
            elif tag in _CONTAINERS:
                flush()
                out.extend(self.blocks(child))
            elif tag == "jurAbsatz":
                flush()
                out.extend(self.absatz(child))
            elif tag == "ul":
                flush()
                lines = self.ul(child, 0)
                if lines:
                    out.append("\n".join(lines))
            elif tag == "table":
                flush()
                table = self.table(child)
                if table:
                    out.append("\n".join(table))
            elif tag == "gliederung":  # inside an Anlage
                flush()
                heading, _ = self.gliederung_heading(child)
                if heading:
                    out.append(f"**{heading}**")
                out.extend(self.blocks(child))
            elif tag == "einzelnorm":  # inside an Anlage
                flush()
                heading = " ".join(x for x in self.norm_heading(child) if x)
                if heading:
                    out.append(f"**{heading}**")
                out.extend(self.blocks(child))
            else:
                buffer.append(self.inline_child(child))
            buffer.append(_ws(child.tail))
        flush()
        return out

    def absatz(self, el: ET.Element) -> list[str]:
        nr = self.plain(el.find("absatz.nr"))
        blocks = self.blocks(el)
        if nr:
            if blocks and not blocks[0].startswith(("- ", "|", "**")):
                blocks[0] = f"{nr} {blocks[0]}"
            else:
                blocks.insert(0, nr)
        return blocks

    def ul(self, el: ET.Element, depth: int) -> list[str]:
        lines: list[str] = []
        indent = "  " * depth
        for li in el.findall("li"):
            symbol = ""
            texts: list[str] = []
            nested: list[str] = []
            for child in li:
                if child.tag == "symbol":
                    symbol = self.plain(child)
                elif child.tag == "ul":
                    nested.extend(self.ul(child, depth + 1))
                elif child.tag == "table":
                    nested.extend(indent + "  " + line for line in self.table(child))
                else:
                    text = _text(self.inline(child))
                    if not text:
                        continue
                    if nested:  # text after a nested list continues the item below it
                        nested.append(indent + "  " + text.replace("\n", "\n" + indent + "  "))
                    else:
                        texts.append(text)
            head = " ".join(texts).replace("\n", "\n" + indent + "  ")
            label = _escape_list_marker(symbol)
            lines.append(f"{indent}- {label} {head}".rstrip() if label else f"{indent}- {head}".rstrip())
            lines.extend(nested)
        return lines

    def table(self, el: ET.Element) -> list[str]:
        rows: list[list[str]] = []
        header_rows = 0
        sections = [s for s in el if s.tag in ("thead", "tbody")] or [el]
        for section in sections:
            for row in section.findall("tr"):
                cells: list[str] = []
                for cell in row:
                    if cell.tag not in ("td", "th"):
                        continue
                    text = "<br>".join(b.replace("\n", "<br>") for b in self.blocks(cell))
                    cells.append(text.replace("  <br>", "<br>").replace("|", "\\|"))
                    span = cell.get("colspan", "1")
                    cells.extend([""] * (int(span) - 1 if span.isdigit() and int(span) > 1 else 0))
                rows.append(cells)
                if section.tag == "thead":
                    header_rows += 1
        rows = [r for r in rows if any(c.strip() for c in r)]
        if not rows:
            return []
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        head, body = (rows[0], rows[1:]) if header_rows else ([""] * width, rows)
        out = ["| " + " | ".join(head) + " |", "|" + "---|" * width]
        out += ["| " + " | ".join(r) + " |" for r in body]
        return out

    # -- inline

    def inline(self, el: ET.Element | None) -> str:
        """An element's text with inline markup; line breaks only from <br/>."""
        if el is None:
            return ""
        parts = [_ws(el.text)]
        for child in el:
            parts.append(self.inline_child(child))
            parts.append(_ws(child.tail))
        return "".join(parts)

    def plain(self, el: ET.Element | None) -> str:
        """One line of text for a heading: no emphasis, footnotes still collected."""
        if el is None:
            return ""
        parts = [_ws(el.text)]
        for child in el:
            if child.tag == "br":
                parts.append(" ")
            elif child.tag in ("fn.call", "satz.nr", "sup", "sub", "img"):
                parts.append(self.inline_child(child))
            else:
                parts.append(self.plain(child))
            parts.append(_ws(child.tail))
        return _line("".join(parts))

    def inline_child(self, el: ET.Element) -> str:
        tag = el.tag
        if tag == "br":
            return "\n"
        if tag in ("satz.nr", "sup"):
            inner = self.plain(el)
            return inner.translate(_SUPERSCRIPT) if inner.isdigit() else f"^({inner})" if inner else ""
        if tag == "sub":
            inner = self.plain(el)
            return inner.translate(_SUBSCRIPT) if inner.isdigit() else f"_({inner})" if inner else ""
        if tag == "span" and el.get("class") in ("b", "i"):
            raw = self.inline(el)
            inner = _line(raw)
            mark = "**" if el.get("class") == "b" else "*"
            # Spaces at the edges go outside the markers, or Markdown would not see them.
            lead, trail = (" " if raw[:1] == " " else ""), (" " if raw[-1:] == " " else "")
            return f"{lead}{mark}{inner}{mark}{trail}" if inner else raw
        if tag == "fn.call":
            # The marker ("3)") stays in the text as superscript; the note goes below the unit.
            marker = _line("".join(el.find("fn.text").itertext())) if el.find("fn.text") is not None else ""
            note = el.find("fn.def")
            text = "\n\n".join(self.blocks(note)) if note is not None else ""
            if text:
                self.notes.append(f"{marker} {text}" if marker else text)
            return marker.translate(_SUPERSCRIPT).replace(")", "⁾") if marker else ""
        if tag in ("fn.def", "fn.text"):
            return ""
        if tag == "img":
            return " *(Abbildung, siehe Originalfassung)* "
        if tag in ("ul", "table"):  # a block inside an inline context (rare): flatten it
            return " " + _line(" ".join(self.ul(el, 0) if tag == "ul" else self.table(el))) + " "
        return self.inline(el)
