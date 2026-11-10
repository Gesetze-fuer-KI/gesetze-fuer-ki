"""The search charts and tables are drawn from docs/suche.history.json (docs_hooks/charts.py), never typed by hand."""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def hook():
    spec = importlib.util.spec_from_file_location("charts_hook", ROOT / "docs_hooks" / "charts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_marker_is_drawn_and_none_is_left_over():
    charts = hook()
    for page in ("suche.md",):
        text = (ROOT / "docs" / page).read_text()
        assert "<!-- chart:" in text, page
        out = charts.on_page_markdown(text, None, None, None)
        assert "<!-- chart:" not in out and "<!-- table:" not in out and "<svg" in out, page


def test_every_chart_has_a_label_and_every_mark_a_tooltip():
    charts = hook()
    history = charts.load()
    for name, draw in charts.CHARTS.items():
        svg = draw(history)
        assert 'aria-label="' in svg, name
        marks = len(re.findall(r"<(?:rect|path|circle)[^>]*class=\"gk-s\d", svg))
        legend = len(re.findall(r"<rect[^>]*width=\"10\" height=\"10\"", svg))
        assert svg.count("<title>") == marks - legend, name


def test_the_finding_chart_splits_each_set_into_its_questions():
    charts = hook()
    history = charts.load()
    svg = charts.chart_finden(history)
    now = charts.latest(history, "heute")
    for group in charts.FINDEN:
        counts = [int(c) for c in re.findall(rf"(\d+) von {now[group]['n']} \(", svg)]
        assert now[group]["n"] in {sum(counts[i:i + 3]) for i in range(len(counts))}, group
