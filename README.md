<h1 align="center"><a href="https://gesetze-fuer-ki.de">Gesetze für KI</a></h1>

<p align="center">
  <a href="https://gesetze-fuer-ki.de/"><img alt="Documentation" src="https://img.shields.io/badge/docs-gesetze--fuer--ki.de-1f4e79"></a>
  <a href="https://github.com/Marceltov/Gesetze-fuer-KI/pkgs/container/gesetze-fuer-ki"><img alt="GHCR image" src="https://img.shields.io/badge/ghcr.io-marceltov%2Fgesetze--fuer--ki-2496ED?logo=docker&logoColor=white"></a>
  <a href="LICENSE"><img alt="License: AGPL v3" src="https://img.shields.io/badge/License-AGPL_v3-blue.svg"></a>
</p>

A public [MCP](https://modelcontextprotocol.io) server with all current German federal
law, so that Claude, ChatGPT and other agents look up the actual text instead of quoting
from memory. Connect any MCP client to

```text
https://gesetze-fuer-ki.de/mcp
```

No login, no key. The setup per client is on [gesetze-fuer-ki.de](https://gesetze-fuer-ki.de/verbinden/) (in German).

## How it works

```text
gesetze-im-internet.de ──nightly──▶ Marceltov/gesetze ──hourly git pull──▶ server ──▶ /mcp
  (6,100 laws as XML)    sync.py    (one Markdown file   (clone + SQLite     (5 read-only
                         in the     per law, history      FTS5 index)         tools)
                         data repo's  in git)
                         Action)
```

- **`app/sync.py`** mirrors [gesetze-im-internet.de](https://www.gesetze-im-internet.de):
  for every law in `gii-toc.xml` it requests the XML zip with the last ETag, converts the
  changed ones with **`app/convert.py`** and writes `<first two letters>/<slug>.md`. A full
  first run takes about a minute; a nightly run is ~6,100 `304 Not Modified`s.
- **[Marceltov/gesetze](https://github.com/Marceltov/gesetze)** holds the result. Its
  Action (template in [`data-repo/`](data-repo/)) runs the sync every night and commits with
  the official amendment notes as the message, so git is the version history.
- **`app/server.py`** clones that repository, rebuilds the index (**`app/store.py`**) when
  it changes and serves the tools over streamable HTTP. **`app/repo.py`** answers the
  history questions from git. The docs site from [`docs/`](docs/) is served at `/`.

| Tool | |
|---|---|
| `search_laws` | full-text search over all provisions, optionally within one law |
| `get_provision` | the full text of one § / Artikel / Anlage, optionally as of a date |
| `find_law` | find a law by name or abbreviation |
| `get_law_outline` | a law's structure with all headings |
| `get_law_changes` | when a law changed, with the official amendment note |

## Running it

```yaml
services:
  gesetze-fuer-ki:
    image: ghcr.io/marceltov/gesetze-fuer-ki:0.1.0
    restart: unless-stopped
    volumes:
      - ./data:/data
    ports:
      - "8081:8081"
```

| Variable | Default | |
|---|---|---|
| `GESETZE_REPO_URL` | `https://github.com/Marceltov/gesetze.git` | the data repository |
| `GESETZE_REPO_BRANCH` | `main` | |
| `REFRESH_SECONDS` | `3600` | how often to pull |
| `DATA_DIR` | `/data` | the clone (~260 MB) and the index (~300 MB) |
| `ALLOWED_HOSTS` | | comma-separated Host headers to accept, e.g. `gesetze-fuer-ki.de` |
| `PORT` | `8081` | |

The first start clones and indexes for about a minute; `/health` reports `"ready": false`
until then. The container needs about 200 MB of memory.

## Development

```bash
cd app
uv sync --all-groups
uv run pytest -q
uv run python sync.py --out /tmp/gesetze --only estg ustg_1980 gewo   # a few laws
cd /tmp/gesetze && git init -q -b main && git add -A && git commit -qm init && cd -
GESETZE_REPO_URL=/tmp/gesetze DATA_DIR=/tmp/gk SITE_DIR=../site uv run python server.py
uv run --only-group docs mkdocs build -f ../mkdocs.yml --site-dir ../site   # the docs at /
```

## License

Copyright © 2026 Marcel Bruckner. Licensed under the
[GNU Affero General Public License v3.0 or later](LICENSE). The law texts themselves are
in the public domain (§ 5 UrhG).
