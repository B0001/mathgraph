"""Neighbour-anchored blueprint \\lean completion (mathgraph-fxh).

Hide one blueprint statement's \\lean tag. The gold tags of its \\uses
neighbours are the anchors, and the candidates are the declarations one Lean
reference away from an anchor (N1). Rank inside N1; abstain when N1 is empty or
its top is tied. In-project only: the hidden tag must name a declaration in the
project's own Lean source, and N1 holds only that project's declarations.

Rankers inside N1: graph (how many anchors a candidate is linked to), lexical
(the shipped Aligner, with the PMI table swapped for idx_mathlib's so that no
project docstring trains it) and bge-small (project rows embedded as name and
head, no docstring: mathgraph-dem.1). The two text rankers also run over the
whole project and over mathlib plus the project, on the same statements.

Edge direction is split out. `down` keeps the candidates a downstream anchor
cites; `up` keeps the candidates that cite an upstream anchor, the realistic
case of a statement whose dependants are not tagged yet. Results and the
pre-registered kill test: sandbox-handoffs/mathgraph-fxh.md.

Prints the summary; the optional path also gets per-statement records.
    uv run --with sentence-transformers python -m mathgraph.complete [records.json]
"""

from __future__ import annotations

import collections
import json
import os
import re
import statistics
import sys

import numpy as np

from .bench_pretrained import QUERY_PREFIX, precision_at_coverage, wilson
from .harvest import find_lean, find_tex
from .latex import parse

DATA = os.environ.get("MATHGRAPH_DATA", "./mathgraph-data")
IDENT = re.compile(r"[A-Za-z_][\w'.₀-₉ᵢ]*")   # the pilot's identifier pattern
ABSTAIN = -1e9                                 # confidence of an abstention
BGE = "BAAI/bge-small-en-v1.5"


