"""HTML law pages to Markdown with the standard library only: a small DOM and a block renderer.

The stdlib has only a streaming HTML parser, so `parse_html` builds a minimal tree from it.
`Renderer` turns a container of law text (paragraphs, lists, tables, emphasis) into Markdown
blocks in the format of convert.py. Portals with footnote links override `is_footnote` and
`footnote`.
"""

from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser

from convert import _SUBSCRIPT, _SUPERSCRIPT, _clean, _escape_list_marker

VOID = {"br", "img", "col", "input", "meta", "link", "hr", "wbr", "source"}
BLOCK = {"p", "div", "dl", "table", "ul", "ol", "pre", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6",
         "section", "header", "footer", "nav", "article"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


class Node:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: dict[str, str]):
        self.tag = tag
        self.attrs = attrs
        self.children: list[Node | str] = []

    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def elements(self) -> list[Node]:
        return [c for c in self.children if isinstance(c, Node)]

    def iter(self):
        yield self
        for child in self.elements():
            yield from child.iter()

    def find(self, tag: str, **attrs: str) -> Node | None:
        return next((n for n in self.iter() if n.tag == tag
                     and all(n.attrs.get(k) == v for k, v in attrs.items())), None)

    def text(self) -> str:
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in BLOCK and self.stack[-1].tag == "p":
            self.stack.pop()  # a block element ends an open paragraph, as in a browser
        node = Node(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.stack[-1].children.append(Node(tag, {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def parse_html(page: str) -> Node:
    builder = _TreeBuilder()
    builder.feed(page)
    builder.close()
    return builder.root


def line(text: str) -> str:
    """One line: all whitespace collapsed."""
    return re.sub(r"\s+", " ", text).strip()


def text(raw: str) -> str:
    """Inline text with line breaks kept, spaces collapsed within lines."""
    lines = [_clean(x).strip() for x in raw.split("\n")]
    return "  \n".join(x for x in lines if x)


def designation_slug(designation: str) -> str:
    """An id part from a designation: "§ 44a" -> "par44a", "Artikel 3" -> "art3", "1. Abschnitt" -> "1abschnitt"."""
    s = designation.lower().replace("§", "par")
    s = re.sub(r"^artikel\b|^art\.", "art", s)
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", s)[:40]


class Renderer:
    """Law text in HTML as Markdown blocks: paragraphs, dl/ul lists, tables, emphasis, sup/sub."""

    def is_footnote(self, el: Node) -> bool:
        """Whether an element is a footnote marker; such markers are handed to `footnote`."""
        return False

    def footnote(self, el: Node) -> str:
        """Collect the note behind a footnote marker; returns the marker text ("1)") or ""."""
        return ""

    def heading_lines(self, el: Node) -> list[str]:
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
        return [x for x in (line(x) for x in "".join(parts).split("\n")) if x]

    # -- blocks

    def blocks(self, el: Node, skip: Node | None = None) -> list[str]:
        """Render a container as a list of Markdown blocks."""
        out: list[str] = []
        buffer: list[str] = []

        def flush() -> None:
            t = text("".join(buffer))
            if t:
                out.append(t)
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
                t = text(self.inline(child))
                if t:
                    out.append(t)
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
            elif tag in HEADINGS:
                flush()
                t = " ".join(self.heading_lines(child))
                if t:
                    out.append(f"**{t}**")
            elif tag == "pre":
                flush()
                t = "\n".join(x.rstrip() for x in child.text().strip("\n").split("\n"))
                if t.strip():
                    out.append("```text\n" + t + "\n```")
            else:
                buffer.append(self.inline_child(child))
        flush()
        return out

    def has_blocks(self, el: Node) -> bool:
        return any(c.tag in BLOCK for c in el.elements())

    def dl(self, el: Node, depth: int) -> list[str]:
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

    def ul(self, el: Node, depth: int) -> list[str]:
        lines: list[str] = []
        indent = "  " * depth
        for li in el.elements():
            if li.tag == "li":
                head, nested = self.item(li, depth)
                lines.append(f"{indent}- {head}".rstrip())
                lines.extend(nested)
        return lines

    def item(self, el: Node, depth: int) -> tuple[str, list[str]]:
        """The text of a list item and the lines of what is nested in it (lists, tables, later text)."""
        indent = "  " * (depth + 1)
        texts: list[str] = []
        nested: list[str] = []

        def text_block(raw: str) -> None:
            t = text(raw)
            if not t:
                return
            if nested:  # text after a nested list continues the item below it
                nested.append(indent + t.replace("\n", "\n" + indent))
            else:
                texts.append(t)

        inline: list[str] = []
        for child in el.children:
            if isinstance(child, Node) and child.tag in ("dl", "ul", "ol", "table", "p", "div"):
                text_block("".join(inline))
                inline = []
                if child.tag == "dl":
                    nested.extend(self.dl(child, depth + 1))
                elif child.tag in ("ul", "ol"):
                    nested.extend(self.ul(child, depth + 1))
                elif child.tag == "table":
                    nested.extend(indent + x for block in self.table(child) for x in block.split("\n"))
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

    def table(self, el: Node) -> list[str]:
        """The caption (bold) and the table as Markdown blocks."""
        out: list[str] = []
        caption = next((c for c in el.elements() if c.tag == "caption"), None)
        if caption is not None:
            t = line(self.plain(caption))
            if t:
                out.append(f"**{t}**")
        rows: list[list[str]] = []
        header_rows = 0
        sections = [s for s in el.elements() if s.tag in ("thead", "tbody", "tfoot")] or [el]
        for section in sections:
            for row in (r for r in section.elements() if r.tag == "tr"):
                cells: list[str] = []
                for cell in row.elements():
                    if cell.tag not in ("td", "th"):
                        continue
                    t = "<br>".join(b.replace("  \n", "<br>").replace("\n", "<br>") for b in self.blocks(cell))
                    cells.append(t.replace("|", "\\|"))
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

    def inline(self, el: Node) -> str:
        """An element's text with inline markup; line breaks only from <br>."""
        return "".join(_clean(c) if isinstance(c, str) else self.inline_child(c) for c in el.children)

    def plain(self, el: Node) -> str:
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
        return line("".join(parts))

    def inline_child(self, el: Node) -> str:
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
            for x in raw.split("\n"):
                inner = line(x)
                lead, trail = (" " if x[:1] == " " else ""), (" " if x[-1:] == " " else "")
                out.append(f"{lead}{mark}{inner}{mark}{trail}" if inner else x)
            return "\n".join(out)
        if tag == "img":
            return " *(Abbildung, siehe Originalfassung)* "
        if tag in ("script", "style"):
            return ""
        if tag in BLOCK:  # a block inside an inline context (rare): flatten it
            return " " + line(" ".join(self.blocks(el))) + " "
        return self.inline(el)
