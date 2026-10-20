"""Render a state law (Landesrecht) in the same Markdown format as the federal laws.

The output follows `convert.convert`: YAML front matter, a title line, Stand and Quelle,
then every unit preceded by its marker comment, so `store.split_law` reads it unchanged.
"""

from __future__ import annotations

import yaml

import states
from store import Unit

FRONT_KEYS = ("land", "abkuerzung", "titel", "kurztitel", "stand", "gilt_ab", "naechste_fassung_ab", "quelle")


def render(front: dict, units: list[Unit]) -> str:
    """The Markdown file for one state law."""
    meta = {k: front[k] for k in FRONT_KEYS if front.get(k)}
    title, abk = front["titel"], front["abkuerzung"]
    out = ["---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=1000) + "---"]
    out.append(f"# {title}" + (f" ({abk})" if abk and abk != title else ""))
    if front.get("stand"):
        out.append(f"Stand: {front['stand']}")
    out.append(f"Quelle: <{front['quelle']}>")
    out.append("Nichtamtliche Fassung des Landesportals.")
    state = states.STATES.get(front["land"])
    if state and state.attribution:
        out.append(state.attribution)

    level = 1  # heading level of the enclosing gliederung, as in convert.convert
    for u in units:
        if u.kind == "gliederung":
            level = min(1 + (u.ebene or 1), 5)
            out.append(f'<!-- gliederung id="{u.unit_id}" ebene="{u.ebene or 1}" -->\n{"#" * level} {u.heading}')
        else:
            out.append(f'<!-- norm id="{u.unit_id}" -->\n{"#" * min(level + 1, 6)} {u.heading}')
        if u.body:
            out.append(u.body)
    return "\n\n".join(out).rstrip() + "\n"
