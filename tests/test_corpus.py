"""Tests that need a built corpus. Skipped cleanly when there isn't one.

These pin the calibrated behaviour -- the part that cannot be checked by
reading the source, because every threshold in `cli.py` is a constant fitted
numerically against a specific scorer. The README puts it plainly: "Changing a
scorer silently invalidates every constant fitted against it." That is the
failure this file exists to catch.

Run with a corpus present:

    MATHGRAPH_DATA=./mathgraph-data python -m unittest discover tests

Roughly a minute, dominated by the benchmark.
"""

import glob
import json
import os
import unittest

import numpy as np

from mathgraph.align import MATCHED, Aligner
from mathgraph.cli import GRAPH_THRESHOLDS, LEX, VERIFY_PROFILES
from mathgraph.index import load
from mathgraph.latex import parse
from mathgraph.verify import NONEXISTENT, Verifier

DATA = os.environ.get("MATHGRAPH_DATA", "./mathgraph-data")
ART = os.path.join(DATA, "artifacts")


def _has(name):
    return os.path.exists(os.path.join(ART, name, "index.pkl.gz"))


needs = lambda *n: unittest.skipUnless(       # noqa: E731
    all(_has(x) for x in n), f"corpus {'/'.join(n)} not built")

_cache = {}


def idx(name):
    if name not in _cache:
        _cache[name] = load(os.path.join(ART, name))
    return _cache[name]


def aligner(name, **over):
    return Aligner(idx(name), **{**LEX, "tau_cov": 0.0, "delta_margin": 0.0,
                                 **over})


def pfr_blocks():
    pat = os.path.join(DATA, "blueprints", "pfr", "blueprint", "src",
                       "chapter", "*.tex")
    out = []
    for f in sorted(glob.glob(pat)):
        with open(f, encoding="utf-8") as fh:
            out.extend(parse(fh.read()))
    return [b for b in out if b.declared_lean and b.kind != "proof"
            and len(b.text.split()) >= 5]


def bp_pairs():
    p = os.path.join(ART, "blueprint_pairs.jsonl")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh]


@needs("idx_full", "idx_elaborated")
class CoverageIsAFraction(unittest.TestCase):
    """`coverage` is the abstention statistic: `align` returns UNMATCHED below
    tau_cov. It is only meaningful if it is a fraction of the query's available
    evidence.

    It used to not be. `_score` accumulated the denominator only for tokens
    with *name* postings while module and type postings still fed the
    numerator, so a token living solely in the type field -- exactly what the
    third field was added to serve -- inflated it without bound. The two-token
    query {equiv, bg} reached coverage 2.315.

    This held silently only because typ_weight is small, which is precisely why
    it needs pinning across weights rather than at the shipped one.
    """

    def _queries(self):
        qs = [(p["text"], p.get("title", "")) for p in bp_pairs()[:150]]
        return qs or [("a compact subset of a Hausdorff space is closed", "")]

    def test_bounded_at_every_type_weight(self):
        for corpus in ("idx_full", "idx_elaborated"):
            for tw in (0.0, 0.15, 1.0, 2.0):
                al = aligner(corpus, typ_weight=tw)
                worst = max(al.align(t, topk=5, title=ti).coverage
                            for t, ti in self._queries())
                self.assertLessEqual(
                    worst, 1.0 + 1e-9,
                    f"{corpus} typ_weight={tw}: coverage {worst:.4f} exceeds 1; "
                    f"`mass` is no longer an upper bound on `raw`")

    def test_never_negative(self):
        al = aligner("idx_full")
        for t, ti in self._queries():
            self.assertGreaterEqual(al.align(t, topk=5, title=ti).coverage, 0.0)

    def test_the_regression_case_specifically(self):
        """{equiv, bg}: `bg` exists only in the type field with IDF 12.35,
        `equiv` is an ordinary name token. This is the constructed witness."""
        al = aligner("idx_elaborated")
        if "bg" not in al.typpost or "equiv" not in al.post:
            self.skipTest("witness tokens absent from this corpus build")
        res = al._score({"equiv": 1.0, "bg": 1.0}, 10)
        self.assertNotEqual(len(res), 3, "expected a scored result")
        _ids, _sc, mass, rawtop = res
        self.assertLessEqual(float(rawtop[0] / mass), 1.0 + 1e-9)


