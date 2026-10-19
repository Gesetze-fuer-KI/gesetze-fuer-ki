from pathlib import Path

import pytest

import store
from convert import convert

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
