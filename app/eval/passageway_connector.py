"""passageway connector for the comparison in docs/suche-vergleich.md: one item per norm of an index built by store.build."""

import hashlib
import re
import sqlite3

from passageway_sdk import Connector, SettingsError


def norm_url(quelle: str, enbez: str | None) -> str:
    # Same scheme as server.provision_url, so a case can expect "/ddg/__5.html".
    if enbez:
        if m := re.match(r"^§\s*(\d+[a-z]*)$", enbez):
            return f"{quelle}__{m.group(1)}.html"
        if m := re.match(r"^Art(?:ikel|\.)?\s*(\d+[a-z]*)$", enbez, re.I):
            return f"{quelle}art_{m.group(1)}.html"
    return quelle


class GesetzeConnector(Connector):
    name = "gesetze connector"

    def __init__(self, env):
        if not env.get("GK_DB"):
            raise SettingsError("GK_DB is required")
        self.db = sqlite3.connect(f"file:{env['GK_DB']}?mode=ro", uri=True)
        self.db.row_factory = sqlite3.Row

    def _rows(self, where: str = "", args: tuple = ()):
        return self.db.execute(
            "SELECT units.slug, units.unit_id, units.enbez, units.heading, units.breadcrumb, units.body,"
            " laws.abk, laws.titel, laws.quelle FROM units JOIN laws ON laws.slug = units.slug"
            f" WHERE units.kind = 'norm' AND (units.body <> '' OR units.heading <> '') {where}", args)

    @staticmethod
    def _version(r) -> str:
        return hashlib.sha1(f"{r['heading']}\0{r['breadcrumb']}\0{r['body']}".encode()).hexdigest()[:16]

    def versions(self):
        return {f"{r['slug']}/{r['unit_id']}": self._version(r) for r in self._rows()}

    def fetch(self, ids):
        out = []
        for item_id in ids:
            slug, unit_id = item_id.split("/", 1)
            for r in self._rows("AND units.slug = ? AND units.unit_id = ?", (slug, unit_id)):
                out.append({
                    "id": item_id,
                    "title": f"{r['heading']} {r['abk']}",
                    "url": norm_url(r["quelle"], r["enbez"]),
                    "version": self._version(r),
                    "path": [f"{r['abk']} {r['titel']}", *[p for p in r["breadcrumb"].split(" › ") if p]],
                    "labels": ["bund"],
                    "sections": [{"text": r["body"] or r["heading"]}],  # the heading is in the title already
                })
                break
        return out


if __name__ == "__main__":
    GesetzeConnector.main()