@needs("idx_full")
class Benchmark(unittest.TestCase):
    """The published PFR numbers.

    Tolerance is deliberate. Exact equality catches scorer regressions but
    fires the moment anyone legitimately improves the scorer, which would train
    people to edit the test. A band of one percentage point is wider than the
    ~0.6pt that a single statement moves at n=175, and narrower than any change
    worth reporting. If this fails because you improved something, that is the
    signal to refit GRAPH_THRESHOLDS and VERIFY_PROFILES and update the numbers
    here in the same commit -- not to widen the band.
    """

    DELTA = 0.01
    EXPECTED = {"lexical": (0.189, 0.320), "+structural": (0.200, 0.389)}

    @classmethod
    def setUpClass(cls):
        from mathgraph.structmatch import StructReranker
        al = aligner("idx_full")
        known = {r["name"] for r in al.rows}
        blocks = pfr_blocks()
        if not blocks:
            raise unittest.SkipTest("PFR blueprint sources not present")
        rr = StructReranker(al, lam=0.9, depth=10000)
        cls.got = {}
        for label, lam in (("lexical", 0.0), ("+structural", 0.9)):
            rr.lam = lam
            h1 = h5 = n = 0
            for b in blocks:
                gold = [g for g in b.declared_lean if g in known]
                if not gold:
                    continue
                n += 1
                names, _ = rr.rank(b.text, b.title, b.math, topk=5)
                if names and names[0] in gold:
                    h1 += 1
                if set(names) & set(gold):
                    h5 += 1
            cls.got[label] = (h1 / n, h5 / n, n)

    def test_evaluated_on_the_documented_number_of_statements(self):
        self.assertEqual(self.got["lexical"][2], 175)

    def test_recall_matches_published(self):
        for label, (r1, r5) in self.EXPECTED.items():
            g1, g5, _ = self.got[label]
            self.assertAlmostEqual(g1, r1, delta=self.DELTA,
                                   msg=f"{label} recall@1 {g1:.3f} vs {r1}")
            self.assertAlmostEqual(g5, r5, delta=self.DELTA,
                                   msg=f"{label} recall@5 {g5:.3f} vs {r5}")

    def test_structural_reranking_beats_lexical_at_recall5(self):
        """The claim the structural matcher exists to support."""
        self.assertGreater(self.got["+structural"][1], self.got["lexical"][1])


@needs("idx_mathlib")
class Abstention(unittest.TestCase):
    """The central calibration claim: on statements whose answer is genuinely
    absent from the index, the aligner says so. Zero false matches is the
    operating point every threshold in GRAPH_THRESHOLDS was fitted to hold."""

    @classmethod
    def setUpClass(cls):
        cls.blocks = pfr_blocks()
        if not cls.blocks:
            raise unittest.SkipTest("PFR blueprint sources not present")
        cls.al = aligner("idx_mathlib", **GRAPH_THRESHOLDS)
        cls.known = {r["name"] for r in cls.al.rows}

    def test_zero_false_matches_on_the_absent_arm(self):
        false = []
        n = 0
        for b in self.blocks:
            if any(g in self.known for g in b.declared_lean):
                continue                     # genuinely present; not a negative
            n += 1
            a = self.al.align(b.text, title=b.title, topk=3)
            if a.status == MATCHED:
                false.append((b.id, a.candidates[0].name, round(a.coverage, 3)))
        self.assertGreater(n, 100, "expected a substantial negative arm")
        self.assertEqual(false, [], f"{len(false)}/{n} false matches; "
                                    f"GRAPH_THRESHOLDS need refitting")

    def test_thresholds_are_actually_engaged(self):
        """Guard against the failure mode where abstention looks perfect
        because the thresholds are so high that nothing is ever answered --
        which is what the pre-refit 0.35/0.08 pair did (1 answered of 439)."""
        self.assertGreater(self.al.tau_cov, 0.0)
        self.assertGreater(self.al.delta_margin, 0.0)

    def test_zero_false_matches_on_the_arm_it_was_fitted_on(self):
        """The arm above is PFR; this is the 439 blueprint pairs, which is
        what GRAPH_THRESHOLDS was actually fitted against. It was untested,
        and that is how 0.2474/0.2671 came to hold on PFR while admitting
        three false matches here the moment the corpus was rebuilt with the
        to_additive ground truth wired in.

        Same construction as the fit: a pair whose declaration is genuinely
        absent from a mathlib-only index has no correct answer but abstain."""
        pairs = bp_pairs()
        if not pairs:
            self.skipTest("blueprint_pairs.jsonl not present")
        false = []
        n = 0
        for p in pairs:
            if set(p["targets"]) & self.known:
                continue                 # answer is in mathlib; not a negative
            n += 1
            a = self.al.align(p["text"], title=p.get("title", ""), topk=3)
            if a.status == MATCHED:
                false.append((p["id"], a.candidates[0].name, round(a.coverage, 4)))
        self.assertGreater(n, 400, "expected essentially all 439 to be negatives")
        self.assertEqual(false, [], f"{len(false)}/{n} false matches; "
                                    f"GRAPH_THRESHOLDS need refitting")


