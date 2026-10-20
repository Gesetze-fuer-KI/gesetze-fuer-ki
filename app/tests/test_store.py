import json
from pathlib import Path

import pytest

import store
from convert import convert
from state_markdown import render

MINI = (Path(__file__).parent / "fixtures" / "mini.xml").read_bytes()


@pytest.fixture
def index(tmp_path):
    data = tmp_path / "data"
    (data / "m").mkdir(parents=True)
    md, _ = convert(MINI, "minig")
    (data / "m" / "minig.md").write_text(md, encoding="utf-8")
    db = tmp_path / "index.sqlite"
    assert store.build(data, db, "rev1") == 1
    s = store.Store(db)
    yield s
    s.close()


def test_norm_key():
    assert store.norm_key("§ 19a") == store.norm_key("19a") == "19a"
    assert store.norm_key("Art. 3") == store.norm_key("Artikel 3") == "3"
    assert store.norm_key("Anlage 2") == "anlage2"


def test_query_terms_drop_stopwords_and_stem():
    assert store.query_terms("Brauche ich für mein Gewerbe eine Anzeige?") == ["gewerb", "anzeig"]
    assert store.fts_query("Grenze Umsatz", "OR") == '"grenz"* OR "umsatz"*'


def test_search_finds_by_stem_and_falls_back_to_any_term(index):
    rows = index.search("Gewerbe anzeigen")
    assert rows[0]["heading"] == "§ 1 Anzeigepflicht"
    assert rows[0]["breadcrumb"] == "Abschnitt 1 Allgemeines"
    # "Mond" matches nothing, so the OR pass still finds the provision with "Grenze"
    assert index.search("Grenze Mond")[0]["enbez"] == "§ 1"


def test_resolve_and_lookup(index):
    assert index.resolve_law("minig")[0]["abk"] == "MiniG"
    assert index.resolve_law("Mini G")[0]["slug"] == "minig"
    assert index.find_laws("kleine Gewerbe")[0]["slug"] == "minig"
    assert index.norm("minig", "1a")["heading"] == "§ 1a Tabelle"
    assert index.norm("minig", "§ 99") is None
    assert index.meta("revision") == "rev1"


GELTUNG = """---
abkuerzung: GeltG
titel: Geltungsgesetz
quelle: https://www.gesetze-im-internet.de/geltg/
---

# Geltungsgesetz (GeltG)

<!-- norm id="BJNR000000002BJNE000100000" -->
## § 1 Geltungsbereich

Dieses Gesetz gilt für den Bund.
"""


def _state_law(clone: Path, land: str, slug: str, abk: str, titel: str, heading: str, body: str) -> None:
    front = {"land": land, "abkuerzung": abk, "titel": titel, "quelle": f"https://example.org/{slug}"}
    units = [store.Unit(kind="norm", unit_id=f"{slug}-1", ebene=None, heading=heading, body=body)]
    path = clone / slug[:2] / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(front, units), encoding="utf-8")


def _state_file(clone: Path, complete: bool) -> None:
    (clone / ".sync").mkdir(parents=True, exist_ok=True)
    state = {"complete": complete, "pass_done": [], "pass_failed": [], "laws": {}}
    (clone / ".sync" / "state.json").write_text(json.dumps(state))


@pytest.fixture
def index2(tmp_path):
    data = tmp_path / "data"
    (data / "m").mkdir(parents=True)
    md, _ = convert(MINI, "minig")
    (data / "m" / "minig.md").write_text(md, encoding="utf-8")
    (data / "ge").mkdir()
    (data / "ge" / "geltg.md").write_text(GELTUNG, encoding="utf-8")
    by, nw = tmp_path / "landesrecht-by", tmp_path / "landesrecht-nw"
    _state_law(by, "BY", "by-minig", "MiniG", "Bayerisches Minigesetz", "Art. 1 Geltungsbereich",
               "Dieses Gesetz gilt in Bayern.")
    _state_file(by, complete=True)
    _state_law(nw, "NW", "nw-nwg", "NwG", "Nordrhein-westfälisches Gesetz", "§ 1 Geltungsbereich",
               "Dieses Gesetz gilt in Nordrhein-Westfalen.")
    _state_file(nw, complete=False)
    db = tmp_path / "index.sqlite"
    assert store.build(data, db, "rev1", states={"BY": by, "NW": nw}) == 3
    s = store.Store(db)
    yield s
    s.close()


def test_incomplete_state_not_indexed(index2):
    assert index2.state_status() == {"BY": True, "NW": False}
    assert index2.resolve_law("NwG", land="NW") == []


def test_search_defaults_to_bund(index2):
    assert {r["land"] for r in index2.search("Geltungsbereich")} == {None}
    assert {r["land"] for r in index2.search("Geltungsbereich", land="BY")} == {"BY"}
    assert {r["land"] for r in index2.search("Geltungsbereich", land=None)} == {None, "BY"}


def test_count_by_land(index2):
    assert index2.count_by_land("Geltungsbereich") == {"BY": 1}


def test_resolve_same_abbreviation_returns_both(index2):
    assert {r["land"] for r in index2.resolve_law("MiniG")} == {None, "BY"}
    assert [r["land"] for r in index2.resolve_law("MiniG", land="BY")] == ["BY"]
    assert [r["land"] for r in index2.resolve_law("MiniG", land=store.BUND)] == [None]


def test_state_law_path_is_relative_to_its_clone(index2):
    law = index2.law("by-minig")
    assert law["path"] == "by/by-minig.md"
    assert [r["slug"] for r in index2.find_laws("Minigesetz", land="BY")] == ["by-minig"]
    assert index2.find_laws("Minigesetz", land=store.BUND) == []


def test_clone_without_state_file_counts_as_incomplete(tmp_path):
    data, clone = tmp_path / "data", tmp_path / "landesrecht-sn"
    data.mkdir()
    _state_law(clone, "SN", "sn-sng", "SnG", "Sächsisches Gesetz", "§ 1 Geltungsbereich", "Text.")
    db = tmp_path / "index.sqlite"
    assert store.build(data, db, "rev", states={"SN": clone}) == 0
    s = store.Store(db)
    assert s.state_status() == {"SN": False}
    s.close()


def test_broken_state_does_not_abort_build(tmp_path):
    data, bad_json, bad_law = tmp_path / "data", tmp_path / "landesrecht-sn", tmp_path / "landesrecht-hb"
    (data / "m").mkdir(parents=True)
    md, _ = convert(MINI, "minig")
    (data / "m" / "minig.md").write_text(md, encoding="utf-8")
    _state_law(bad_json, "SN", "sn-sng", "SnG", "Sächsisches Gesetz", "§ 1 Geltungsbereich", "Text.")
    (bad_json / ".sync").mkdir()
    (bad_json / ".sync" / "state.json").write_text("{not json")
    _state_law(bad_law, "HB", "hb-hbg", "HbG", "Bremisches Gesetz", "§ 1 Geltungsbereich", "Text.")
    (bad_law / "hb" / "hb-kaputt.md").write_text("---\nfront matter without end\n", encoding="utf-8")
    _state_file(bad_law, complete=True)
    db = tmp_path / "index.sqlite"
    assert store.build(data, db, "rev", states={"SN": bad_json, "HB": bad_law}) == 1
    s = store.Store(db)
    assert s.state_status() == {"HB": False, "SN": False}
    assert [r["land"] for r in s.resolve_law("MiniG")] == [None]
    assert s.resolve_law("HbG", land="HB") == []
    assert s.meta("schema") == store.SCHEMA_VERSION
    s.close()
