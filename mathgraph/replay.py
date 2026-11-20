"""History-replay `\\lean` suggester benchmark (mathgraph-8c3).

Replay each blueprint's git history. At the parent P of every commit C that
adds `\\lean{X}`, rank P's untagged project declarations for that statement.
X already declared at P ('pre') makes a positive. X first declared in C
('same') or after it ('later') makes a real "not formalized yet" negative, on
which a suggester should abstain. Pre-registration, kill test and results:
sandbox-handoffs/mathgraph-8c3.md.

    HF_HUB_OFFLINE=1 MATHGRAPH_DATA=... python -m mathgraph.replay [clones] [out.json]

`clones` holds one full clone (or mirror) per project, named after it.
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from functools import lru_cache

import numpy as np

from .bench_pretrained import QUERY_PREFIX, wilson
from .latex import LEAN_RE, _strip_comments, parse
from .leanscan import _IDENT, scan_file

DATA = os.environ.get("MATHGRAPH_DATA", "./mathgraph-data")
BGE = "BAAI/bge-small-en-v1.5"
PREFIX = QUERY_PREFIX["BAAI/"]
IDENT = re.compile(_IDENT)
STATEMENT = ("theorem", "definition")
Z_MIN = 5                       # untagged statements a snapshot needs before z is defined
B, SEED = 2000, 20261120        # commit-cluster bootstrap
NAMED = ("cos", "z")            # the two pre-registered confidences


def names_in(src: str) -> set:
    return {x.strip() for grp in LEAN_RE.findall(src) for x in grp.split(",") if x.strip()}


def root(name: str) -> str:
    """`A._root_.foo` declares `foo`."""
    i = name.rfind("_root_.")
    return name[i + 7:] if i >= 0 else name


def short(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def query(title: str, text: str) -> str:
    return ". ".join(x for x in (title, text) if x)


class Repo:
    """One project's history, read through git, with per-blob scan caches."""

    def __init__(self, path: str):
        self.path = path
        self.lean: dict[str, list] = {}   # blob -> [(name, kind, line, head)]
        self.tex_: dict[str, tuple] = {}  # blob -> (statement blocks, names tagged in the file)

    def git(self, *args: str, stdin: bytes | None = None) -> bytes:
        return subprocess.run(["git", "-C", self.path, "-c", "core.quotepath=off", *args],
                              input=stdin, capture_output=True, check=True).stdout

    def blobs(self, commit: str, ext: str, under: tuple = ()) -> list[tuple[str, str]]:
        out = []
        for ln in self.git("ls-tree", "-r", commit, "--", *under).decode("utf-8", "replace").splitlines():
            meta, path = ln.split("\t", 1)
            _, kind, sha = meta.split()
            if kind == "blob" and path.endswith(ext) and not {".lake", "lake-packages"} & set(path.split("/")):
                out.append((sha, path))
        return out

    def read(self, shas: list) -> dict[str, str]:
        if not shas:
            return {}
        data, out, i = self.git("cat-file", "--batch", stdin="".join(s + "\n" for s in shas).encode()), {}, 0
        for s in shas:
            j = data.index(b"\n", i)
            size = int(data[i:j].split()[2])
            out[s] = data[j + 1:j + 1 + size].decode("utf-8", "replace")
            i = j + 2 + size
        return out

    @lru_cache(maxsize=16)
    def decls(self, commit: str) -> dict:
        """{full name: (module, kind, line, head)} at `commit`; the first declaration wins.
        ponytail: leanscan's line scanner, so macro-made declarations are invisible."""
        files = self.blobs(commit, ".lean")
        todo = sorted({s for s, _ in files if s not in self.lean})
        if todo:
            with tempfile.TemporaryDirectory() as d:
                tmp = os.path.join(d, "blob.lean")
                for s, text in self.read(todo).items():
                    with open(tmp, "w", encoding="utf-8") as fh:
                        fh.write(text)
                    self.lean[s] = [(root(x.name), x.kind, x.line, x.head) for x in scan_file(tmp, "")]
        out = {}
        for s, path in files:
            for name, kind, line, head in self.lean[s]:
                out.setdefault(name, (path[:-5].replace("/", "."), kind, line, head))
        return out

    def tex(self, commit: str, paths: set | None = None) -> list[tuple]:
        """[(path, statement blocks, names tagged anywhere in the file)] under blueprint/."""
        files = [(s, p) for s, p in self.blobs(commit, ".tex", ("blueprint",)) if paths is None or p in paths]
        for s, text in self.read(sorted({s for s, _ in files if s not in self.tex_})).items():
            self.tex_[s] = ([b for b in parse(text) if b.kind in STATEMENT], names_in(_strip_comments(text)))
        return [(p, *self.tex_[s]) for s, p in files]

    def tagged(self, commit: str) -> set:
        return set().union(*(t for _, _, t in self.tex(commit)))


