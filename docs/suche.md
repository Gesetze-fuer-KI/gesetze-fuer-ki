# Wie gut die Suche findet

Wenn Claude eine Vorschrift sucht, ruft es `gesetze_durchsuchen` auf. Diese Seite misst,
wie oft dabei das richtige Gesetz und die richtige Vorschrift herauskommen. Sie ist der
Maßstab, um die Suche zu verbessern: Erst wird gemessen, dann geändert, dann wieder
gemessen.

## So sucht Claude

1. **Claude formuliert die Frage zuerst um.** Es sucht nicht mit den Worten des Nutzers,
   sondern mit denen des Gesetzes: Aus „Wie hoch darf die Kaution sein?“ wird
   „Mietsicherheit Monatsmiete“, aus „Ist Schwarzfahren strafbar?“ wird „Erschleichen von
   Leistungen Beförderung“. Der Server bittet Claude darum, und Claude kennt diese Wörter
   aus seinem Training.
2. **Die Suche liefert bis zu 8 Treffer**, und Claude erkennt darunter das passende
   Gesetz. Steht die richtige Vorschrift nicht ganz oben, sucht es mit `law` gezielt in
   diesem Gesetz weiter oder liest dessen Gliederung.
3. **Claude liest den Wortlaut** mit `vorschrift_lesen`, folgt den Verweisen und antwortet
   mit Stand und Link.

## Ergebnis: Claude findet fast immer das richtige Gesetz

Mit umformulierten Fragen steht das **richtige Gesetz in rund 9 von 10 Fällen unter den
ersten 3 Treffern**, auch bei seltenen Verordnungen, die kaum jemand kennt. Die genaue
Vorschrift steht seltener ganz oben; von dort ist sie aber einen Schritt entfernt.

<!-- chart:finden -->

<!-- table:finden -->

Wörtlich gesucht, also mit den Worten des Nutzers, findet die Suche viel weniger: Wörter
wie „Impressum“, „Kaution“ oder „Minijob“ stehen in keinem Gesetz. Das ist der Grund,
warum Claude zuerst umformuliert. Wie die Fragen entstanden sind, steht unten in
[Die Messung](#die-messung).

## Warum es diesen Server trotzdem braucht

Wenn Claude die Wörter des Gesetzes kennt, kennt es dann nicht auch die Antwort? Oft weiß
Claude, **wo** eine Regel steht. Was dort **heute genau** steht, weiß es nicht sicher:

- **Gesetze ändern sich, Claudes Wissen nicht.** Beispiel § 19 UStG: Bis 2024 lagen die
  Grenzen für Kleinunternehmer bei 22.000 und 50.000 Euro. Heute stehen dort 25.000 und
  100.000 Euro, und die Regel selbst ist eine andere (die Umsätze sind jetzt steuerfrei).
  Aus dem Gedächtnis nennt Claude die alten Zahlen, und zwar überzeugt. Mit
  `vorschrift_lesen` nennt es den geltenden Wortlaut, mit Stand und Link.
- **Das Gedächtnis ist in den Einzelheiten ungenau.** Claude erinnert sich, dass es eine
  Regel gibt, aber nicht an jeden Absatz, jede Ausnahme und jeden Verweis. Für eine
  Antwort, die man nachprüfen kann, braucht es den Text selbst.
- **Die meisten Gesetze sind selten gefragt.** Von den 6.144 Gesetzen und Verordnungen
  kennt Claude viele nur ungefähr oder gar nicht. Gerade dort findet erst die Suche das
  richtige Gesetz.
- **Manches kann Claude gar nicht wissen:** das Landesrecht der Länder und wie sich ein
  Gesetz geändert hat (`aenderungen_anzeigen`, `date=`).

## So funktioniert die Suche

Die Suche vergleicht **Wörter, keine Bedeutungen**. Sie findet einen Paragrafen nur,
wenn die gesuchten Wörter (oder Wörter, die mit ihnen anfangen) darin vorkommen:

- Füllwörter wie „der“, „ich“ oder „muss“ fallen weg, die übrigen Wörter werden auf
  ihren Stamm gekürzt („anzeigen“ wird zu „anzeig“ und findet so auch „Anzeigepflicht“).
- Zuerst sucht sie Paragrafen, die **alle** Wörter enthalten. Sind das zu wenige,
  sucht sie Paragrafen mit **irgendeinem** der Wörter.
- Ein Treffer in der Überschrift zählt mehr als einer im Text, und große Gesetze wie
  das BGB bekommen einen kleinen Vorsprung vor Spezialverordnungen.

## Die Messung

Vier Fragensätze mit bekannter Antwort, alle zum Bundesrecht:

- **Alltagsfragen (46):** so, wie Menschen fragen, etwa „Was muss ins Impressum meiner
  Webseite?“ (richtig: § 5 DDG). Dazu 8 Fragen in Fachsprache, etwa „Haftung des
  Tierhalters“ (§ 833 BGB), und 5 Fragen, auf die es im Gesetz keine Antwort gibt, etwa
  „Rezept für Lasagne“.
- **Alltagsfragen, von Claude umformuliert (46):** dieselben Fragen, so, wie Claude sie an
  die Suche schickt.
- **Seltene Gesetze (35):** Aus 60 zufällig gezogenen kleineren Gesetzen wurde je eine
  Vorschrift gezogen, die bekanntesten Gesetze ausgenommen. Zu 35 davon hat Claude eine
  Frage geschrieben, wie sie ein Mensch stellen würde, etwa „Ich arbeite in einem
  Schlachtbetrieb. Muss ich meine Schutzkleidung und Messer selbst bezahlen?“ (§ 4 GSA
  Fleisch).
- **Seltene Gesetze, von Claude umformuliert (35).**

Umformuliert hat jeweils ein eigenes Claude, das nur die Fragen und die Anleitung des
Servers kannte, nicht die richtigen Antworten. So bleibt die Messung ehrlich.

| Wert | Bedeutung |
|---|---|
| Richtige Vorschrift auf Platz 1 | Sie steht ganz oben. |
| … unter den ersten 3 / 8 | Sie steht unter den ersten drei Treffern / unter den acht, die die Suche standardmäßig liefert. |
| Richtiges Gesetz unter den ersten 3 | Unter den ersten drei Treffern ist eine Vorschrift aus dem richtigen Gesetz, vielleicht nicht die gesuchte. Von dort findet Claude sie mit einer Suche im Gesetz. |

## Verlauf

Jede neue Messung kommt hier hinzu. So zeigt sich, ob eine Änderung an der Suche hilft
oder schadet.

<!-- chart:verlauf -->

<!-- table:verlauf -->

## Selbst nachmessen

Die Fragensätze liegen in
[`app/eval/`](https://github.com/Gesetze-fuer-KI/gesetze-fuer-ki/tree/main/app/eval):
`cases.toml`, `cases_rewritten.toml`, `cases_rare.toml` und `cases_rare_rewritten.toml`.

```bash
git clone --depth 1 https://github.com/Gesetze-fuer-KI/bundesrecht.git /tmp/bundesrecht
cd app
uv run python -c "import store; from pathlib import Path; store.build(Path('/tmp/bundesrecht'), Path('/tmp/gk.db'))"
uv run python eval/baseline.py eval/cases_rewritten.toml /tmp/gk.db
```

Mit `--history ../docs/suche.history.json --stand JJJJ-MM-TT` kommt die Messung in die
Grafiken dieser Seite.
