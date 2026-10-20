import datetime
import json
from pathlib import Path

import httpx
import pytest

import sources
import state_sync
import store
from sources import nw

FIXTURES = Path(__file__).parent / "fixtures" / "nw"
D = datetime.date(2026, 10, 20)
# The fixture laws: taxonomy term (the slug's id) -> URL path of the version the index holds.
PATHS = {
    "31127": "/lrgv/gesetz/16102026-studierendenwerksgesetz-stwg",
    "26520": "/lrgv/rechtsverordnung/16102026-landeswahlordnung",
    "32868": "/lrgv/rechtsverordnung/08092026-vergabeverordnung-nrw-vergabevo-nrw",
    "26486": "/lrgv/gesetz/16012026-verfassung-fuer-das-land-nordrhein-westfalen",
}
LASTMOD = {"31127": "2026-10-16", "26520": "2026-10-16", "32868": "2026-09-08", "26486": "2026-01-16"}


def page(term: str) -> str:
    return (FIXTURES / f"{term}.html").read_text(encoding="utf-8")


class Portal:
    """Serves the fixtures like recht.nrw.de: the search index behind /search-middleware, version pages under /lrgv/.

    Version pages answer a Range request with the first bytes (206), as the portal does.
    """

    def __init__(self, pages: dict[str, str] | None = None, listing: dict | None = None,
                 index: dict[str, dict] | None = None):
        self.pages = pages if pages is not None else {p: page(t) for t, p in PATHS.items()}
        self.listing = listing or json.loads((FIXTURES / "suche.json").read_text(encoding="utf-8"))
        self.index = index or json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))
        self.requests: list[str] = []
        self.queries: list[dict] = []
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/search-middleware/opensearch_internet/_search":
            query = json.loads(request.content)
            self.queries.append(query)
            if query.get("track_total_hits"):
                self.requests.append("POST listing")
                return httpx.Response(200, json=self.listing)
            url = query["query"]["bool"]["filter"][0]["term"]["url"]
            self.requests.append(f"POST index {url}")
            hits = [{"_source": self.index[url]}] if url in self.index else []
            return httpx.Response(200, json={"hits": {"total": {"value": len(hits), "relation": "eq"}, "hits": hits}})
        text = self.pages.get(path.rstrip("/"))
        if request.method == "GET" and path.endswith("/") and text is not None:
            byte_range = request.headers.get("range")
            self.requests.append(f"GET {path}" + (f" {byte_range}" if byte_range else ""))
            if byte_range:
                end = int(byte_range.removeprefix("bytes=0-"))
                return httpx.Response(206, content=text.encode()[:end + 1])
            return httpx.Response(200, text=text)
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=self.transport, follow_redirects=True)


def fetch(term: str, portal: Portal | None = None, today: datetime.date = D,
          lastmod: str | None = None) -> state_sync.Fetched | None:
    portal = portal or Portal()
    entry = state_sync.Entry(nw.slug_for(term), nw.BASE + PATHS[term], lastmod or LASTMOD[term])
    with portal.client() as client:
        return nw.NwSource().fetch(client, entry, today)


def units_of(term: str) -> list[store.Unit]:
    fetched = fetch(term)
    assert fetched is not None
    return store.split_law(fetched.markdown)[2]


def test_registered():
    assert sources.SOURCES["nw"]().code == "NW"


def test_slug():
    assert nw.slug_for("31127") == "nw-31127"


def test_list_laws_asks_the_index_for_gesetze_and_verordnungen_and_reads_each_law_id():
    portal = Portal()
    with portal.client() as client:
        entries = nw.NwSource().list_laws(client)
    by_slug = {e.slug: e for e in entries}
    assert sorted(by_slug) == ["nw-26486", "nw-26520", "nw-31127", "nw-32868"]
    stwg = by_slug["nw-31127"]
    assert stwg.url == "https://recht.nrw.de/lrgv/gesetz/16102026-studierendenwerksgesetz-stwg"
    assert stwg.lastmod == "2026-10-16"
    assert by_slug["nw-26486"].lastmod == "2026-01-16"
    # Only Gesetze and Verordnungen, in force, not historical; never Verwaltungsvorschriften.
    listing = portal.queries[0]
    filters = listing["query"]["bool"]["filter"]
    assert {"terms": {"field_document_type_name": ["Gesetz", "Rechtsverordnung", "Verordnung"]}} in filters
    assert "Verwaltungsvorschrift" not in json.dumps(listing)
    assert {"bool": {"must_not": {"term": {"field_historically": {"value": True}}}}} in filters
    # One query, then the first bytes of every version page for its law id.
    assert portal.requests[0] == "POST listing"
    assert sorted(portal.requests[1:]) == sorted(f"GET {p}/ bytes=0-8191" for p in PATHS.values())


