<h1 align="center"><a href="https://gesetze-fuer-ki.de">Gesetze für KI</a></h1>

<p align="center">
  <a href="https://gesetze-fuer-ki.de/"><img alt="Dokumentation" src="https://img.shields.io/badge/docs-gesetze--fuer--ki.de-1f4e79"></a>
  <a href="https://github.com/Marceltov/Gesetze-fuer-KI/pkgs/container/gesetze-fuer-ki"><img alt="GHCR-Image" src="https://img.shields.io/badge/ghcr.io-marceltov%2Fgesetze--fuer--ki-2496ED?logo=docker&logoColor=white"></a>
  <a href="LICENSE"><img alt="Lizenz: AGPL v3" src="https://img.shields.io/badge/License-AGPL_v3-blue.svg"></a>
</p>

Ein öffentlicher [MCP](https://modelcontextprotocol.io)-Server mit dem gesamten aktuellen
Bundesrecht, damit Claude, ChatGPT und andere Assistenten den Wortlaut nachschlagen,
statt aus dem Gedächtnis zu zitieren. Jeder MCP-Client verbindet sich mit

```text
https://gesetze-fuer-ki.de/mcp
```

Ohne Anmeldung, ohne Schlüssel. Wie das in den einzelnen Programmen geht, steht auf
[gesetze-fuer-ki.de](https://gesetze-fuer-ki.de/verbinden/).

## So funktioniert es

```text
gesetze-im-internet.de ──nachts──▶ Marceltov/gesetze ──stündlich git pull──▶ Server ──▶ /mcp
  (6.100 Gesetze als XML)  sync.py   (eine Markdown-Datei   (Klon + SQLite-       (5 Werkzeuge,
                           in der    je Gesetz, Historie    FTS5-Index)           nur lesend)
                           Action    in git)
                           des Daten-Repos)
```

- **`app/sync.py`** spiegelt [gesetze-im-internet.de](https://www.gesetze-im-internet.de):
  Für jedes Gesetz aus `gii-toc.xml` fragt es das XML-Archiv mit dem letzten ETag an,
  wandelt geänderte mit **`app/convert.py`** um und schreibt `<erste zwei Buchstaben>/<kennung>.md`.
  Ein erster vollständiger Lauf dauert etwa eine Minute; ein nächtlicher Lauf besteht aus
  rund 6.100 Antworten `304 Not Modified`.
- **[Marceltov/gesetze](https://github.com/Marceltov/gesetze)** enthält das Ergebnis. Seine
  Action (Vorlage in [`data-repo/`](data-repo/)) führt den Abgleich jede Nacht aus und
  committet mit den amtlichen Änderungsvermerken als Nachricht; git ist damit die
  Versionsgeschichte.
- **`app/server.py`** klont dieses Repository, baut den Index (**`app/store.py`**) neu, wenn
  es sich ändert, und stellt die Werkzeuge über Streamable HTTP bereit. **`app/repo.py`**
  beantwortet Fragen zur Historie aus git. Die Dokumentation aus [`docs/`](docs/) liegt unter `/`.

| Werkzeug | |
|---|---|
| `search_laws` | Volltextsuche über alle Vorschriften, optional in einem Gesetz |
| `get_provision` | der vollständige Wortlaut eines §, Artikels oder einer Anlage, optional zu einem Datum |
| `find_law` | ein Gesetz über Namen oder Abkürzung finden |
| `get_law_outline` | die Gliederung eines Gesetzes mit allen Überschriften |
| `get_law_changes` | wann sich ein Gesetz geändert hat, mit dem amtlichen Änderungsvermerk |

## Selbst betreiben

```yaml
services:
  gesetze-fuer-ki:
    image: ghcr.io/marceltov/gesetze-fuer-ki:0.1.3
    restart: unless-stopped
    volumes:
      - ./data:/data
    ports:
      - "8081:8081"
```

| Variable | Standard | |
|---|---|---|
| `GESETZE_REPO_URL` | `https://github.com/Marceltov/gesetze.git` | das Daten-Repository |
| `GESETZE_REPO_BRANCH` | `main` | |
| `REFRESH_SECONDS` | `3600` | wie oft abgeglichen wird |
| `DATA_DIR` | `/data` | der Klon (~260 MB) und der Index (~300 MB) |
| `ALLOWED_HOSTS` | | erlaubte Host-Header, durch Kommas getrennt, z. B. `gesetze-fuer-ki.de` |
| `PORT` | `8081` | |

Beim ersten Start klont und indiziert der Server etwa eine Minute lang; bis dahin meldet
`/health` `"ready": false`. Der Container braucht etwa 200 MB Arbeitsspeicher.

## Entwicklung

```bash
cd app
uv sync --all-groups
uv run pytest -q
uv run python sync.py --out /tmp/gesetze --only estg ustg_1980 gewo   # ein paar Gesetze
cd /tmp/gesetze && git init -q -b main && git add -A && git commit -qm init && cd -
GESETZE_REPO_URL=/tmp/gesetze DATA_DIR=/tmp/gk SITE_DIR=../site uv run python server.py
uv run --only-group docs mkdocs build -f ../mkdocs.yml --site-dir ../site   # die Dokumentation unter /
```

Code, Kommentare und Werkzeugbeschreibungen sind Englisch; alles, was Nutzer sehen, ist Deutsch.

## Lizenz

Copyright © 2026 Marcel Bruckner. Lizenziert unter der
[GNU Affero General Public License v3.0 oder später](LICENSE). Die Gesetzestexte selbst
sind gemeinfrei (§ 5 UrhG).
