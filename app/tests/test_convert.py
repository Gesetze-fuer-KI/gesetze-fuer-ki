from pathlib import Path

import store
from convert import convert

MINI = (Path(__file__).parent / "fixtures" / "mini.xml").read_bytes()


def test_front_matter_and_title():
    md, front = convert(MINI, "minig")
    assert front["abkuerzung"] == "MiniG"
    assert front["stand"] == "zuletzt geändert durch Art. 1 G v. 1.1.2026 I Nr. 1"
    assert front["quelle"] == "https://www.gesetze-im-internet.de/minig/"
    assert "# Gesetz über kleine Gewerbe (MiniG)" in md


def test_units_are_marked_and_toc_is_skipped():
    md, _ = convert(MINI, "minig")
    assert '<!-- gliederung id="BJNG000100000" ebene="1" -->\n## Abschnitt 1 Allgemeines' in md
    assert '<!-- norm id="BJNE000200000" -->\n### § 1 Anzeigepflicht' in md
    assert "Inhaltsübersicht" not in md
    assert "(XXXX)" not in md


def test_sentence_numbers_and_nested_lists():
    md, _ = convert(MINI, "minig")
    assert "(1) ¹Wer ein Gewerbe beginnt, muss dies anzeigen. ²Das gilt auch, wenn" in md
    assert "- 1\\. der Betrieb verlegt wird," in md
    assert "- 2\\. der Gegenstand gewechselt wird\n  - a) ganz oder\n  - b) teilweise." in md


def test_tables_and_footnotes():
    md, _ = convert(MINI, "minig")
    assert "| Stufe | Betrag |\n|---|---|\n| 1 | 100 \\| 200 |" in md
    assert "> **Fußnote**\n>\n> § 1a: IdF d. Art. 2" in md


def test_split_law_round_trip():
    md, _ = convert(MINI, "minig")
    front, preamble, units = store.split_law(md)
    assert front["abkuerzung"] == "MiniG"
    assert "Stand:" in preamble
    assert [(u.kind, u.heading) for u in units] == [
        ("gliederung", "Abschnitt 1 Allgemeines"),
        ("norm", "§ 1 Anzeigepflicht"),
        ("norm", "§ 1a Tabelle"),
        ("norm", "§§ 2 bis 4 (weggefallen)"),
    ]
    assert units[1].body.startswith("(1) ¹Wer")