def short(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def lean_bodies(bp_dir: str, decls: list[dict]) -> dict[str, tuple[str, str]]:
    """{name: (project, source)}: a declaration's lines up to the next scanned
    declaration of its module. ponytail: line slicing, not a Lean parser; the
    hand check in the results file bounds what it gets wrong."""
    where = {}
    for proj in sorted(os.listdir(bp_dir)):
        root = os.path.join(bp_dir, proj)
        for path in find_lean(root):
            where.setdefault(os.path.relpath(path, root)[:-5].replace(os.sep, "."), (proj, path))
    bymod = collections.defaultdict(list)
    for d in decls:
        bymod[d["module"]].append(d)
    out = {}
    for mod, ds in bymod.items():
        if mod not in where:
            continue
        proj, path = where[mod]
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
        ds.sort(key=lambda d: d["line"])
        for d, nxt in zip(ds, ds[1:] + [None]):
            out[d["name"]] = (proj, "\n".join(lines[d["line"] - 1:nxt["line"] - 1 if nxt else None]))
    return out


class Refs:
    """Who mentions whom inside one project. The pilot's matcher: a body
    mentions every declaration whose last name component equals the last
    component of one of its identifiers, so `Foo.bar`, `bar` and `h.bar`
    all mention every `*.bar`."""

    def __init__(self, bodies: dict[str, str]):
        self.toks = {n: {short(t) for t in IDENT.findall(b)} for n, b in bodies.items()}
        self.named = collections.defaultdict(set)     # short name -> declarations
        self.mentions = collections.defaultdict(set)  # short name -> bodies mentioning it
        for n, ts in self.toks.items():
            self.named[short(n)].add(n)
            for t in ts:
                self.mentions[t].add(n)

    def __contains__(self, name: str) -> bool:
        return name in self.toks

    def cites(self, name: str) -> set:
        return {c for t in self.toks.get(name, ()) for c in self.named.get(t, ())}

    def cited_by(self, name: str) -> set:
        return set(self.mentions.get(short(name), ())) if name in self.toks else set()


def blueprint(proj_dir: str):
    """A leanblueprint's statement graph: ({id: \\lean names}, {id: ids it
    \\uses}, {id: first tagged block}). A proof's \\uses count for its statement."""
    tags, uses, block = collections.defaultdict(set), collections.defaultdict(set), {}
    for path in find_tex(os.path.join(proj_dir, "blueprint")):
        with open(path, encoding="utf-8", errors="replace") as fh:
            blocks = parse(fh.read())
        local = {b.id: f"{path}#{b.id}" for b in blocks if not b.label}  # `theorem:3` restarts per file
        for b in blocks:
            key = local.get(b.proof_of, b.proof_of) if b.kind == "proof" else local.get(b.id, b.id)
            if not key:
                continue
            if b.kind in ("theorem", "definition") and b.declared_lean:
                tags[key].update(b.declared_lean)
                block.setdefault(key, b)
            uses[key].update(u for u in b.uses if u != key)
    return tags, uses, block


def neighbourhoods(tags: dict, uses: dict, refs: Refs) -> list[dict]:
    """Leave-one-out records for every statement with an in-project tag.

    `links[split]` counts, per candidate, the anchors it is linked to:
    n1 by a reference either way, up by citing an upstream anchor (one the
    statement \\uses), down by being cited by a downstream anchor (one that
    \\uses the statement). Anchors themselves are never candidates."""
    used_by = collections.defaultdict(set)
    for s, us in uses.items():
        for u in us:
            used_by[u].add(s)
    out = []
    for sid, ts in tags.items():
        gold = {t for t in ts if t in refs}
        if not gold:
            continue
        up = {t for u in uses.get(sid, ()) for t in tags.get(u, ())} - ts
        down = {t for d in used_by.get(sid, ()) for t in tags.get(d, ())} - ts
        links = {"n1": collections.Counter(), "up": collections.Counter(), "down": collections.Counter()}
        for a in up | down:
            links["n1"].update((refs.cites(a) | refs.cited_by(a)) - up - down)
        for a in up:
            links["up"].update(refs.cited_by(a) - up)
        for a in down:
            links["down"].update(refs.cites(a) - down)
        out.append({"id": sid, "gold": sorted(gold), "anchors": {"up": len(up), "down": len(down)},
                    "links": links})
    return out


def graph_top(links: collections.Counter, n_anchors: int):
    """(most-linked candidate, confidence), or (None, ABSTAIN) when the set is
    empty or its top is tied. Confidence is the link count, then the lead over
    the runner-up: lead / (n_anchors + 1) < 1 never reorders counts."""
    top = links.most_common(2)
    if not top or (len(top) == 2 and top[0][1] == top[1][1]):
        return None, ABSTAIN
    lead = top[0][1] - (top[1][1] if len(top) == 2 else 0)
    return top[0][0], top[0][1] + lead / (n_anchors + 1)


def pick(names: list, score: np.ndarray, conf: np.ndarray, idx: np.ndarray, floor: float):
    """(best of `names[idx]` by score, its confidence), abstaining when nothing
    clears `floor` or the top two tie."""
    if idx.size == 0:
        return None, ABSTAIN
    s = score[idx]
    if idx.size == 1:
        i, s2 = 0, -np.inf
    else:
        two = np.argpartition(-s, 1)[:2]
        i, j = two[np.argsort(-s[two])]
        s2 = s[j]
    if s[i] <= floor or s[i] == s2:
        return None, ABSTAIN
    return names[idx[i]], float(conf[idx[i]])


def text_tops(rec: dict, names: list, pos: dict, score, conf, ml: list, floor: float) -> dict:
    """One text ranker's answer on every candidate set. `score`/`conf` cover
    the project's declarations (`names`); `ml` is mathlib's best two as
    (name, score, conf), which is all the global top-1 and tie test need."""
    u_names = names + [m[0] for m in ml]
    u_score = np.concatenate([score, [m[1] for m in ml]]).astype(np.float64)
    u_conf = np.concatenate([conf, [m[2] for m in ml]]).astype(np.float64)
    sets = {k: np.array(sorted(pos[c] for c in v), dtype=np.int64) for k, v in rec["links"].items()}
    sets["project"] = np.arange(len(names))
    sets["global"] = np.arange(len(u_names))
    return {k: pick(u_names, u_score, u_conf, v, floor) for k, v in sets.items()}


def top2(names: list, score: np.ndarray, conf: np.ndarray) -> list:
    two = np.argpartition(-score, 1)[:2]
    return [(names[i], float(score[i]), float(conf[i])) for i in two[np.argsort(-score[two])]]


def lexical(recs: list, art_dir: str, projects: dict) -> None:
    """Fill rec['top']['lexical/*'] for every record."""
    from .align import Aligner
    from .cli import LEX
    from .index import load

    ml = load(os.path.join(art_dir, "idx_mathlib"))
    trans, n_ml = ml["trans"], len(ml["rows"])   # PMI from mathlib docstrings only
    del ml
    for idx in ("idx_blueprint", "idx_full"):
        mine = [p for p in projects if (p == "pfr") == (idx == "idx_full")]
        art = load(os.path.join(art_dir, idx))
        art["trans"] = trans
        al = Aligner(art, **LEX)
        del art
        row = {}
        for i, r in enumerate(al.rows):
            row.setdefault(r["name"], i)
        ml_rows = np.array([i for i, r in enumerate(al.rows) if r["module"].startswith("Mathlib.")])
        assert len(ml_rows) == n_ml, (idx, len(ml_rows), n_ml)
        ml_names = [al.rows[i]["name"] for i in ml_rows]
        for p in mine:
            names, pos = projects[p]["names"], projects[p]["pos"]
            rowid = np.array([row.get(n, al.N) for n in names])   # al.N: a zero slot
            for rec in (r for r in recs if r["project"] == p):
                dense, cov = np.zeros(al.N + 1), np.zeros(al.N + 1)
                res = al._score(al.query_weights(rec["text"], title=rec["title"]), al.N)
                if len(res) == 4:
                    ids, norm, mass, raw = res
                    dense[ids], cov[ids] = norm, raw / mass
                ml = top2(ml_names, dense[ml_rows], cov[ml_rows])
                for k, v in text_tops(rec, names, pos, dense[rowid], cov[rowid], ml, 0.0).items():
                    rec["top"][f"lexical/{k}"] = v
        del al


def bge(recs: list, art_dir: str, projects: dict, decls: dict) -> None:
    """Fill rec['top']['bge/*']. Mathlib rows reuse bench_pretrained's cached
    corpus embeddings (name, doc, head); project rows are embedded fresh as
    name and head, with no docstring."""
    import torch
    from sentence_transformers import SentenceTransformer

    from .index import load

    model = SentenceTransformer(BGE, device="mps" if torch.backends.mps.is_available() else "cpu")
    enc = lambda xs: model.encode(xs, batch_size=128, normalize_embeddings=True,  # noqa: E731
                                  convert_to_numpy=True).astype(np.float32)
    full = load(os.path.join(art_dir, "idx_full"))["rows"]
    M = np.load(os.path.join(art_dir, f"emb_{BGE.replace('/', '__')}.npy"), mmap_mode="r")
    assert M.shape[0] == len(full)
    keep = np.array([r["module"].startswith("Mathlib.") for r in full])
    M = np.ascontiguousarray(M[keep])
    ml_names = [r["name"] for r, k in zip(full, keep) if k]
    del full
    prefix = QUERY_PREFIX["BAAI/"]
    for p, v in projects.items():
        names, pos = v["names"], v["pos"]
        E = enc([". ".join(x for x in (n, decls[n].get("head") or "") if x) for n in names])
        mine = [r for r in recs if r["project"] == p]
        for c in range(0, len(mine), 64):
            chunk = mine[c:c + 64]
            Q = enc([prefix + ". ".join(x for x in (r["title"], r["text"]) if x) for r in chunk])
            S = Q @ M.T
            for rec, q, s in zip(chunk, Q, S):
                own = E @ q
                for k, t in text_tops(rec, names, pos, own, own, top2(ml_names, s, s), -np.inf).items():
                    rec["top"][f"bge/{k}"] = t


def rate(k: int, n: int) -> dict:
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "wilson95": [round(lo, 4), round(hi, 4)]}


