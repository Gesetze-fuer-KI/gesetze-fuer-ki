# Daten und Grenzen

## Bundesrecht

Das Bundesrecht stammt von [gesetze-im-internet.de](https://www.gesetze-im-internet.de), dem
Angebot des Bundesministeriums der Justiz, das die konsolidierten Fassungen des
Bundesrechts veröffentlicht. Amtlich verkündet werden Gesetze im
Bundesgesetzblatt; gesetze-im-internet.de ist die gepflegte, zusammengeführte Fassung,
in die jede Änderung eingearbeitet ist.

Jede Nacht fragt ein automatischer Abgleich alle rund 6.100 Gesetze und Verordnungen
ab, übernimmt die geänderten und legt sie als Markdown in einem öffentlichen
Repository ab: [github.com/Gesetze-fuer-KI/bundesrecht](https://github.com/Gesetze-fuer-KI/bundesrecht).
Der Server holt sich diese Fassung stündlich. Zwischen einer Änderung auf
gesetze-im-internet.de und ihrer Verfügbarkeit hier liegt also höchstens ein Tag.

Jede Antwort nennt den **Stand** des Gesetzes, so wie gesetze-im-internet.de ihn angibt
(*„zuletzt geändert durch Art. 7 G v. 29.6.2026 I Nr. 197“*). Achtung: Ein beschlossenes
Gesetz kann bereits verkündet, aber noch nicht eingearbeitet sein. Bei Änderungen der
letzten Wochen lohnt ein Blick ins [Bundesgesetzblatt](https://www.recht.bund.de).

Amtliche Gesetzestexte sind nach § 5 UrhG gemeinfrei. Die Aufbereitung steht unter
derselben Lizenz wie der Server.

## Landesrecht

Bauordnungen, Polizei-, Schul- und Kommunalrecht regeln die Länder selbst. Dieses
Landesrecht holt der Dienst direkt von den offiziellen Portalen der Länder, jedes Land in
ein eigenes öffentliches Repository (`landesrecht-by`, `landesrecht-nw` und so weiter).
Übernommen werden nur Gesetze und Verordnungen in der heute geltenden Fassung, keine
Verwaltungsvorschriften. Die Texte sind die **nichtamtlichen Fassungen** der Portale; das
steht auch in jeder Antwort. Verbindlich ist, was im Gesetz- und Verordnungsblatt des
Landes verkündet wurde.

Ein Land wird erst durchsuchbar, wenn es **einmal vollständig abgeglichen** ist. Bis dahin
steht es hier als „im Aufbau“, und Ihr Assistent bekommt den Hinweis, dass es bald
verfügbar ist, mit einem Link zum Landesportal. Danach wird jede Nacht abgeglichen. Die
Ausnahme ist Brandenburg: Das Portal erlaubt nur eine Anfrage alle 20 Sekunden und zeigt
nicht an, welche Gesetze sich geändert haben. Ein vollständiger Durchgang dauert dort
etwa zwei Nächte, ein Brandenburger Text kann also bis zu zwei Tage alt sein.

Abgeglichen wird nur, wo das Portal den automatischen Abruf zulässt. Zwölf Länder fehlen
deshalb noch: Zehn Portale (von juris betrieben) sperren in ihrer robots.txt jeden Abruf
außer durch Suchmaschinen. Niedersachsen behält sich die Nutzung der Texte ausdrücklich
vor. Bremen sperrt jeden automatischen Abruf aus Rechenzentren, also auch von dem Server,
auf dem dieser Dienst läuft; nur Anschlüsse von zu Hause kommen durch. Auf der Seite jedes
Landes steht, woran es genau scheitert.

Welche Länder enthalten sind, warum die anderen fehlen und an wen Sie schreiben können, um
das zu ändern, steht auf der Seite [Bundesländer](laender/index.md), mit einer eigenen Seite je Land.

## Was nicht enthalten ist

- **Landesrecht der Länder, die den Abruf nicht erlauben** (siehe Tabelle oben), sowie
  Satzungen und Ortsrecht von Städten und Gemeinden.
- **EU-Recht.** Die DSGVO und andere EU-Verordnungen gelten unmittelbar, sind aber kein
  Bundesrecht. Deutsche Begleitgesetze wie das BDSG sind enthalten.
- **Gerichtsentscheidungen.** Die Urteile der Bundesgerichte von
  [rechtsprechung-im-internet.de](https://www.rechtsprechung-im-internet.de) sind
  geplant.
- **Verwaltungsvorschriften** des Bundes und der Länder, etwa die
  Umsatzsteuer-Anwendungserlasse und BMF-Schreiben.
- **Ältere Fassungen.** Die Historie beginnt mit dem Start dieses Dienstes im Oktober
  2026, beim Landesrecht mit dem ersten Abgleich des jeweiligen Landes.

## Wie genau die Texte sind

Die Umwandlung aus dem XML von gesetze-im-internet.de und aus den Seiten der
Landesportale erhält Absätze, Satznummern
(¹ ² ³), Aufzählungen, Tabellen und Fußnoten. Bilder und Formeln in Anlagen werden
nicht übernommen, sondern als *(Abbildung, siehe Originalfassung)* markiert. Für die
verbindliche Fassung verlinkt jede Antwort auf die Vorschrift bei
gesetze-im-internet.de oder auf das Gesetz im Landesportal. Anlagen, die ein Landesportal
nur als PDF anhängt, fehlen.
