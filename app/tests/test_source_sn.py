import datetime
import urllib.parse
from pathlib import Path

import httpx
import pytest

import sources
import state_sync
import store
from sources import sn

FIXTURES = Path(__file__).parent / "fixtures" / "sn"
D = datetime.date(2026, 10, 20)
TOKEN = "khcWwTS0T_mSH-xJaGIWZWZVrUibKXL3o9lC4euHe87SrhQLYWPNc0C7H5nb7-7h7pFkO-0zqWtM6MRJ108UdA"


class Portal:
    """Serves the fixtures like revosax.sachsen.de: the search lives in the session (cookie).

    The search form hands out a CSRF token; the hit list is posted once and then paged with GET.
    The listing fixtures are real pages, trimmed; their hit counts were edited to match.
    """

    def __init__(self, laws: dict[str, str] | None = None, pages: dict[int, str] | None = None):
        self.laws = laws or {}
        self.pages = pages or {n: (FIXTURES / f"suche-{n}.html").read_text(encoding="utf-8") for n in (1, 2)}
        self.requests: list[str] = []
        self.posted: dict[str, list[str]] = {}
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        query = f"?{request.url.query.decode()}" if request.url.query else ""
        self.requests.append(f"{request.method} {path}{query}")
        session = "session=s1" in request.headers.get("cookie", "")
        if path == "/vorschriftensuche":
            return httpx.Response(200, text=(FIXTURES / "vorschriftensuche.html").read_text(encoding="utf-8"),
                                  headers={"Set-Cookie": "session=s1; path=/"})
        if path == "/suche" and request.method == "POST":
            self.posted = urllib.parse.parse_qs(request.content.decode(), keep_blank_values=True)
            if not session or self.posted.get("authenticity_token") != [TOKEN]:
                return httpx.Response(422)
            return httpx.Response(200, text=self.pages[1])
        if path == "/suche" and request.method == "GET":
            page = int(request.url.params.get("seite", "1"))
            if not session or page not in self.pages:
                return httpx.Response(200, text="<h2>0 Treffer</h2>")
            return httpx.Response(200, text=self.pages[page])
        if path.startswith("/vorschrift/"):
            doc_id = path.rsplit("/", 1)[1]
            if doc_id in self.laws:
                return httpx.Response(200, text=self.laws[doc_id])
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=self.transport, follow_redirects=True)


def page(doc_id: str) -> str:
    return (FIXTURES / f"{doc_id}.html").read_text(encoding="utf-8")


def fetch(doc_id: str, html: str | None = None, today: datetime.date = D,
          lastmod: str | None = None) -> state_sync.Fetched | None:
    portal = Portal({doc_id: html if html is not None else page(doc_id)})
    entry = state_sync.Entry(sn.slug_for(doc_id), f"{sn.BASE}/vorschrift/{doc_id}", lastmod)
    with portal.client() as client:
        return sn.SnSource().fetch(client, entry, today)


def units_of(doc_id: str, html: str | None = None) -> list[store.Unit]:
    fetched = fetch(doc_id, html)
    assert fetched is not None
    return store.split_law(fetched.markdown)[2]


def test_registered():
    assert sources.SOURCES["sn"]().code == "SN"


def test_slug():
    assert sn.slug_for("20111") == "sn-20111"


def test_list_laws_searches_gesetze_and_verordnungen_and_pages_through():
    portal = Portal()
    with portal.client() as client:
        entries = sn.SnSource().list_laws(client)
    slugs = [e.slug for e in entries]
    assert len(entries) == 7 == len(set(slugs))
    assert "sn-12495" in slugs and "sn-10742" in slugs and "sn-21653" in slugs
    jagd = next(e for e in entries if e.slug == "sn-12495")
    assert jagd.url == "https://www.revosax.sachsen.de/vorschrift/12495"
    assert jagd.lastmod == "2026-10-17"
    assert next(e for e in entries if e.slug == "sn-10742").lastmod == "2026-09-16"
    # Only the types G and VO, no Mantelvorschriften, valid today; never Verwaltungsvorschriften.
    assert portal.posted["search_request[categories][]"] == ["G", "VO"]
    assert portal.posted["search_request[include_envelopes]"] == ["0"]
    assert portal.posted["search_request[valid_day_de]"] == [datetime.date.today().strftime("%d.%m.%Y")]
    assert portal.requests == ["GET /vorschriftensuche", "POST /suche", "GET /suche?seite=2"]


