"""Today's search (store.Store.search) on a cases file: where the expected provision ranks.

    cd app && uv run python eval/baseline.py eval/cases.toml INDEX.db [--history ../docs/suche.history.json --stand DATE]

Law@3 counts a question whose expected law is among the first three hits, even at another §: from there
Claude reads the law's outline or searches inside it. With --history, one entry per question group is appended
to the file the docs draw their charts and tables from (docs_hooks/charts.py).

INDEX.db is built by store.build from a clone of the data repo.
"""

import argparse
import json
import sys
import time
import tomllib
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402
import store  # noqa: E402

LIMIT = 8


def run(cases: list[dict], s: store.Store) -> list[dict]:
    rows = []
    for c in cases:
        t = time.perf_counter()
        hits = s.search(c["query"], limit=LIMIT)
        ms = (time.perf_counter() - t) * 1000
        urls = [server.provision_url(dict(h), h["enbez"]) for h in hits]
        expect = c.get("expect", [])
        rank = next((i + 1 for i, u in enumerate(urls) if any(e in u for e in expect)), None)
        law3 = any(e.split("__")[0] in u for e in expect for u in urls[:3])
        rows.append({"group": c.get("group", "leer"), "query": c["query"], "rank": rank, "hits": len(hits),
                     "top": [f"{h['abk']} {h['enbez']}" for h in hits[:3]], "law3": law3, "ms": ms})
    return rows


def percentile(values: list[float], p: float) -> float:
    values = sorted(values)
    return round(values[min(int(len(values) * p), len(values) - 1)], 1)


def entry(group: str, rows: list[dict]) -> dict:
    """One history entry: the rates of an answerable group, or the silence of the unanswerable one."""
    n = len(rows)
    out = {"group": group, "search": "heute", "n": n,
           "p50_ms": percentile([r["ms"] for r in rows], 0.5), "p95_ms": percentile([r["ms"] for r in rows], 0.95)}
    if group == "leer":
        out["silent"] = sum(r["hits"] == 0 for r in rows)
        return out
    ranks = [r["rank"] for r in rows]
    out |= {"hit_at_1": sum(x == 1 for x in ranks), "hit_at_3": sum(x is not None and x <= 3 for x in ranks),
            "hit_at_8": sum(x is not None for x in ranks), "law_at_3": sum(r["law3"] for r in rows),
            "mrr": round(sum(1 / x for x in ranks if x) / n, 3)}
    return out


def line(e: dict) -> str:
    if e["group"] == "leer":
        return f"leer    silence {e['silent']}/{e['n']}"
    n = e["n"]
    return (f"{e['group']:7} n={n}  Hit@1 {e['hit_at_1'] / n:.1%}  Hit@3 {e['hit_at_3'] / n:.1%}  "
            f"Hit@8 {e['hit_at_8'] / n:.1%}  MRR {e['mrr']:.3f}  Law@3 {e['law_at_3'] / n:.1%}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("cases", type=Path)
    p.add_argument("index", type=Path)
    p.add_argument("--history", type=Path, help="append one entry per group to this JSON file")
    p.add_argument("--stand", help="the data's date (YYYY-MM-DD), recorded with --history")
    args = p.parse_args()
    rows = run(tomllib.loads(args.cases.read_text())["case"], store.Store(args.index))
    groups = sorted({r["group"] for r in rows}, key=lambda g: g == "leer")
    entries = [entry(g, [r for r in rows if r["group"] == g]) for g in groups]
    for e in entries:
        print(line(e))
    times = [r["ms"] for r in rows]
    print(f"latency p50 {percentile(times, 0.5)} ms  p95 {percentile(times, 0.95)} ms")
    print()
    for r in rows:
        print(f"{r['group']:6} {str(r['rank'] or '-'):>2}  {r['query']}  ->  {', '.join(r['top'])}")
    if args.history:
        history = json.loads(args.history.read_text()) if args.history.exists() else []
        today = date.today().isoformat()
        history += [{"date": today, "stand": args.stand, **e} for e in entries]
        args.history.write_text(json.dumps(history, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
