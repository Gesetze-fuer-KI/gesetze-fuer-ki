# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Gesetze für KI

Public MCP server for German federal and state law. Code in `app/`, docs site (German) in `docs/`. Federal data
lives in `Gesetze-fuer-KI/bundesrecht`, state law in one repo per state, `Gesetze-fuer-KI/landesrecht-<code>` (by, bb,
nw, sn are integrated; the other twelve are not. hb keeps its source `sources/hb.py`, but Bremen's portal
answers 403 to data centres, so it stays off until Bremen allows access). Each data repo's nightly workflow
(`.github/workflows/sync.yml` there) checks out this repo and runs `app/sync.py`, so a change to the sync's command line must be made in this
repo, `bundesrecht` and the four integrated state repos.

Data flow: `sync.py` (nightly, in the data repo's Action) mirrors gesetze-im-internet.de into one Markdown file per
law and commits; `server.py` clones that repo, pulls hourly, rebuilds the SQLite FTS5 index (`store.py`) on change
and swaps it in atomically; `repo.py` answers history questions (`aenderungen_anzeigen`, `date=`) from git itself.
State law: `sync.py --land xx` runs `state_sync.py` with the portal's source in `sources/` (one per state, keyed in
`sources.SOURCES`; the 16 states and which are integrated are in `states.py`) and renders with `state_markdown.py`
in the federal format. A pass may span several nightly runs. The server clones every integrated state's repo
(`STATE_REPO_URL`) next to the federal one and indexes them together.

## Commands

```bash
cd app && uv run pytest -q                                   # tests
cd app && uv run pytest -q tests/test_store.py::test_norm_key  # one test
cd app && uv run python sync.py --out DIR --only estg gewo   # sync a few laws (no deletions with --only)
cd app && uv run python sync.py --land SN --out DIR --max-minutes 5  # part of a state pass; resumes next run
cd app && GESETZE_REPO_URL=DIR STATE_REPO_URL= DATA_DIR=/tmp/gk SITE_DIR=../site uv run python server.py  # DIR: a git repo; empty STATE_REPO_URL: no state law
cd app && uv run --only-group docs mkdocs build --strict -f ../mkdocs.yml --site-dir /tmp/site
docker build -t gesetze-fuer-ki:dev .
```

## Rules

- The Markdown format (`convert.py`) is a contract with `store.split_law`: the `<!-- norm id=… -->` /
  `<!-- gliederung id=… ebene=… -->` markers must stay exactly as they are. Changing the output rewrites all
  ~6,100 files in the data repo in one commit, which buries real changes in its history: do it rarely, on purpose.
- The commit message `sync.py` writes (`.sync/commit-message.txt`, one `- ABK: stand` / `- neu: ABK (…)` line per
  law) is parsed by `repo.changes`; keep the two in step.
- `.sync/state.json` in a state repo is written by `state_sync.py` and read by `store.build`: until its `complete`
  is true (first full pass done) the state is „im Aufbau“ and not indexed. Keep both sides in step.
- Everything users see is German: docs (written for non-lawyers), tool responses, READMEs, and the tool names,
  titles and descriptions (set via `@mcp.tool(name=…, title=…, description=…)` and `Field(description=…)`, since
  users read them in Claude). Code, comments, docstrings, Python names and parameter names stay English.
- No request content is logged; the privacy page (`docs/datenschutz.md`) promises it. The docs site makes no
  third-party requests either (privacy plugin, no `repo_url`).
- Releases: tag `vX.Y.Z` → `publish.yml` pushes `ghcr.io/gesetze-fuer-ki/gesetze-fuer-ki`. Deployment lives in
  `../notefeed-stacks` (compose + Caddy, pins the version) and `../notefeed-ansible`, not here.
