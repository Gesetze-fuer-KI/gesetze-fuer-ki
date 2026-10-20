import datetime
import urllib.parse
from pathlib import Path

import httpx
import pytest

import sources
import state_sync
import store
from sources import bb

FIXTURES = Path(__file__).parent / "fixtures" / "bb"
D = datetime.date(2026, 10, 20)


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class Portal:
    """Serves the fixtures like bravors.brandenburg.de.

    The search form is posted and redirects to its result (kept in the session); the
    Fundstellennachweis has one page per Sachgebiet. The listing fixtures are real pages,
    trimmed (Sachgebiete 2-9 to three entries); the search's hit count was edited to match
    (102 in the Fundstellennachweis and the search's ten newest).
    """

    def __init__(self, laws: dict[str, str] | None = None, fna: dict[int, str] | None = None,
                 search: str | None = None, redirects: dict[str, str] | None = None):
        self.laws = laws or {}
        self.redirects = redirects or {}
        self.fna = fna or {n: read(f"fna-{n}.html") for n in range(1, 10)}
        self.search = search if search is not None else read("suche.html")
        self.requests: list[str] = []
        self.posted: dict[str, list[str]] = {}
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append(f"{request.method} {path}")
        if path == "/de/vorschriften_erweiterte_suche" and request.method == "POST":
            self.posted = urllib.parse.parse_qs(request.content.decode(), keep_blank_values=True)
            return httpx.Response(302, headers={"Location": "/de/vorschriften_erweiterte_suche/ergebnis",
                                                "Set-Cookie": "sixcms_project=s1; path=/"})
        if path == "/de/vorschriften_erweiterte_suche/ergebnis":
            if "sixcms_project=s1" not in request.headers.get("cookie", ""):
                return httpx.Response(200, text="<p>Keine Suche</p>")
            return httpx.Response(200, text=self.search)
        prefix = "/de/vorschriften_fundstellennachweis_gesetzte_und_verordnungen_sachgebietlich/sachgebiet/"
        if path.startswith(prefix):
            n = int(path.removeprefix(prefix))
            if n in self.fna:
                return httpx.Response(200, text=self.fna[n])
        if path in self.redirects:
            return httpx.Response(302, headers={"Location": self.redirects[path]})
        if path in self.laws:
            return httpx.Response(200, text=self.laws[path])
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=self.transport, follow_redirects=True)


PATHS = {"212792": "/de/gesetze-212792", "263411": "/verordnungen/kpangzv", "212897": "/gesetze/swg"}


def fetch(doc_id: str, html: str | None = None, path: str | None = None,
          source: bb.BbSource | None = None) -> state_sync.Fetched | None:
    path = path or PATHS[doc_id]
    portal = Portal({path: html if html is not None else read(f"{doc_id}.html")})
    with portal.client() as client:
        return (source or bb.BbSource()).fetch(client, state_sync.Entry(bb.slug_for(doc_id), bb.BASE + path), D)


def units_of(doc_id: str, html: str | None = None) -> list[store.Unit]:
    fetched = fetch(doc_id, html)
    assert fetched is not None
    return store.split_law(fetched.markdown)[2]


def test_registered():
    source = sources.SOURCES["bb"]()
    assert source.code == "BB"
    assert source.crawl_delay == 20 and source.workers == 1  # robots.txt: Crawl-delay: 20


def test_slug():
    assert bb.slug_for("212792") == "bb-212792"


def test_list_laws_reads_the_fundstellennachweis_without_vertraege():
    portal = Portal()
    with portal.client() as client:
        entries = bb.BbSource().list_laws(client)
    slugs = [e.slug for e in entries]
    assert len(entries) == 112 == len(set(slugs))
    assert slugs == sorted(slugs, key=lambda s: int(s.removeprefix("bb-")))  # ordered by id
    verfassung = next(e for e in entries if e.slug == "bb-212792")
    assert verfassung.url == "https://bravors.brandenburg.de/de/gesetze-212792" and verfassung.lastmod is None
    assert next(e for e in entries if e.slug == "bb-212897").url == "https://bravors.brandenburg.de/gesetze/swg"
    # The newest law is not in the Fundstellennachweis yet; the search's first page has it.
    newest = next(e for e in entries if e.slug == "bb-263411")
    assert newest.url == "https://bravors.brandenburg.de/verordnungen/kpangzv"
    assert "bb-212520" not in slugs  # a Vertrag (Vereinbarung zwischen Landtag und Landesregierung)
    assert all(e.lastmod is None for e in entries)  # no change signal: every pass fetches every law
    assert portal.posted["search[art_vorschrift][]"] == ["landesrecht"]  # Gesetze und Verordnungen
    assert portal.requests[:3] == ["POST /de/vorschriften_erweiterte_suche",
                                   "GET /de/vorschriften_erweiterte_suche/ergebnis",
                                   "GET /de/vorschriften_fundstellennachweis_gesetzte_und_verordnungen_sachgebietlich/sachgebiet/1"]
    assert len(portal.requests) == 11


