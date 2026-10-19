# Werkzeuge

Der Server stellt fünf Werkzeuge bereit. Alle lesen nur; keines ändert etwas oder
speichert, was Sie fragen. Ihr Assistent wählt sie selbst aus. Die Liste hilft, wenn Sie
ihn gezielt lenken wollen oder verstehen möchten, was er gerade tut.

| Werkzeug | Was es tut | Beispiel |
|---|---|---|
| `search_laws` | Volltextsuche über alle Paragrafen, Artikel und Anlagen. Optional auf ein Gesetz beschränkt. | „Kleinunternehmer Umsatz“, nur im `UStG` |
| `get_provision` | Der vollständige Wortlaut einer Vorschrift mit Stand und Link. Mit `date` die Fassung an einem früheren Tag. | `§ 19` `UStG` |
| `find_law` | Ein Gesetz über seinen Namen oder seine Abkürzung finden. | „Mindestlohn“ → `MiLoG` |
| `get_law_outline` | Die Gliederung eines Gesetzes mit allen Überschriften. | `ArbZG` |
| `get_law_changes` | Wann sich ein Gesetz geändert hat, mit dem amtlichen Änderungsvermerk. | `EStG` |

## Wie die Suche funktioniert

Die Suche vergleicht Wörter, nicht Bedeutungen. Sie findet zuverlässig, was im Gesetz
steht, aber nicht, was man umgangssprachlich meint: Das Wort „Impressum“ kommt im
Gesetz nicht vor, die Pflicht dazu heißt in § 5 DDG „Allgemeine Informationspflichten“.
Gute Assistenten suchen deshalb mit den Begriffen des Gesetzes, probieren mehrere
Formulierungen und rufen eine Vorschrift direkt auf, wenn sie wissen, wo sie steht. Das
steht auch in den Hinweisen, die der Server jedem Assistenten mitgibt.

Wortendungen und zusammengesetzte Wörter werden berücksichtigt: „anzeigen“ findet
„Anzeige“ und „Anzeigepflicht“, „Kleinunternehmer“ findet „Kleinunternehmerregelung“.

## Frühere Fassungen

Jede nächtliche Änderung wird als eigener Stand gespeichert. `get_law_changes` zeigt,
wann sich ein Gesetz geändert hat, und `get_provision` mit `date` liefert den Wortlaut
von damals. So lässt sich zum Beispiel fragen: *„Was hat sich an § 19 UStG seit Januar
geändert?“* Die Historie beginnt mit dem Start dieses Dienstes im Oktober 2026.
