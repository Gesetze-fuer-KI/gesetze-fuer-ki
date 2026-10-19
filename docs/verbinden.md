# Verbinden

Alle Assistenten brauchen dieselbe Adresse:

```text
https://gesetze-fuer-ki.de/mcp
```

Es gibt keine Anmeldung und keinen Schlüssel. Wo ein Assistent nach einer
Authentifizierung fragt, wählen Sie **keine**. Nach dem Verbinden stehen fünf
[Werkzeuge](werkzeuge.md) bereit; der Assistent entscheidet selbst, wann er sie benutzt.
Sie können ihn aber auch direkt bitten: *„Schau im Gesetz nach.“*

## Claude (claude.ai, Desktop und Mobil)

Ein Connector, den Sie im Web hinzufügen, steht auch in der Desktop-App und in den
Mobil-Apps zur Verfügung.

1. Öffnen Sie *Einstellungen → Connectors* und klicken Sie auf **Benutzerdefinierten
   Connector hinzufügen** (*Add custom connector*). Im Chat geht das auch über
   **+ → Connectors**.
2. Name: `Gesetze`, URL: `https://gesetze-fuer-ki.de/mcp`. Klicken Sie auf **Hinzufügen**.
   Erweiterte Einstellungen und OAuth bleiben leer.
3. Im Chat unter **+ → Connectors** den Connector **Gesetze** einschalten.

Unter *Einstellungen → Connectors → Gesetze* sehen Sie die fünf Werkzeuge. Da alle nur
lesen, können Sie sie auf **Immer erlauben** stellen; dann fragt Claude nicht bei jeder
Suche nach.

## ChatGPT

ChatGPT verbindet MCP-Server im Entwicklermodus.

1. *Einstellungen → Apps & Connectors → Erweiterte Einstellungen*: **Entwicklermodus**
   einschalten.
2. Zurück in *Apps & Connectors* auf **Erstellen** klicken.
3. Name `Gesetze`, URL `https://gesetze-fuer-ki.de/mcp`, Authentifizierung
   **Keine Authentifizierung**. Bestätigen, dass Sie dem Server vertrauen, und erstellen.
4. Im Chat den Connector im Menü des Entwicklermodus auswählen.

## Claude Code

```bash
claude mcp add gesetze --scope user --transport http https://gesetze-fuer-ki.de/mcp
```

`/mcp` in Claude Code zeigt, ob die Verbindung steht.

## Weitere Assistenten

=== "Cursor"

    In `~/.cursor/mcp.json` (für alle Projekte) oder `.cursor/mcp.json` (für eines):

    ```json
    {
      "mcpServers": {
        "gesetze": { "url": "https://gesetze-fuer-ki.de/mcp" }
      }
    }
    ```

=== "VS Code (Copilot)"

    In `.vscode/mcp.json` oder über *MCP: Add Server → HTTP*:

    ```json
    {
      "servers": {
        "gesetze": { "type": "http", "url": "https://gesetze-fuer-ki.de/mcp" }
      }
    }
    ```

=== "Gemini CLI"

    In `~/.gemini/settings.json`:

    ```json
    {
      "mcpServers": {
        "gesetze": { "httpUrl": "https://gesetze-fuer-ki.de/mcp" }
      }
    }
    ```

=== "Codex CLI"

    ```bash
    codex mcp add gesetze --url https://gesetze-fuer-ki.de/mcp
    ```

=== "Andere"

    Jeder Client, der MCP über **Streamable HTTP** spricht, funktioniert mit der
    Adresse `https://gesetze-fuer-ki.de/mcp` ohne weitere Angaben. Clients, die nur
    lokale Server (stdio) kennen, verbinden sich über eine Brücke wie
    [`mcp-remote`](https://www.npmjs.com/package/mcp-remote):

    ```json
    {
      "mcpServers": {
        "gesetze": {
          "command": "npx",
          "args": ["-y", "mcp-remote", "https://gesetze-fuer-ki.de/mcp"]
        }
      }
    }
    ```

## Funktioniert es?

Fragen Sie Ihren Assistenten: *„Was steht in § 14 der Gewerbeordnung?“* Er sollte das
Werkzeug `get_provision` aufrufen und den Wortlaut mit Stand und Link zeigen. Antwortet
er ohne Werkzeug aus dem Gedächtnis, ist der Connector im aktuellen Chat nicht
eingeschaltet.