def additions(repo: Repo) -> list[dict]:
    """ev.py's walk: per commit, the tags on added diff lines minus those on removed ones."""
    log = repo.git("log", "--reverse", "-p", "--no-color", "--no-ext-diff",
                   "--format=@@C %H %P %cs", "--", "blueprint/src").decode("utf-8", "replace")
    out, cur = [], None
    for ln in log.split("\n"):
        if ln.startswith("@@C "):
            p = ln.split()
            cur = {"commit": p[1], "parent": p[2] if len(p) > 3 else None, "date": p[-1],
                   "add": set(), "rem": set(), "tex": set()}
            out.append(cur)
        elif cur is None:
            continue
        elif ln.startswith("+++ b/"):
            cur["tex"].add(ln[6:])
        elif ln[:1] in ("+", "-") and not ln.startswith(("+++", "---")) and "\\lean{" in ln:
            cur["add" if ln[0] == "+" else "rem"] |= names_in(ln)
    return out


def tag_events(repo: Repo, mathlib: set) -> list[dict]:
    """Every tag addition, labelled pre/same/later, or with the first drop reason that applies."""
    head = set(repo.decls(repo.git("rev-parse", "HEAD").decode().strip()))
    out, seen = [], set()
    for c in additions(repo):
        removes = None
        for x in sorted(c["add"] - c["rem"]):
            rec = {"name": x, "commit": c["commit"], "parent": c["parent"], "date": c["date"],
                   "label": None, "blocks": [], "drop": None}
            out.append(rec)
            if not c["parent"]:
                rec["drop"] = "no_parent"
            elif x in seen:
                rec["drop"] = "repeat"
            elif not IDENT.fullmatch(x) or ".." in x or x.endswith("."):
                rec["drop"] = "not_identifier"
            elif x in mathlib:
                rec["drop"] = "mathlib_name"
            seen.add(x)
            if rec["drop"]:
                continue
            P, C = repo.decls(c["parent"]), repo.decls(c["commit"])
            if removes is None:
                removes = bool(P.keys() - C.keys())
            blocks = [f"{p}#{b.id}" for p, bs, _ in repo.tex(c["commit"], c["tex"]) for b in bs
                      if x in b.declared_lean]
            if removes:
                rec["drop"] = "commit_removes_decls"
            elif not blocks:
                rec["drop"] = "no_statement_block"
            else:
                rec["label"] = "pre" if x in P else "same" if x in C else "later" if x in head else "never"
                rec["blocks"] = blocks
                rec["short_at_parent"] = short(x) in {short(n) for n in P}
                if rec["label"] == "never":
                    rec["drop"] = "never"
    return out


def statement_events(repo: Repo, tags: list[dict]) -> tuple[list[dict], collections.Counter]:
    """Group the surviving tags by the statement block that gains them. A block with a
    'pre' tag is a positive whose gold is its pre tags untagged at the parent."""
    by_block = collections.defaultdict(list)
    for t in tags:
        if t["drop"] is None:
            for k in t["blocks"]:
                by_block[(t["commit"], k)].append(t)
    events, drops = [], collections.Counter()
    for (commit, key), ts in by_block.items():
        path = key.split("#", 1)[0]
        blk = next(b for p, bs, _ in repo.tex(commit, {path}) for b in bs if f"{p}#{b.id}" == key)
        pre = sorted(t["name"] for t in ts if t["label"] == "pre")
        gold = []
        if pre:
            tagged = repo.tagged(ts[0]["parent"])
            gold = [g for g in pre if g not in tagged]
            if not gold:
                drops["gold_tagged_at_parent"] += 1
                continue
        events.append({"commit": commit, "parent": ts[0]["parent"], "date": ts[0]["date"], "block": key,
                       "positive": bool(pre), "labels": sorted({t["label"] for t in ts}),
                       "tags": sorted(t["name"] for t in ts), "gold": gold,
                       "short_absent": not any(t["short_at_parent"] for t in ts),
                       "title": blk.title, "text": blk.text})
    return events, drops


