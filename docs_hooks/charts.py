"""MkDocs hook: draws the search measurement charts and their tables from docs/suche.history.json.

`<!-- chart:NAME -->` becomes inline SVG and `<!-- table:NAME -->` the table it was drawn from, so neither is typed
by hand and both move with the next measurement (app/eval/baseline.py --history).
Every mark carries its value as a tooltip; colours are CSS variables (stylesheets/extra.css), so the dark theme
follows. Text stays in the text colour, never in a series colour.
"""

import html
import json
import re
from pathlib import Path

HISTORY = Path(__file__).resolve().parents[1] / "docs" / "suche.history.json"
W = 640
FONT = 'font-family="inherit"'

LABELS = {
    "alltag": "Alltagsfragen, wörtlich gesucht",
    "fach": "Fragen in Fachsprache",
    "umformuliert": "Alltagsfragen, von Claude umformuliert",
    "selten": "Seltene Gesetze, wörtlich gesucht",
    "selten_umformuliert": "Seltene Gesetze, von Claude umformuliert",
}


def load() -> list[dict]:
    return json.loads(HISTORY.read_text(encoding="utf-8"))


def latest(history: list[dict], search: str) -> dict[str, dict]:
    """The newest entry of each group for one search (the file is in date order)."""
    out: dict[str, dict] = {}
    for e in history:
        if e["search"] == search:
            out[e["group"]] = e
    return out


def pct(count: int, n: int) -> str:
    return f"{round(100 * count / n)} %"


def date_de(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)}.{int(m)}.{y}"


def _svg(height: int, body: str, label: str) -> str:
    # one line: a blank line would end the raw HTML block in Python-Markdown
    return (f'<figure class="gk-chart"><svg viewBox="0 0 {W} {height}" role="img" '
            f'aria-label="{html.escape(label)}">{body}</svg></figure>')


def _text(x: float, y: float, s: str, anchor: str = "start", cls: str = "") -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" class="{cls}" {FONT}>{html.escape(s)}</text>'


def _legend(items: list[tuple[str, int]], x: float, y: float) -> tuple[str, float]:
    """Swatches with their names, wrapped onto a new row before they leave the chart; returns the body and its last y."""
    body, x0 = "", x
    for name, slot in items:
        width = 16 + 7.0 * len(name) + 22
        if x > x0 and x + width > W:
            x, y = x0, y + 20
        body += f'<rect x="{x:.1f}" y="{y - 9}" width="10" height="10" rx="2" class="gk-s{slot}"/>'
        body += _text(x + 16, y, name, cls="gk-chart-small")
        x += width
    return body, y


FINDEN = ["alltag", "umformuliert", "selten", "selten_umformuliert"]
FINDEN_SEGMENTS = [("richtige Vorschrift", 1), ("nur das richtige Gesetz", 3), ("weder noch", 2)]


def chart_finden(history: list[dict]) -> str:
    """Per question set: the right § in the first three, only the right law there, or neither."""
    now = latest(history, "heute")
    body, y = "", 16
    for group in FINDEN:
        e = now[group]
        n = e["n"]
        counts = [e["hit_at_3"], e["law_at_3"] - e["hit_at_3"], n - e["law_at_3"]]
        body += _text(0, y, f"{LABELS[group]} ({n})", cls="gk-chart-label")
        x = 0.0
        for (name, slot), count in zip(FINDEN_SEGMENTS, counts):
            w = W * count / n
            if w > 0:
                body += (f'<rect x="{x + 1:.1f}" y="{y + 8}" width="{max(w - 2, 0):.1f}" height="26" rx="3" '
                         f'class="gk-s{slot}"><title>{html.escape(name)}: {count} von {n} ({pct(count, n)})</title></rect>')
                if w > 44:
                    body += _text(x + w / 2, y + 26, pct(count, n), "middle", "gk-chart-ontext")
            x += w
        y += 62
    legend, y = _legend([(f"{name} unter den ersten 3" if slot == 1 else name, slot) for name, slot in FINDEN_SEGMENTS], 0, y)
    body += legend
    return _svg(round(y) + 8, body, "Wie oft die heutige Suche die richtige Vorschrift oder das richtige Gesetz "
                             "unter den ersten drei Treffern hat")