def test_list_laws_rejects_a_short_answer():
    listing = json.loads((FIXTURES / "suche.json").read_text(encoding="utf-8"))
    listing["hits"]["total"]["value"] = 5
    portal = Portal(listing=listing)
    with portal.client() as client, pytest.raises(ValueError, match="5 hits announced, 4 returned"):
        nw.NwSource().list_laws(client)


def test_list_laws_rejects_other_document_types():
    listing = json.loads((FIXTURES / "suche.json").read_text(encoding="utf-8"))
    listing["hits"]["hits"][0]["_source"]["field_document_type_name"] = ["Verwaltungsvorschrift"]
    portal = Portal(listing=listing)
    with portal.client() as client, pytest.raises(ValueError, match="Verwaltungsvorschrift"):
        nw.NwSource().list_laws(client)


def test_list_laws_fails_when_a_law_id_cannot_be_read():
    pages = {p: page(t) for t, p in PATHS.items()}
    pages[PATHS["26520"]] = pages[PATHS["26520"]].replace('rel="canonical"', 'rel="shortlink"')
    portal = Portal(pages=pages)
    with portal.client() as client, pytest.raises(ValueError, match="no canonical link"):
        nw.NwSource().list_laws(client)
    del pages[PATHS["26520"]]
    portal = Portal(pages=pages)
    with portal.client() as client, pytest.raises(httpx.HTTPStatusError):
        nw.NwSource().list_laws(client)


def test_a_law_without_a_term_is_named_after_its_page():
    # Two laws had no taxonomy term on 2026-10-20: their page is its own canonical link.
    pages = {p: page(t) for t, p in PATHS.items()}
    pages[PATHS["26520"]] = pages[PATHS["26520"]].replace(
        "https://recht.nrw.de/taxonomy/term/26520", nw.BASE + PATHS["26520"])
    portal = Portal(pages=pages)
    with portal.client() as client:
        slugs = {e.slug for e in nw.NwSource().list_laws(client)}
    assert "nw-16102026-landeswahlordnung" in slugs and "nw-26520" not in slugs
    pages[PATHS["26520"]] = page("26520").replace("https://recht.nrw.de/taxonomy/term/26520", "https://example.org/")
    portal = Portal(pages=pages)
    with portal.client() as client, pytest.raises(ValueError, match="neither the law nor the page"):
        nw.NwSource().list_laws(client)


def test_two_indexed_versions_of_one_law_give_one_entry_the_newer():
    listing = json.loads((FIXTURES / "suche.json").read_text(encoding="utf-8"))
    old = json.loads(json.dumps(listing["hits"]["hits"][0]))
    old["_source"]["url"] = ["/lrgv/rechtsverordnung/14071994-landeswahlordnung"]
    old["_source"]["field_effective_from"] = [774187200]  # 1994-07-14
    listing["hits"]["hits"].append(old)
    listing["hits"]["total"]["value"] = 5
    pages = {p: page(t) for t, p in PATHS.items()}
    pages["/lrgv/rechtsverordnung/14071994-landeswahlordnung"] = page("26520")
    portal = Portal(pages=pages, listing=listing)
    with portal.client() as client:
        entries = nw.NwSource().list_laws(client)
    assert len(entries) == 4
    assert next(e for e in entries if e.slug == "nw-26520").url.endswith("/16102026-landeswahlordnung")


