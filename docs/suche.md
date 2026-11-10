# Wie gut die Suche findet

Claude sucht nicht mit den Worten des Nutzers. Es formuliert die Frage zuerst in die
Sprache des Gesetzes um: Aus „Wie hoch darf die Kaution sein?“ wird „Mietsicherheit
Monatsmiete“, aus „Ist Schwarzfahren strafbar?“ wird „Erschleichen von Leistungen“. Damit
sucht es (wie die Suche arbeitet, steht unter [Werkzeuge](werkzeuge.md#wie-die-suche-funktioniert)),
und unter den Treffern erkennt es das passende Gesetz. Dann liest es den Wortlaut der
Vorschrift. Diese Seite misst, wie oft dabei das richtige Gesetz und die richtige
Vorschrift herauskommen.

## Ergebnis: Claude findet fast immer das richtige Gesetz

Mit umformulierten Fragen steht das **richtige Gesetz in rund 9 von 10 Fällen unter den
ersten 3 Treffern**, auch bei seltenen Verordnungen. Die genaue Vorschrift steht nicht
immer ganz oben, ist von dort aber einen Schritt entfernt: Claude sucht mit `law` gezielt
in diesem Gesetz weiter oder liest seine Gliederung. Die blassen Balken zeigen dieselben
Fragen wörtlich gesucht: Wörter wie „Impressum“ oder „Kaution“ stehen in keinem Gesetz,
deshalb formuliert Claude um.

<!-- chart:finden -->

<!-- table:finden -->

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

## Die Messung

- **Alltagsfragen (46):** so, wie Menschen fragen, etwa „Was muss ins Impressum meiner
  Webseite?“ (richtig: § 5 DDG). Dazu 8 Fragen in Fachsprache, etwa „Haftung des
  Tierhalters“ (§ 833 BGB).
- **Seltene Gesetze (35):** Aus 60 zufällig gezogenen kleineren Gesetzen wurde je eine
  Vorschrift gezogen, die bekanntesten Gesetze ausgenommen. Zu 35 davon hat Claude eine
  Frage geschrieben, wie sie ein Mensch stellen würde, etwa „Ich arbeite in einem
  Schlachtbetrieb. Muss ich meine Schutzkleidung und Messer selbst bezahlen?“ (§ 4 GSA
  Fleisch).

Beide Sätze hat ein eigenes Claude umformuliert, das nur die Fragen und die Anleitung des
Servers kannte, nicht die richtigen Antworten. So bleibt die Messung ehrlich.

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