def test_list_laws_rejects_a_short_listing():
    pages = {1: (FIXTURES / "suche-1.html").read_text(encoding="utf-8"),
             2: (FIXTURES / "suche-2.html").read_text(encoding="utf-8").split('<div class="result_hit">')[0]
             + '<div class="result_hit"><a href="/vorschrift/21649-X">X</a><p>Vorschriftentyp: Verordnung<br>'
               "Fassung gültig ab: 16. September 2026</p></div>"}
    portal = Portal(pages=pages)
    with portal.client() as client, pytest.raises(ValueError, match="7 hits announced, 6 listed"):
        sn.SnSource().list_laws(client)


def test_list_laws_rejects_other_document_types():
    pages = {1: (FIXTURES / "suche-1.html").read_text(encoding="utf-8"),
             2: (FIXTURES / "suche-2.html").read_text(encoding="utf-8").replace(
                 "Vorschriftentyp: Verordnung", "Vorschriftentyp: Verwaltungsvorschrift", 1)}
    portal = Portal(pages=pages)
    with portal.client() as client, pytest.raises(ValueError, match="Verwaltungsvorschrift"):
        sn.SnSource().list_laws(client)


def test_fetch_richtergesetz_front_and_units():
    f = fetch("20111")
    assert f is not None and f.next_version_from is None
    assert f.front == {
        "land": "SN",
        "abkuerzung": "SächsRiG",
        "titel": "Sächsisches Gesetz über die Rechtsstellung der Richterinnen und Richter sowie "
                 "Staatsanwältinnen und Staatsanwälte",
        "kurztitel": "Sächsisches Richtergesetz",
        "stand": "Fassung gültig ab 01.01.2025",
        "gilt_ab": "2025-01-01",
        "naechste_fassung_ab": None,
        "quelle": "https://www.revosax.sachsen.de/vorschrift/20111",
    }
    front, preamble, units = store.split_law(f.markdown)
    assert front["abkuerzung"] == "SächsRiG" and "naechste_fassung_ab" not in front
    assert "Stand: Fassung gültig ab 01.01.2025" in preamble
    assert [(u.kind, u.unit_id, u.ebene, u.heading) for u in units[:4]] == [
        ("norm", "eingangsformel", None, "Eingangsformel"),
        ("gliederung", "abschnitt1", 1, "Abschnitt 1 Allgemeine Vorschriften"),
        ("norm", "par1", None, "§ 1 Grundsatz"),
        ("norm", "par2", None, "§ 2 Geltungsbereich"),
    ]
    ids = [u.unit_id for u in units]
    assert "abschnitt2" in ids and "abschnitt2-unterabschnitt1" in ids  # ids follow the structure path
    sub = next(u for u in units if u.unit_id == "abschnitt2-unterabschnitt1")
    assert (sub.ebene, sub.heading) == (2, "Unterabschnitt 1 Allgemeines")
    assert units[0].body.startswith("erlassen als Artikel 2 des Gesetzes zur Änderung des sächsischen Nachbar-")
    assert "**4. Juli 2023**" in units[0].body
    assert units[2].body == ("¹Die rechtsprechende Gewalt obliegt den Richterinnen und Richtern. "
                             "²Sie sind unabhängig und nur dem Gesetz unterworfen. "
                             "³Sie sprechen Recht im Namen des Volkes.")
    p6 = next(u for u in units if u.unit_id == "par6").body
    assert "Beurteilungswesens, insbesondere\n\n- 1\\. die Anlässe, insbesondere die Anlassbeurteilungen,\n" \
           "- 2\\. die Zeitpunkte," in p6
    assert p6.endswith("²Der Landesrichterrat sowie der Landesstaatsanwaltsrat sind anzuhören.")
    anlage = units[-1]
    assert (anlage.unit_id, anlage.heading) == ("anlage", "Anlage (zu § 5 Absatz 1)")
    assert "**Eintritt in den Ruhestand**" in anlage.body
    assert "| Geburtsjahrgang | Lebensalter |\n|---|---|\n" in anlage.body
    assert "| 1947 | 65 Jahre und 1 Monat |" in anlage.body


def test_footnote_marker_stays_in_the_text():
    p5 = next(u for u in units_of("20111") if u.unit_id == "par5").body
    assert "ist auf eigenen Antrag in den Ruhestand zu versetzen.¹⁾\n\n> **Fußnote**" in p5
    assert p5.endswith("> 1) § 5 geändert durch Artikel 8 Absatz 4 des Gesetzes vom 6. Juli 2023 "
                       "(SächsGVBl. S. 467) und durch Artikel 9 des Gesetzes vom 6. Juli 2023 (SächsGVBl. S. 467)")


def test_known_paragraph_is_found_by_designation():
    hits = [u for u in units_of("20111") if u.kind == "norm" and store.split_enbez(u.heading)
            and store.norm_key(store.split_enbez(u.heading)) == store.norm_key("§ 5")]
    assert len(hits) == 1
    assert hits[0].heading == "§ 5 Altersgrenze"
    assert hits[0].body.startswith("(1) ¹Die Richterin oder der Richter auf Lebenszeit")


