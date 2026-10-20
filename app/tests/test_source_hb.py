import datetime
import re
from pathlib import Path

import httpx
import pytest

import sources
import state_sync
import store
from sources import hb

FIXTURES = Path(__file__).parent / "fixtures" / "hb"
D = datetime.date(2026, 10, 20)
LAWS = ("410489", "270394", "232507", "192655", "344516")


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class Portal:
    """Serves the fixtures like transparenz.bremen.de.

    The listing is the Vorschriften search, filtered to "Gesetze und Rechtsverordnungen" in
    force, paged with skip/max; a law's page is /metainformationen/<title>-<version id>. The
    listing fixtures are two real hit pages trimmed to five hits (count edited to 5); the law
    pages are real, trimmed to some of their units.
    """

    def __init__(self, listing: dict[int, str] | None = None, laws: dict[str, str] | None = None):
        self.listing = listing if listing is not None else {0: read("liste-0.html"), 3: read("liste-3.html")}
        self.laws = laws if laws is not None else {doc: read(f"{doc}.html") for doc in LAWS}
        self.requests: list[str] = []
        self.params: list[dict[str, str]] = []
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append(path)
        if path == "/vorschriften-72741":
            params = dict(request.url.params)
            self.params.append(params)
            page = self.listing.get(int(params["skip"]))
            return httpx.Response(200, text=page) if page else httpx.Response(404)
        m = re.fullmatch(r"/metainformationen/[a-z0-9-]+-(\d+)", path)
        if m and m[1] in self.laws and request.url.params.get("template") == "20_gp_ifg_meta_detail_d":
            return httpx.Response(200, text=self.laws[m[1]])
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=self.transport, follow_redirects=True)


@pytest.fixture(autouse=True)
def small_pages(monkeypatch):
    monkeypatch.setattr(hb, "PAGE_SIZE", 3)  # the fixtures hold three and two hits


def url(doc: str) -> str:
    return f"{hb.BASE}/metainformationen/gesetz-{doc}?asl=bremen203_tpgesetz.c.55340.de&template=20_gp_ifg_meta_detail_d"


SLUGS = {"410489": "hb-tariftvergabegbr", "270394": "hb-schulgbr", "232507": "hb-verfbr2019",
         "406160": "hb-kostobr", "332115": "hb-bgbr2010", "344516": "hb-athschulbacpobr2023", "192655": "hb-192655"}


def fetch(doc: str, html: str | None = None, today: datetime.date = D) -> state_sync.Fetched | None:
    portal = Portal(laws={doc: html if html is not None else read(f"{doc}.html")})
    with portal.client() as client:
        return hb.HbSource().fetch(client, state_sync.Entry(SLUGS[doc], url(doc)), today)


def units_of(doc: str) -> list[store.Unit]:
    fetched = fetch(doc)
    assert fetched is not None
    return store.split_law(fetched.markdown)[2]


def test_registered():
    source = sources.SOURCES["hb"]()
    assert source.code == "HB"
    assert source.crawl_delay == 0 and source.workers == 2


def test_slug():
    assert hb.slug_for("TariftVergabeGBR") == "hb-tariftvergabegbr"
    assert hb.slug_for("192655") == "hb-192655"


def test_list_laws_reads_every_page_and_resolves_each_version_once():
    portal = Portal()
    source = hb.HbSource()
    with portal.client() as client:
        entries = source.list_laws(client)
    assert [e.slug for e in entries] == ["hb-tariftvergabegbr", "hb-schulgbr", "hb-verfbr2019",
                                         "hb-192655", "hb-athschulbacpobr2023"]
    first = entries[0]
    assert first.url == ("https://www.transparenz.bremen.de/metainformationen/bremisches-gesetz-zur-sicherung-von-"
                         "tariftreue-sozialstandards-und-wettbewerb-bei-oeffentlicher-auftragsvergabe-tariftreue-und-"
                         "vergabegesetz-vom-24-november-2009-410489?asl=bremen203_tpgesetz.c.55340.de"
                         "&template=20_gp_ifg_meta_detail_d")
    assert first.lastmod == "2026-10-08/410489"  # Stand in the listing and the version's id
    # Only Gesetze und Rechtsverordnungen in force, sorted by title for a stable paging.
    assert portal.params[0]["vorschriften[0]"] == "Gesetze und Rechtsverordnungen"
    assert portal.params[0]["gltigkeit[0]"] == "In Kraft"
    assert portal.params[0]["sort"] == "titel" and portal.params[0]["order"] == "asc"
    assert [(p["skip"], p["max"]) for p in portal.params] == [("0", "3"), ("3", "3")]
    # The slug needs the law's page (the listing knows only the version): each is requested once ...
    assert len(portal.requests) == 2 + 5
    assert source.cache == {"410489": "hb-tariftvergabegbr", "270394": "hb-schulgbr",
                            "232507": "hb-verfbr2019", "192655": "hb-192655", "344516": "hb-athschulbacpobr2023"}
    # ... and kept for fetch, which then needs no request of its own.
    fetched = source.fetch(client, first, D)
    assert fetched is not None and fetched.front["abkuerzung"] == "TariftVergabeG BR"
    assert len(portal.requests) == 7