def test_list_laws_tolerates_a_small_mismatch_with_the_search():
    # On 2026-10-20 the Fundstellennachweis listed 1,785 laws, the search counted 1,780.
    search = read("suche.html").replace("wurde in 112 Treffern", "wurde in 107 Treffern")
    with Portal(search=search).client() as client:
        assert len(bb.BbSource().list_laws(client)) == 112


def test_list_laws_rejects_a_missing_sachgebiet():
    fna = {n: read(f"fna-{n}.html") for n in range(1, 10)}
    fna[5] = fna[5].replace("<h3>5 ", "<h3>")
    with Portal(fna=fna).client() as client, pytest.raises(ValueError, match="Sachgebiet 5"):
        bb.BbSource().list_laws(client)
    del fna[5]
    with Portal(fna=fna).client() as client, pytest.raises(httpx.HTTPStatusError):
        bb.BbSource().list_laws(client)


def test_list_laws_rejects_a_listing_far_from_the_search_count():
    search = read("suche.html").replace("wurde in 112 Treffern", "wurde in 180 Treffern")
    with Portal(search=search).client() as client, pytest.raises(ValueError, match="180"):
        bb.BbSource().list_laws(client)
    with Portal(search="<p>Fehler</p>").client() as client, pytest.raises(ValueError, match="count"):
        bb.BbSource().list_laws(client)


def test_list_laws_rejects_unknown_document_kinds():
    fna = {n: read(f"fna-{n}.html") for n in range(1, 10)}
    fna[2] = fna[2].replace('<a href="/gesetze/log"', '<a href="/verwaltungsvorschriften/log"')
    with Portal(fna=fna).client() as client, pytest.raises(ValueError, match="/verwaltungsvorschriften/log"):
        bb.BbSource().list_laws(client)


def test_fetch_verfassung_front_and_units():
    f = fetch("212792")
    assert f is not None and f.next_version_from is None
    assert f.front == {
        "land": "BB",
        "abkuerzung": "212792",  # no abbreviation in the title
        "titel": "Verfassung des Landes Brandenburg",
        "kurztitel": None,
        "stand": "zuletzt geändert durch Gesetz vom 5. Juli 2022 (GVBl.I/22, [Nr. 19])",
        "gilt_ab": None,
        "naechste_fassung_ab": None,
        "quelle": "https://bravors.brandenburg.de/de/gesetze-212792",
    }
    front, preamble, units = store.split_law(f.markdown)
    assert "Stand: zuletzt geändert durch Gesetz vom 5. Juli 2022 (GVBl.I/22, [Nr. 19])" in preamble
    assert [(u.kind, u.unit_id, u.ebene, u.heading) for u in units[:5]] == [
        ("norm", "eingangsformel", None, "Eingangsformel"),
        ("norm", "praeambel", None, "Präambel"),
        ("gliederung", "1hauptteil", 1, "1. Hauptteil Grundlagen"),
        ("norm", "art1", None, "Artikel 1 (Land Brandenburg)"),
        ("norm", "art2", None, "Artikel 2 (Grundsätze der Verfassung)"),
    ]
    assert units[0].body.startswith("Der Landtag hat am 14. April 1992 den Entwurf einer Landesverfassung")
    assert "Inhaltsverzeichnis" not in f.markdown and "Artikel 113 Zuständigkeit" not in f.markdown  # no TOC
    assert units[1].body.startswith("Wir, die Bürgerinnen und Bürger des Landes Brandenburg")
    assert units[3].body == ("(1) Brandenburg ist ein Land der Bundesrepublik Deutschland.\n\n"
                             "(2) Das Land gliedert sich in Gemeinden und Gemeindeverbände.\n\n"
                             "(3) Die Landeshauptstadt ist Potsdam.")
    ids = [u.unit_id for u in units]
    # Gliederung ids follow the structure path; their level the order the kinds first appear in.
    assert ids[ids.index("2hauptteil"):ids.index("2hauptteil") + 3] == ["2hauptteil", "2hauptteil-1abschnitt", "art5"]
    sub = next(u for u in units if u.unit_id == "3hauptteil-7abschnitt")
    assert (sub.kind, sub.ebene, sub.heading) == ("gliederung", 2, "7. Abschnitt Übergangs- und Schlussbestimmungen")
    assert "art7a" in ids
    assert next(u for u in units if u.unit_id == "art114").heading == "Artikel 114 (aufgehoben)"
    assert units[-1].unit_id == "art117"