def test_fetch_is_deterministic():
    for doc_id in ("20111", "12868", "3975", "21677"):
        assert fetch(doc_id).markdown.encode() == fetch(doc_id).markdown.encode()


def test_future_version_is_announced():
    f = fetch("12868")
    assert f.front["abkuerzung"] == "SächsWG"
    assert f.front["titel"] == "Sächsisches Wassergesetz" and f.front["kurztitel"] is None
    assert f.front["gilt_ab"] == "2025-07-10"
    assert f.next_version_from == "2027-01-01"
    assert f.front["naechste_fassung_ab"] == "2027-01-01"
    assert "naechste_fassung_ab: '2027-01-01'" in f.markdown
    units = store.split_law(f.markdown)[2]
    assert [(u.kind, u.unit_id, u.ebene) for u in units[:5]] == [
        ("norm", "eingangsformel", None),
        ("gliederung", "teil1", 1),
        ("norm", "par1", None),
        ("norm", "par2", None),
        ("gliederung", "teil2", 1),
    ]
    assert units[1].heading == "Teil 1 Allgemeine Bestimmungen"
    assert units[2].heading == "§ 1 Anwendungs- und Geltungsbereich (zu § 2 WHG)"
    assert "teil2-abschnitt1" in [u.unit_id for u in units]
    # The footnote on the date line of the Eingangsformel goes below it.
    assert "> 1) Zum Inkrafttreten siehe Artikel 17 des Gesetzes vom 12. Juli 2013" in units[0].body
    # On the start date the portal shows the new version; a page still showing the old one announces nothing.
    assert fetch("12868", today=datetime.date(2027, 1, 1)).next_version_from is None


def test_text_not_yet_in_force_waits():
    with pytest.raises(state_sync.NotYetInForce) as exc:
        fetch("12868", today=datetime.date(2025, 7, 9))
    assert exc.value.start == "2025-07-10"


def test_verfassung_with_artikel_and_praeambel():
    f = fetch("3975")
    assert f.front["abkuerzung"] == "Verfassung"  # the portal's short name, no amtliche Abkürzung
    assert f.front["titel"] == "Verfassung des Freistaates Sachsen"
    assert f.front["gilt_ab"] == "2014-01-01" and f.next_version_from is None
    units = store.split_law(f.markdown)[2]
    assert [(u.kind, u.unit_id, u.heading) for u in units[:4]] == [
        ("norm", "eingangsformel", "Eingangsformel"),
        ("norm", "praeambel", "Präambel"),
        ("gliederung", "1abschnitt", "1. Abschnitt Die Grundlagen des Staates"),
        ("norm", "art1", "Artikel 1 [Verfassungsgrundsätze]"),
    ]
    assert units[0].body.endswith("Der Sächsische Landtag hat als verfassungsgebende Landesversammlung am "
                                  "26. Mai 1992 die folgende Verfassung beschlossen:")
    assert units[1].body.startswith("**Anknüpfend an die Geschichte der Mark Meißen,**  \n**des sächsischen")
    art2 = next(u for u in units if u.unit_id == "art2")
    assert store.norm_key(store.split_enbez(art2.heading)) == "2"
    assert art2.body.startswith("(1) Die Hauptstadt des Freistaates ist Dresden.\n\n(2) Die Landesfarben")
    art122 = units[-1]
    assert art122.unit_id == "art122"
    assert art122.body.endswith("> **Fußnote**\n>\n> 4) Verkündet am 5. Juni 1992")


def test_verordnung_with_sections_in_a_wrapper():
    f = fetch("21677")
    assert f.front["abkuerzung"] == "SächsKomPauschVO"
    assert f.front["kurztitel"] == "Sächsische Kommunalpauschalenverordnung"
    assert f.front["titel"] == ("Verordnung des Sächsischen Staatsministeriums für Soziales, Gesundheit und "
                                "Gesellschaftlichen Zusammenhalt über die Gewährung einer Pauschale "
                                "für soziale Zwecke")
    units = store.split_law(f.markdown)[2]
    assert [u.unit_id for u in units] == ["eingangsformel", "par1", "par2", "anlagen"]
    assert units[1].body.startswith("(1) Gefördert werden\n\n- 1\\. regionale Pflegebudgets")
    assert "**Anlage 1**  \n**(zu § 7 Absatz 8 Satz 1)**" in units[3].body


def test_a_page_of_another_document_type_is_refused_not_skipped():
    # The listing only holds Gesetze and Verordnungen: another type on the page is an error
    # (kept file, retried), never a skip that would delete the law.
    html = page("21677").replace("Landesrecht Verordnung:", "Landesrecht Verwaltungsvorschrift:")
    with pytest.raises(ValueError, match="Verwaltungsvorschrift"):
        fetch("21677", html)
    html = page("21677").replace('name="description"', 'name="other"')
    with pytest.raises(ValueError, match="document type"):
        fetch("21677", html)


