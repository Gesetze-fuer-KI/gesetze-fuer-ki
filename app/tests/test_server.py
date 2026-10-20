import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

import server
import store
import sync
from convert import convert
from test_store import GELTUNG, MINI, _state_file, _state_law


def test_provision_url():
    law = {"quelle": "https://www.gesetze-im-internet.de/gg/"}
    assert server.provision_url(law, "Art 3") == "https://www.gesetze-im-internet.de/gg/art_3.html"
    assert server.provision_url(law, "§ 19a") == "https://www.gesetze-im-internet.de/gg/__19a.html"
    assert server.provision_url(law, "Anlage 2") == "https://www.gesetze-im-internet.de/gg/anlage_2.html"
    assert server.provision_url(law, None) == law["quelle"]


def test_split_parts_keeps_paragraphs_whole():
    body = "\n\n".join(["x" * 40] * 10)
    parts = server.split_parts(body, size=100)
    assert all(len(p) <= 100 for p in parts)
    assert "\n\n".join(parts) == body


def test_law_path_shards_by_first_two_characters():
    out = Path("/d")
    assert sync.law_path(out, "estg") == out / "es" / "estg.md"
    assert sync.law_path(out, "1-dm-goldm_nzg") == out / "0-9" / "1-dm-goldm_nzg.md"


def test_commit_message_lists_each_law():
    msg = sync.commit_message(
        [{"slug": "estg", "abkuerzung": "EStG", "stand": "zuletzt geändert durch X", "_new": False},
         {"slug": "neug", "abkuerzung": "NeuG", "titel": "Neues Gesetz", "_new": True}],
        ["altg"], [],
    )
    assert msg.splitlines()[0].endswith("1 geändert, 1 neu, 1 entfernt")
    assert "- EStG: zuletzt geändert durch X" in msg
    assert "- neu: NeuG (Neues Gesetz)" in msg
    assert "- entfernt: altg" in msg


