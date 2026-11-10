# Wie gut die Suche findet

Wenn Claude eine Vorschrift sucht, ruft es `gesetze_durchsuchen` auf. Diese Seite
misst, wie oft dabei die richtige Vorschrift herauskommt. Sie ist die Grundlage, um
die Suche zu verbessern: Erst wird gemessen, dann geändert, dann wieder gemessen.

## So funktioniert die Suche heute

Die Suche vergleicht **Wörter, keine Bedeutungen**. Sie findet einen Paragrafen nur,
wenn die gesuchten Wörter (oder Wörter, die mit ihnen anfangen) darin vorkommen:

- Füllwörter wie „der“, „ich“ oder „muss“ fallen weg, die übrigen Wörter werden auf
  ihren Stamm gekürzt („anzeigen“ wird zu „anzeig“ und findet so auch „Anzeigepflicht“).
- Zuerst sucht sie Paragrafen, die **alle** Wörter enthalten. Sind das zu wenige,
  sucht sie Paragrafen mit **irgendeinem** der Wörter.
- Ein Treffer in der Überschrift zählt mehr als einer im Text, und große Gesetze wie
  das BGB bekommen einen kleinen Vorsprung vor Spezialverordnungen.

Deshalb bittet der Server Claude, mit den Wörtern des Gesetzes zu suchen
(„Informationspflichten Diensteanbieter“ statt „Impressum“).

## Die Messung

54 Fragen mit bekannter Antwort und 5 Fragen, auf die es im Gesetz keine Antwort gibt:

- **Alltagssprache (46 Fragen):** so, wie Menschen fragen, etwa „Was muss ins
  Impressum meiner Webseite?“ (richtig: § 5 DDG) oder „Wer bekommt Bürgergeld?“
  (richtig: § 19 SGB II).
- **Fachsprache (8 Fragen):** mit den Wörtern des Gesetzes, etwa „Haftung des
  Tierhalters“ (richtig: § 833 BGB).
- **Ohne Antwort (5 Fragen):** etwa „Rezept für Lasagne“. Hier sollte die Suche
  nichts liefern.

Gemessen wird, an welcher Stelle die richtige Vorschrift unter den Treffern steht:

| Wert | Bedeutung |
|---|---|
| Treffer auf Platz 1 | Die richtige Vorschrift steht ganz oben. |
| Treffer unter den ersten 3 | Sie steht unter den ersten drei Treffern. |
| Treffer unter den ersten 8 | Sie steht unter den acht Treffern, die die Suche standardmäßig liefert. |
| MRR | Durchschnitt aus 1 / Platz (Platz 1 zählt 1, Platz 2 zählt ½, nicht gefunden 0). 1 wäre perfekt. |