class Encoder:
    """bge-small with a text-hash cache, so each snapshot embeds only what changed."""

    def __init__(self, cache: str | None = None):
        self.cache, self.vec, self._model = cache, {}, None
        if cache and os.path.exists(cache):
            z = np.load(cache)
            self.vec = dict(zip(z["keys"].tolist(), z["vecs"]))

    def __call__(self, texts: list[str]) -> np.ndarray:
        keys = [hashlib.sha1(t.encode()).hexdigest() for t in texts]
        miss = dict(zip(keys, texts))
        miss = {k: t for k, t in miss.items() if k not in self.vec}
        if miss:
            if self._model is None:
                import torch
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(BGE, device="mps" if torch.backends.mps.is_available() else "cpu")
            V = self._model.encode(list(miss.values()), batch_size=128, normalize_embeddings=True,
                                   convert_to_numpy=True).astype(np.float32)
            self.vec.update(zip(miss, V))
        return np.stack([self.vec[k] for k in keys]) if keys else np.zeros((0, 384), np.float32)

    def save(self) -> None:
        if self.cache:
            keys = list(self.vec)
            np.savez(self.cache, keys=np.array(keys), vecs=np.stack([self.vec[k] for k in keys]))


def lexical_aligner(names: list, decls: dict, trans: dict):
    """The shipped Aligner over one snapshot's candidates. attrs and docs are blanked, so
    no to_additive twin or project docstring enters; the PMI table is mathlib's."""
    from .align import Aligner
    from .cli import LEX
    from .index import build, load

    with tempfile.TemporaryDirectory() as d:
        raw = os.path.join(d, "rows.jsonl")
        with open(raw, "w", encoding="utf-8") as fh:
            for n in names:
                module, kind, line, head = decls[n]
                fh.write(json.dumps({"name": n, "kind": kind, "module": module, "line": line, "doc": "",
                                     "head": head, "attrs": "", "namespace": "", "provenance": "source"}) + "\n")
        build(raw, d)
        art = load(d)
    art["trans"] = trans
    return Aligner(art, **LEX)


def rank(repo: Repo, events: list[dict], enc: Encoder, trans: dict) -> None:
    """Fill each event's bge and lexical answers, one parent snapshot at a time."""
    by_parent = collections.defaultdict(list)
    for e in events:
        by_parent[e["parent"]].append(e)
    for parent, evs in by_parent.items():
        D = repo.decls(parent)
        tex = repo.tex(parent)
        tagged = repo.tagged(parent)
        names = sorted(n for n in D if n not in tagged)
        pos = {n: i for i, n in enumerate(names)}
        untagged = [b for _, bs, _ in tex for b in bs if not b.declared_lean]
        E = enc([f"{n}. {D[n][3]}" if D[n][3] else n for n in names])
        Q = enc([PREFIX + query(e["title"], e["text"]) for e in evs])
        U = enc([PREFIX + query(b.title, b.text) for b in untagged])
        top_u = (U @ E.T).max(1) if len(names) and len(untagged) else np.zeros(0)
        mu, sd = (top_u.mean(), top_u.std(ddof=1)) if len(top_u) >= Z_MIN else (np.nan, np.nan)
        al = lexical_aligner(names, D, trans) if names else None
        for e, q in zip(evs, Q):
            e["n_cand"], e["n_untagged"] = len(names), len(untagged)
            e["bge"] = bge_answer(E @ q, names, [pos[g] for g in e["gold"] if g in pos], mu, sd)
            e["lex"] = lex_answer(al, e)