def test_list_laws_uses_the_cache_and_forgets_unlisted_versions():
    portal = Portal()
    source = hb.HbSource()
    source.cache = {"410489": "hb-tariftvergabegbr", "270394": "hb-schulgbr", "232507": "hb-verfbr2019",
                    "192655": "hb-192655", "344516": "hb-athschulbacpobr2023", "186596": "hb-tariftvergabegbr"}
    with portal.client() as client:
        entries = source.list_laws(client)
        assert len(entries) == 5
        assert portal.requests == ["/vorschriften-72741"] * 2  # no law page
        assert "186596" not in source.cache  # an earlier version, no longer listed
        # Without a page kept from the listing, fetch requests it.
        assert source.fetch(client, entries[1], D) is not None
    assert len(portal.requests) == 3


def test_list_laws_rejects_a_count_mismatch():
    listing = {0: read("liste-0.html").replace("von (5)", "von (6)"), 3: read("liste-3.html").replace("von (5)", "von (6)")}
    with Portal(listing=listing).client() as client, pytest.raises(ValueError, match="6"):
        hb.HbSource().list_laws(client)
    listing = {0: read("liste-0.html"), 3: read("liste-3.html").replace("von (5)", "von (7)")}
    with Portal(listing=listing).client() as client, pytest.raises(ValueError, match="page"):
        hb.HbSource().list_laws(client)
    with Portal(listing={0: "<p>Fehler</p>"}).client() as client, pytest.raises(ValueError, match="count"):
        hb.HbSource().list_laws(client)


def test_list_laws_rejects_other_document_types():
    listing = {0: read("liste-0.html").replace("<span>Gesetze und Rechtsverordnungen</span>",
                                               "<span>Verwaltungsvorschriften</span>", 1), 3: read("liste-3.html")}
    with Portal(listing=listing).client() as client, pytest.raises(ValueError, match="Verwaltungsvorschriften"):
        hb.HbSource().list_laws(client)


def test_list_laws_rejects_two_versions_of_one_law():
    source = hb.HbSource()
    source.cache = {"410489": "hb-tariftvergabegbr", "270394": "hb-tariftvergabegbr", "232507": "hb-verfbr2019",
                    "192655": "hb-192655", "344516": "hb-athschulbacpobr2023"}
    with Portal().client() as client, pytest.raises(ValueError, match="hb-tariftvergabegbr"):
        source.list_laws(client)


def test_list_laws_fails_on_an_unreachable_law_page_but_keeps_what_it_resolved():
    laws = {doc: read(f"{doc}.html") for doc in LAWS if doc != "232507"}
    source = hb.HbSource()
    with Portal(laws=laws).client() as client, pytest.raises(httpx.HTTPStatusError):
        source.list_laws(client)
    assert "232507" not in source.cache and source.cache["410489"] == "hb-tariftvergabegbr"


