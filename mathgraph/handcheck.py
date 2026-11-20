"""Hand check of Lean reference extraction (mathgraph-ydf): the pre-registered
sample, and the score of its blind judgments.

    python -m mathgraph.handcheck sample OUT.json    # the 50 test bodies and their candidates
    python -m mathgraph.handcheck score JUDGED.json  # precision and recall of both matchers

P is the set of gold declarations of the anchored statements (724, as in
mathgraph-fxh). fxh's sample, Random(0).sample(sorted(P), 50), was ydf's
development set; the test set is Random(20261120).sample(sorted(P - dev), 50).
A body's candidates are the union of both matchers' references, self excluded.
The judge sees them without the matcher labels and marks one genuine when the
body refers to that declaration under Lean name resolution. JUDGED.json is
OUT.json with `genuine` (and a `note`) filled in on every candidate.
"""

from __future__ import annotations

import json
import os
import random
import sys

from .bench_pretrained import wilson
from .complete import DATA, PilotRefs, blueprint, lean_bodies, lean_files, load_rows, neighbourhoods
from .leanrefs import Mathlib, Project


def split(P: set) -> tuple[list, list]:
    dev = random.Random(0).sample(sorted(P), 50)
    return dev, random.Random(20261120).sample(sorted(P - set(dev)), 50)


def sample(out_path: str) -> None:
    art_dir, bp_dir = os.path.join(DATA, "artifacts"), os.path.join(DATA, "blueprints")
    rows = load_rows(art_dir)
    decls = {d["name"]: d for d in rows}
    bodies, where = lean_bodies(bp_dir, rows), lean_files(bp_dir)
    P, pilots = set(), {}
    for p in sorted({p for p, _ in bodies.values()}):
        pilots[p] = PilotRefs({n: b for n, (q, b) in bodies.items() if q == p})
        tags, uses, _ = blueprint(os.path.join(bp_dir, p))
        P.update(g for r in neighbourhoods(tags, uses, pilots[p])
                 if r["anchors"]["up"] + r["anchors"]["down"] for g in r["gold"])
    dev, test = split(P)
    ml, out = Mathlib(os.path.join(art_dir, "mathlib.jsonl")), []
    for p in sorted({bodies[n][0] for n in test}):
        files = {m: f for m, (q, f) in where.items() if q == p}
        proj = Project(files, ml)
        own = [d for d in rows if d["name"] in pilots[p] and where.get(d["module"], ("",))[0] == p]
        new = proj.refs(own)
        at = {(d.module, d.line): d for d in proj.decls}
        for n in (n for n in test if bodies[n][0] == p):
            row, old = decls[n], pilots[p].cites(n) - {n}
            cmd = at.get((row["module"], row["line"]))
            end = max(row["line"] + bodies[n][1].count("\n"), cmd.end if cmd else 0)
            cands = {c: {"new": c in new[n], "pilot": c in old, "module": decls[c]["module"],
                         "line": decls[c]["line"], "kind": decls[c]["kind"], "head": decls[c]["head"][:240]}
                     for c in sorted(new[n] | old)}
            out.append({"name": n, "project": p, "module": row["module"],
                        "path": os.path.relpath(files[row["module"]], bp_dir), "line": row["line"],
                        "end": end, "lines": proj.text[row["module"]][row["line"] - 1:end],
                        "candidates": cands})
    out.sort(key=lambda b: test.index(b["name"]))
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"P": len(P), "dev": dev, "test": test, "bodies": out}, fh, indent=1, ensure_ascii=False)


def score(judged: dict) -> dict:
    """Precision of each matcher, and the pre-registered criteria: new
    precision >= 70% (the Wilson interval reported beside it) and no fewer
    genuine references than the pilot on the same candidates."""
    tally = {k: [0, 0, 0] for k in ("new", "pilot")}   # genuine, extracted, bodies with a spurious one
    for b in judged["bodies"]:
        for k, t in tally.items():
            mine = [c["genuine"] for c in b["candidates"].values() if c[k]]
            t[0], t[1], t[2] = t[0] + sum(mine), t[1] + len(mine), t[2] + (not all(mine))
    out = {k: {"genuine": g, "extracted": n, "precision": round(g / n, 4) if n else None,
               "wilson95": [round(x, 4) for x in wilson(g, n)], "bodies_with_spurious": s}
           for k, (g, n, s) in tally.items()}
    union = [c for b in judged["bodies"] for c in b["candidates"].values() if c["genuine"]]
    out["genuine_in_union"] = len(union)
    out["genuine_new_only"] = sum(c["new"] and not c["pilot"] for c in union)
    out["genuine_pilot_only"] = sum(c["pilot"] and not c["new"] for c in union)
    out["precision_at_least_70"] = bool(out["new"]["extracted"]) and out["new"]["precision"] >= 0.70
    out["recall_not_lower"] = tally["new"][0] >= tally["pilot"][0]
    return out


if __name__ == "__main__":
    if sys.argv[1:2] == ["sample"]:
        sample(sys.argv[2])
    else:
        with open(sys.argv[2], encoding="utf-8") as fh:
            print(json.dumps(score(json.load(fh)), indent=1))