def bge_answer(s: np.ndarray, names: list, gold: list, mu: float, sd: float) -> dict:
    if not len(names):
        return {"top": None, "cos": -math.inf, "z": -math.inf, "zq": -math.inf, "margin": -math.inf, "rank": None}
    order = np.argsort(-s, kind="stable")
    i = int(order[0])
    s2 = float(s[order[1]]) if len(s) > 1 else -math.inf
    z = float((s[i] - mu) / sd) if sd > 0 else -math.inf          # nan sd compares False
    zq = float((s[i] - s.mean()) / s.std()) if len(s) > 1 and s.std() > 0 else -math.inf
    rank = int((s > s[gold].max()).sum()) + 1 if gold else None
    return {"top": names[i], "cos": float(s[i]), "z": z, "zq": zq, "margin": float(s[i]) - s2, "rank": rank}


def lex_answer(al, e: dict) -> dict:
    """complete.py's lexical answer: top normalised score, coverage as confidence, abstain on a tie."""
    res = al._score(al.query_weights(e["text"], title=e["title"]), al.N) if al else ()
    if len(res) != 4 or not len(res[0]) or (len(res[1]) > 1 and res[1][0] == res[1][1]):
        return {"top": None, "conf": -math.inf, "rank": None}
    ids, norm, mass, raw = res
    hits = [al.rows[int(i)]["name"] for i in ids]
    rank = next((r + 1 for r, n in enumerate(hits) if n in e["gold"]), None)
    return {"top": hits[0], "conf": float(raw[0] / mass), "rank": rank}


# --- analysis -------------------------------------------------------------------

CONF = {"cos": ("bge", "cos"), "z": ("bge", "z"), "zq": ("bge", "zq"), "margin": ("bge", "margin"),
        "lex": ("lex", "conf")}


def conf(e: dict, c: str) -> float:
    ranker, field = CONF[c]
    return e[ranker][field]


def ok(e: dict, c: str) -> bool:
    return e["positive"] and e[CONF[c][0]]["top"] in e["gold"]


def auroc(pos, neg) -> float | None:
    """Mann-Whitney AUROC, ties counted 1/2 (two -inf abstentions tie)."""
    if not len(pos) or not len(neg):
        return None
    p, n = np.asarray(pos, float)[:, None], np.asarray(neg, float)[None, :]
    return float(((p > n) + 0.5 * (p == n)).mean())


def cut(vals: list, frac: float = 0.10) -> tuple[float, bool]:
    """precision_at_coverage's cut: (tau, inclusive). The top ceil(frac*N) are answered,
    unless a tie group straddles the cut, in which case the whole group is left out."""
    s = sorted(vals, reverse=True)
    m = max(1, math.ceil(frac * len(s)))
    tau = s[m - 1]
    return tau, sum(v >= tau for v in s) <= m


def answers(v: float, tau: float, inclusive: bool) -> bool:
    return v >= tau if inclusive else v > tau


def transfer(evs: list[dict], c: str, frac: float = 0.10) -> dict:
    """Freeze tau at frac coverage on the pfr events; apply it to the pooled others."""
    pfr = [e for e in evs if e["project"] == "pfr"]
    rest = [e for e in evs if e["project"] != "pfr"]
    if not pfr or not rest:
        return {"answered": 0, "precision": None, "wilson95": [0.0, 1.0]}
    tau, inc = cut([conf(e, c) for e in pfr], frac)
    ans = [e for e in rest if answers(conf(e, c), tau, inc)]
    k = sum(ok(e, c) for e in ans)
    lo, hi = wilson(k, len(ans))
    return {"tau": tau, "inclusive": inc, "answered": len(ans), "n": len(rest),
            "coverage": round(len(ans) / len(rest), 4), "correct": k,
            "precision": round(k / len(ans), 4) if ans else None, "wilson95": [round(lo, 4), round(hi, 4)]}


def in_sample(evs: list[dict], c: str, frac: float = 0.10) -> dict:
    tau, inc = cut([conf(e, c) for e in evs], frac)
    ans = [e for e in evs if answers(conf(e, c), tau, inc)]
    k = sum(ok(e, c) for e in ans)
    lo, hi = wilson(k, len(ans))
    return {"answered": len(ans), "correct": k, "precision": round(k / len(ans), 4) if ans else None,
            "wilson95": [round(lo, 4), round(hi, 4)]}


def roc(evs: list[dict], c: str, neg=lambda e: True) -> float | None:
    return auroc([conf(e, c) for e in evs if e["positive"]],
                 [conf(e, c) for e in evs if not e["positive"] and neg(e)])