def test_fetch_stwg():
    fetched = fetch("31127")
    assert fetched is not None
    assert fetched.front == {
        "land": "NW",
        "abkuerzung": "StWG",
        "titel": "Gesetz über die Studierendenwerke im Land Nordrhein-Westfalen",
        "kurztitel": "Studierendenwerksgesetz",
        "stand": "Fassung gültig ab 16.10.2026",
        "gilt_ab": "2026-10-16",
        "naechste_fassung_ab": None,
        "quelle": "https://recht.nrw.de/lrgv/gesetz/16102026-studierendenwerksgesetz-stwg",
    }
    assert fetched.next_version_from is None
    front, _, units = store.split_law(fetched.markdown)
    assert front["abkuerzung"] == "StWG"
    assert [(u.kind, u.unit_id, u.heading) for u in units] == [
        ("norm", "eingangsformel", "Eingangsformel"),
        ("norm", "par1", "§ 1 Einrichtung von Anstalten des öffentlichen Rechts"),
        ("norm", "par2", "§ 2 Aufgaben"),
        ("norm", "par16", "§ 16 Inkrafttreten, Neubildung von Gremien"),
        ("norm", "schlussformel", "Schlussformel"),
    ]
    assert units[0].body.startswith("Vom 16. September 2014")
    par2 = units[2].body
    assert par2.startswith("(1) Die Studierendenwerke erbringen für die Studierenden Dienstleistungen")
    assert "\n\n1\\. die Errichtung, Bereitstellung und Unterhaltung" in par2  # not a Markdown list
    assert par2.endswith("> **Fußnote**\n>\n> GV. NRW. 2026 S. 695: Absatz 3 geändert und Absatz 6 angefügt "
                         "durch Artikel 1 des Gesetzes vom 6. Oktober 2026, in Kraft getreten am 16. Oktober 2026.")
    assert "Link kopiert" not in fetched.markdown and "Mehr" not in fetched.markdown.split("\n")


def test_a_paragraph_is_found_by_its_designation():
    units = units_of("31127")
    unit = next(u for u in units if u.kind == "norm" and store.norm_key(store.split_enbez(u.heading) or "")
                == store.norm_key("§ 2"))
    assert unit.unit_id == "par2"


def test_roman_gliederung_anlagen_and_notes_on_the_whole_law():
    fetched = fetch("26520")
    assert fetched is not None
    assert fetched.front["abkuerzung"] == "LWahlO"
    assert fetched.front["titel"] == "Landeswahlordnung"
    assert fetched.front["kurztitel"] is None
    units = store.split_law(fetched.markdown)[2]
    assert [(u.kind, u.unit_id, u.ebene, u.heading) for u in units] == [
        ("norm", "eingangsformel", None, "Eingangsformel"),
        ("gliederung", "i", 1, "I. Wahlorgane und Wahlbehörden"),
        ("norm", "par1", None, "§ 1 Kreiswahlleiter"),
        ("norm", "par2", None, "§ 2 Aufgaben des Bürgermeisters"),
        ("gliederung", "ii", 1, "II. Wählerverzeichnis und Wahlschein"),
        ("norm", "par9", None, "§ 9 Führung des Wählerverzeichnisses"),
        ("norm", "schlussformel", None, "Schlussformel"),
        ("norm", "anlage1", None, "Anlage 1"),
        ("norm", "anlage3", None, "Anlage 3"),
        ("norm", "anlage9a", None, "Anlage 9a"),
        ("norm", "anlage12b", None, "Anlage 12b"),
    ]
    formel = units[0].body
    assert formel.startswith("Vom 14. Juli 1994\n\nAufgrund des § 42 des Landeswahlgesetzes")
    assert "> Anlagen 1 bis 22 neu gefasst durch Verordnung vom 24. August 2016" in formel
    assert "Inhaltsübersicht" not in fetched.markdown  # the outline is the units
    assert units[6].body.startswith("Der Innenminister")
    assert units[9].body == ("Nur als PDF veröffentlicht: <https://recht.nrw.de/system/files/2026-05/"
                             "lrgv_lwahlo_anlage9a_stand-12.05.2026.pdf>")
    anlage = next(u for u in units if store.norm_key(store.split_enbez(u.heading) or "") == store.norm_key("Anlage 9a"))
    assert anlage.unit_id == "anlage9a"