def test_fetch_tariftreue_front_units_and_next_version():
    f = fetch("410489")
    assert f is not None
    assert f.front == {
        "land": "HB",
        "abkuerzung": "TariftVergabeG BR",
        "titel": "Bremisches Gesetz zur Sicherung von Tariftreue, Sozialstandards und Wettbewerb bei "
                 "öffentlicher Auftragsvergabe",
        "kurztitel": "Tariftreue- und Vergabegesetz",
        "stand": "§§ 2 und 21 geändert sowie §§ 5, 6 und 7 neu gefasst durch Artikel 1 des Gesetzes vom "
                 "29.09.2026 (Brem.GBl. S. 657), gültig ab 02.10.2026",
        "gilt_ab": "2026-10-02",
        "naechste_fassung_ab": "2030-01-01",
        "quelle": url("410489"),
    }
    # This version applies until 31.12.2029; the portal lists one from 01.01.2030.
    assert f.next_version_from == "2030-01-01"
    _, preamble, units = store.split_law(f.markdown)
    assert "Texte: Transparenzportal Bremen" in preamble and "CC BY-NC-ND" in preamble
    assert [(u.kind, u.unit_id, u.ebene, u.heading) for u in units[:5]] == [
        ("norm", "eingangsformel", None, "Eingangsformel"),
        ("gliederung", "abschnitt1", 1, "Abschnitt 1 Allgemeines"),
        ("norm", "par1", None, "§ 1 Zweck"),
        ("norm", "par2", None, "§ 2 Anwendungsbereich"),
        ("gliederung", "abschnitt2", 1, "Abschnitt 2 Anwendung von Vergaberegelungen"),
    ]
    assert units[0].body == "Der Senat verkündet das nachstehende, von der Bürgerschaft (Landtag) beschlossene Gesetz:"
    assert units[2].body.startswith("Dieses Gesetz regelt die Vergabe von öffentlichen Aufträgen")
    assert [u.unit_id for u in units][-3:] == ["abschnitt5", "par20", "par21"]
    par13 = next(u for u in units if u.unit_id == "par13")
    assert "\n\n- a) Zur Überprüfung" in par13.body  # a lettered list keeps its letters
    assert "Stand:" not in "\n".join(u.body for u in units)  # the Stand line heads the file only


def test_fetch_is_deterministic():
    assert fetch("410489").markdown == fetch("410489").markdown


def test_verfassung_nested_gliederungen_and_articles():
    f = fetch("232507")
    assert f.front["abkuerzung"] == "Verf BR 2019"
    assert f.front["titel"] == "Landesverfassung der Freien Hansestadt Bremen"
    assert f.front["kurztitel"] is None
    assert f.front["gilt_ab"] == "2024-06-25"  # no period on the page: the version's Inkrafttreten
    assert f.next_version_from is None
    units = store.split_law(f.markdown)[2]
    got = [(u.kind, u.unit_id, u.ebene, u.heading) for u in units]
    assert got[:4] == [
        ("norm", "eingangsformel", None, "Eingangsformel"),
        ("gliederung", "ersterhauptteil", 1, "Erster Hauptteil Grundrechte und Grundpflichten"),
        ("norm", "art1", None, "Artikel 1"),
        ("norm", "art2", None, "Artikel 2"),
    ]
    assert ("gliederung", "zweiterhauptteil-1abschnitt", 2, "1. Abschnitt Die Familie") in got
    assert ("gliederung", "dritterhauptteil-2abschnitt-i", 3, "I. Der Volksentscheid") in got
    assert ("gliederung", "uebergangsundschlussbestimmungen", 1, "Übergangs- und Schlussbestimmungen") in got
    hits = [u for u in units if u.kind == "norm" and store.split_enbez(u.heading)
            and store.norm_key(store.split_enbez(u.heading)) == store.norm_key("Art. 2")]
    assert len(hits) == 1 and hits[0].body.startswith("(1) Alle Menschen sind vor dem Gesetz gleich")


def test_footnotes_and_table_of_contents():
    f = fetch("270394")
    assert f.front["abkuerzung"] == "BremSchulG"
    assert f.front["titel"] == "Bremisches Schulgesetz"
    assert f.front["kurztitel"] is None  # "(BremSchulG)" is the abbreviation
    units = store.split_law(f.markdown)[2]
    assert "Inhaltsübersicht" not in f.markdown  # the table of contents is left out
    ids = [u.unit_id for u in units]
    assert ids[:6] == ["eingangsformel", "teil1", "par1", "teil2", "teil2-kapitel1", "par3"]
    par22 = next(u for u in units if u.unit_id == "par22")
    # The footnote marker on the heading is dropped, its note kept in the provision's body.
    assert par22.heading == "§ 22 Unterstützungseinrichtungen"
    assert par22.body.endswith("> **Fußnote**\n>\n> *) Gemäß § 69 Absatz 2 dieses Gesetzes tritt § 22 Absatz 5a "
                               "am 1. August 2030 außer Kraft.")