def bootstrap(evs: list[dict], stats: dict, n: int = B, seed: int = SEED) -> dict:
    """Commit-cluster bootstrap, stratified by project; percentile 95% intervals."""
    rng = np.random.default_rng(seed)
    clusters = collections.defaultdict(list)
    for e in evs:
        clusters[(e["project"], e["commit"])].append(e)
    strata = collections.defaultdict(list)
    for k in clusters:
        strata[k[0]].append(k)
    vals, skipped = collections.defaultdict(list), collections.Counter()
    for _ in range(n):
        sample = [e for p in sorted(strata) for j in rng.integers(0, len(strata[p]), len(strata[p]))
                  for e in clusters[strata[p][j]]]
        for name, f in stats.items():
            v = f(sample)
            if v is None:
                skipped[name] += 1
            else:
                vals[name].append(v)
    return {name: {"ci95": [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)]
                   if v else None, "skipped": skipped[name]} for name, v in ((k, vals[k]) for k in stats)}


def summarize(events: list[dict], tags: list[dict], drops: collections.Counter, n_boot: int = B) -> dict:
    pos = [e for e in events if e["positive"]]
    neg = [e for e in events if not e["positive"]]
    projects = sorted({e["project"] for e in events})
    counts = {"positives": len(pos), "negatives": len(neg),
              "negative_commits": len({(e["project"], e["commit"]) for e in neg}),
              "positive_commits": len({(e["project"], e["commit"]) for e in pos}),
              "mixed_positives": sum(len(e["labels"]) > 1 for e in pos),
              "by_project": {p: {"positives": sum(e["project"] == p for e in pos),
                                 "negatives": sum(e["project"] == p for e in neg)} for p in projects},
              "statement_drops": dict(drops),
              "tags": {p: dict(collections.Counter(t["drop"] or t["label"] for t in tags if t["project"] == p))
                       for p in sorted({t["project"] for t in tags})}}
    stats = {f"auroc/{c}": (lambda c: lambda s: roc(s, c))(c) for c in CONF}
    stats |= {f"transfer/{c}": (lambda c: lambda s: transfer(s, c)["precision"])(c) for c in NAMED}
    stats |= {f"auroc/{c}/{p}": (lambda c, p: lambda s: roc([e for e in s if e["project"] == p], c))(c, p)
              for c in NAMED for p in projects}
    boot = bootstrap(events, stats, n_boot)
    m = {"counts": counts, "auroc": {}, "transfer": {}, "in_sample_p10": {}, "per_project_auroc": {}}
    for c in CONF:
        m["auroc"][c] = {"point": _r(roc(events, c)), **boot[f"auroc/{c}"]}
        m["in_sample_p10"][c] = in_sample(events, c)
    for c in NAMED:
        m["transfer"][c] = {**transfer(events, c), "bootstrap": boot[f"transfer/{c}"]}
        m["per_project_auroc"][c] = {p: {"point": _r(roc([e for e in events if e["project"] == p], c)),
                                         **boot[f"auroc/{c}/{p}"]} for p in projects}
    m["recall"] = {r: {f"r@{k}": _rate(sum(e[r]["rank"] is not None and e[r]["rank"] <= k for e in pos), len(pos))
                       for k in (1, 5)} for r in ("bge", "lex")}
    m["secondary"] = {
        "short_name_absent_negatives": {"negatives": sum(e["short_absent"] for e in neg),
                                        **{c: _r(roc(events, c, lambda e: e["short_absent"])) for c in NAMED}},
        "same_only_negatives": {c: _r(roc(events, c, lambda e: e["labels"] == ["same"])) for c in NAMED},
        "later_only_negatives": {c: _r(roc(events, c, lambda e: e["labels"] == ["later"])) for c in NAMED},
        "z_undefined_events": sum(e["bge"]["z"] == -math.inf for e in events)}
    m["exploratory"] = {"gold_short_name_in_query": sum(_leak(e) for e in pos)}
    m["kill_test"] = kill_test(m)
    return m


def _r(x):
    return None if x is None else round(x, 4)


def _json(x):
    """Strict JSON: numpy scalars to Python, and the -inf of an abstention to null."""
    if isinstance(x, dict):
        return {k: _json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json(v) for v in x]
    if isinstance(x, np.generic):
        x = x.item()
    return None if isinstance(x, float) and not math.isfinite(x) else x


