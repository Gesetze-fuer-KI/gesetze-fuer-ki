<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/readme/logo-dunkel.svg">
    <img alt="Logo von Gesetze für KI: eine Waage, deren Säule das MCP-Zeichen bildet" src=".github/readme/logo.svg" width="110">
  </picture>
</p>

<h1 align="center"><a href="https://gesetze-fuer-ki.de">Gesetze für KI</a></h1>

<p align="center">
  <a href="https://gesetze-fuer-ki.de/"><img alt="Webseite" src="https://img.shields.io/badge/gesetze--fuer--ki.de-Anleitung-1f4e79"></a>
  <a href="https://github.com/Gesetze-fuer-KI/gesetze-fuer-ki/actions/workflows/tests.yml"><img alt="Tests" src="https://github.com/Gesetze-fuer-KI/gesetze-fuer-ki/actions/workflows/tests.yml/badge.svg"></a>
  <a href="https://github.com/Gesetze-fuer-KI/gesetze-fuer-ki/pkgs/container/gesetze-fuer-ki"><img alt="Container-Image" src="https://img.shields.io/badge/ghcr.io-gesetze--fuer--ki-2496ED?logo=docker&logoColor=white"></a>
  <a href="https://liberapay.com/GesetzeFuerKI"><img alt="Über Liberapay unterstützen" src="https://img.shields.io/badge/Liberapay-unterst%C3%BCtzen-F6C915?logo=liberapay&logoColor=black"></a>
  <a href="LICENSE"><img alt="Lizenz: AGPL v3" src="https://img.shields.io/badge/Lizenz-AGPL_v3-blue"></a>
</p>

<p align="center"><b>Der MCP-Server hinter gesetze-fuer-ki.de: das aktuelle Bundesrecht für KI-Assistenten.</b></p>

Claude, ChatGPT und andere Assistenten schlagen über diesen Server den Wortlaut von rund 6.100 Gesetzen und Verordnungen nach, statt aus dem Gedächtnis zu zitieren. Ohne Anmeldung, ohne Schlüssel:

```text
https://gesetze-fuer-ki.de/mcp
```

Wie man den eigenen Assistenten verbindet, steht auf **[gesetze-fuer-ki.de](https://gesetze-fuer-ki.de/verbinden/)**.

## So funktioniert es

<picture>
  <source media="(prefers-color-scheme: dark)" srcset=".github/readme/ablauf-dunkel.svg">
  <img alt="Ablauf: Die amtlichen Texte von gesetze-im-internet.de werden jede Nacht in das Repository gesetze übernommen, eine Markdown-Datei je Gesetz mit jeder Änderung als Commit. Der Server gesetze-fuer-ki holt sie stündlich, baut den Suchindex und stellt sie über MCP bereit. Ihr KI-Assistent schlägt darüber den Wortlaut nach." src=".github/readme/ablauf.svg" width="100%">
</picture>

- **`app/sync.py`** spiegelt gesetze-im-internet.de: Für jedes Gesetz aus `gii-toc.xml` fragt es das XML-Archiv mit dem letzten ETag an, wandelt geänderte mit **`app/convert.py`** in Markdown um und schreibt `<erste zwei Buchstaben>/<kennung>.md`. Ein vollständiger Lauf dauert etwa eine Minute, ein nächtlicher besteht aus rund 6.100 Antworten `304 Not Modified`.
- **[gesetze](https://github.com/Gesetze-fuer-KI/gesetze)** enthält das Ergebnis. Seine [Action](https://github.com/Gesetze-fuer-KI/gesetze/blob/main/.github/workflows/sync.yml) führt den Abgleich jede Nacht aus und committet mit den amtlichen Änderungsvermerken als Nachricht; git ist damit die Versionsgeschichte.
- **`app/server.py`** klont dieses Repository, baut den SQLite-Suchindex (**`app/store.py`**) neu, wenn es sich ändert, und stellt die Werkzeuge über Streamable HTTP bereit. **`app/repo.py`** beantwortet Fragen zur Historie aus git. Die Webseite aus [`docs/`](docs/) liegt unter `/`.

## Werkzeuge

Alle fünf lesen nur.

| Werkzeug | Was es tut |
|---|---|
| `gesetze_durchsuchen` | Volltextsuche über alle Vorschriften, optional in einem Gesetz |
| `vorschrift_lesen` | der vollständige Wortlaut eines §, Artikels oder einer Anlage, optional zu einem Datum |
| `gesetz_finden` | ein Gesetz über Namen oder Abkürzung finden |
| `gliederung_anzeigen` | die Gliederung eines Gesetzes mit allen Überschriften |
| `aenderungen_anzeigen` | wann sich ein Gesetz geändert hat, mit dem amtlichen Änderungsvermerk |

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

| Variable | Standard | |
|---|---|---|
| `GESETZE_REPO_URL` | `https://github.com/Gesetze-fuer-KI/gesetze.git` | das Daten-Repository |
| `GESETZE_REPO_BRANCH` | `main` | |
| `REFRESH_SECONDS` | `3600` | wie oft abgeglichen wird |
| `DATA_DIR` | `/data` | der Klon (~260 MB) und der Index (~300 MB) |
| `ALLOWED_HOSTS` | | erlaubte Host-Header, durch Kommas getrennt, z. B. `gesetze-fuer-ki.de` |
| `PORT` | `8081` | |

Beim ersten Start klont und indiziert der Server etwa eine Minute lang; bis dahin meldet `/health` `"ready": false`. Der Container braucht etwa 200 MB Arbeitsspeicher.

## Entwicklung

```bash
cd app
uv sync --all-groups
uv run pytest -q
uv run python sync.py --out /tmp/gesetze --only estg ustg_1980 gewo   # ein paar Gesetze
cd /tmp/gesetze && git init -q -b main && git add -A && git commit -qm init && cd -
GESETZE_REPO_URL=/tmp/gesetze DATA_DIR=/tmp/gk SITE_DIR=../site uv run python server.py
uv run --only-group docs mkdocs build -f ../mkdocs.yml --site-dir ../site   # die Webseite unter /
```

Code und Kommentare sind Englisch; alles, was Nutzer sehen, auch Namen und Beschreibungen der Werkzeuge, ist Deutsch. Fehler und Wünsche bitte als [Issue](https://github.com/Gesetze-fuer-KI/gesetze-fuer-ki/issues).

## Unterstützen

Der Dienst wird privat betrieben. Wer die Kosten für Server und Domain mittragen möchte, findet alles auf [gesetze-fuer-ki.de/unterstuetzen](https://gesetze-fuer-ki.de/unterstuetzen/). Ein Beitrag ist eine freiwillige Unterstützung, keine steuerlich absetzbare Spende.

## Lizenz

Copyright © 2026 Marcel Bruckner. Lizenziert unter der [GNU Affero General Public License v3.0 oder später](LICENSE). Die Gesetzestexte selbst sind gemeinfrei (§ 5 UrhG).

---

<sub>Keine Rechtsberatung: Der Dienst liefert Gesetzestexte; maßgeblich ist die amtliche Fassung. · [Impressum](https://gesetze-fuer-ki.de/impressum/) · [Datenschutz](https://gesetze-fuer-ki.de/datenschutz/)</sub>
