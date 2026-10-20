---
title: Aktuelles Bundesrecht für KI-Assistenten
hide:
  - navigation
---

# Gesetze für KI

**Ihr KI-Assistent schlägt die Gesetze nach, statt sie aus dem Gedächtnis zu zitieren.**

Gesetze für KI ist ein kostenloser [MCP-Server](https://modelcontextprotocol.io) mit dem
gesamten aktuellen Bundesrecht: rund 6.100 Gesetze und Verordnungen, von der
Gewerbeordnung bis zum Umsatzsteuergesetz, jede Nacht abgeglichen mit den amtlichen
Texten auf [gesetze-im-internet.de](https://www.gesetze-im-internet.de).
Einmal verbunden, sucht Claude, ChatGPT oder ein anderer Agent selbst die passenden
Paragrafen heraus, wenn Ihre Frage das Recht berührt, und antwortet mit dem Wortlaut,
dem Stand und einem Link zur Quelle.

<div class="endpoint" markdown>
**Adresse zum Verbinden:** `https://gesetze-fuer-ki.de/mcp`

Ohne Anmeldung, ohne API-Schlüssel.
</div>

[So verbinden Sie Ihren Assistenten](verbinden.md){ .md-button .md-button--primary }
[Welche Werkzeuge es gibt](werkzeuge.md){ .md-button }

## Wie das aussieht

> **Sie:** Ich melde nächsten Monat ein Gewerbe für 3D-Druck an. Muss ich Umsatzsteuer
> ausweisen, wenn ich im ersten Jahr vielleicht 15.000 Euro umsetze?
>
> **Assistent:** *(sucht „Kleinunternehmer Umsatz“, liest § 19 UStG)*
> Nach **§ 19 Abs. 1 UStG** sind Ihre Umsätze steuerfrei, wenn der Gesamtumsatz im
> vorangegangenen Kalenderjahr 25.000 Euro nicht überschritten hat und im laufenden
> Jahr 100.000 Euro nicht überschreitet. … Sie können darauf verzichten (§ 19 Abs. 3).
> *Stand: zuletzt geändert durch Art. 5 G v. 29.6.2026 · [Quelle](https://www.gesetze-im-internet.de/ustg_1980/__19.html)*

Typische Anlässe: die Gewerbeanmeldung, die Vorbereitung auf das Gespräch mit der
Steuerberaterin, ein Arbeitsvertrag, eine Mieterhöhung, eine Frage zum Datenschutz auf
der eigenen Website.

## Was drin ist und was nicht

| Enthalten | Nicht enthalten |
|---|---|
| Alle Gesetze und Rechtsverordnungen des Bundes in der aktuellen Fassung | Landesrecht (z. B. Bauordnungen, Schulgesetze) |
| Änderungen ab Oktober 2026 mit Datum, abrufbar als frühere Fassung | Ältere Fassungen vor dem Start dieses Dienstes |
| | Gerichtsentscheidungen (geplant), EU-Verordnungen wie die DSGVO |

Mehr dazu unter [Daten und Grenzen](daten.md).

!!! warning "Keine Rechtsberatung"

    Der Dienst liefert Gesetzestexte. Was ein Assistent daraus macht, ist eine
    Einschätzung, keine Rechtsberatung. Für Entscheidungen mit Folgen fragen Sie eine
    Steuerberaterin, einen Rechtsanwalt oder die zuständige Behörde.

## Offen

Der Server, die Aufbereitung der Gesetze und diese Seite sind Open Source
([Gesetze-fuer-KI/gesetze-fuer-ki](https://github.com/Gesetze-fuer-KI/gesetze-fuer-ki)). Die Gesetzestexte
selbst liegen als lesbare Markdown-Dateien mit vollständiger Änderungshistorie in einem
eigenen Repository ([gesetze](https://github.com/Gesetze-fuer-KI/gesetze)): Jede Änderung eines
Gesetzes ist dort ein Commit, den man Zeile für Zeile nachlesen kann.

Betrieben wird der Dienst privat. Wer mithelfen möchte, die Kosten für Server und Domain
zu tragen: [Unterstützen](unterstuetzen.md).