def test_nested_gliederung():
    units = units_of("32868")
    assert [(u.kind, u.unit_id, u.ebene) for u in units if u.kind == "gliederung"] == [
        ("gliederung", "kapitel1", 1),
        ("gliederung", "kapitel2", 1),
        ("gliederung", "kapitel2-abschnitt1", 2),
        ("gliederung", "kapitel2-abschnitt2", 2),
        ("gliederung", "kapitel2-abschnitt2-unterabschnitt1", 3),
        ("gliederung", "kapitel2-abschnitt2-unterabschnitt2", 3),
        ("gliederung", "kapitel3", 1),
    ]
    ids = [u.unit_id for u in units]
    assert ids.index("kapitel2-abschnitt2-unterabschnitt1") < ids.index("par6") < ids.index(
        "kapitel2-abschnitt2-unterabschnitt2") < ids.index("par8")
    sub = next(u for u in units if u.unit_id == "kapitel2-abschnitt2-unterabschnitt1")
    assert sub.heading == "Unterabschnitt 1 Antragstellung, Verfahrensbeteiligung"
    assert [u.unit_id for u in units if u.unit_id.startswith("anlage")] == ["anlage1", "anlage4"]


def test_verfassung_artikel_and_unnumbered_articles():
    fetched = fetch("26486")
    assert fetched is not None
    # No abbreviation in the index and none in the title: the law id stands in.
    assert fetched.front["abkuerzung"] == "26486"
    units = store.split_law(fetched.markdown)[2]
    assert [(u.unit_id, u.heading) for u in units] == [
        ("eingangsformel", "Eingangsformel"),  # an unnamed first article
        ("art1", "Artikel 1"),
        ("art4", "Artikel 4"),
        ("ohnebezeichnung", "(ohne Bezeichnung)"),  # only the note that Art. 67a was repealed
        ("art93", "Artikel 93"),
    ]
    assert "**Präambel**" in units[0].body
    assert "| --- |" not in units[4].body and "|---|" in units[4].body  # a Markdown table
    art4 = next(u for u in units if store.norm_key(store.split_enbez(u.heading) or "") == store.norm_key("Art. 4"))
    assert art4.unit_id == "art4"


def test_deterministic():
    for term in PATHS:
        a, b = fetch(term), fetch(term)
        assert a is not None and b is not None
        assert a.markdown.encode() == b.markdown.encode()


def _future_stwg(older: bool = True) -> tuple[str, str]:
    """(path, page) of a made-up StWG version from 2027-01-01, listing today's version as older.

    No law on the portal had a version starting after today on 2026-10-20, so the newest StWG
    page is turned into one: its date moves to 01.01.2027 and its version list starts with it,
    followed by a link to the real page (if `older`).
    """
    path = "/lrgv/gesetz/01012027-studierendenwerksgesetz-stwg"
    text = page("31127")
    text = text.replace("16.10.2026\n", "01.01.2027\n", 1)
    assert "01.01.2027" in text
    start = text.index('<ul class="list-group editions-list ">')
    end = text.index("</ul>", start)
    items = '<li class="version-item latest-version"><span>vom 01.01.2027 <br />(aktuelle Seite)</span></li>'
    if older:
        items += f"<li class=\"version-item latest-version\"><a href='{PATHS['31127']}'>vom 16.10.2026</a></li>"
    return path, text[:start] + '<ul class="list-group editions-list ">' + items + text[end:]


def test_a_newer_version_from_a_later_date_returns_todays_text_and_its_start():
    path, text = _future_stwg()
    pages = {PATHS["31127"]: page("31127"), path: text}
    index = json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))
    index[path] = index[PATHS["31127"]]
    portal = Portal(pages=pages, index=index)
    entry = state_sync.Entry("nw-31127", nw.BASE + path, "2027-01-01")
    with portal.client() as client:
        fetched = nw.NwSource().fetch(client, entry, D)
    assert fetched is not None
    assert fetched.next_version_from == "2027-01-01"
    assert fetched.front["naechste_fassung_ab"] == "2027-01-01"
    assert fetched.front["gilt_ab"] == "2026-10-16"
    assert fetched.front["quelle"] == nw.BASE + PATHS["31127"]
    assert portal.requests == [f"POST index {path}", f"GET {path}/", f"GET {PATHS['31127']}/"]
    # On its start date the newer version is the text in force.
    with portal.client() as client:
        later = nw.NwSource().fetch(client, entry, datetime.date(2027, 1, 1))
    assert later is not None and later.front["gilt_ab"] == "2027-01-01" and later.next_version_from is None


def test_a_law_not_in_force_yet_waits():
    path, text = _future_stwg(older=False)
    index = {path: json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))[PATHS["31127"]]}
    portal = Portal(pages={path: text}, index=index)
    entry = state_sync.Entry("nw-31127", nw.BASE + path, "2027-01-01")
    with portal.client() as client, pytest.raises(state_sync.NotYetInForce) as exc:
        nw.NwSource().fetch(client, entry, D)
    assert exc.value.start == "2027-01-01"


