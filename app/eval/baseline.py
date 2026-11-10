"""Today's search (store.Store.search) on a cases file, scored like passageway eval.

    cd app && uv run python eval/baseline.py eval/cases.toml INDEX.db

Law@3 counts a question whose expected law is among the first three hits, even at another §: from there
Claude reads the law's outline or searches inside it.

INDEX.db is built by store.build from a clone of the data repo.
"""

import sys
import time
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402
import store  # noqa: E402

cases = tomllib.loads(Path(sys.argv[1]).read_text())["case"]
s = store.Store(Path(sys.argv[2]))
limit = 8
rows_out, times = [], []
for c in cases:
    t = time.perf_counter()
    hits = s.search(c["query"], limit=limit)
    times.append((time.perf_counter() - t) * 1000)
    urls = [server.provision_url(dict(h), h["enbez"]) for h in hits]
    expect = c.get("expect", [])
    rank = next((i + 1 for i, u in enumerate(urls) if any(e in u for e in expect)), None)
    law3 = any(e.split("__")[0] in u for e in expect for u in urls[:3])
    rows_out.append((c.get("group", "leer"), c["query"], rank, len(hits),
                     [f"{h['abk']} {h['enbez']}" for h in hits[:3]], law3))


def score(rows):
    ans = [r for r in rows if r[0] != "leer"]
    if not ans:
        return ""
    h1 = sum(r[2] == 1 for r in ans) / len(ans)
    h3 = sum(r[2] is not None and r[2] <= 3 for r in ans) / len(ans)
    h8 = sum(r[2] is not None for r in ans) / len(ans)
    mrr = sum(1 / r[2] for r in ans if r[2]) / len(ans)
    law3 = sum(r[5] for r in ans) / len(ans)
    return f"n={len(ans)}  Hit@1 {h1:.1%}  Hit@3 {h3:.1%}  Hit@8 {h8:.1%}  MRR {mrr:.3f}  Law@3 {law3:.1%}"


groups = sorted({r[0] for r in rows_out} - {"leer"})
for g in groups:
    print(f"{g:7} {score([r for r in rows_out if r[0] == g])}")
if len(groups) > 1:
    print(f"{'gesamt':7} {score(rows_out)}")
empty = [r for r in rows_out if r[0] == "leer"]
if empty:
    print(f"leer    silence {sum(r[3] == 0 for r in empty)}/{len(empty)}")
times.sort()
print(f"latency p50 {times[len(times) // 2]:.1f} ms  p95 {times[int(len(times) * 0.95)]:.1f} ms")
print()
for g, q, rank, n, top, _ in rows_out:
    print(f"{g:6} {str(rank or '-'):>2}  {q}  ->  {', '.join(top)}")
