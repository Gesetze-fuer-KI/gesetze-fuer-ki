# Gesetze für KI

Public MCP server for German federal law. Code in `app/`, docs site (German) in `docs/`, template for the
`Marceltov/gesetze` data repository in `data-repo/`.

## Commands

```bash
cd app && uv run pytest -q                                   # tests
cd app && uv run python sync.py --out DIR --only estg gewo   # sync a few laws (no deletions with --only)
cd app && uv run --only-group docs mkdocs build --strict -f ../mkdocs.yml --site-dir /tmp/site
docker build -t gesetze-fuer-ki:dev .
```

## Rules

- The Markdown format (`convert.py`) is a contract with `store.split_law`: the `<!-- norm id=… -->` /
  `<!-- gliederung id=… ebene=… -->` markers must stay exactly as they are. Changing the output rewrites all
  ~6,100 files in the data repo in one commit, which buries real changes in its history: do it rarely, on purpose.
- Docs are German, written for non-lawyers. Tool names and descriptions are English (for the models).
- No request content is logged; the privacy page (`docs/datenschutz.md`) promises it.
- Deployment lives in `../notefeed-stacks` (compose + Caddy) and `../notefeed-ansible`, not here.
