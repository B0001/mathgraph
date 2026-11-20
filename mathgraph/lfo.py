"""Leave-family-out test of the co-arrival hypothesis (mathgraph-sd8).

The time-split arm (mathgraph-269) failed its kill test in the unexpected
direction: theorems added after the pin are *easier* negatives than random
holdouts (bge-small false-match rate 2.2% against 14.0% at the 10%-coverage
threshold). The co-arrival hypothesis says novelty is not the cause. A holdout
leaves its family indexed (name-stem siblings, its to_additive twin, its
aliases), while a new theorem tends to arrive together with its family, so
nothing that close to it is indexed.

The test moves families in and out of the index one query at a time, without
rebuilding anything:

* holdout and deletion, family removed: every indexed member of the query's
  family is masked out of that query's ranking;
* holdout and deletion, matched control: the same number of random rows from
  the query's own module, outside its family, are masked instead;
* time, siblings added: the 13,008 declarations new at NOV join the index,
  except the query itself and the names its to_additive and alias links reach.

The family rule is name-only (never an embedding, which would be circular:
206 of 221 bge false matches sit inside a cos >= 0.9 family). It was frozen,
with the analysis and the kill test, in sandbox-handoffs/mathgraph-sd8-prereg.md
before any score under these conditions was computed.
"""

from __future__ import annotations

import os
from collections import defaultdict
from functools import lru_cache

from .names import _CAMEL
from .timesplit import _ALIAS_TARGET, _DEP_TARGET, path_of, twin

# -- the family rule (frozen by the pre-registration) -------------------------

# Variant markers: the additive/multiplicative and left/right versions of a
# fact, and the Within/NE/On restrictions of a filter or a set
# (`continuousWithinAt`, `nhdsNE`, `continuousOn`). Case matters: `NE` is the
# marker, while `ne` in `mul_ne_zero` is part of the statement.
_DROP = frozenset("add Add mul Mul left Left right Right Within NE On".split())


def stem(name: str) -> str:
    """A declaration's family stem: the last name component with its primes
    removed, cut before an `_of_` hypothesis tail, and with the variant
    markers dropped. Empty when nothing is left, and an empty stem has no
    family."""
    parts = name.rsplit(".", 1)[-1].replace("'", "").split("_")
    if "of" in parts[1:]:
        parts = parts[:parts.index("of", 1)]
    return "_".join(t for p in parts for t in _CAMEL.split(p)
                     if t and t not in _DROP).lower()


@lru_cache(maxsize=4096)
def _lines(path: str) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


def link_target(r: dict, tree: str | None = None) -> str | None:
    """What an `alias` or an `@[deprecated X]` declaration points at, as
    written. An alias can put its target on the next line, which the scanned
    head leaves out; then it is read from source when a tree is given."""
    if r["kind"] == "alias":
        m = _ALIAS_TARGET.search(r["head"])
        if not m and tree:
            ln = _lines(os.path.join(tree, path_of(r["module"])))
            m = _ALIAS_TARGET.search(" ".join(ln[r["line"] - 1:r["line"] + 2]))
    elif "deprecated" in r.get("attrs", ""):
        m = _DEP_TARGET.search(r["attrs"])
    else:
        return None
    return m.group(1).rstrip(",") if m else None


def resolve(target: str, namespace: str, known) -> str | None:
    """The declaration a name written inside `namespace` refers to: the
    innermost reading that exists, as Lean resolves it."""
    if target.startswith("_root_."):
        target = target[len("_root_."):]
        return target if target in known else None
    parts = namespace.split(".") if namespace else []
    for i in range(len(parts), -1, -1):
        cand = ".".join(parts[:i] + [target])
        if cand in known:
            return cand
    return None


class Families:
    """The encoder-independent family of a declaration:

    * same module AND same `stem`; or
    * its to_additive twin, either direction, from the scanned attributes; or
    * an alias of it, or a declaration deprecated in its favour, either
      direction.

    `universe` holds the rows that can be indexed (name, module); `sources`
    holds (scan rows, source tree) pairs whose attributes and aliases supply
    the links."""

    def __init__(self, universe: list[dict], sources: list[tuple[list[dict], str | None]]):
        self.stems: dict[tuple[str, str], set[str]] = defaultdict(set)
        for r in universe:
            if s := stem(r["name"]):
                self.stems[(r["module"], s)].add(r["name"])
        known = {r["name"] for r in universe} | {r["name"] for rows, _ in sources for r in rows}
        self.links: dict[str, set[str]] = defaultdict(set)
        for rows, tree in sources:
            for r in rows:
                t = link_target(r, tree)
                for other in (twin(r), t and resolve(t, r.get("namespace", ""), known)):
                    if other and other != r["name"]:
                        self.links[r["name"]].add(other)
                        self.links[other].add(r["name"])

    def linked(self, name: str) -> set[str]:
        """The to_additive and alias half of the family only."""
        return set(self.links.get(name, ()))

    def of(self, name: str, module: str) -> set[str]:
        s = stem(name)
        out = set(self.stems.get((module, s), ())) if s else set()
        return (out | self.linked(name)) - {name}