@needs("idx_full")
class NonexistentIsSound(unittest.TestCase):
    """`rejected` and `verified` are calibrated; `nonexistent` is a claim about
    whether the name is in the index at all.

    It is sound, and the tests below pin exactly that. A name absent from the
    index always reports nonexistent. Whether the converse holds depends on how
    the index was built, so these tests deliberately do not assume it: the ~10k
    to_additive declarations are *reconstructed* by applying a naming
    dictionary, and 29.1% of the inferred ones name something mathlib never
    generated. `index.build` drops those when an elaborated environment is
    available, which makes nonexistent exact in both directions on a validated
    mathlib-only index -- but the index under test here may have been built
    without one, and idx_full keeps unvalidated reconstructions in PFR modules
    the environment does not cover either way.

    So "not nonexistent" means reachable, not real. Do not strengthen these
    tests into an existence claim; assert on `provenance` instead, which is
    where the distinction actually lives.
    """

    @classmethod
    def setUpClass(cls):
        cls.V = Verifier(aligner("idx_full"), **VERIFY_PROFILES["permissive"])
        cls.rows = idx("idx_full")["rows"]

    def test_absent_name_is_nonexistent(self):
        v = self.V.verify("the sum of two continuous functions is continuous",
                          "Totally.Made.Up.Name")
        self.assertEqual(v.status, NONEXISTENT)

    def test_present_name_is_never_nonexistent(self):
        v = self.V.verify("the sum of two continuous functions is continuous",
                          "Continuous.add")
        self.assertNotEqual(v.status, NONEXISTENT)

    def test_to_additive_reconstructions_stay_reachable(self):
        """These appear in no source file. If the reconstruction regresses they
        become invisible and the tool starts calling real lemmas nonexistent.

        Reachability only -- see the class docstring. Roughly 3,000 of these
        names are inventions, and this test deliberately does not assert they
        exist."""
        gen = [r["name"] for r in self.rows
               if r.get("provenance", "").startswith("to_additive")][:25]
        self.assertTrue(gen, "no to_additive declarations in this index")
        for name in gen:
            self.assertNotEqual(
                self.V.verify("an additive statement", name).status,
                NONEXISTENT, f"{name} was reconstructed but reads nonexistent")

    def test_provenance_is_reported_and_distinguishes_scanned_from_guessed(self):
        """The only signal a caller has for how much to trust a match, now that
        `nonexistent` is known to be incomplete.

        Both kinds are drawn from the index rather than hardcoded, because
        guessing wrong is easy: `Continuous.add` reads as a plain source lemma
        and is in fact to_additive-generated from `Continuous.mul`.
        """
        want = {}
        for r in self.rows:
            p = r.get("provenance", "source")
            key = "source" if p == "source" else "generated"
            want.setdefault(key, r["name"])
            if len(want) == 2:
                break
        self.assertEqual(set(want), {"source", "generated"})
        for key, name in want.items():
            got = self.V.verify("an arbitrary statement", name).to_json()
            self.assertNotEqual(got["status"], NONEXISTENT)
            if key == "source":
                self.assertEqual(got["provenance"], "source")
            else:
                self.assertTrue(got["provenance"].startswith("to_additive"),
                                f"{name} reported {got['provenance']}")


@needs("idx_blueprint")
class VerifierProfiles(unittest.TestCase):
    """The three profiles are strictly nested in what they accept.

    Measured, not assumed: on 120 blueprint pairs they accept 6 / 15 / 31, and
    each acceptance set is a subset of the next. A profile named `precise` that
    accepted something `permissive` rejected would make the names meaningless.
    """

    @classmethod
    def setUpClass(cls):
        al = aligner("idx_blueprint")
        known = {r["name"] for r in al.rows}
        pairs = [p for p in bp_pairs()
                 if any(t in known for t in p["targets"])][:120]
        if not pairs:
            raise unittest.SkipTest("no blueprint pairs resolvable")
        cls.acc = {}
        for name, kw in VERIFY_PROFILES.items():
            V = Verifier(al, **kw)
            cls.acc[name] = {
                i for i, p in enumerate(pairs)
                if V.verify(p["text"],
                            [t for t in p["targets"] if t in known][0],
                            p.get("title", ""),
                            math_segments=p.get("math", [])).status == "verified"}

    def test_nested_acceptance(self):
        self.assertLessEqual(self.acc["precise"], self.acc["balanced"])
        self.assertLessEqual(self.acc["balanced"], self.acc["permissive"])

    def test_profiles_are_distinguishable(self):
        """If they all accepted the same set the three names would be a lie."""
        self.assertLess(len(self.acc["precise"]), len(self.acc["permissive"]))


if __name__ == "__main__":
    unittest.main()