def test_page_and_listing_must_agree_on_the_date():
    with pytest.raises(ValueError, match="listing says 2026-10-01"):
        fetch("31127", lastmod="2026-10-01")


def test_a_document_of_another_type_is_skipped():
    index = json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))
    index[PATHS["31127"]]["field_document_type_name"] = ["Verwaltungsvorschrift"]
    portal = Portal(index=index)
    assert fetch("31127", portal=portal) is None
    assert portal.requests == [f"POST index {PATHS['31127']}"]


def test_abbreviation_from_the_title():
    assert nw._abbreviation({}, "Weiterbildungs- und Prüfungsverordnung für Pflegeberufe (WBVO-Pflege-NRW)",
                            "30017") == "WBVO-Pflege-NRW"
    assert nw._abbreviation({}, "Verordnung über … (ECTS-Statistikverordnung – ECTS-VO)", "1") == "ECTS-VO"
    assert nw._abbreviation({}, "Gesetz über den Nordrhein-Westfalen-Plan für gute Infrastruktur 2025 bis 2036",
                            "34508") == "34508"
    assert nw._abbreviation({"field_abbreviation": ["StWG"]}, "Gesetz (X)", "1") == "StWG"


def test_run_end_to_end(tmp_path):
    portal = Portal()
    code = state_sync.run(tmp_path, nw.NwSource(), only=["nw-31127", "nw-32868"], max_minutes=10, today=D,
                          transport=portal.transport)
    assert code == 0
    assert state_sync.state_law_path(tmp_path, "nw-31127").exists()
    assert state_sync.state_law_path(tmp_path, "nw-32868").exists()
    message = (tmp_path / ".sync" / "commit-message.txt").read_text(encoding="utf-8")
    assert "- neu: StWG (Gesetz über die Studierendenwerke im Land Nordrhein-Westfalen)" in message
    assert "- neu: VergabeVO NRW (Verordnung über die Vergabe von Studienplätzen in Nordrhein-Westfalen)" in message


def test_a_warm_cache_spares_the_page_requests():
    portal = Portal()
    source = nw.NwSource()
    with portal.client() as client:
        first = source.list_laws(client)
    assert source.cache == {nw.BASE + p: t for t, p in PATHS.items()}
    portal.requests.clear()
    with portal.client() as client:
        second = source.list_laws(client)
    assert portal.requests == ["POST listing"]
    assert sorted((e.slug, e.url, e.lastmod) for e in second) == sorted((e.slug, e.url, e.lastmod) for e in first)


def test_the_cache_reads_new_urls_and_drops_unlisted_ones():
    source = nw.NwSource()
    stale = nw.BASE + "/lrgv/gesetz/01012025-gesetz-ueber-die-studierendenwerke-im-land-nordrhein-westfalen"
    source.cache = {nw.BASE + p: t for t, p in PATHS.items() if t != "32868"} | {stale: "31127"}
    portal = Portal()
    with portal.client() as client:
        entries = source.list_laws(client)
    assert portal.requests == ["POST listing", f"GET {PATHS['32868']}/ bytes=0-8191"]
    assert len(entries) == 4
    assert stale not in source.cache and source.cache[nw.BASE + PATHS["32868"]] == "32868"


def test_a_broken_listing_keeps_the_ids_it_has_read():
    pages = {p: page(t) for t, p in PATHS.items()}
    del pages[PATHS["26520"]]
    source = nw.NwSource()
    portal = Portal(pages=pages)
    with portal.client() as client, pytest.raises(httpx.HTTPStatusError):
        source.list_laws(client)
    assert source.cache == {nw.BASE + p: t for t, p in PATHS.items() if t != "26520"}


def test_a_page_without_a_law_body_is_refused():
    pages = {p: page(t) for t, p in PATHS.items()}
    pages[PATHS["31127"]] = pages[PATHS["31127"]].replace("field--field_body", "field--field_other")
    with pytest.raises(ValueError, match="no law body"):
        fetch("31127", portal=Portal(pages=pages))


def test_an_index_document_without_a_type_is_skipped():
    index = json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))
    index[PATHS["31127"]]["field_document_type_name"] = []
    assert fetch("31127", portal=Portal(index=index)) is None
