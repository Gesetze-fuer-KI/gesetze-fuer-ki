"""Write the docs' Bundesländer pages (docs/laender/) from the landesrecht-<code> repositories.

    cd app && uv run python laender_pages.py

Each state's README is the source: for a state that is not integrated it says why and carries the complaint template
(addressee, mail, letter), which the page shows with a button that opens the mail prefilled. Whether an integrated
state is complete comes from its .sync/state.json. Run it after changing a README or when a state's first pass is
done, then commit the pages. The nav in mkdocs.yml lists the pages by name.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote

import httpx

import states

OUT = Path(__file__).resolve().parent.parent / "docs" / "laender"
RAW = "https://raw.githubusercontent.com/Gesetze-fuer-KI/landesrecht-{code}/main/{path}"
REPO = "https://github.com/Gesetze-fuer-KI/landesrecht-"
SLUG = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", " ": "-"}
# What the overview says about access for the states we mirror; the others take states.State.reason.
ALLOWED = {
    "BY": "Nutzungshinweise erlauben die Weiterverwendung",
    "BB": "erlaubt (ein Abruf alle 20 Sekunden)",
    "NW": "kein Verbot",
    "SN": "kein Verbot",
}
# The same for the states we cannot mirror, by their states.State.reason.
BLOCKED = {
    states.REASON_JURIS: "Portal sperrt automatische Abrufe (robots.txt)",
    states.REASON_NI: "Betreiber behält sich die Nutzung der Texte vor",
    states.REASON_HB: "Portal sperrt Abrufe aus Rechenzentren",
}
ICON = {"yes": "✅ enthalten", "building": "⏳ im Aufbau", "no": "❌ nicht erlaubt"}


def slug(name: str) -> str:
    return "".join(SLUG.get(c, c) for c in name.lower())


def fetch(client: httpx.Client, code: str, path: str) -> str | None:
    resp = client.get(RAW.format(code=code.lower(), path=path))
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text


def section(text: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |^---|\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def missing_page(code: str, name: str, text: str) -> str:
    text = re.sub(r"<!--.*?-->\s*", "", text, flags=re.S)
    body = text.split("\n", 1)[1] if text.startswith("# ") else text
    intro = body.split("## Beschwerde schreiben")[0].strip()
    # The robots.txt quote is long; fold it.
    def fold(m: re.Match) -> str:
        block = "\n".join("    " + line if line else "" for line in m.group(0).splitlines())
        return '??? quote "Auszug aus der robots.txt"\n\n' + block + "\n"
    intro = re.sub(r"^```\n.*?^```", fold, intro, flags=re.S | re.M)
    complaint = section(text, "Beschwerde schreiben")
    to = re.search(r"\*\*An:\*\* (.+?) – (\S+@\S+?)(?:<br>)?$", complaint, re.M)
    subject = re.search(r"\*\*Betreff:\*\* (.+)$", complaint, re.M).group(1).strip()
    letter_md = "\n".join(l for l in complaint.splitlines() if l.startswith(">")).replace("\\\n", "<br>\n")
    letter = "\n".join(re.sub(r"^> ?", "", l) for l in letter_md.splitlines()).replace("\\\n", "\n").strip()
    who, mail = to.group(1).strip(), to.group(2).strip()
    note = ""
    nm = re.search(r"^\*\((.+?)\)\*(?:<br>)?$", complaint, re.M)
    if nm:
        note = " *(" + nm.group(1) + ")*"
    mailto = f"mailto:{mail}?subject={quote(subject)}&body={quote(letter)}"
    portal = re.search(r"\[Landesrecht .+? auf dem Landesportal\]\((\S+?)\)", text)
    portal_url = portal.group(1) if portal else ""
    return f"""# {name}

{intro}

## Sich einsetzen

Schreiben Sie der zuständigen Stelle. Der Text unten ist eine Vorlage; passen Sie ihn gern an.

**An:** {who}<br>
**Mail:** [{mail}](mailto:{mail}){note}<br>
**Betreff:** {subject}

{letter_md}

[Mail mit dieser Vorlage öffnen]({mailto}){{ .md-button .md-button--primary }}

