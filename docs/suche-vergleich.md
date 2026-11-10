# Suche nach Bedeutung: der Vergleich

Die heutige Suche vergleicht Wörter (siehe [Wie gut die Suche findet](suche.md)). Eine
Suche nach **Bedeutung** übersetzt Frage und Paragrafen in Zahlen, die ihren Sinn
beschreiben, und findet so auch einen Paragrafen, der andere Wörter benutzt als die
Frage. Diese Seite misst, ob das die Suche besser macht.

Gemessen wurde mit [passageway](https://getpassageway.com), einer Suche, die beides
verbindet: die Wortsuche und die Suche nach Bedeutung, mit dem kleinen Sprachmodell
multilingual-e5-small. passageway liefert höchstens 3 Treffer und gar keinen, wenn nichts
gut genug passt.

**Kurz gesagt: Wir bauen sie nicht ein.** Sie hilft nur, wenn jemand in Alltagssprache
sucht. Claude sucht aber mit den Wörtern des Gesetzes, und dann ist die heutige Suche
fast genauso gut, bei selteneren Gesetzen sogar deutlich besser, und zehnmal schneller.

## 1. Fragen in Alltagssprache

Gemessen am 6. November 2026 auf dem Bundesrecht mit Stand 5. November 2026
(106.468 Vorschriften aus 6.144 Gesetzen und Verordnungen). Weil passageway nur 3 Treffer
liefert, vergleicht die Tabelle Platz 1 und die ersten 3; der MRR zählt hier ebenfalls nur
die ersten 3 Plätze.

| Fragen | | Platz 1 | Unter den ersten 3 | MRR |
|---|---|---|---|---|
| Alltagssprache (46) | heute | 0 % | 4 % | 0,01 |
| | nach Bedeutung | 7 % | 17 % | 0,11 |
| Fachsprache (8) | heute | 63 % | 88 % | 0,73 |
| | nach Bedeutung | 75 % | 88 % | 0,81 |
| Alle (54) | heute | 9 % | 17 % | 0,12 |
| | nach Bedeutung | 17 % | 28 % | 0,22 |

| | heute | nach Bedeutung |
|---|---|---|
| Fragen ohne Antwort, bei denen die Suche nichts liefert | 0 von 5 | 3 von 5 |
| Fragen mit Antwort, bei denen die Suche fälschlich nichts liefert | 0 von 54 | 1 von 54 |
| Antwortzeit, Hälfte der Suchen unter | 20 ms | 270 ms |
| Antwortzeit, 95 % der Suchen unter | 500 ms | 1.100 ms |
| Größe des Suchindex | 303 MB | 775 MB |

**Was das heißt:**

- **In Alltagssprache findet die Suche nach Bedeutung viermal so oft die richtige
  Vorschrift unter den ersten 3**, aber immer noch nur bei 8 von 46 Fragen. „Wie hoch ist
  der Mindestlohn?“, „Bekomme ich weiter Lohn, wenn ich krank bin?“ oder „Ich bin
  umgezogen, muss ich mich ummelden?“ findet sie, die heutige Suche nicht.
- **Oft liegt sie knapp daneben:** Sie findet den Nachbarparagrafen (§ 1612 statt
  § 1612a BGB beim Kindesunterhalt, § 651n statt § 651m BGB bei der mangelhaften Reise)
  oder dieselbe Regel in einem anderen Gesetz (die Probezeit im Pflegeberufegesetz statt
  im Berufsbildungsgesetz, die Kündigungsfrist im SGB IX statt im Mietrecht).
- **In Fachsprache ist sie so gut wie die heutige Suche**, mit etwas mehr Treffern auf
  Platz 1. Bei „Widerrufsrecht Verbraucherverträge“ liefert sie § 312g BGB statt des
  erwarteten § 355 BGB, also auch ein Widerrufsrecht, aber nicht das gemessene.
- **Sie kann schweigen:** Bei „Wie wird das Wetter morgen in Berlin?“ liefert sie nichts,
  die heutige Suche liefert immer etwas. Dafür schweigt sie einmal zu Unrecht („Darf ein
  Laden mich mit Kameras filmen?“).
- **Sie ist langsamer und größer:** Eine Suche dauert gut zehnmal so lange, bleibt aber
  meist unter einer halben Sekunde. Das Sprachmodell selbst braucht davon nur 5 ms je
  Frage. Den Index aufzubauen dauerte knapp 4 Stunden (auf 8 Prozessorkernen); danach
  wird nur neu berechnet, was sich geändert hat.

**Wie sicher das ist:** 46 Fragen in Alltagssprache sind wenige. Bei „unter den ersten 3“
liegt der wahre Wert der heutigen Suche mit 95 % Sicherheit zwischen 1 % und 15 %, der
der Suche nach Bedeutung zwischen 9 % und 31 %. Die Richtung ist klar, die genaue Größe
des Unterschieds nicht.

??? note "Alle Fragen im Einzelnen"

    Platz der richtigen Vorschrift; „–“ heißt nicht gefunden, „nichts“ heißt, die Suche
    hat keinen Treffer geliefert. Die heutige Suche liefert 8 Treffer, die Suche nach
    Bedeutung höchstens 3.

    | Frage | Richtig | Heute (von 8) | Nach Bedeutung (von 3) |
    |---|---|---|---|
    | Was muss ins Impressum meiner Webseite? | § 5 DDG | – | – |
    | Ab welchem Umsatz muss eine kleine Firma Umsatzsteuer zahlen? | § 19 UStG | – | – |
    | Wie melde ich ein Gewerbe an? | § 14 GewO | – | – |
    | Wie lange ist die Kündigungsfrist für meine Mietwohnung? | § 573c BGB | – | – |
    | Wie viele Urlaubstage stehen mir mindestens zu? | § 3 BUrlG | – | – |
    | Wie viele Stunden darf ich am Tag höchstens arbeiten? | § 3 ArbZG | – | – |
    | Kann ich online gekaufte Sachen zurückschicken? | § 355 / § 312g BGB | – | – |
    | Wie hoch darf die Kaution für eine Wohnung sein? | § 551 BGB | – | – |
    | Nach wie vielen Jahren muss ich eine offene Rechnung nicht mehr bezahlen? | § 195 / § 199 BGB | – | – |
    | Mit welcher Frist kann mein Chef mir kündigen? | § 622 BGB | – | – |
    | Darf mein Vermieter einfach die Miete erhöhen? | § 558 BGB | 8 | – |
    | Wie viele Monate bekomme ich Elterngeld? | § 4 BEEG | 7 | 1 |
    | Wann darf mein Arbeitgeber mich nicht einfach rauswerfen? | § 1 KSchG | – | – |
    | Wie lange habe ich Garantie auf ein gekauftes Handy? | § 438 BGB | – | – |
    | Muss ich als Angestellter eine Steuererklärung machen? | § 46 EStG / § 149 AO | – | – |
    | Wie viel darf ich im Minijob verdienen? | § 8 SGB IV | – | – |
    | Wer erbt, wenn es kein Testament gibt? | § 1924 BGB | – | – |
    | Wie viel bekommen enterbte Kinder vom Erbe? | § 2303 BGB | – | – |
    | Bekomme ich weiter Lohn, wenn ich krank bin? | § 3 EntgFG | – | 1 |
    | Ab wann vor der Geburt darf ich nicht mehr arbeiten? | § 3 MuSchG | – | 3 |
    | Darf ein Laden mich mit Kameras filmen? | § 4 BDSG | – | nichts |
    | Wer zahlt, wenn ein Hund jemanden beißt? | § 833 BGB | – | – |
    | Wer haftet für einen Autounfall? | § 7 StVG | – | – |
    | Wie lange dauert die Probezeit in der Lehre? | § 20 BBiG | 6 | – |
    | Ab welchem Alter ist man erwachsen? | § 2 BGB | – | – |
    | Wie viel Kindergeld gibt es pro Kind? | § 66 EStG | 3 | 3 |
    | Wie hoch ist der Mindestlohn? | § 1 MiLoG | – | 2 |
    | Ab wie vielen Mitarbeitern kann man einen Betriebsrat gründen? | § 1 BetrVG | – | – |
    | Die Äste vom Baum des Nachbarn hängen in meinen Garten | § 910 BGB | 3 | 2 |
    | Ich habe eine Geldbörse gefunden, was muss ich tun? | § 965 BGB | – | – |
    | Ist Schwarzfahren strafbar? | § 265a StGB | – | – |
    | Jemand hat mich beschimpft, ist das strafbar? | § 185 StGB | – | – |
    | Personalausweis verloren, was muss ich machen? | § 27 PAuswG | – | – |
    | Kann ich erfahren, welche Daten eine Firma über mich hat? | § 34 BDSG | – | – |
    | Wie lange muss ich Belege für das Finanzamt aufheben? | § 147 AO / § 257 HGB | – | – |
    | Was muss alles auf einer Rechnung stehen? | § 14 UStG | – | – |
    | Wie lange muss man getrennt leben bis zur Scheidung? | § 1566 BGB | 8 | 2 |
    | Wie viel Unterhalt muss ich für mein Kind zahlen? | § 1612a / § 1601 BGB | – | – |
    | Hotel im Urlaub war dreckig, bekomme ich Geld vom Reiseveranstalter zurück? | § 651m BGB | – | – |
    | Wie lange dürfen Jugendliche arbeiten? | § 8 JArbSchG | – | – |
    | Wie lange bekomme ich Arbeitslosengeld? | § 147 SGB III | – | – |
    | Wer bekommt Bürgergeld? | § 19 SGB II | – | – |
    | Mit wie viel Jahren kann ich in Rente gehen? | § 35 SGB VI | – | – |
    | Wie wechsle ich meine Krankenkasse? | § 175 SGB V | – | – |
    | Wie viel Alkohol darf ich beim Autofahren getrunken haben? | § 24a StVG | – | – |
    | Ich bin umgezogen, muss ich mich ummelden? | § 17 BMG | – | 1 |
    | Informationspflichten Diensteanbieter | § 5 DDG | 3 | 1 |
    | Kleinunternehmer Umsatz | § 19 UStG | 4 | 2 |
    | Widerrufsrecht Verbraucherverträge | § 355 BGB | 1 | – |
    | Haftung des Tierhalters | § 833 BGB | 1 | 1 |
    | Erschleichen von Leistungen | § 265a StGB | 1 | 1 |
    | Fristen der ordentlichen Kündigung Wohnraum | § 573c BGB | 1 | 1 |
    | Entgeltfortzahlung im Krankheitsfall | § 3 EntgFG | 2 | 1 |
    | Regelaltersrente | § 35 SGB VI | 1 | 1 |

## 2. Wenn Claude die Frage umformuliert

Claude sucht nicht mit den Worten des Nutzers. Der Server bittet es, mit den Wörtern des
Gesetzes zu suchen, und Claude kennt diese Wörter aus seinem Training: Aus „Kaution“ wird
„Mietsicherheit“, aus „Schwarzfahren“ wird „Erschleichen von Leistungen“. Um das
nachzustellen, hat ein zweites Claude die 46 Alltagsfragen so umformuliert, wie es sie an
`gesetze_durchsuchen` schicken würde. Es kannte nur die Fragen und die Anleitung des
Servers, nicht die richtigen Antworten.

| 46 Alltagsfragen, von Claude umformuliert | heute | nach Bedeutung |
|---|---|---|
| Platz 1 | 57 % | 67 % |
| Unter den ersten 3 | 78 % | 80 % |
| Unter den ersten 8 | 89 % | – (höchstens 3 Treffer) |
| Richtiges Gesetz unter den ersten 3 | 91 % | |
| Antwortzeit, Hälfte der Suchen unter | 20 ms | 260 ms |

- **Das Umformulieren macht den Unterschied, nicht die Suche nach Bedeutung.** Die
  heutige Suche springt von 4 % auf 78 % unter den ersten 3.
- **Die Suche nach Bedeutung sortiert etwas besser**, findet aber kaum mehr: Unter den
  8 Treffern der heutigen Suche, die Claude alle zu sehen bekommt, steht die richtige
  Vorschrift öfter (41-mal) als unter den 3 der Suche nach Bedeutung (37-mal).

## 3. Seltenere Gesetze

Die 46 Alltagsfragen betreffen bekannte Gesetze, die Claude gut kennt. Von den 6.144
Gesetzen und Verordnungen sind die meisten aber selten gefragt. Für diese Messung wurde aus
60 zufällig gezogenen kleineren Gesetzen je eine Vorschrift gezogen (die bekanntesten
Gesetze ausgenommen). Ein Claude hat zu 35 davon eine Frage geschrieben, wie sie ein
Mensch stellen würde, etwa „Ich arbeite in einem Schlachtbetrieb. Muss ich meine
Schutzkleidung und Messer selbst bezahlen?“ (richtig: § 4 GSA Fleisch). Ein zweites Claude
hat sie, ohne die Antworten zu kennen, umformuliert.

| 35 Fragen zu selteneren Gesetzen | | Platz 1 | Unter den ersten 3 | Unter den ersten 8 |
|---|---|---|---|---|
| wie Menschen fragen | heute | 31 % | 51 % | 54 % |
| | nach Bedeutung | 17 % | 31 % | – |
| von Claude umformuliert | heute | 37 % | 63 % | 86 % |
| | nach Bedeutung | 29 % | 34 % | – |

Hier ist die Suche nach Bedeutung **deutlich schlechter**. Das kleine Sprachmodell kennt
Fachwörter wie „Nasszurichtung“ oder Ortsnamen wie „Spangdahlem“ kaum; die Wortsuche
findet sie genau. Bei den umformulierten Fragen nennt die heutige Suche in 94 % der Fälle
das richtige Gesetz unter den ersten 3. Von dort liest Claude die Gliederung oder sucht
mit `law` gezielt im Gesetz weiter.

## 4. Und die Rangfolge der heutigen Suche?

Geprüft wurden auch kleine Änderungen an der heutigen Rangfolge: ohne den Vorsprung für
große Gesetze, mit weniger Gewicht für lange Anlagen, mit mehr Gewicht für Treffer in der
Überschrift. Keine davon verschiebt mehr als ein oder zwei Fragen je Fragensatz, in die
eine oder andere Richtung. Das liegt im Bereich des Zufalls, deshalb bleibt die Rangfolge,
wie sie ist.

## Was daraus folgt

- Die heutige Wortsuche bleibt. Sie passt zu der Art, wie Claude sucht, und ist schnell.
- Der wichtigste Teil dieses Servers ist nicht das Finden, sondern der **aktuelle
  Wortlaut**: Claude weiß meist, wo eine Regel steht, aber nicht, was dort heute genau
  steht (etwa die Kleinunternehmergrenze in § 19 UStG, seit 2025 25.000 statt 22.000 Euro).
- Die vier Fragensätze bleiben als Maßstab: Jede künftige Änderung an der Suche wird an
  ihnen gemessen.

## Selbst nachmessen

Die Fragensätze liegen in `app/eval/`: `cases.toml` (Alltags- und Fachsprache),
`cases_rewritten.toml` (von Claude umformuliert), `cases_rare.toml` (seltenere Gesetze)
und `cases_rare_rewritten.toml`. Die heutige Suche misst
`uv run python eval/baseline.py eval/<datei>.toml /tmp/gk.db` (siehe
[Wie gut die Suche findet](suche.md#selbst-nachmessen)).

Für die Suche nach Bedeutung braucht es den Suchindex aus [Wie gut die Suche findet](suche.md#selbst-nachmessen)
(`/tmp/gk.db`) und passageway (`git clone https://github.com/getpassageway/passageway`,
dann `uv sync` darin). Der Connector
[`app/eval/passageway_connector.py`](https://github.com/Gesetze-fuer-KI/gesetze-fuer-ki/blob/main/app/eval/passageway_connector.py)
gibt passageway jede Vorschrift aus diesem Index.

```bash
PW=/pfad/zu/passageway
cat > /tmp/passageway.toml <<EOF
[[connector]]
name = "bundesrecht"
command = ["$PW/.venv/bin/python", "-I", "$PWD/app/eval/passageway_connector.py"]
env = { GK_DB = "/tmp/gk.db" }
timeout = 600
EOF
$PW/.venv/bin/passageway eval app/eval/cases.toml --config /tmp/passageway.toml \
  --data-dir /tmp/pw-index --sweep 0.80,0.82,0.845,0.86 --include-cases --out /tmp/pw-report
```

Beim ersten Lauf lädt passageway das Sprachmodell herunter. Während der Index entsteht,
zeigt es an, wie weit es ist; der Bericht steht danach in `/tmp/pw-report/report.md`.
