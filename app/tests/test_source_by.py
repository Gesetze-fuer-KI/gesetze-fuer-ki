import datetime
import io
import zipfile
from pathlib import Path

import httpx
import pytest

import sources
import state_sync
import store
from sources import by

FIXTURES = Path(__file__).parent / "fixtures" / "by"
D = datetime.date(2026, 10, 20)


def zipped(name: str, xml: bytes | None = None) -> bytes:
    """The portal's per-law ZIP: the XML under bayportalnorm/, plus a manifest."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "bayportalnorm+zip")
        z.writestr("META-INF/manifest.xml", "<manifest/>")
        z.writestr(f"bayportalnorm/{name}.xml", xml if xml is not None else (FIXTURES / f"{name}.xml").read_bytes())
    return buf.getvalue()


class Portal:
    """Serves the fixtures like gesetze-bayern.de: the hit list is paged per session (cookie).

    The listing fixtures are real pages, trimmed; their hit counts were edited to match.
    """

    def __init__(self, laws: dict[str, bytes] | None = None):
        self.laws = laws or {}
        self.requests: list[str] = []
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append(path)
        if path.startswith("/Search/Filter/NORMTYP/"):
            normtyp = path.rsplit("/", 1)[1]
            return httpx.Response(302, headers={"Location": "/Search/Hitlist",
                                                "Set-Cookie": f"filter={normtyp}; path=/"})
        if path in ("/Search/Hitlist", "/Search/Page/1", "/Search/Page/2"):
            normtyp = request.headers.get("cookie", "").partition("filter=")[2].split(";")[0]
            page = 2 if path.endswith("/2") else 1
            name = FIXTURES / f"hitlist-{normtyp}-{page}.html"
            if not name.exists():
                return httpx.Response(200, text="<p id=\"readable\">0 Treffer</p>")
            return httpx.Response(200, text=name.read_text(encoding="utf-8"))
        if path.startswith("/Content/Zip/"):
            abk = path.rsplit("/", 1)[1]
            if abk in self.laws:
                return httpx.Response(200, content=self.laws[abk], headers={"Content-Type": "application/zip"})
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=self.transport, follow_redirects=True)


def fetch(name: str, xml: bytes | None = None, today: datetime.date = D) -> state_sync.Fetched:
    portal = Portal({name: zipped(name, xml)})
    entry = state_sync.Entry(by.slug_for(name), f"{by.BASE}/Content/Document/{name}", "2026-05-01")
    with portal.client() as client:
        fetched = by.BySource().fetch(client, entry, today)
    assert fetched is not None
    return fetched


def test_registered():
    assert sources.SOURCES["by"]().code == "BY"


def test_slug():
    assert by.slug_for("BayBO") == "by-baybo"
    assert by.slug_for("BAY_2251_3_2_S") == "by-bay_2251_3_2_s"
    assert by.slug_for("Bay.X G") == "by-bay_x_g"


def test_list_laws_pages_through_gesetze_and_verordnungen():
    portal = Portal()
    with portal.client() as client:
        entries = by.BySource().list_laws(client)
    slugs = [e.slug for e in entries]
    assert len(entries) == 21 == len(set(slugs))
    assert "by-bayabmg" in slugs and "by-bayzweckvermg" in slugs and "by-bayabfzustv" in slugs
    # Verwaltungsvorschriften (NORMTYP vv) are never asked for.
    assert not any("vv" in p for p in portal.requests)
    abm = next(e for e in entries if e.slug == "by-bayabmg")
    assert abm.url == "https://www.gesetze-bayern.de/Content/Document/BayAbmG"
    assert abm.lastmod == "2015-08-01"


def test_list_laws_rejects_a_short_listing(monkeypatch):
    portal = Portal()
    original = portal.handle

    def drop_page_two(request):
        if request.url.path == "/Search/Page/2":
            return httpx.Response(200, text='<p id="readable">11 Treffer</p><div id="hitlist"><ul></ul></div>')
        return original(request)

    portal.transport = httpx.MockTransport(drop_page_two)
    with portal.client() as client, pytest.raises(ValueError, match="ges"):
        by.BySource().list_laws(client)


def test_fetch_baybo_front_and_units():
    f = fetch("BayBO")
    assert f.next_version_from is None
    assert f.front["land"] == "BY"
    assert f.front["abkuerzung"] == "BayBO"
    assert f.front["titel"] == "Bayerische Bauordnung"
    assert f.front["stand"] == "Text gilt ab: 01.05.2026"
    assert f.front["gilt_ab"] == "2026-05-01"
    assert f.front["quelle"] == "https://www.gesetze-bayern.de/Content/Document/BayBO"
    front, preamble, units = store.split_law(f.markdown)
    assert front["abkuerzung"] == "BayBO"
    assert "Stand: Text gilt ab: 01.05.2026" in preamble
    assert [(u.kind, u.unit_id, u.ebene, u.heading) for u in units[:4]] == [
        ("gliederung", "ersterteil", 1, "Erster Teil Allgemeine Vorschriften"),
        ("norm", "art1", None, "Art. 1 Anwendungsbereich"),
        ("norm", "art2", None, "Art. 2 Begriffe"),
        ("norm", "art3", None, "Art. 3 Allgemeine Anforderungen"),
    ]
    ids = [u.unit_id for u in units]
    assert "dritterteil" in ids and "dritterteil-abschnitti" in ids  # ids follow the structure path
    assert units[-1].heading == "Anlage (nicht mehr belegt)" and units[-1].unit_id == "anlage"
    art1 = units[1].body
    assert art1.startswith("(1) ¹Dieses Gesetz gilt für alle baulichen Anlagen und Bauprodukte. ²Es gilt")
    assert "(2) Dieses Gesetz gilt nicht für\n\n- 1\\. Anlagen des öffentlichen Verkehrs" in art1
    art2 = next(u for u in units if u.unit_id == "art2").body
    assert "  - a) freistehende Gebäude mit einer Höhe bis zu 7 m" in art2  # nested list
    assert "400 m²" in art2


def test_known_article_is_found_by_designation():
    _, _, units = store.split_law(fetch("BayBO").markdown)
    hits = [u for u in units if u.kind == "norm" and store.split_enbez(u.heading)
            and store.norm_key(store.split_enbez(u.heading)) == store.norm_key("Art. 6")]
    assert len(hits) == 1
    assert hits[0].heading == "Art. 6 Abstandsflächen, Abstände"
    assert hits[0].body.startswith("(1) ¹")


def test_fetch_is_deterministic():
    assert fetch("BayBO").markdown.encode() == fetch("BayBO").markdown.encode()
    assert fetch("BayBhV").markdown.encode() == fetch("BayBhV").markdown.encode()


def test_verordnung_with_tables_annexes_and_eingangsformel():
    f = fetch("BayBhV")
    assert f.front["abkuerzung"] == "BayBhV"
    assert f.front["kurztitel"] == "Bayerische Beihilfeverordnung"
    assert f.front["titel"].startswith("Verordnung über die Beihilfefähigkeit von Aufwendungen")
    _, _, units = store.split_law(f.markdown)
    assert units[0].unit_id == "eingangsformel" and units[0].heading == "Eingangsformel"
    assert units[0].body.startswith("Auf Grund des Art. 86a Abs. 5 Satz 1")
    p12a = next(u for u in units if u.heading.startswith("§ 12a"))
    assert p12a.unit_id == "par12a"
    assert "|  | Einzelbehandlung | Gruppenbehandlung |" in p12a.body
    schluss = next(u for u in units if u.heading == "Schlussformel")
    assert schluss.unit_id == "schlussformel"
    assert "**Bayerisches Staatsministerium der Finanzen**" in schluss.body
    anlagen = [u for u in units if u.heading.startswith("Anlage")]
    assert [u.unit_id for u in anlagen] == ["anlage1", "anlage2", "anlage6"]
    assert anlagen[0].heading.startswith("Anlage 1 (zu § 7 Abs. 1) Beihilfefähige Höchstbeträge")
    assert store.norm_key(store.split_enbez(anlagen[0].heading)) == "anlage1"
    assert "| GebüH-Nr. | Leistungsbeschreibung |" in anlagen[0].body
    assert "**I. Beamtinnen und Beamte**" in anlagen[2].body
    assert "**1. Zu § 3 Abs. 1 Nr. 2**" in anlagen[2].body


def test_law_without_abbreviation_and_with_footnotes():
    f = fetch("BayAlmG")
    assert f.front["abkuerzung"] == "BayAlmG"  # no amtliche Abkürzung: the portal's id
    assert f.front["kurztitel"] == "Almgesetz"
    assert f.front["titel"] == "Gesetz über den Schutz der Almen und die Förderung der Almwirtschaft"
    _, _, units = store.split_law(f.markdown)
    assert [u.unit_id for u in units][:5] == ["art1", "art2", "art3", "art4", "art5bis17"]
    last = units[-1]
    assert last.heading == "Art. 22"
    assert "> **Fußnote**" in last.body


def test_duplicate_designations_get_stable_suffixes():
    xml = (FIXTURES / "BayAlmG.xml").read_bytes().replace(b"<para.nr>Art. 2</para.nr>", b"<para.nr>Art. 1</para.nr>")
    _, _, units = store.split_law(fetch("BayAlmG", xml).markdown)
    assert [u.unit_id for u in units][:3] == ["art1", "art1-2", "art3"]


def test_portal_serves_only_the_current_version():
    # The portal has no future versions (Hilfe: "in aktueller Fassung"). A text that only
    # starts after today is not mirrored early: the runner keeps the old file until then.
    xml = (FIXTURES / "BayBO.xml").read_bytes().replace(b"<inkraft>2026-05-01</inkraft>",
                                                       b"<inkraft>2027-01-01</inkraft>")
    with pytest.raises(state_sync.NotYetInForce) as exc:
        fetch("BayBO", xml)
    assert exc.value.start == "2027-01-01"
    assert fetch("BayBO", xml, today=datetime.date(2027, 1, 1)).next_version_from is None


def test_hit_count_with_thousands_separator():
    total, entries = by.parse_hitlist('<p id="readable">1.476 Treffer in 1.476 Verwaltungsvorschriften</p>')
    assert total == 1476 and entries == []


def test_fetch_requests_the_zip():
    portal = Portal({"BayAlmG": zipped("BayAlmG")})
    entry = state_sync.Entry("by-bayalmg", f"{by.BASE}/Content/Document/BayAlmG")
    with portal.client() as client:
        by.BySource().fetch(client, entry, D)
    assert portal.requests == ["/Content/Zip/BayAlmG"]


def test_run_with_by_source(tmp_path):
    portal = Portal({"BayAlmG": zipped("BayAlmG")})
    code = state_sync.run(tmp_path, by.BySource(), ["by-bayalmg"], max_minutes=10, today=D,
                          transport=portal.transport)
    assert code == 0
    path = state_sync.state_law_path(tmp_path, "by-bayalmg")
    assert path.exists() and "land: BY" in path.read_text(encoding="utf-8")
    assert "- neu: BayAlmG (Gesetz über den Schutz der Almen" in \
        (tmp_path / ".sync" / "commit-message.txt").read_text(encoding="utf-8")


def test_footnote_marker_stays_in_the_text():
    _, _, units = store.split_law(fetch("BayAlmG").markdown)
    art19 = next(u for u in units if u.unit_id == "art19").body
    # The portal's text has no space after the marker either.
    assert "*Art. 167 bis 176 des Wassergesetzes*³⁾mit der Maßgabe" in art19
    assert art19.endswith("> **Fußnote**\n>\n> 3) Nunmehr Art. 76 bis 82 BayWG, BayRS 753-1-I")


def test_emphasis_keeps_spaces_outside_the_markers():
    xml = (FIXTURES / "BayAlmG.xml").read_bytes().replace(
        b'<span class="i">Art. 167 bis 176 des Wassergesetzes</span>', b'<span class="i">Art. 167 </span>bis 176')
    _, _, units = store.split_law(fetch("BayAlmG", xml).markdown)
    assert "Vorschriften der *Art. 167* bis 176" in next(u for u in units if u.unit_id == "art19").body
