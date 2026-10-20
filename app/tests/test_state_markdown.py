from state_markdown import render
from store import Unit, split_law

UNITS = [Unit("gliederung", "g1", 1, "Erster Teil Allgemeines", ""),
         Unit("norm", "n1", None, "Art. 1 Geltungsbereich", "(1) Text.\n\n(2) Mehr."),
         Unit("norm", "n2", None, "Art. 2 Begriffe", "Text.")]
FRONT = {"land": "BY", "abkuerzung": "BayBO", "titel": "Bayerische Bauordnung",
         "stand": "Text gilt ab: 01.01.2026", "quelle": "https://www.gesetze-bayern.de/Content/Document/BayBO"}


def test_render_roundtrips_through_split_law():
    front, _, units = split_law(render(FRONT, UNITS))
    assert front["land"] == "BY" and front["abkuerzung"] == "BayBO"
    assert [(u.kind, u.unit_id, u.heading, u.body) for u in units] == \
           [(u.kind, u.unit_id, u.heading, u.body) for u in UNITS]


def test_render_marks_unofficial_text():
    assert "Nichtamtliche Fassung des Landesportals." in render(FRONT, UNITS)


def test_render_bremen_adds_attribution():
    md = render({**FRONT, "land": "HB"}, UNITS)
    assert "CC BY-NC-ND" in md


def test_render_heading_levels_and_optional_keys():
    md = render({**FRONT, "kurztitel": None, "gilt_ab": "2026-01-01"}, UNITS)
    assert "\n# Bayerische Bauordnung (BayBO)\n" in md
    assert '<!-- gliederung id="g1" ebene="1" -->\n## Erster Teil Allgemeines' in md
    assert '<!-- norm id="n1" -->\n### Art. 1 Geltungsbereich' in md
    assert "kurztitel" not in md and "gilt_ab: '2026-01-01'" in md or "gilt_ab: 2026-01-01" in md
    assert "Nichtamtliche Fassung" in md and "Texte: Transparenzportal" not in md