def table_finden(history: list[dict]) -> str:
    now = latest(history, "heute")
    rows = ["| Fragen | Richtige Vorschrift auf Platz 1 | … unter den ersten 3 | … unter den ersten 8 "
            "| Richtiges Gesetz unter den ersten 3 |", "|---|---|---|---|---|"]
    for group in [*FINDEN, "fach"]:
        e = now[group]
        n = e["n"]
        rows.append(f"| {LABELS[group]} ({n}) | {pct(e['hit_at_1'], n)} | {pct(e['hit_at_3'], n)} "
                    f"| {pct(e['hit_at_8'], n)} | {pct(e['law_at_3'], n)} |")
    return "\n".join(rows)


VERLAUF = [("umformuliert", 1), ("selten_umformuliert", 3)]


def chart_verlauf(history: list[dict]) -> str:
    """The right law in the first three, per measurement, for the two sets that search the way Claude does."""
    dates = sorted({e["date"] for e in history if e["search"] == "heute"})
    left, right, top, bottom, h = 44, 220, 12, 36, 240
    span = max(len(dates) - 1, 1)
    px = (lambda i: left + i / span * (W - left - right)) if len(dates) > 1 else (lambda i: left + (W - left - right) / 2)
    py = lambda v: top + (1 - v) * (h - top - bottom)  # noqa: E731
    body, ends = "", []
    for g in (0, .25, .5, .75, 1):
        body += (f'<line x1="{left}" x2="{W - right}" y1="{py(g):.1f}" y2="{py(g):.1f}" class="gk-grid"/>'
                 + _text(left - 8, py(g) + 4, f"{round(g * 100)} %", "end", "gk-chart-small"))
    for i, d in enumerate(dates):
        body += _text(px(i), h - 12, date_de(d), "middle", "gk-chart-small")
    for group, slot in VERLAUF:
        points = []
        for i, d in enumerate(dates):
            e = next((x for x in history if x["date"] == d and x["group"] == group and x["search"] == "heute"), None)
            if e:
                points.append((i, e["law_at_3"] / e["n"], e))
        if len(points) > 1:
            pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v, _ in points)
            body += f'<polyline points="{pts}" class="gk-line gk-l{slot}"/>'
        for i, v, e in points:
            body += (f'<circle cx="{px(i):.1f}" cy="{py(v):.1f}" r="5" class="gk-s{slot} gk-ring"><title>'
                     f'{LABELS[group]}, {date_de(e["date"])}: {e["law_at_3"]} von {e["n"]} ({pct(e["law_at_3"], e["n"])})'
                     f'</title></circle>')
        if points:
            i, v, e = points[-1]
            ends.append([py(v) + 4, px(i) + 12, f"{LABELS[group]}: {pct(e['law_at_3'], e['n'])}"])
    ends.sort()
    for a, b in zip(ends, ends[1:]):
        b[0] = max(b[0], a[0] + 16)
    for y, x, label in ends:
        body += _text(x, y, label, cls="gk-chart-small")
    return _svg(h, body, "Richtiges Gesetz unter den ersten drei, je Messung")


def table_verlauf(history: list[dict]) -> str:
    dates = sorted({e["date"] for e in history if e["search"] == "heute"})
    rows = ["| Gemessen | Stand der Daten | " + " | ".join(LABELS[g] for g, _ in VERLAUF) + " |",
            "|---|---|" + "---|" * len(VERLAUF)]
    for d in dates:
        cells, stand = [], ""
        for group, _ in VERLAUF:
            e = next((x for x in history if x["date"] == d and x["group"] == group and x["search"] == "heute"), None)
            cells.append(f"{pct(e['law_at_3'], e['n'])} Gesetz, {pct(e['hit_at_3'], e['n'])} Vorschrift" if e else "–")
            stand = stand or (date_de(e["stand"]) if e and e.get("stand") else "")
        rows.append(f"| {date_de(d)} | {stand} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


CHARTS = {"finden": chart_finden, "verlauf": chart_verlauf}
TABLES = {"finden": table_finden, "verlauf": table_verlauf}


def on_page_markdown(markdown: str, page, config, files) -> str:
    if "<!-- chart:" not in markdown and "<!-- table:" not in markdown:
        return markdown
    history = load()
    markdown = re.sub(r"<!-- chart:(\w+) -->", lambda m: CHARTS[m.group(1)](history), markdown)
    return re.sub(r"<!-- table:(\w+) -->", lambda m: TABLES[m.group(1)](history), markdown)
