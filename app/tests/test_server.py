from pathlib import Path

import server
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