def _git_repo(path: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_text(text, encoding="utf-8")
    for args in (["init", "-q", "-b", "main"], ["add", "-A"],
                 ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"]):
        subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def test_refresh_skips_missing_state_repo(tmp_path, monkeypatch):
    federal = tmp_path / "gesetze"
    _git_repo(federal, {"ab/abg.md": "---\nabkuerzung: AbG\ntitel: Abgesetz\nquelle: q\n---\n\n# Abgesetz\n"})
    monkeypatch.setattr(server, "DATA_REPO_URL", str(federal))
    monkeypatch.setattr(server, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(server, "STATE_REPO_URL", str(tmp_path / "missing-{code}"))
    monkeypatch.setattr(server, "INDEX", server.Index())
    server.refresh_once()
    s = server.INDEX.get()
    assert [r["slug"] for r in s.resolve_law("AbG")] == ["abg"]
    assert s.state_status() == {}
    assert server.INDEX.error is None


def test_clone_for():
    assert server.clone_for({"land": None}) == server.DATA_DIR / "bundesrecht"
    assert server.clone_for({"land": "BY"}) == server.DATA_DIR / "landesrecht-by"


def test_refresh_indexes_state_repo(tmp_path, monkeypatch):
    federal, by = tmp_path / "gesetze", tmp_path / "landesrecht-by"
    _git_repo(federal, {"ab/abg.md": "---\nabkuerzung: AbG\ntitel: Abgesetz\nquelle: q\n---\n\n# Abgesetz\n"})
    _git_repo(by, {"by/by-bayg.md": "---\nland: BY\nabkuerzung: BayG\ntitel: Bayerngesetz\nquelle: q\n---\n\n# B\n",
                   ".sync/state.json": '{"complete": true}'})
    monkeypatch.setattr(server, "DATA_REPO_URL", str(federal))
    monkeypatch.setattr(server, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(server, "STATE_REPO_URL", str(tmp_path / "landesrecht-{code}"))
    monkeypatch.setattr(server, "INDEX", server.Index())
    server.refresh_once()
    s = server.INDEX.get()
    assert s.state_status() == {"BY": True}
    law = dict(s.resolve_law("BayG")[0])
    assert law["land"] == "BY"
    assert (server.clone_for(law) / law["path"]).exists()
    assert server.INDEX.revision.count("+") == 1


def test_index_with_other_schema_is_rebuilt(tmp_path, monkeypatch):
    federal = tmp_path / "gesetze"
    _git_repo(federal, {"ab/abg.md": "---\nabkuerzung: AbG\ntitel: Abgesetz\nquelle: q\n---\n\n# Abgesetz\n"})
    rev = subprocess.run(["git", "-C", str(federal), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    data = tmp_path / "data"
    data.mkdir()
    # An index from before the current schema: same revision, no schema version.
    db = sqlite3.connect(data / "index.sqlite")
    db.executescript("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);")
    db.execute("INSERT INTO meta VALUES ('revision', ?)", (rev,))
    db.commit()
    db.close()
    monkeypatch.setattr(server, "DATA_REPO_URL", str(federal))
    monkeypatch.setattr(server, "DATA_DIR", data)
    monkeypatch.setattr(server, "STATE_REPO_URL", "")
    monkeypatch.setattr(server, "INDEX", server.Index())
    server.refresh_once()
    s = server.INDEX.get()
    assert s.meta("schema") == store.SCHEMA_VERSION
    assert [r["slug"] for r in s.resolve_law("AbG")] == ["abg"]


def test_failing_update_keeps_existing_state_clone(tmp_path, monkeypatch):
    federal, by = tmp_path / "gesetze", tmp_path / "landesrecht-by"
    _git_repo(federal, {"ab/abg.md": "---\nabkuerzung: AbG\ntitel: Abgesetz\nquelle: q\n---\n\n# Abgesetz\n"})
    _git_repo(by, {"by/by-bayg.md": "---\nland: BY\nabkuerzung: BayG\ntitel: Bayerngesetz\nquelle: q\n---\n\n# B\n",
                   ".sync/state.json": '{"complete": true}'})
    monkeypatch.setattr(server, "DATA_REPO_URL", str(federal))
    monkeypatch.setattr(server, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(server, "STATE_REPO_URL", str(tmp_path / "landesrecht-{code}"))
    monkeypatch.setattr(server, "INDEX", server.Index())
    server.refresh_once()
    revision = server.INDEX.revision
    shutil.rmtree(by)  # the remote is gone; the server's clone stays
    server.refresh_once()
    assert server.INDEX.revision == revision
    assert server.INDEX.get().state_status() == {"BY": True}


# ---- tools with state law ---------------------------------------------------------------------


def _federal_data(data: Path) -> None:
    (data / "m").mkdir(parents=True)
    md, _ = convert(MINI, "minig")
    (data / "m" / "minig.md").write_text(md, encoding="utf-8")
    (data / "ge").mkdir()
    (data / "ge" / "geltg.md").write_text(GELTUNG, encoding="utf-8")


def _serve(tmp_path, monkeypatch, states: dict[str, Path]) -> store.Store:
    data = tmp_path / "gesetze"
    _federal_data(data)
    db = tmp_path / "index.sqlite"
    store.build(data, db, "rev1", states=states)
    s = store.Store(db)
    monkeypatch.setattr(server, "DATA_DIR", tmp_path)
    monkeypatch.setattr(server, "INDEX", server.Index())
    server.INDEX.swap(s, "rev1")
    return s


@pytest.fixture
def srv(tmp_path, monkeypatch):
    by, nw = tmp_path / "landesrecht-by", tmp_path / "landesrecht-nw"
    _state_law(by, "BY", "by-minig", "MiniG", "Bayerisches Minigesetz", "Art. 1 Geltungsbereich",
               "Dieses Gesetz gilt in Bayern.")
    _state_file(by, complete=True)
    _state_law(nw, "NW", "nw-nwg", "NwG", "Nordrhein-westfälisches Gesetz", "§ 1 Geltungsbereich",
               "Dieses Gesetz gilt in Nordrhein-Westfalen.")
    _state_file(nw, complete=False)
    hb = tmp_path / "landesrecht-hb"
    _state_law(hb, "HB", "hb-brg", "BrG", "Bremisches Gesetz", "§ 1 Zweck", "Dieses Gesetz gilt in Bremen.")
    _state_file(hb, complete=True)
    s = _serve(tmp_path, monkeypatch, {"BY": by, "NW": nw, "HB": hb})
    yield s
    s.close()


def test_search_hints_at_state_hits(srv):
    out = server.search_laws("Geltungsbereich")
    assert "GeltG" in out and "by-minig" not in out
    assert "Auch im Landesrecht gibt es Treffer: Bayern (1). Mit land gezielt suchen." in out


def test_search_with_land_only_that_state(srv):
    out = server.search_laws("Geltungsbereich", land="Bayern")
    assert "by-minig" in out and "geltg" not in out and "Auch im Landesrecht" not in out


def test_search_in_law_without_land_finds_state_law(srv):
    out = server.search_laws("Geltungsbereich", law="by-minig")
    assert "by-minig" in out


def test_not_integrated_state(srv):
    out = server.search_laws("Schule", land="Hessen")
    assert "noch nicht integriert" in out and "kontakt@gesetze-fuer-ki.de" in out


def test_state_in_progress(srv):
    out = server.search_laws("x", land="NRW")
    assert "zum ersten Mal abgeglichen" in out and "https://recht.nrw.de" in out
    assert "https://recht.nrw.de." not in out


def test_unknown_land(srv):
    out = server.search_laws("x", land="Österreich")
    assert "„Österreich“ ist kein Bundesland" in out and "Bayern" in out


def test_land_scope(srv):
    assert server.land_scope(srv, None) == (None, None)
    assert server.land_scope(srv, "Freistaat Bayern") == ("BY", None)
    code, message = server.land_scope(srv, "SN")  # integrated, but no repository indexed yet
    assert code is None and "zum ersten Mal abgeglichen" in message


def test_find_law_tags_state_results(srv):
    out = server.find_law("MiniG")
    assert "`minig`" in out and "`by-minig`" in out and "[Bayern]" in out
    out = server.find_law("MiniG", land="BY")
    assert "`by-minig`" in out and "`minig`" not in out


def test_same_abbreviation_asks(srv):
    out = server.get_provision("MiniG", "§ 1")
    assert "mehrdeutig" in out and "Bayern" in out and "Bundesrecht" in out


def test_state_provision_labelled(srv):
    out = server.get_provision("MiniG", "§ 1", land="Bayern")
    assert "Landesrecht Bayern" in out and "Nichtamtliche Fassung" in out
    assert "Quelle: https://example.org/by-minig" in out


def test_state_attribution(srv):
    out = server.get_provision("BrG", "§ 1")
    assert "CC BY-NC-ND 3.0." in out
    assert "CC BY-NC-ND 3.0." in server.get_law_outline("BrG")


def test_federal_provision_unchanged(srv):
    out = server.get_provision("minig", "§ 1")
    assert "Landesrecht" not in out and "Nichtamtliche" not in out


def test_not_found_lists_contained_states(srv):
    out = server.get_provision("HBO", "§ 1")
    assert "Enthalten: Bundesrecht und Landesrecht aus Bayern und Bremen." in out
    assert "Im Aufbau: Brandenburg, Nordrhein-Westfalen und Sachsen." in out
    assert "Andere Länder fehlen noch (kontakt@gesetze-fuer-ki.de)." in out


def test_missing_provision_has_no_coverage_footer(srv):
    out = server.get_provision("GeltG", "§ 99")
    assert "nicht gefunden" in out and "Enthalten:" not in out


def test_federal_law_with_land_falls_back_to_federal(srv):
    out = server.get_provision("GeltG", "§ 1", land="Bayern")
    assert "Dieses Gesetz gilt für den Bund." in out and "Landesrecht" not in out
    assert "GeltG (Geltungsgesetz) – Bundesrecht (gilt auch in Bayern)" in out
    assert "– Bundesrecht (gilt auch in Bayern)" in server.get_law_outline("GeltG", land="BY")
    assert "Bundesrecht" not in server.get_provision("GeltG", "§ 1")


def test_law_not_found_in_state_names_the_state(srv):
    out = server.get_provision("HBO", "§ 1", land="Bayern")
    assert "Kein Gesetz zu „HBO“ im Landesrecht Bayern gefunden." in out and "gesetz_finden" in out


def test_no_hits_in_state_names_the_state(srv):
    out = server.search_laws("Mondfahrt", land="Bayern")
    assert "Keine Treffer für „Mondfahrt“ im Landesrecht Bayern." in out and "juristischere Begriffe" in out


def test_not_found_without_complete_states(tmp_path, monkeypatch):
    s = _serve(tmp_path, monkeypatch, {})
    out = server.find_law("Gibtsnicht")
    assert "Enthalten: nur Bundesrecht" in out and "Bayern" in out
    s.close()


def test_outline_with_land(srv):
    out = server.get_law_outline("MiniG", land="BY")
    assert "Landesrecht Bayern" in out and "Art. 1 Geltungsbereich" in out


def _commit(repo_dir: Path, date: str, message: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    for args in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message]):
        subprocess.run(["git", "-C", str(repo_dir), *args], check=True, capture_output=True, env=env)


@pytest.fixture
def srv_with_git(tmp_path, monkeypatch):
    by = tmp_path / "landesrecht-by"
    by.mkdir()
    subprocess.run(["git", "-C", str(by), "init", "-q", "-b", "main"], check=True, capture_output=True)
    _state_law(by, "BY", "by-minig", "MiniG", "Bayerisches Minigesetz", "Art. 1 Geltungsbereich", "Alter Text.")
    _state_file(by, complete=True)
    _commit(by, "2026-01-10T12:00:00+00:00", "Landesrecht Bayern\n\n- neu: MiniG (Bayerisches Minigesetz)")
    _state_law(by, "BY", "by-minig", "MiniG", "Bayerisches Minigesetz", "Art. 1 Geltungsbereich", "Neuer Text.")
    _commit(by, "2026-03-10T12:00:00+00:00", "Landesrecht Bayern\n\n- MiniG: geändert im März")
    s = _serve(tmp_path, monkeypatch, {"BY": by})
    yield s
    s.close()


def test_history_works_for_state_law(srv_with_git):
    assert "Neuer Text." in server.get_provision("MiniG", "Art. 1", land="BY")
    old = server.get_provision("MiniG", "Art. 1", date="2026-02-01", land="BY")
    assert "Alter Text." in old and "Landesrecht Bayern" in old
    changes = server.get_law_changes("MiniG", land="BY")
    assert "MiniG: geändert im März" in changes and "neu: MiniG" in changes


def test_health_reports_states(srv):
    response = asyncio.run(server.health(None))
    assert json.loads(response.body)["states"] == {"BY": True, "HB": True, "NW": False}


def test_search_in_federal_law_with_land(srv):
    assert "geltg" in server.search_laws("Geltungsbereich", law="GeltG", land="Bayern")


@pytest.mark.parametrize("land", ["Hessen", "NRW"])  # not integrated; integrated but still being built
def test_federal_law_with_a_state_without_index_falls_back_to_federal(srv, monkeypatch, land):
    name = {"Hessen": "Hessen", "NRW": "Nordrhein-Westfalen"}[land]
    out = server.get_provision("GeltG", "§ 1", land=land)
    assert "Dieses Gesetz gilt für den Bund." in out
    assert f"GeltG (Geltungsgesetz) – Bundesrecht (gilt auch in {name})" in out
    assert "Geltungsbereich" in server.get_law_outline("GeltG", land=land)
    assert "geltg" in server.search_laws("Geltungsbereich", law="GeltG", land=land)
    monkeypatch.setattr(server.repo, "changes", lambda *a: [])
    monkeypatch.setattr(server.repo, "first_date", lambda *a: "2026-01-01T00:00:00+00:00")
    assert f"Änderungen an GeltG (Geltungsgesetz) – Bundesrecht (gilt auch in {name})" in \
        server.get_law_changes("GeltG", land=land)
    # A law that is no federal law still gets the notice, and so does a search without law.
    assert ("noch nicht integriert" if land == "Hessen" else "zum ersten Mal abgeglichen") in \
        server.get_provision("HSchulG", "§ 1", land=land)
    assert ("noch nicht integriert" if land == "Hessen" else "zum ersten Mal abgeglichen") in \
        server.search_laws("Geltungsbereich", land=land)


def test_a_corrupt_state_clone_is_left_out(tmp_path, monkeypatch, caplog):
    federal, by = tmp_path / "gesetze", tmp_path / "landesrecht-by"
    _git_repo(federal, {"ab/abg.md": "---\nabkuerzung: AbG\ntitel: Abgesetz\nquelle: q\n---\n\n# Abgesetz\n"})
    _git_repo(by, {"by/by-bayg.md": "---\nland: BY\nabkuerzung: BayG\ntitel: Bayerngesetz\nquelle: q\n---\n\n# B\n",
                   ".sync/state.json": '{"complete": true}'})
    monkeypatch.setattr(server, "DATA_REPO_URL", str(federal))
    monkeypatch.setattr(server, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(server, "STATE_REPO_URL", str(tmp_path / "landesrecht-{code}"))
    monkeypatch.setattr(server, "INDEX", server.Index())
    server.refresh_once()
    shutil.rmtree(by)  # the remote is gone, and the clone is broken
    (tmp_path / "data" / "landesrecht-by" / ".git" / "HEAD").write_text("kaputt\n")
    server.refresh_once()
    s = server.INDEX.get()
    assert s.state_status() == {}
    assert [r["slug"] for r in s.resolve_law("AbG")] == ["abg"]