def test_known_article_is_found_by_designation():
    hits = [u for u in units_of("212792") if u.kind == "norm" and store.split_enbez(u.heading)
            and store.norm_key(store.split_enbez(u.heading)) == store.norm_key("Art. 7a")]
    assert len(hits) == 1
    assert hits[0].heading == "Artikel 7a (Schutz des friedlichen Zusammenlebens)"


def test_verordnung_with_abbreviation_and_signatures():
    f = fetch("263411")
    assert f.front["abkuerzung"] == "KPAnGZV"
    assert f.front["kurztitel"] == "Kraftstoffpreisanpassungsgesetz-Zuständigkeitsverordnung"
    assert f.front["titel"] == "Verordnung über Zuständigkeiten nach dem Kraftstoffpreisanpassungsgesetz"
    assert f.front["stand"] == "Ursprüngliche Fassung vom 16. Oktober 2026 (GVBl.II/26, [Nr. 47])"
    units = store.split_law(f.markdown)[2]
    assert [(u.unit_id, u.heading) for u in units] == [
        ("eingangsformel", "Eingangsformel"), ("par1", "§ 1 Zuständigkeiten"), ("par2", "§ 2 Inkrafttreten")]
    assert units[0].body.startswith("Auf Grund des § 6 Absatz 2 und 4 des Landesorganisationsgesetzes")
    assert units[1].body.startswith("(1) Das Landesamt für Ländliche Entwicklung")
    assert units[2].body.startswith("Diese Verordnung tritt am Tag nach der Verkündung in Kraft.\n\nPotsdam, den 16. Oktober 2026")


def test_gesetz_with_kurztitel_toc_and_anlage():
    f = fetch("212897")
    assert (f.front["abkuerzung"], f.front["kurztitel"]) == ("SWG", "Sorben/Wenden-Gesetz")
    assert f.front["stand"] == ("zuletzt geändert durch Artikel 5 Absatz 1 des Gesetzes vom 5. März 2024 "
                                "(GVBl.I/24, [Nr. 10], S.78)")
    units = store.split_law(f.markdown)[2]
    ids = [u.unit_id for u in units]
    assert ids[:4] == ["praeambel", "par1", "par2", "par3"]  # ids from the designation, not the anchor
    assert units[2].heading == "§ 2 Sorbische/Wendische Volkszugehörigkeit"
    assert "par4a" in ids and ids[-1] == "anlage"
    assert "Inhaltsübersicht" not in f.markdown


def test_ordered_lists_keep_their_numbers():
    html = read("263411.html").replace(
        "<p>Diese Verordnung tritt", "<ol><li>erstens,</li><li>zweitens.</li></ol><p>Diese Verordnung tritt", 1)
    par2 = units_of("263411", html)[2]
    assert par2.body.startswith("- 1\\. erstens,\n- 2\\. zweitens.\n\nDiese Verordnung tritt")


def test_footnote_to_the_title_follows_the_provisions():
    html = read("263411.html").replace(
        "<p>Potsdam, den 16. Oktober 2026</p>",
        '<p><a name="0"></a><sup>*</sup>&nbsp;Diese Verordnung dient der Umsetzung der Richtlinie X.</p>', 1)
    units = units_of("263411", html)
    assert (units[-1].unit_id, units[-1].heading) == ("fussnoten", "Fußnoten")
    assert units[-1].body.startswith("Diese Verordnung dient der Umsetzung der Richtlinie X.\n\nDie Landesregierung")
    assert "Diese Verordnung dient" not in units[2].body


def test_fetch_is_deterministic():
    for doc_id in PATHS:
        assert fetch(doc_id).markdown.encode() == fetch(doc_id).markdown.encode()


def test_duplicate_designations_get_stable_suffixes():
    html = read("263411.html").replace("&sect; 2<br />", "&sect; 1<br />", 1)
    assert [u.unit_id for u in units_of("263411", html)] == ["eingangsformel", "par1", "par1-2"]


def test_archived_law_is_skipped_without_caching():
    source = bb.BbSource()
    assert fetch("212627", read("archiv.html"), path="/gesetze/bbgbo", source=source) is None
    assert source.cache == {}  # asked again next pass: the listing should drop it