Gern auch an uns: [kontakt@gesetze-fuer-ki.de](mailto:kontakt@gesetze-fuer-ki.de). Die Begründung mit Quellen steht im
Repository [landesrecht-{code}]({REPO}{code}).

## Bis dahin

Das Landesrecht von {name} steht auf dem [Landesportal]({portal_url}), lesbar von Hand im Browser.
"""


def integrated_page(code: str, name: str, status: str, text: str) -> str:
    source = section(text, "Quelle")
    licence = section(text, "Herkunft und Lizenz").split("\n\nFehler der Umwandlung")[0]
    licence = licence.replace("](LIZENZ.md)", f"]({REPO}{code}/blob/main/LIZENZ.md)")
    sync = section(text, "Wie der Abgleich läuft")
    if status == "building":
        head = f"""!!! info "Im Aufbau"

    Das Landesrecht von {name} wird gerade zum ersten Mal vollständig abgeglichen und ist danach durchsuchbar."""
    else:
        head = f"""!!! success "Enthalten"

    Alle Gesetze und Rechtsverordnungen von {name} in der heute geltenden Fassung, jede Nacht abgeglichen."""
    rhythm = ("Das Portal erlaubt nur einen Abruf alle 20 Sekunden und zeigt nicht an, was sich geändert hat. Ein "
              "vollständiger Durchgang dauert deshalb etwa zwei Nächte; ein Text kann bis zu zwei Tage alt sein."
              if code == "bb" else
              "Jede Nacht holt der Abgleich, was sich auf dem Portal geändert hat.")
    return f"""# {name}

{head}

## Quelle

{source}

## Aktualität

{rhythm} Ihr Assistent nennt zu jeder Vorschrift den Stand und verlinkt die Fassung auf dem Portal.

## Lizenz

{licence}

## Daten

Alle Texte als Markdown mit Änderungshistorie: [landesrecht-{code}]({REPO}{code}).
"""


INDEX = """# Bundesländer

Landesrecht übernimmt Gesetze für KI nur, wo das Portal des Landes den automatischen Abruf erlaubt. Jedes Land hat eine
eigene Seite: bei den enthaltenen die Quelle und die Lizenz, bei den fehlenden, woran es scheitert, und eine Vorlage für
eine Mail an die zuständige Stelle.

| Land | Stand | Abruf |
|---|---|---|
{rows}

**Enthalten** heißt: vollständig abgeglichen und durchsuchbar. **Im Aufbau** heißt: Der erste Abgleich läuft noch.
**Nicht erlaubt** heißt: Das Land lässt den Abruf nicht zu; die Gesetze stehen nur auf dem Landesportal.

!!! info "Ihr Land fehlt?"

    Auf der Seite Ihres Landes steht, an wen Sie schreiben können, mit einer Vorlage. Gern auch an uns:
    [kontakt@gesetze-fuer-ki.de](mailto:kontakt@gesetze-fuer-ki.de).

    Und an die Länder: Wenn Sie den automatischen Abruf Ihres Portals erlauben oder die Texte als Download anbieten
    können, melden Sie sich bitte unter derselben Adresse.
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for state in sorted(states.STATES.values(), key=lambda s: s.name):
            code = state.code.lower()
            readme = fetch(client, code, "README.md") or ""
            if not state.integrated:
                status, why = "no", BLOCKED[state.reason]
                page = missing_page(code, state.name, readme)
            else:
                state_file = fetch(client, code, ".sync/state.json")
                complete = bool(state_file and json.loads(state_file).get("complete"))
                status, why = ("yes" if complete else "building"), ALLOWED[state.code]
                page = integrated_page(code, state.name, status, readme)
            name = slug(state.name)
            (OUT / f"{name}.md").write_text(re.sub(r"\n{3,}", "\n\n", page), encoding="utf-8")
            rows.append(f"| [{state.name}]({name}.md) | {ICON[status]} | {why} |")
    (OUT / "index.md").write_text(INDEX.format(rows="\n".join(rows)), encoding="utf-8")
    print(f"wrote {len(rows) + 1} pages to {OUT}")


if __name__ == "__main__":
    main()
