# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Gesetze für KI

Public MCP server for German federal law. Code in `app/`, docs site (German) in `docs/`. The data lives in
`Gesetze-fuer-KI/gesetze`; its nightly workflow (`.github/workflows/sync.yml` there) checks out this repo and runs
`app/sync.py`, so a change to the sync's command line must be made in both repos.

Data flow: `sync.py` (nightly, in the data repo's Action) mirrors gesetze-im-internet.de into one Markdown file per
law and commits; `server.py` clones that repo, pulls hourly, rebuilds the SQLite FTS5 index (`store.py`) on change
and swaps it in atomically; `repo.py` answers history questions (`aenderungen_anzeigen`, `date=`) from git itself.

## Commands

```bash
cd app && uv run pytest -q                                   # tests
cd app && uv run pytest -q tests/test_store.py::test_norm_key  # one test
cd app && uv run python sync.py --out DIR --only estg gewo   # sync a few laws (no deletions with --only)
cd app && GESETZE_REPO_URL=DIR DATA_DIR=/tmp/gk SITE_DIR=../site uv run python server.py  # DIR must be a git repo
cd app && uv run --only-group docs mkdocs build --strict -f ../mkdocs.yml --site-dir /tmp/site
docker build -t gesetze-fuer-ki:dev .
```

## Rules

- The Markdown format (`convert.py`) is a contract with `store.split_law`: the `<!-- norm id=… -->` /
  `<!-- gliederung id=… ebene=… -->` markers must stay exactly as they are. Changing the output rewrites all
  ~6,100 files in the data repo in one commit, which buries real changes in its history: do it rarely, on purpose.
- The commit message `sync.py` writes (`.sync/commit-message.txt`, one `- ABK: stand` / `- neu: ABK (…)` line per
  law) is parsed by `repo.changes`; keep the two in step.
- Everything users see is German: docs (written for non-lawyers), tool responses, READMEs, and the tool names,
  titles and descriptions (set via `@mcp.tool(name=…, title=…, description=…)` and `Field(description=…)`, since
  users read them in Claude). Code, comments, docstrings, Python names and parameter names stay English.
- No request content is logged; the privacy page (`docs/datenschutz.md`) promises it. The docs site makes no
  third-party requests either (privacy plugin, no `repo_url`).
- Releases: tag `vX.Y.Z` → `publish.yml` pushes `ghcr.io/gesetze-fuer-ki/gesetze-fuer-ki`. Deployment lives in
  `../notefeed-stacks` (compose + Caddy, pins the version) and `../notefeed-ansible`, not here.