def scores(recs: list, key: str) -> dict:
    """r@1 over all records (an abstention is a miss) and precision at 10%
    coverage, answering the most confident tenth."""
    ok = [int(r["top"][key][0] in r["gold"]) for r in recs]
    (p10,) = precision_at_coverage([{"conf": r["top"][key][1], "ok": o} for r, o in zip(recs, ok)],
                                   "conf", coverages=(0.10,))
    return {"answered": sum(r["top"][key][0] is not None for r in recs), "r@1": rate(sum(ok), len(recs)),
            "p@10%": p10}


SPLITS = {"n1": lambda r: r["anchors"]["up"] + r["anchors"]["down"] > 0,
          "up": lambda r: r["anchors"]["up"] > 0,
          "down": lambda r: r["anchors"]["down"] > 0}


def summarize(recs: list) -> dict:
    out = {}
    for split, has in SPLITS.items():
        rs = [r for r in recs if has(r)]
        sizes = [r["n"][split] for r in rs]
        keys = [f"graph/{split}", f"lexical/{split}", f"bge/{split}", "lexical/project", "bge/project",
                "lexical/global", "bge/global"]
        out[split] = {"statements": len(rs),
                      "gold_in_set": rate(sum(r["hit"][split] for r in rs), len(rs)),
                      "median_size": statistics.median(sizes) if sizes else None,
                      "median_size_nonempty": statistics.median([s for s in sizes if s]) if any(sizes) else None,
                      "rankers": {k: scores(rs, k) for k in keys}}
    return out


