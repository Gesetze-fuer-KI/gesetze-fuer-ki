# Daten und Grenzen

## Woher die Texte kommen

Alle Texte stammen von [gesetze-im-internet.de](https://www.gesetze-im-internet.de), dem
Angebot des Bundesministeriums der Justiz, das die konsolidierten Fassungen des
Bundesrechts veröffentlicht. Amtlich verkündet werden Gesetze im
Bundesgesetzblatt; gesetze-im-internet.de ist die gepflegte, zusammengeführte Fassung,
in die jede Änderung eingearbeitet ist.

Jede Nacht fragt ein automatischer Abgleich alle rund 6.100 Gesetze und Verordnungen
ab, übernimmt die geänderten und legt sie als Markdown in einem öffentlichen
Repository ab: [github.com/Gesetze-fuer-KI/gesetze](https://github.com/Gesetze-fuer-KI/gesetze).
Der Server holt sich diese Fassung stündlich. Zwischen einer Änderung auf
gesetze-im-internet.de und ihrer Verfügbarkeit hier liegt also höchstens ein Tag.

Jede Antwort nennt den **Stand** des Gesetzes, so wie gesetze-im-internet.de ihn angibt
(*„zuletzt geändert durch Art. 7 G v. 29.6.2026 I Nr. 197“*). Achtung: Ein beschlossenes
Gesetz kann bereits verkündet, aber noch nicht eingearbeitet sein. Bei Änderungen der
letzten Wochen lohnt ein Blick ins [Bundesgesetzblatt](https://www.recht.bund.de).

Amtliche Gesetzestexte sind nach § 5 UrhG gemeinfrei. Die Aufbereitung steht unter
derselben Lizenz wie der Server.

## Was nicht enthalten ist

- **Landesrecht.** Bauordnungen, Polizeigesetze, Schul- und Kommunalrecht der Länder
  stehen nicht auf gesetze-im-internet.de.
- **EU-Recht.** Die DSGVO und andere EU-Verordnungen gelten unmittelbar, sind aber kein
  Bundesrecht. Deutsche Begleitgesetze wie das BDSG sind enthalten.
- **Gerichtsentscheidungen.** Die Urteile der Bundesgerichte von
  [rechtsprechung-im-internet.de](https://www.rechtsprechung-im-internet.de) sind
  geplant.
- **Verwaltungsvorschriften** wie die Umsatzsteuer-Anwendungserlasse und
  BMF-Schreiben.
- **Fassungen vor Oktober 2026.** Die Historie beginnt mit dem Start dieses Dienstes.

## Wie genau die Texte sind

Die Umwandlung aus dem XML von gesetze-im-internet.de erhält Absätze, Satznummern
(¹ ² ³), Aufzählungen, Tabellen und Fußnoten. Bilder und Formeln in Anlagen werden
nicht übernommen, sondern als *(Abbildung, siehe Originalfassung)* markiert. Für die
verbindliche Fassung verlinkt jede Antwort auf die Vorschrift bei
gesetze-im-internet.de.