def _rate(k: int, n: int) -> dict:
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "wilson95": [round(lo, 4), round(hi, 4)]}


def _leak(e: dict) -> bool:
    """Exploratory: a gold short name of 6+ characters, read without punctuation, occurs in the query."""
    q = re.sub(r"[^a-z0-9]", "", (e["title"] + e["text"]).lower())
    return any(len(s) >= 6 and s in q for s in (re.sub(r"[^a-z0-9]", "", short(g).lower()) for g in e["gold"]))


def kill_test(m: dict) -> dict:
    c = m["counts"]
    k1 = c["positives"] < 150 or c["negatives"] < 150 or c["negative_commits"] < 40
    best = max(NAMED, key=lambda x: m["auroc"][x]["point"] or 0.0)
    lo = lambda x: (m["auroc"][x]["ci95"] or [0.0])[0]   # noqa: E731
    k2 = lo(best) < 0.65
    k3 = m["transfer"][best]["wilson95"][0] < 0.50
    passes = [x for x in NAMED if lo(x) >= 0.65 and m["transfer"][x]["wilson95"][0] >= 0.50]
    return {"best": best, "K1_counts": k1, "K2_auroc_lower_bound_below_0.65": k2,
            "K3_transfer_wilson_lower_below_0.50": k3, "killed": k1 or k2 or k3,
            "secondary_point_reading_killed": k1 or (m["auroc"][best]["point"] or 0.0) < 0.65 or k3,
            "secondary_either_confidence_survives": not k1 and bool(passes), "passing_confidences": passes}


def ev_agreement(tags: list[dict], ev_dirs: list[str]) -> dict:
    """S5: do our additions match the round-2 ev.py rows on (name, commit)?"""
    out = {}
    for p in sorted({t["project"] for t in tags}):
        f = next((f for f in (os.path.join(d, f"{p}.json") for d in ev_dirs) if os.path.exists(f)), None)
        if f is None:
            continue
        with open(f, encoding="utf-8") as fh:
            theirs = {(r["name"], r["h"]) for r in json.load(fh)}
        ours = {(t["name"], t["commit"]) for t in tags if t["project"] == p and t["drop"] != "no_parent"}
        out[p] = {"ev_rows": len(theirs), "ours": len(ours), "both": len(theirs & ours)}
    return out


def main(clones: str = "build/replay/clones", out_path: str = "results/replay.json") -> dict:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from .index import load

    ml = load(os.path.join(DATA, "artifacts", "idx_mathlib"))
    mathlib, trans = {r["name"] for r in ml["rows"]}, ml["trans"]
    del ml
    os.makedirs(os.path.join("build", "replay"), exist_ok=True)
    enc = Encoder(os.path.join("build", "replay", "emb_cache.npz"))   # never next to shared inputs
    tags, events, drops, heads = [], [], collections.Counter(), {}
    for d in sorted(os.listdir(clones)):
        project = d[:-4] if d.endswith(".git") else d
        repo = Repo(os.path.join(clones, d))
        heads[project] = repo.git("rev-parse", "HEAD").decode().strip()
        ts = tag_events(repo, mathlib)
        for t in ts:
            t["project"] = project
        evs, dr = statement_events(repo, ts)
        for e in evs:
            e["project"] = project
        rank(repo, evs, enc, trans)
        tags += ts
        events += evs
        drops += dr
        print(f"{project:22s} tags {len(ts):5d}  events {len(evs):4d}", file=sys.stderr)
    enc.save()
    res = {"heads": heads, "encoder": BGE, "mathlib_names": len(mathlib), **summarize(events, tags, drops),
           "ev_agreement": ev_agreement(tags, [os.path.join(os.path.dirname(os.path.abspath(clones)), d)
                                               for d in ("ev", "hr")]),   # hr/: the r2 scratchpad's name
           "events": [{k: v for k, v in e.items() if k != "text"} for e in events]}
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(_json(res), fh, indent=1, ensure_ascii=False, allow_nan=False)
    return res


if __name__ == "__main__":
    out = main(*sys.argv[1:3])
    print(json.dumps(_json({k: v for k, v in out.items() if k != "events"}), indent=1))
