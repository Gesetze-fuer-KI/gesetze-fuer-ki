"""Convert a law from gesetze-im-internet.de (gii-norm XML) into one Markdown file.

The Markdown is read by the server first and by people on GitHub second. Every
unit of the law is preceded by a hidden marker comment, so the server can split
a file into its parts without guessing from headings:

    <!-- gliederung id="BJNG000108140" ebene="1" -->
    ## I. Steuerpflicht

    <!-- norm id="BJNE003619116" -->
    ### § 1 Steuerpflicht

The front matter holds the law's metadata (abbreviation, title, Stand, source).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import yaml

SOURCE_BASE = "https://www.gesetze-im-internet.de"

_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
_SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def _clean(text: str) -> str:
    """Collapse runs of whitespace the XML carries for layout."""
    return re.sub(r"[ \t\r\n ]+", " ", text)


def _inline(el: ET.Element) -> str:
    """Render an element's text content with inline markup, without block structure."""
    parts: list[str] = [el.text or ""]
    for child in el:
        parts.append(_inline_child(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _inline_child(el: ET.Element) -> str:
    tag = el.tag
    if tag == "BR":
        return "\n"
    if tag == "SUP":
        inner = _clean(_inline(el)).strip()
        return inner.translate(_SUPERSCRIPT) if inner.isdigit() else f"^({inner})"
    if tag == "SUB":
        inner = _clean(_inline(el)).strip()
        return inner.translate(_SUBSCRIPT) if inner.isdigit() else f"_({inner})"
    if tag in ("B",):
        inner = _clean(_inline(el)).strip()
        return f"**{inner}**" if inner else ""
    if tag in ("I",):
        inner = _clean(_inline(el)).strip()
        return f"*{inner}*" if inner else ""
    if tag == "IMG":
        return " *(Abbildung, siehe Originalfassung)* "
    if tag in ("DL", "table", "P", "Content", "pre"):
        # Block inside an inline context (rare): flatten it.
        return " " + _clean(" ".join(_blocks(el))) + " "
    return _inline(el)


def _text(el: ET.Element) -> str:
    """Inline text with line breaks kept, whitespace collapsed within lines."""
    lines = [_clean(line).strip() for line in _inline(el).split("\n")]
    return "  \n".join(line for line in lines if line)


def _escape_list_marker(marker: str) -> str:
    # "1." or "1a." at the start of a list item would become a Markdown ordered list.
    return re.sub(r"^(\d+[a-z]?)\.", r"\1\\.", marker)


def _dl(el: ET.Element, depth: int) -> list[str]:
    lines: list[str] = []
    indent = "  " * depth
    marker = ""
    for child in el:
        if child.tag == "DT":
            marker = _clean(_inline(child)).strip()
        elif child.tag == "DD":
            head, nested = _dd(child, depth + 1)
            label = _escape_list_marker(marker)
            head = head.replace("\n", "\n" + indent + "  ")
            lines.append(f"{indent}- {label} {head}".rstrip())
            lines.extend(nested)
            marker = ""
    return lines


def _dd(el: ET.Element, depth: int) -> tuple[str, list[str]]:
    """The text of a list item and the lines of the lists nested inside it."""
    texts: list[str] = []
    nested: list[str] = []

    def walk(node: ET.Element) -> None:
        if node.text and node.text.strip():
            texts.append(node.text)
        for child in node:
            if child.tag == "DL":
                nested.extend(_dl(child, depth))
            elif child.tag in ("LA", "P"):
                walk(child)
                texts.append(" ")
            elif child.tag == "table":
                nested.extend("  " * depth + line for line in _table(child))
            else:
                texts.append(_inline_child(child))
            if child.tail and child.tail.strip():
                (texts if not nested else nested).append(
                    child.tail if not nested else "  " * depth + _clean(child.tail).strip()
                )

    walk(el)
    lines = [_clean(line).strip() for line in "".join(texts).split("\n")]
    head = "  \n".join(line for line in lines if line)
    return head, nested


def _table(el: ET.Element) -> list[str]:
    rows: list[list[str]] = []
    header_rows = 0
    for group in el.iter("tgroup"):
        for section in group:
            if section.tag not in ("thead", "tbody"):
                continue
            for row in section.iter("row"):
                cells = [_text(entry).replace("  \n", "<br>").replace("|", "\\|") for entry in row.iter("entry")]
                rows.append(cells)
                if section.tag == "thead":
                    header_rows += 1
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    if header_rows:
        head, body = rows[0], rows[1:]
    else:
        head, body = [""] * width, rows
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * width]
    out += ["| " + " | ".join(r) + " |" for r in body]
    return out


def _blocks(el: ET.Element) -> list[str]:
    """Render a container (Content, P, …) as a list of Markdown blocks."""
    blocks: list[str] = []
    buffer: list[str] = [el.text or ""]

    def flush() -> None:
        lines = [_clean(line).strip() for line in "".join(buffer).split("\n")]
        text = "  \n".join(line for line in lines if line)
        if text:
            blocks.append(text)
        buffer.clear()

    for child in el:
        tag = child.tag
        if tag in ("P", "Content"):
            flush()
            blocks.extend(_blocks(child))
        elif tag == "DL":
            flush()
            blocks.append("\n".join(_dl(child, 0)))
        elif tag == "table":
            flush()
            table = _table(child)
            if table:
                blocks.append("\n".join(table))
        elif tag == "pre":
            flush()
            text = "\n".join(_clean(line).strip() for line in _inline(child).split("\n"))
            text = text.strip()
            if text:
                blocks.append("```text\n" + text + "\n```")
        elif tag in ("TOC", "noindex"):
            pass
        elif tag in ("Title", "Ident"):
            flush()
            text = _clean(_inline(child)).strip()
            if text:
                blocks.append(f"**{text}**")
        else:
            buffer.append(_inline_child(child))
        buffer.append(child.tail or "")
    flush()
    return blocks


def _meta_text(meta: ET.Element, tag: str) -> str:
    found = meta.find(tag)
    return _clean("".join(found.itertext())).strip() if found is not None else ""


def convert(xml_bytes: bytes, slug: str) -> tuple[str, dict]:
    """Return the Markdown for one law and its front-matter metadata."""
    root = ET.fromstring(xml_bytes)
    norms = root.findall("norm")
    if not norms:
        raise ValueError(f"{slug}: no <norm> elements")

    head = norms[0]
    meta = head.find("metadaten")
    jurabk = _meta_text(meta, "jurabk")
    amtabk = _meta_text(meta, "amtabk")
    title = _meta_text(meta, "langue") or _meta_text(meta, "kurzue") or jurabk
    stand = [
        _clean("".join(s.findtext("standkommentar") or "")).strip()
        for s in meta.findall("standangabe")
        if (s.findtext("standtyp") or "").strip() == "Stand"
    ]
    front = {
        "abkuerzung": amtabk or jurabk,
        "jurabk": jurabk,
        "titel": title,
        "kurztitel": _meta_text(meta, "kurzue") or None,
        "stand": stand[0] if stand else None,
        "ausfertigung": _meta_text(meta, "ausfertigung-datum") or None,
        "quelle": f"{SOURCE_BASE}/{slug}/",
        "doknr": root.get("doknr"),
        "builddate": root.get("builddate"),
    }
    front = {k: v for k, v in front.items() if v}

    out: list[str] = []
    out.append("---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False, width=1000) + "---")
    display_abk = front["abkuerzung"]
    out.append(f"# {title}" + (f" ({display_abk})" if display_abk and display_abk != title else ""))
    if front.get("stand"):
        out.append(f"Stand: {front['stand']}")
    out.append(f"Quelle: <{front['quelle']}>")
    head_notes = head.find("textdaten/fussnoten")
    if head_notes is not None:
        out.extend(_footnotes(head_notes))

    level = 1
    for norm in norms[1:]:
        m = norm.find("metadaten")
        doknr = norm.get("doknr", "")
        unit_id = doknr[len(root.get("doknr", "")):] or doknr
        einheit = m.find("gliederungseinheit")
        if einheit is not None:
            kennzahl = (einheit.findtext("gliederungskennzahl") or "").strip()
            depth = max(1, len(kennzahl) // 3)
            level = min(1 + depth, 5)
            bez = _meta_text(einheit, "gliederungsbez")
            titel = _meta_text(einheit, "gliederungstitel")
            heading = " ".join(x for x in (bez, titel) if x) or "(ohne Überschrift)"
            out.append(f'<!-- gliederung id="{unit_id}" ebene="{depth}" -->\n{"#" * level} {heading}')
            body = _norm_body(norm)
            out.extend(body)
            continue

        enbez = _meta_text(m, "enbez")
        if enbez == "(XXXX)":  # placeholder for a gap left by repealed provisions
            enbez = ""
        if enbez == "Inhaltsübersicht":
            continue
        titel = _meta_text(m, "titel")
        heading = " ".join(x for x in (enbez, titel) if x) or "(ohne Bezeichnung)"
        out.append(f'<!-- norm id="{unit_id}" -->\n{"#" * min(level + 1, 6)} {heading}')
        out.extend(_norm_body(norm))

    return "\n\n".join(out).rstrip() + "\n", front


def _norm_body(norm: ET.Element) -> list[str]:
    blocks: list[str] = []
    content = norm.find("textdaten/text/Content")
    if content is not None:
        blocks.extend(_blocks(content))
    notes = norm.find("textdaten/fussnoten")
    if notes is not None:
        blocks.extend(_footnotes(notes))
    return blocks


def _footnotes(notes: ET.Element) -> list[str]:
    content = notes.find("Content")
    if content is None:
        return []
    blocks = _blocks(content)
    if not blocks:
        return []
    return [footnote_block(blocks)]


def footnote_block(blocks: list[str]) -> str:
    """Footnote text, one or more blocks, as a Markdown quote headed „Fußnote“."""
    quoted = ["\n".join("> " + line if line else ">" for line in block.split("\n")) for block in blocks]
    return "> **Fußnote**\n>\n" + "\n>\n".join(quoted)
