import shutil
import sqlite3
import subprocess
from pathlib import Path

import server
import store
import sync


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
    assert server.clone_for({"land": None}) == server.DATA_DIR / "gesetze"
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
