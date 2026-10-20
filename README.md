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

Claude, ChatGPT und andere KI-Assistenten schlagen über diesen Server den Wortlaut von rund 6.100 Gesetzen und Verordnungen nach, statt aus dem Gedächtnis zu zitieren. Ohne Anmeldung, ohne Schlüssel:

```text
https://gesetze-fuer-ki.de/mcp
```

## Loslegen

| | |
|---|---|
| **[Verbinden](https://gesetze-fuer-ki.de/verbinden/)** | Schritt für Schritt für [Claude](https://gesetze-fuer-ki.de/verbinden/#claude-claudeai-desktop-und-mobil), [ChatGPT](https://gesetze-fuer-ki.de/verbinden/#chatgpt), [Claude Code](https://gesetze-fuer-ki.de/verbinden/#claude-code), Cursor, VS Code, Gemini CLI, Codex und [weitere](https://gesetze-fuer-ki.de/verbinden/#weitere-assistenten) |
| **[Werkzeuge](https://gesetze-fuer-ki.de/werkzeuge/)** | Was der Assistent damit kann, [wie die Suche funktioniert](https://gesetze-fuer-ki.de/werkzeuge/#wie-die-suche-funktioniert) und wie man [frühere Fassungen](https://gesetze-fuer-ki.de/werkzeuge/#fruhere-fassungen) abruft |
| **[Daten und Grenzen](https://gesetze-fuer-ki.de/daten/)** | [Woher die Texte kommen](https://gesetze-fuer-ki.de/daten/#woher-die-texte-kommen) und [was nicht enthalten ist](https://gesetze-fuer-ki.de/daten/#was-nicht-enthalten-ist), etwa Landesrecht und Urteile |
| **[Unterstützen](https://gesetze-fuer-ki.de/unterstuetzen/)** | Der Dienst ist kostenlos und wird privat betrieben |

## So funktioniert es

<picture>
  <source media="(prefers-color-scheme: dark)" srcset=".github/readme/ablauf-dunkel.svg">
  <img alt="Ablauf: Die amtlichen Texte von gesetze-im-internet.de werden jede Nacht in das Repository gesetze übernommen, eine Markdown-Datei je Gesetz mit jeder Änderung als Commit. Der Server gesetze-fuer-ki holt sie stündlich, baut den Suchindex und stellt sie über MCP bereit. Ihr KI-Assistent schlägt darüber den Wortlaut nach." src=".github/readme/ablauf.svg" width="100%">
</picture>

Dieses Repository enthält den Server ([`app/`](app/)) und die Webseite ([`docs/`](docs/)). Die Gesetzestexte selbst liegen in **[Gesetze-fuer-KI/gesetze](https://github.com/Gesetze-fuer-KI/gesetze)**; mehr zur Herkunft auf **[Daten und Grenzen](https://gesetze-fuer-ki.de/daten/)**.

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

Beim ersten Start klont und indiziert der Server etwa eine Minute lang, danach meldet `/health` `"ready": true`. Er braucht etwa 200 MB Arbeitsspeicher und 600 MB Platz. Einstellbar über Umgebungsvariablen: `GESETZE_REPO_URL`, `GESETZE_REPO_BRANCH`, `REFRESH_SECONDS` (Standard 3600), `DATA_DIR`, `ALLOWED_HOSTS`, `PORT` (Standard 8081).

## Entwicklung

```bash
cd app && uv sync --all-groups && uv run pytest -q
```

Weitere Befehle stehen in [`CLAUDE.md`](CLAUDE.md). Code und Kommentare sind Englisch, alles, was Nutzer sehen, ist Deutsch. Fehler und Wünsche bitte als [Issue](https://github.com/Gesetze-fuer-KI/gesetze-fuer-ki/issues).

## Lizenz

[AGPL-3.0 oder später](LICENSE), © 2026 Marcel Bruckner. Die Gesetzestexte selbst sind gemeinfrei (§ 5 UrhG).

---

<sub>Keine Rechtsberatung: Der Dienst liefert Gesetzestexte; maßgeblich ist die amtliche Fassung. · [Impressum](https://gesetze-fuer-ki.de/impressum/) · [Datenschutz](https://gesetze-fuer-ki.de/datenschutz/)</sub>
