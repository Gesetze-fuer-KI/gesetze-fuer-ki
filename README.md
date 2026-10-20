<p align="center">
  <img alt="Logo von Gesetze für KI" src=".github/readme/logo.svg#gh-light-mode-only" width="110">
  <img alt="Logo von Gesetze für KI" src=".github/readme/logo-dunkel.svg#gh-dark-mode-only" width="110">
</p>

<h1 align="center"><a href="https://gesetze-fuer-ki.de">Gesetze für KI</a></h1>

<p align="center"><b>Ihr KI-Assistent schlägt das aktuelle Bundes- und Landesrecht nach. Kostenlos.</b></p>

<p align="center">
  Alles zum Einrichten und Benutzen steht auf <b><a href="https://gesetze-fuer-ki.de">gesetze-fuer-ki.de</a></b>:<br>
  <a href="https://gesetze-fuer-ki.de/verbinden/"><b>So verbinden Sie Ihren Assistenten</b></a>
</p>

<p align="center">
  <a href="https://github.com/Gesetze-fuer-KI/gesetze-fuer-ki/actions/workflows/tests.yml"><img alt="Tests" src="https://github.com/Gesetze-fuer-KI/gesetze-fuer-ki/actions/workflows/tests.yml/badge.svg"></a>
  <a href="https://liberapay.com/GesetzeFuerKI"><img alt="Über Liberapay unterstützen" src="https://img.shields.io/badge/Liberapay-unterst%C3%BCtzen-F6C915?logo=liberapay&logoColor=black"></a>
  <a href="LICENSE"><img alt="Lizenz: AGPL v3" src="https://img.shields.io/badge/Lizenz-AGPL_v3-blue"></a>
</p>

---

<sub>Ab hier für Neugierige und alle, die mitmachen wollen.</sub>

## Wie es funktioniert

<img alt="Ablauf: Die amtlichen Texte von gesetze-im-internet.de werden jede Nacht in das Repository bundesrecht übernommen, eine Markdown-Datei je Gesetz mit jeder Änderung als Commit. Der Server gesetze-fuer-ki holt sie stündlich, baut den Suchindex und stellt sie über MCP bereit. Ihr KI-Assistent schlägt darüber den Wortlaut nach." src=".github/readme/ablauf.svg#gh-light-mode-only" width="100%">
<img alt="Ablauf: Die amtlichen Texte von gesetze-im-internet.de werden jede Nacht in das Repository bundesrecht übernommen, eine Markdown-Datei je Gesetz mit jeder Änderung als Commit. Der Server gesetze-fuer-ki holt sie stündlich, baut den Suchindex und stellt sie über MCP bereit. Ihr KI-Assistent schlägt darüber den Wortlaut nach." src=".github/readme/ablauf-dunkel.svg#gh-dark-mode-only" width="100%">

- **[`app/sync.py`](app/sync.py)** holt jede Nacht die geänderten Gesetze von gesetze-im-internet.de und wandelt sie mit [`app/convert.py`](app/convert.py) in Markdown um. Das läuft als Action im Repository **[bundesrecht](https://github.com/Gesetze-fuer-KI/bundesrecht)**, das die Dateien samt Historie enthält.
- **Landesrecht:** `sync.py --land BY` spiegelt das Portal eines Landes ([`app/sources/`](app/sources/), [`app/state_sync.py`](app/state_sync.py)) in dasselbe Format, jedes Land in ein eigenes Repository `landesrecht-<kürzel>` ([Bayern](https://github.com/Gesetze-fuer-KI/landesrecht-by), [Brandenburg](https://github.com/Gesetze-fuer-KI/landesrecht-bb), [Nordrhein-Westfalen](https://github.com/Gesetze-fuer-KI/landesrecht-nw), [Sachsen](https://github.com/Gesetze-fuer-KI/landesrecht-sn)). Die übrigen zwölf Länder erlauben den automatischen Abruf nicht (Bremen sperrt Abrufe aus Rechenzentren); warum, steht in ihren Repositories und auf [gesetze-fuer-ki.de/daten](https://gesetze-fuer-ki.de/daten/#landesrecht).
- **[`app/server.py`](app/server.py)** klont diese Repositories, baut daraus einen SQLite-Suchindex ([`app/store.py`](app/store.py)) und stellt die [fünf Werkzeuge](https://gesetze-fuer-ki.de/werkzeuge/) über MCP bereit. Frühere Fassungen liest [`app/repo.py`](app/repo.py) aus git.
- **[`docs/`](docs/)** ist die Webseite gesetze-fuer-ki.de; der Server liefert sie unter `/` mit aus.

## Selbst betreiben

```yaml
services:
  gesetze-fuer-ki:
    image: ghcr.io/gesetze-fuer-ki/gesetze-fuer-ki:0.1.4
    restart: unless-stopped
    volumes:
      - ./data:/data
    ports:
      - "8081:8081"
```

Der erste Start dauert einige Minuten (Klonen und Indizieren); danach meldet `/health` `"ready": true` und unter `states`, welche Länder vollständig sind. Für das Bundesrecht etwa 200 MB Arbeitsspeicher und 600 MB Platz, mit dem Landesrecht mehr. Einstellbar über `GESETZE_REPO_URL`, `GESETZE_REPO_BRANCH`, `STATE_REPO_URL` (`{code}` steht für das Länderkürzel; leer: nur Bundesrecht), `REFRESH_SECONDS`, `DATA_DIR`, `ALLOWED_HOSTS` und `PORT`.

## Mitmachen

```bash
cd app
uv sync --all-groups
uv run pytest -q                                            # Tests
uv run python sync.py --out /tmp/gesetze --only estg gewo   # ein paar Gesetze laden
uv run python sync.py --land SN --out /tmp/landesrecht-sn --max-minutes 5   # Landesrecht, Teil eines Durchgangs
```

- **Sprache:** Code, Kommentare und Commits sind Englisch; alles, was Nutzer sehen (Webseite, Werkzeugnamen und -beschreibungen, Antworten), ist Deutsch und für Nicht-Juristen geschrieben.
- **Das Markdown-Format ist ein Vertrag** zwischen `convert.py` und dem Index. Eine Änderung schreibt alle 6.100 Dateien im Daten-Repository neu; bitte vorher in einem Issue besprechen.
- **Datenschutz:** Der Server protokolliert keine Inhalte von Anfragen. So steht es auf der [Datenschutzseite](https://gesetze-fuer-ki.de/datenschutz/), und so soll es bleiben.
- Weitere Befehle und Regeln stehen in [`CLAUDE.md`](CLAUDE.md). Fehler, Wünsche und Fragen bitte als [Issue](https://github.com/Gesetze-fuer-KI/gesetze-fuer-ki/issues).

## Lizenz

[AGPL-3.0 oder später](LICENSE), © 2026 Marcel Bruckner. Die Gesetzestexte des Bundes, von Nordrhein-Westfalen, Sachsen und Brandenburg sind als amtliche Werke gemeinfrei (§ 5 UrhG); für Bayern erlauben die Nutzungshinweise des Portals die uneingeschränkte Weiterverwendung.

---

<sub>Keine Rechtsberatung: Der Dienst liefert Gesetzestexte; maßgeblich ist die amtliche Fassung. · [Unterstützen](https://gesetze-fuer-ki.de/unterstuetzen/) · [Impressum](https://gesetze-fuer-ki.de/impressum/) · [Datenschutz](https://gesetze-fuer-ki.de/datenschutz/)</sub>