Die Fragen stehen in [`app/eval/cases.toml`](https://github.com/Gesetze-fuer-KI/gesetze-fuer-ki/blob/main/app/eval/cases.toml),
das Messprogramm in [`app/eval/baseline.py`](https://github.com/Gesetze-fuer-KI/gesetze-fuer-ki/blob/main/app/eval/baseline.py).

## Ergebnis: die heutige Suche

Gemessen am 6. November 2026 auf dem Bundesrecht mit Stand 5. November 2026
(106.468 Vorschriften aus 6.144 Gesetzen und Verordnungen).

| Fragen | Platz 1 | Unter den ersten 3 | Unter den ersten 8 | MRR |
|---|---|---|---|---|
| Alltagssprache (46) | 0 % | 4 % | 13 % | 0,03 |
| Fachsprache (8) | 63 % | 88 % | 100 % | 0,76 |
| Alle (54) | 9 % | 17 % | 26 % | 0,14 |

- **Ohne Antwort:** Die Suche liefert bei allen 5 Fragen trotzdem Treffer. Sie kann
  nicht erkennen, dass nichts passt.
- **Antwortzeit:** Die Hälfte der Suchen dauert unter 20 ms, 95 % unter 500 ms. Langsam
  sind die Fälle, in denen sie auf „irgendeines der Wörter“ ausweicht.

**Was das heißt:** Mit den Wörtern des Gesetzes findet die Suche fast immer die
richtige Vorschrift. In Alltagssprache findet sie sie fast nie, weil Wörter wie
„Impressum“, „Kaution“, „Minijob“ oder „Schwarzfahren“ im Gesetz nicht vorkommen. Dann
gewinnen sehr lange Anlagen, die fast jedes Wort enthalten (etwa Anlage 1 der
Einbürgerungstestverordnung). In der Praxis übersetzt Claude die Frage meist selbst in
die Sprache des Gesetzes, bevor es sucht. Die Alltagssprache ist also der ungünstigste
Fall, zeigt aber, wie viel davon abhängt, dass Claude die richtigen Fachwörter errät.
Wie viel eine Suche nach Bedeutung daran ändert und wie gut die Suche ist, wenn Claude
die Frage vorher umformuliert, steht in
[Suche nach Bedeutung: der Vergleich](suche-vergleich.md).

??? note "Alle Fragen im Einzelnen"

    Platz der richtigen Vorschrift unter den ersten 8 Treffern; „–“ heißt nicht gefunden.

    | Frage | Richtig | Platz |
    |---|---|---|
    | Was muss ins Impressum meiner Webseite? | § 5 DDG | – |
    | Ab welchem Umsatz muss eine kleine Firma Umsatzsteuer zahlen? | § 19 UStG | – |
    | Wie melde ich ein Gewerbe an? | § 14 GewO | – |
    | Wie lange ist die Kündigungsfrist für meine Mietwohnung? | § 573c BGB | – |
    | Wie viele Urlaubstage stehen mir mindestens zu? | § 3 BUrlG | – |
    | Wie viele Stunden darf ich am Tag höchstens arbeiten? | § 3 ArbZG | – |
    | Kann ich online gekaufte Sachen zurückschicken? | § 355 / § 312g BGB | – |
    | Wie hoch darf die Kaution für eine Wohnung sein? | § 551 BGB | – |
    | Nach wie vielen Jahren muss ich eine offene Rechnung nicht mehr bezahlen? | § 195 / § 199 BGB | – |
    | Mit welcher Frist kann mein Chef mir kündigen? | § 622 BGB | – |
    | Darf mein Vermieter einfach die Miete erhöhen? | § 558 BGB | 8 |
    | Wie viele Monate bekomme ich Elterngeld? | § 4 BEEG | 7 |
    | Wann darf mein Arbeitgeber mich nicht einfach rauswerfen? | § 1 KSchG | – |
    | Wie lange habe ich Garantie auf ein gekauftes Handy? | § 438 BGB | – |
    | Muss ich als Angestellter eine Steuererklärung machen? | § 46 EStG / § 149 AO | – |
    | Wie viel darf ich im Minijob verdienen? | § 8 SGB IV | – |
    | Wer erbt, wenn es kein Testament gibt? | § 1924 BGB | – |
    | Wie viel bekommen enterbte Kinder vom Erbe? | § 2303 BGB | – |
    | Bekomme ich weiter Lohn, wenn ich krank bin? | § 3 EntgFG | – |
    | Ab wann vor der Geburt darf ich nicht mehr arbeiten? | § 3 MuSchG | – |
    | Darf ein Laden mich mit Kameras filmen? | § 4 BDSG | – |
    | Wer zahlt, wenn ein Hund jemanden beißt? | § 833 BGB | – |
    | Wer haftet für einen Autounfall? | § 7 StVG | – |
    | Wie lange dauert die Probezeit in der Lehre? | § 20 BBiG | 6 |
    | Ab welchem Alter ist man erwachsen? | § 2 BGB | – |
    | Wie viel Kindergeld gibt es pro Kind? | § 66 EStG | 3 |
    | Wie hoch ist der Mindestlohn? | § 1 MiLoG | – |
    | Ab wie vielen Mitarbeitern kann man einen Betriebsrat gründen? | § 1 BetrVG | – |
    | Die Äste vom Baum des Nachbarn hängen in meinen Garten | § 910 BGB | 3 |
    | Ich habe eine Geldbörse gefunden, was muss ich tun? | § 965 BGB | – |
    | Ist Schwarzfahren strafbar? | § 265a StGB | – |
    | Jemand hat mich beschimpft, ist das strafbar? | § 185 StGB | – |
    | Personalausweis verloren, was muss ich machen? | § 27 PAuswG | – |
    | Kann ich erfahren, welche Daten eine Firma über mich hat? | § 34 BDSG | – |
    | Wie lange muss ich Belege für das Finanzamt aufheben? | § 147 AO / § 257 HGB | – |
    | Was muss alles auf einer Rechnung stehen? | § 14 UStG | – |
    | Wie lange muss man getrennt leben bis zur Scheidung? | § 1566 BGB | 8 |
    | Wie viel Unterhalt muss ich für mein Kind zahlen? | § 1612a / § 1601 BGB | – |
    | Hotel im Urlaub war dreckig, bekomme ich Geld vom Reiseveranstalter zurück? | § 651m BGB | – |
    | Wie lange dürfen Jugendliche arbeiten? | § 8 JArbSchG | – |
    | Wie lange bekomme ich Arbeitslosengeld? | § 147 SGB III | – |
    | Wer bekommt Bürgergeld? | § 19 SGB II | – |
    | Mit wie viel Jahren kann ich in Rente gehen? | § 35 SGB VI | – |
    | Wie wechsle ich meine Krankenkasse? | § 175 SGB V | – |
    | Wie viel Alkohol darf ich beim Autofahren getrunken haben? | § 24a StVG | – |
    | Ich bin umgezogen, muss ich mich ummelden? | § 17 BMG | – |
    | Informationspflichten Diensteanbieter | § 5 DDG | 3 |
    | Kleinunternehmer Umsatz | § 19 UStG | 4 |
    | Widerrufsrecht Verbraucherverträge | § 355 BGB | 1 |
    | Haftung des Tierhalters | § 833 BGB | 1 |
    | Erschleichen von Leistungen | § 265a StGB | 1 |
    | Fristen der ordentlichen Kündigung Wohnraum | § 573c BGB | 1 |
    | Entgeltfortzahlung im Krankheitsfall | § 3 EntgFG | 2 |
    | Regelaltersrente | § 35 SGB VI | 1 |

## Selbst nachmessen

```bash
git clone --depth 1 https://github.com/Gesetze-fuer-KI/bundesrecht.git /tmp/bundesrecht
cd app
uv run python -c "import store; from pathlib import Path; store.build(Path('/tmp/bundesrecht'), Path('/tmp/gk.db'))"
uv run python eval/baseline.py eval/cases.toml /tmp/gk.db
```