def kill_test(s: dict) -> dict:
    """The bead's pre-registered criteria, read off the pooled summary. A text
    ranker must beat graph on r@1 and on P@10% both (point estimates)."""
    n1 = s["n1"]
    g = n1["rankers"]["graph/n1"]

    def beats(k):
        t = n1["rankers"][k]
        return (t["r@1"]["rate"] > g["r@1"]["rate"]
                and (t["p@10%"]["precision"] or 0) > (g["p@10%"]["precision"] or 0))

    low = n1["gold_in_set"]["wilson95"][0] < 0.60
    big = n1["median_size"] > 300
    flat = not (beats("lexical/n1") or beats("bge/n1"))
    up = s["up"]["gold_in_set"]["rate"] < 0.40
    return {"gold_in_n1_wilson_lo_below_60": low, "median_n1_above_300": big,
            "no_text_ranker_beats_graph_on_r1_and_p10": flat, "up_gold_in_set_below_40": up,
            "killed": low or big or flat, "realistic_use_killed": up}


def main(out_path: str | None = None) -> dict:
    art_dir, bp_dir = os.path.join(DATA, "artifacts"), os.path.join(DATA, "blueprints")
    rows = []
    for f in ("blueprint_decls.jsonl", "pfr.jsonl"):
        with open(os.path.join(art_dir, f), encoding="utf-8") as fh:
            rows.extend(json.loads(line) for line in fh)
    decls = {d["name"]: d for d in rows}
    bodies = lean_bodies(bp_dir, rows)
    projects, recs, noanchor = {}, [], collections.Counter()
    for p in sorted({p for p, _ in bodies.values()}):
        own = {n: b for n, (q, b) in bodies.items() if q == p}
        names = sorted(own)
        projects[p] = {"names": names, "pos": {n: i for i, n in enumerate(names)}}
        tags, uses, block = blueprint(os.path.join(bp_dir, p))
        for r in neighbourhoods(tags, uses, Refs(own)):
            if not r["anchors"]["up"] + r["anchors"]["down"]:
                noanchor[p] += 1
                continue
            b = block[r["id"]]
            r.update(project=p, title=b.title, text=b.text, top={},
                     n={k: len(v) for k, v in r["links"].items()},
                     hit={k: bool(set(r["gold"]) & v.keys()) for k, v in r["links"].items()})
            for k, v in r["links"].items():
                r["top"][f"graph/{k}"] = graph_top(v, r["anchors"]["up"] + r["anchors"]["down"])
            recs.append(r)
    lexical(recs, art_dir, projects)
    bge(recs, art_dir, projects, decls)
    res = {"statements": len(recs), "no_anchor": dict(noanchor), "pooled": summarize(recs),
           "pfr": summarize([r for r in recs if r["project"] == "pfr"]),
           "by_project": {p: summarize([r for r in recs if r["project"] == p])["n1"] for p in projects}}
    res["kill_test"] = kill_test(res["pooled"])
    res["records"] = [{k: r[k] for k in ("project", "id", "gold", "anchors", "n", "hit", "top")} for r in recs]
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, ensure_ascii=False)
    return res


if __name__ == "__main__":
    res = main(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps({k: v for k, v in res.items() if k != "records"}, indent=1))
