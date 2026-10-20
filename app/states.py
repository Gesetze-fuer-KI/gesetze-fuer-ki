"""The 16 German states (Länder): which state law is integrated, and where the rest lives.

State law (Landesrecht) is mirrored from the states' official portals into one data repository
per state. Five states are integrated; for the others the portal forbids or reserves automated
use, and the tools answer with a short explanation and a link instead.
"""

from __future__ import annotations

from dataclasses import dataclass

CONTACT = "kontakt@gesetze-fuer-ki.de"
REPO_BASE = "https://github.com/Gesetze-fuer-KI/landesrecht-"

REASON_JURIS = "Das Landesportal erlaubt keinen automatischen Abruf."
REASON_NI = "Der Betreiber des Landesportals behält sich die Nutzung der Texte vor."

# Prefixes that are ignored when looking a state up by name (longest first).
PREFIXES = ("freie und hansestadt ", "freie hansestadt ", "freistaat ", "land ")


@dataclass(frozen=True)
class State:
    code: str
    name: str
    portal: str
    integrated: bool
    reason: str | None = None
    aliases: tuple[str, ...] = ()
    attribution: str | None = None

    @property
    def repo(self) -> str:
        return REPO_BASE + self.code.lower()


def _state(code: str, name: str, portal: str, aliases: tuple[str, ...] = (), **kw) -> State:
    return State(code=code, name=name, portal=portal, aliases=aliases, **kw)


STATES: dict[str, State] = {
    s.code: s
    for s in (
        _state("BW", "Baden-Württemberg", "https://www.landesrecht-bw.de", ("BaWü",),
               integrated=False, reason=REASON_JURIS),
        _state("BY", "Bayern", "https://www.gesetze-bayern.de", ("Freistaat Bayern",), integrated=True),
        _state("BE", "Berlin", "https://gesetze.berlin.de", integrated=False, reason=REASON_JURIS),
        _state("BB", "Brandenburg", "https://bravors.brandenburg.de", integrated=True),
        _state("HB", "Bremen", "https://www.transparenz.bremen.de", ("Freie Hansestadt Bremen",),
               integrated=True,
               attribution="Texte: Transparenzportal Bremen, Der Senator für Finanzen der Freien Hansestadt "
               "Bremen, Lizenz CC BY-NC-ND 3.0."),
        _state("HH", "Hamburg", "https://www.landesrecht-hamburg.de", ("Freie und Hansestadt Hamburg",),
               integrated=False, reason=REASON_JURIS),
        _state("HE", "Hessen", "https://www.rv.hessenrecht.hessen.de", integrated=False, reason=REASON_JURIS),
        _state("MV", "Mecklenburg-Vorpommern", "https://www.landesrecht-mv.de", ("Meck-Pomm",),
               integrated=False, reason=REASON_JURIS),
        _state("NI", "Niedersachsen", "https://voris.wolterskluwer-online.de",
               integrated=False, reason=REASON_NI),
        _state("NW", "Nordrhein-Westfalen", "https://recht.nrw.de", ("NRW",), integrated=True),
        _state("RP", "Rheinland-Pfalz", "https://www.landesrecht.rlp.de", integrated=False, reason=REASON_JURIS),
        _state("SL", "Saarland", "https://recht.saarland.de", integrated=False, reason=REASON_JURIS),
        _state("SN", "Sachsen", "https://www.revosax.sachsen.de", ("Freistaat Sachsen",), integrated=True),
        _state("ST", "Sachsen-Anhalt", "https://www.landesrecht.sachsen-anhalt.de",
               integrated=False, reason=REASON_JURIS),
        _state("SH", "Schleswig-Holstein", "https://www.gesetze-rechtsprechung.sh.juris.de",
               integrated=False, reason=REASON_JURIS),
        _state("TH", "Thüringen", "https://landesrecht.thueringen.de", ("Freistaat Thüringen",),
               integrated=False, reason=REASON_JURIS),
    )
}


def _normalize(text: str) -> str:
    text = " ".join(text.casefold().split())
    for prefix in PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


_LOOKUP: dict[str, State] = {
    _normalize(key): s for s in STATES.values() for key in (s.code, s.name, *s.aliases)
}


def find(text: str) -> State | None:
    """Look a state up by code, name or alias, ignoring case and prefixes like "Freistaat"."""
    return _LOOKUP.get(_normalize(text))


def not_integrated_text(state: State) -> str:
    """Explain, in German, why a state is missing and where its law can be read.

    Each URL ends its line: a period after it would end up in the link in many clients."""
    return (
        f"{state.name} ist noch nicht integriert. {state.reason}\n"
        f"Die Texte stehen auf dem Landesportal: {state.portal}\n"
        f"Mehr dazu: {state.repo}\n"
        f"Wer {state.name} braucht oder die Nutzung erlauben kann: {CONTACT}"
    )


def unknown_text(text: str) -> str:
    """Tell, in German, that a name is not a state and list the valid ones."""
    names = ", ".join(s.name for s in STATES.values())
    return f"„{text}“ ist kein Bundesland. Verfügbare Bundesländer: {names}."