def test_duplicate_designations_get_stable_suffixes():
    html = page("20111").replace('<h4 class="centre">§\u00a02<br>', '<h4 class="centre">§\u00a01<br>')
    assert html != page("20111")
    ids = [u.unit_id for u in units_of("20111", html)]
    assert ids[2:4] == ["par1", "par1-2"]


def test_fetch_requests_the_law_page_only():
    portal = Portal({"3975": page("3975")})
    with portal.client() as client:
        sn.SnSource().fetch(client, state_sync.Entry("sn-3975", f"{sn.BASE}/vorschrift/3975"), D)
    assert portal.requests == ["GET /vorschrift/3975"]


def test_run_with_sn_source(tmp_path, monkeypatch):
    portal = Portal({"3975": page("3975")})
    monkeypatch.setattr(sn.SnSource, "list_laws",
                        lambda self, client: [state_sync.Entry("sn-3975", f"{sn.BASE}/vorschrift/3975", "2014-01-01")])
    code = state_sync.run(tmp_path, sn.SnSource(), ["sn-3975"], max_minutes=10, today=D, transport=portal.transport)
    assert code == 0
    path = state_sync.state_law_path(tmp_path, "sn-3975")
    assert path.exists() and "land: SN" in path.read_text(encoding="utf-8")
    assert "- neu: Verfassung (Verfassung des Freistaates Sachsen)" in \
        (tmp_path / ".sync" / "commit-message.txt").read_text(encoding="utf-8")


def test_footnote_on_a_gliederung_heading_keeps_it_a_gliederung():
    # Live case: the heading of SächsWG Teil 3 Abschnitt 5 carries a footnote ("Überschrift … geändert").
    units = units_of("12868")
    seq = [(u.kind, u.unit_id, u.ebene) for u in units]
    i = seq.index(("gliederung", "teil3", 1))
    assert seq[i:i + 5] == [
        ("gliederung", "teil3", 1),
        ("gliederung", "teil3-abschnitt4", 2),
        ("norm", "par58", None),
        ("gliederung", "teil3-abschnitt5", 2),
        ("norm", "par59", None),
    ]
    abschnitt5 = units[i + 3]
    assert abschnitt5.heading == "Abschnitt 5 Vorbeugender Gewässerschutz und Gewässerschutzbeauftragte"
    assert abschnitt5.body == ("> **Fußnote**\n>\n> 13) Überschrift Abschnitt 5 geändert durch Artikel 12 des "
                               "Gesetzes vom 20. Dezember 2022 (SächsGVBl. S. 705)")
    assert "> **Fußnote**" not in units[i + 4].body
    # Without the footnote the ids are the same.
    html = page("12868").replace('<a title="Überschrift Abschnitt 5', '<a data-x="1" title="Überschrift Abschnitt 5')
    html = html.replace('href="#FNID_13"><sup>13</sup></a>', "")
    assert html.count("FNID_13") == 1
    assert [u.unit_id for u in units_of("12868", html)] == [u.unit_id for u in units]


def test_gliederung_with_text_of_its_own_stays_a_gliederung():
    html = page("20111").replace("Allgemeine Vorschriften</h4>", "Allgemeine Vorschriften</h4><p>Vorbemerkung.</p>", 1)
    assert html != page("20111")
    units = units_of("20111", html)
    assert (units[1].kind, units[1].unit_id, units[1].body) == ("gliederung", "abschnitt1", "Vorbemerkung.")
    assert units[2].unit_id == "par1"


def test_page_newer_or_older_than_the_listing_is_refused():
    assert fetch("20111", lastmod="2025-01-01") is not None
    with pytest.raises(ValueError, match="2024-05-01"):
        fetch("20111", lastmod="2024-05-01")


def test_gliederung_named_with_an_ordinal_word_stays_a_gliederung():
    # "Zweiter Abschnitt" with text of its own: a Gliederung like "Abschnitt 2", not a norm.
    html = page("20111").replace("Allgemeine Vorschriften</h4>", "Allgemeine Vorschriften</h4><p>Vorbemerkung.</p>", 1)
    html = html.replace('<h4 class="centre">Abschnitt\u00a01', '<h4 class="centre">Erster Abschnitt', 1)
    assert html.count("Erster Abschnitt") == 1
    units = units_of("20111", html)
    assert (units[1].kind, units[1].unit_id, units[1].ebene) == ("gliederung", "ersterabschnitt", 1)
    assert units[1].body == "Vorbemerkung."