def test_title_footnote():
    f = fetch("332115")
    assert f.front["titel"] == "Bremisches Beamtengesetz" and f.front["abkuerzung"] == "BremBG"
    assert f.front["stand"] == "zuletzt geändert durch Gesetz vom 26.05.2026 (Brem.GBl. S. 407), gültig ab 01.07.2026"
    assert f.next_version_from == "2032-07-31"
    _, preamble, units = store.split_law(f.markdown)
    assert "*" not in preamble.split("\n")[0]  # the marker after the title is dropped
    # The note to the title follows the last provision, under its own heading.
    assert (units[-1].unit_id, units[-1].heading) == ("fussnoten", "Fußnoten")
    assert units[-1].body == ("> **Fußnote**\n>\n> *) Verkündet als Artikel 1 des Gesetzes zur Neuregelung des "
                              "Beamtenrechts in der Freien Hansestadt Bremen - Beamtenrechtsneuregelungsgesetz "
                              "(BremBNeuG) vom 22. Dezember 2009 (Brem.GBl. S. 17)")
    assert [u.unit_id for u in units] == ["abschnitt1", "par1", "par2", "fussnoten"]


def test_amtliche_abkuerzung_and_anlage_table():
    f = fetch("406160")
    assert f.front["abkuerzung"] == "AllKostV"
    assert f.front["titel"] == "Allgemeine Kostenverordnung"
    assert f.front["stand"] == "zuletzt geändert durch Verordnung vom 01.09.2026 (Brem.GBl. S. 652), gültig ab 30.09.2026"
    units = store.split_law(f.markdown)[2]
    assert [u.unit_id for u in units] == ["eingangsformel", "par1", "par2", "par3", "anlage"]
    assert "\n| " in units[-1].body  # the Kostenverzeichnis is a table


def test_documents_other_than_gesetze_and_verordnungen_are_skipped():
    assert fetch("344516") is None  # a Prüfungsordnung ("ohne Qualifikation")
    assert fetch("192655") is None  # an overview without a juris document


def test_a_version_not_yet_in_force():
    html = read("410489.html").replace("Gesamtausgabe in der Gültigkeit vom 02.10.2026", "Gesamtausgabe in der Gültigkeit vom 01.11.2026")
    with pytest.raises(state_sync.NotYetInForce) as exc:
        fetch("410489", html)
    assert exc.value.start == "2026-11-01"
    # On the day before the next version starts, it is still announced; on its start date it is not.
    assert fetch("410489", today=datetime.date(2029, 12, 31)).next_version_from == "2030-01-01"


def test_rejects_the_page_of_another_law():
    portal = Portal()
    with portal.client() as client, pytest.raises(ValueError, match="hb-schulgbr"):
        hb.HbSource().fetch(client, state_sync.Entry("hb-tariftvergabegbr", url("270394")), D)


def test_rejects_a_page_without_law_text():
    html = read("410489.html")
    broken = re.sub(r'<div class="jgwsAiZDoc" ', '<div class="other" ', html)
    with pytest.raises(ValueError, match="no law text"):
        fetch("410489", broken)
    # Many characters, no § or Artikel: a layout this parser does not know.
    long = html.replace("§ ", "Nr. ")
    with pytest.raises(ValueError, match="no § or Artikel"):
        fetch("410489", long)


def test_runner_syncs_through_the_portal(tmp_path):
    portal = Portal()
    code = state_sync.run(tmp_path, hb.HbSource(), ["hb-tariftvergabegbr", "hb-192655"], 10, D,
                          transport=portal.transport)
    assert code == 0
    assert (tmp_path / "ta" / "hb-tariftvergabegbr.md").exists()
    assert not list(tmp_path.glob("*/hb-192655.md"))  # skipped: no Gesetz
    # Seven requests: two listing pages and five law pages; fetch reused them.
    assert len(portal.requests) == 7