def test_other_document_kinds_are_skipped_for_good():
    source = bb.BbSource()
    assert fetch("212520", read("263411.html"), path="/de/vertraege-212520", source=source) is None
    assert source.cache == {"212520": bb.SKIPPED}
    with Portal().client() as client:
        assert "bb-212520" not in {e.slug for e in source.list_laws(client)}
    source.cache = {"212792": bb.SKIPPED}
    with Portal().client() as client:
        assert "bb-212792" not in {e.slug for e in source.list_laws(client)}


def test_page_without_law_text_is_refused():
    with pytest.raises(ValueError, match="no law text"):
        fetch("263411", "<html><body><p>Wartungsarbeiten</p></body></html>")


def test_run_with_bb_source_waits_the_crawl_delay(tmp_path, monkeypatch):
    portal = Portal({"/de/gesetze-212792": read("212792.html"), "/verordnungen/kpangzv": read("263411.html")})
    monkeypatch.setattr(bb.BbSource, "list_laws", lambda self, client: [
        state_sync.Entry("bb-212792", f"{bb.BASE}/de/gesetze-212792"),
        state_sync.Entry("bb-263411", f"{bb.BASE}/verordnungen/kpangzv")])
    slept: list[float] = []
    code = state_sync.run(tmp_path, bb.BbSource(), ["bb-212792", "bb-263411"], max_minutes=10, today=D,
                          sleep=slept.append, transport=portal.transport)
    assert code == 0
    assert slept == [20.0]  # two requests, one pause between them
    assert state_sync.state_law_path(tmp_path, "bb-212792") == tmp_path / "21" / "bb-212792.md"
    assert "land: BB" in (tmp_path / "21" / "bb-212792.md").read_text(encoding="utf-8")
    message = (tmp_path / ".sync" / "commit-message.txt").read_text(encoding="utf-8")
    assert "- neu: KPAnGZV (Verordnung über Zuständigkeiten nach dem Kraftstoffpreisanpassungsgesetz)" in message


def test_gliederung_named_with_an_ordinal_word():
    html = read("212792.html").replace("2. Abschnitt: <br />Freiheit", "Zweiter Abschnitt<br />Freiheit")
    assert html != read("212792.html")
    g = next(u for u in units_of("212792", html) if u.heading.startswith("Zweiter Abschnitt"))
    assert (g.kind, g.unit_id, g.ebene) == ("gliederung", "2hauptteil-zweiterabschnitt", 2)
    assert g.heading == "Zweiter Abschnitt Freiheit, Gleichheit und Würde"
    # "Allgemeiner Teil" at the top: the first kind seen is level 1.
    html = read("263411.html").replace('<h4 class="paragraph_bez"><a name="1">',
                                       '<h3>Allgemeiner Teil</h3><h4 class="paragraph_bez"><a name="1">', 1)
    units = units_of("263411", html)
    assert [(u.kind, u.unit_id, u.ebene) for u in units[1:3]] == [("gliederung", "allgemeinerteil", 1),
                                                                   ("norm", "par1", None)]


def test_law_page_redirecting_to_another_kind_is_skipped_for_good():
    portal = Portal({"/de/vertraege-212999": read("263411.html")}, redirects={"/verordnungen/x": "/de/vertraege-212999"})
    source = bb.BbSource()
    with portal.client() as client:
        assert source.fetch(client, state_sync.Entry("bb-212999", f"{bb.BASE}/verordnungen/x"), D) is None
    assert source.cache == {"212999": bb.SKIPPED}


def test_fundstellennachweis_url_wins_over_the_search():
    # A search hit with the Verfassung's id but another link: the Fundstellennachweis's link wins.
    search = read("suche.html").replace("<!-- 263392-->", "<!-- 212792-->", 1)
    with Portal(search=search).client() as client:
        entries = {e.slug: e for e in bb.BbSource().list_laws(client)}
    assert entries["bb-212792"].url == "https://bravors.brandenburg.de/de/gesetze-212792"


def test_long_text_without_any_provision_is_refused():
    body = "".join(f"<p>Satz {i} eines langen Textes ohne Paragraphen und Artikel.</p>" for i in range(60))
    html = read("263411.html")
    start, end = html.index('<h4 class="paragraph_bez">'), html.index("<p>Potsdam, den")
    with pytest.raises(ValueError, match="no § or Artikel"):
        fetch("263411", html[:start] + body + html[end:])
    short = html[:start] + "<p>Kurzer Text.</p>" + html[end:]
    assert fetch("263411", short) is not None
