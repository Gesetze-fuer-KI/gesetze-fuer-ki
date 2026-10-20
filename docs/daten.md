# Daten und Grenzen

## Bundesrecht

Das Bundesrecht stammt von [gesetze-im-internet.de](https://www.gesetze-im-internet.de), dem
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

Den Abgleich lassen nur Portale zu, die automatischen Abruf nicht verbieten. Elf Länder
fehlen deshalb noch: Ihre Portale (meist von juris betrieben) sperren in ihrer robots.txt
jeden Abruf außer durch Suchmaschinen, und Niedersachsen behält sich die Nutzung der
Texte ausdrücklich vor. Im Repository jedes Landes steht, woran es genau scheitert.

| Land | Stand | Quelle | Hinweis |
|---|---|---|---|
| Baden-Württemberg | noch nicht integriert | [landesrecht-bw.de](https://www.landesrecht-bw.de) | Portal verbietet automatischen Abruf, [warum](https://github.com/Gesetze-fuer-KI/landesrecht-bw) |
| Bayern | enthalten | [gesetze-bayern.de](https://www.gesetze-bayern.de) | Nutzungshinweise erlauben uneingeschränkte Weiterverwendung, [Repository](https://github.com/Gesetze-fuer-KI/landesrecht-by) |
| Berlin | noch nicht integriert | [gesetze.berlin.de](https://gesetze.berlin.de) | Portal verbietet automatischen Abruf, [warum](https://github.com/Gesetze-fuer-KI/landesrecht-be) |
| Brandenburg | im Aufbau | [bravors.brandenburg.de](https://bravors.brandenburg.de) | Keine Lizenzangabe; amtliche Werke (§ 5 UrhG). Texte bis zu zwei Tage alt, [Repository](https://github.com/Gesetze-fuer-KI/landesrecht-bb) |
| Bremen | im Aufbau | [transparenz.bremen.de](https://www.transparenz.bremen.de) | CC BY-NC-ND 3.0, Namensnennung siehe unten. Ohne Ortsgesetze, [Repository](https://github.com/Gesetze-fuer-KI/landesrecht-hb) |
| Hamburg | noch nicht integriert | [landesrecht-hamburg.de](https://www.landesrecht-hamburg.de) | Portal verbietet automatischen Abruf, [warum](https://github.com/Gesetze-fuer-KI/landesrecht-hh) |
| Hessen | noch nicht integriert | [rv.hessenrecht.hessen.de](https://www.rv.hessenrecht.hessen.de) | Portal verbietet automatischen Abruf, [warum](https://github.com/Gesetze-fuer-KI/landesrecht-he) |
| Mecklenburg-Vorpommern | noch nicht integriert | [landesrecht-mv.de](https://www.landesrecht-mv.de) | Portal verbietet automatischen Abruf, [warum](https://github.com/Gesetze-fuer-KI/landesrecht-mv) |
| Niedersachsen | noch nicht integriert | [voris.wolterskluwer-online.de](https://voris.wolterskluwer-online.de) | Betreiber behält sich die Nutzung der Texte vor, [warum](https://github.com/Gesetze-fuer-KI/landesrecht-ni) |
| Nordrhein-Westfalen | im Aufbau | [recht.nrw.de](https://recht.nrw.de) | Keine Lizenzangabe; amtliche Werke (§ 5 UrhG), [Repository](https://github.com/Gesetze-fuer-KI/landesrecht-nw) |
| Rheinland-Pfalz | noch nicht integriert | [landesrecht.rlp.de](https://www.landesrecht.rlp.de) | Portal verbietet automatischen Abruf, [warum](https://github.com/Gesetze-fuer-KI/landesrecht-rp) |
| Saarland | noch nicht integriert | [recht.saarland.de](https://recht.saarland.de) | Portal verbietet automatischen Abruf, [warum](https://github.com/Gesetze-fuer-KI/landesrecht-sl) |
| Sachsen | enthalten | [revosax.sachsen.de](https://www.revosax.sachsen.de) | Keine Lizenzangabe; amtliche Werke (§ 5 UrhG), [Repository](https://github.com/Gesetze-fuer-KI/landesrecht-sn) |
| Sachsen-Anhalt | noch nicht integriert | [landesrecht.sachsen-anhalt.de](https://www.landesrecht.sachsen-anhalt.de) | Portal verbietet automatischen Abruf, [warum](https://github.com/Gesetze-fuer-KI/landesrecht-st) |
| Schleswig-Holstein | noch nicht integriert | [gesetze-rechtsprechung.sh.juris.de](https://www.gesetze-rechtsprechung.sh.juris.de) | Portal verbietet automatischen Abruf, [warum](https://github.com/Gesetze-fuer-KI/landesrecht-sh) |
| Thüringen | noch nicht integriert | [landesrecht.thueringen.de](https://landesrecht.thueringen.de) | Portal verbietet automatischen Abruf, [warum](https://github.com/Gesetze-fuer-KI/landesrecht-th) |

**Enthalten** heißt: vollständig abgeglichen und durchsuchbar. **Im Aufbau** heißt: Der
erste Abgleich läuft noch. **Noch nicht integriert** heißt: Das Land lässt den Abruf nicht
zu; die Gesetze stehen nur auf dem Landesportal.

Die Bremer Texte stehen unter der Lizenz
[CC BY-NC-ND 3.0](https://creativecommons.org/licenses/by-nc-nd/3.0/). Namensnennung:
Transparenzportal Bremen, Der Senator für Finanzen der Freien Hansestadt Bremen. Die Texte
werden nicht verändert, nur ins einheitliche Format gebracht, und jede Antwort nennt die
Quelle.

!!! info "Ihr Land fehlt?"

    Schreiben Sie an [kontakt@gesetze-fuer-ki.de](mailto:kontakt@gesetze-fuer-ki.de), wenn
    Sie das Recht eines fehlenden Landes brauchen. Das hilft, bei den Ländern nachzufragen.

    Und an die Länder: Wenn Sie den automatischen Abruf Ihres Portals erlauben oder die
    Texte als Download anbieten können, melden Sie sich bitte unter derselben Adresse.

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
