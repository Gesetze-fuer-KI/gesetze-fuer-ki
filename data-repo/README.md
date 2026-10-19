# gesetze

Das gesamte Bundesrecht als Markdown, jede Nacht abgeglichen mit
[gesetze-im-internet.de](https://www.gesetze-im-internet.de): rund 6.100 Gesetze und
Verordnungen in ihrer aktuellen Fassung, und mit der Git-Historie jede Änderung seit
dem ersten Abgleich im Oktober 2026.

Diese Dateien sind die Datengrundlage von [gesetze-fuer-ki.de](https://gesetze-fuer-ki.de),
einem MCP-Server, mit dem KI-Assistenten die Gesetze selbst nachschlagen. Sie sind aber
auch für sich nutzbar: zum Lesen, zum Durchsuchen, zum Vergleichen von Fassungen.

## Aufbau

Ein Gesetz ist eine Datei, abgelegt nach den ersten zwei Buchstaben seiner Kennung auf
gesetze-im-internet.de: `es/estg.md` ist das Einkommensteuergesetz, `bg/bgb.md` das
BGB, `ge/gewo.md` die Gewerbeordnung. (GitHub zeigt höchstens 1.000 Einträge je
Verzeichnis, daher die Unterordner.)

Jede Datei beginnt mit den Metadaten:

```yaml
---
abkuerzung: EStG
titel: Einkommensteuergesetz
stand: zuletzt geändert durch Art. 7 G v. 29.6.2026 I Nr. 197
ausfertigung: '1934-10-16'
quelle: https://www.gesetze-im-internet.de/estg/
---
```

Danach folgen Gliederung und Vorschriften als Überschriften. Vor jeder steht ein
unsichtbarer Kommentar mit der Kennung aus dem amtlichen XML
(`<!-- norm id="BJNE003619116" -->`), damit Programme die Datei sicher zerlegen können.

## Änderungen nachlesen

Jeder nächtliche Commit nennt die geänderten Gesetze mit ihrem amtlichen
Änderungsvermerk. Die Historie einer Vorschrift zeigt zum Beispiel

```bash
git log -p -- us/ustg_1980.md
```

## Herkunft und Lizenz

Die Texte stammen von gesetze-im-internet.de (Bundesministerium der Justiz). Amtliche
Gesetzestexte sind nach § 5 UrhG gemeinfrei. Die Umwandlung erledigt
[`sync.py`](https://github.com/Marceltov/Gesetze-fuer-KI/blob/main/app/sync.py) in
Gesetze-fuer-KI. Verbindlich ist die amtliche Fassung; für Fehler der Umwandlung wird
keine Gewähr übernommen.

`.sync/etags.json` merkt sich für jedes Gesetz die Version des letzten Abrufs, damit
nur Geänderte neu geladen werden.
