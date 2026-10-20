import re

import pytest

import states


def test_all_sixteen_states_and_four_integrated():
    assert len(states.STATES) == 16
    assert {s.code for s in states.STATES.values() if s.integrated} == {"BY", "NW", "SN", "BB"}


def test_bremen_blocks_data_centres():
    hb = states.STATES["HB"]
    assert not hb.integrated and hb.reason == states.REASON_HB
    assert "Rechenzentren" in states.not_integrated_text(hb)


@pytest.mark.parametrize("text", ["BY", "by", "Bayern", "Freistaat Bayern"])
def test_find_bayern(text):
    assert states.find(text).code == "BY"


@pytest.mark.parametrize("text", ["NRW", "nrw", "NW", "Nordrhein-Westfalen"])
def test_find_nrw(text):
    assert states.find(text).code == "NW"


@pytest.mark.parametrize(
    "text, code",
    [
        ("Freie und Hansestadt Hamburg", "HH"),
        ("Freie Hansestadt Bremen", "HB"),
        ("Land Berlin", "BE"),
        ("BaWü", "BW"),
        ("Meck-Pomm", "MV"),
        ("Freistaat Thüringen", "TH"),
        ("Sachsen-Anhalt", "ST"),
        ("Sachsen", "SN"),
        ("  niedersachsen ", "NI"),
    ],
)
def test_find_aliases_and_prefixes(text, code):
    assert states.find(text).code == code


def test_find_unknown():
    assert states.find("Österreich") is None
    assert "Bayern" in states.unknown_text("Österreich")


def test_not_integrated_text_names_portal_and_contact():
    he = states.STATES["HE"]
    text = states.not_integrated_text(he)
    assert "noch nicht integriert" in text
    assert he.portal in text and "kontakt@gesetze-fuer-ki.de" in text


def test_not_integrated_text_links_the_state_repo():
    assert states.STATES["HE"].repo == "https://github.com/Gesetze-fuer-KI/landesrecht-he"
    assert states.STATES["HE"].repo in states.not_integrated_text(states.STATES["HE"])


def test_no_url_is_followed_by_a_period():
    # A client that links URLs would take the period into the link.
    for state in states.STATES.values():
        text = states.not_integrated_text(state)
        assert re.search(r"https?://\S*[.,;:]($|\s)", text) is None, text
        assert text.count("\n") >= 2  # each URL ends its line
    assert all(s.repo.endswith("landesrecht-" + s.code.lower()) for s in states.STATES.values())


def test_bremen_attribution_mentions_licence():
    assert "CC BY-NC-ND" in states.STATES["HB"].attribution
    assert all(s.attribution is None for s in states.STATES.values() if s.code != "HB")


def test_reasons_only_for_not_integrated():
    for s in states.STATES.values():
        assert (s.reason is None) == s.integrated
