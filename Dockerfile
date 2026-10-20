# gesetze-fuer-ki.de: the MCP server plus its documentation site, in one image.
#
# Multi-stage: resolve dependencies into a venv with uv, build the MkDocs site,
# then ship only the venv, the app and the static site on python-slim.

# ---- builder: create /app/.venv using uv ----
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

# Use the image's system CPython (never download a managed one), so the venv
# references /usr/local/bin/python3.12, which also exists in the runtime image.
ENV UV_PYTHON_PREFERENCE=only-system \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY app/pyproject.toml app/uv.lock ./
RUN uv sync --frozen --no-dev

# ---- docs: build the site served at / ----
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS docs
ENV UV_PYTHON_PREFERENCE=only-system \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /src
COPY app/pyproject.toml app/uv.lock app/
RUN cd app && uv sync --frozen --only-group docs
COPY mkdocs.yml ./
COPY docs docs
RUN app/.venv/bin/mkdocs build --strict --site-dir /site

# ---- runtime ----
FROM python:3.12-slim-bookworm

# git keeps the clone of the data repository current and answers the history tools;
# curl is used by the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
# Every module next to server.py, so a new import cannot be left out of the image (0.2.0 missed states.py).
COPY app/*.py ./
COPY --from=docs /site /app/site

ENV PATH="/app/.venv/bin:$PATH" \
    DATA_DIR=/data \
    SITE_DIR=/app/site
VOLUME /data
EXPOSE 8081

# The first start clones the data repository and builds the index, which takes a
# minute or two; /health answers during that time, with "ready": false.
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -sf -o /dev/null http://localhost:8081/health || exit 1

CMD ["python", "server.py"]
