"""The time-split arm's filters and kill test (mathgraph-269). Pure logic."""

import os
import tempfile
import unittest

from mathgraph.index import translation
from mathgraph.timesplit import absent_set, auroc, clean_doc, scan, score_system

NOV = """namespace Foo

/-- A brand new fact. -/
theorem fresh (n : Nat) : n + 0 = n := rfl

/-- Renamed from `Foo.old_name`. -/
theorem new_name (n : Nat) : 0 + n = n := by simp

@[deprecated (since := "2026-11-01")]
alias old_name :=
  new_name

/-- Same statement as a PIN theorem, so a move rather than a new fact. -/
theorem moved (a b : Nat) : a + b = b + a := Nat.add_comm a b

/-- The scanner stops at `ₘ`. -/
theorem barₘ : True := trivial

/-- A line the diff did not add. -/
theorem untouched : True := trivial

end Foo
"""


class AbsentSet(unittest.TestCase):
    def test_only_the_new_fact_survives(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "Mathlib"))
            with open(os.path.join(d, "Mathlib", "Foo.lean"), "w") as fh:
                fh.write(NOV)
            pin = [{"name": "Nat.add_comm'", "kind": "theorem",
                    "head": "theorem add_comm' (a b : Nat) : a + b = b + a := sorry"}]
            added = {"Mathlib/Foo.lean": {4, 7, 9, 10, 11, 14, 17}}
            kept, counts = absent_set(scan(d), pin, set(), added, d)
        self.assertEqual([r["name"] for r in kept], ["Foo.fresh"])
        self.assertEqual(counts["declaration line added in the diff"], 4)

    def test_verso_roles_do_not_reach_the_query(self):
        self.assertEqual(clean_doc("See {name}`Foo.bar` and `x`."), "See `Foo.bar` and `x`.")


class KillTest(unittest.TestCase):
    @staticmethod
    def recs(time_scores):
        out = []
        for i in range(200):
            out += [{"arm": "positive", "name": f"p{i}", "score": i / 200, "top1": f"p{i}"},
                    {"arm": "holdout", "name": f"h{i}", "score": 0.0, "top1": "x"},
                    {"arm": "deletion", "name": f"d{i}", "score": 0.0, "top1": "x"},
                    {"arm": "time", "name": f"t{i}", "score": time_scores(i), "top1": "x"}]
        return out

    def test_harder_negatives_survive(self):
        self.assertTrue(score_system(self.recs(lambda i: i / 200))["survives"])

    def test_negatives_no_harder_than_controls_are_killed(self):
        self.assertFalse(score_system(self.recs(lambda i: 0.0))["survives"])


class CrossFit(unittest.TestCase):
    def test_a_withheld_docstring_teaches_the_table_nothing(self):
        rows = ([{"name": f"frob_{i}", "doc": "Frobnicate the widget.", "tokens": ["frob", str(i)]}
                 for i in range(8)]
                + [{"name": f"quux_{i}", "doc": "Quux the gadget.", "tokens": ["quux", str(i)]}
                   for i in range(8)])
        table = translation(rows, {id(r) for r in rows[8:]})
        self.assertEqual(table["widget"], [("frob", 1.0)])
        self.assertNotIn("gadget", table)

    def test_auroc_counts_ties_half(self):
        self.assertEqual(auroc([2, 3], [1, 2]), 0.875)


if __name__ == "__main__":
    unittest.main()
