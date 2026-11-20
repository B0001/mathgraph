"""The leave-family-out family rule (mathgraph-sd8), on known mathlib twins.
Pure logic."""

import unittest

from mathgraph.lfo import Families, stem


class Stem(unittest.TestCase):
    def test_variants_share_a_stem(self):
        for a, b in [
            ("mul_le_mul_left'", "mul_le_mul_left"),                        # prime
            ("add_le_add_left", "mul_le_mul_right"),                        # add/mul, left/right
            ("Finset.prod_le_prod_of_subset_of_one_le'", "Finset.prod_le_prod"),  # _of_ tail
            ("continuousWithinAt_Ioi_iff_Ici", "continuousAt_Ioi_iff_Ici"),  # Within
            ("continuousOn_const", "continuous_const"),                     # On
            ("tendsto_nhdsNE_iff", "tendsto_nhds_iff"),                     # NE
            ("isAddUnit_iff", "isUnit_iff"),                                # camel Add
        ]:
            self.assertEqual(stem(a), stem(b), (a, b))

    def test_different_facts_differ(self):
        self.assertNotEqual(stem("mul_comm"), stem("mul_assoc"))
        self.assertNotEqual(stem("mul_ne_zero"), stem("mul_eq_zero"))  # `ne` is a word, NE a marker
        self.assertNotEqual(stem("Nat.cast_ofNat"), stem("Nat.cast"))   # ofNat is no _of_ tail
        self.assertEqual(stem("of_not_not"), "of_not_not")              # nor is a leading of_

    def test_nothing_left_has_no_family(self):
        self.assertEqual(stem("Commute.mul_left"), "")
        fam = Families([{"name": "Commute.mul_left", "module": "M"},
                        {"name": "Commute.mul_right", "module": "M"}], [])
        self.assertEqual(fam.of("Commute.mul_left", "M"), set())


def row(name, module="Mathlib.Algebra.Foo", kind="theorem", head="", attrs="", namespace=""):
    return {"name": name, "module": module, "kind": kind, "line": 1, "head": head,
            "attrs": attrs, "namespace": namespace, "doc": ""}


class Family(unittest.TestCase):
    def setUp(self):
        src = [
            row("Finset.prod_comm", attrs="@[to_additive]", namespace="Finset"),
            row("mul_le_mul_left'", attrs="@[to_additive add_le_add_left]"),
            row("Finset.sum_comm'", attrs="", namespace="Finset"),
            row("Foo.old_name", kind="alias", head="alias old_name := new_name",
                attrs='@[deprecated (since := "2026-01-01")]', namespace="Foo"),
            row("Foo.new_name", namespace="Foo"),
            row("CompRel.of_rel", attrs='@[deprecated SymmGen.of_rel (since := "2026-01-25")]',
                module="Mathlib.Order.Comparable"),
            row("SymmGen.of_rel", module="Mathlib.Order.Comparable"),
            row("mul_comm", module="Mathlib.Algebra.Group.Defs"),
        ]
        universe = src + [row("Finset.sum_comm"), row("add_le_add_left"),
                          row("Multiset.sum_comm", module="Mathlib.Other")]
        self.fam = Families(universe, [(src, None)])

    def test_to_additive_twins_both_ways(self):
        self.assertIn("Finset.sum_comm", self.fam.of("Finset.prod_comm", "Mathlib.Algebra.Foo"))
        self.assertIn("Finset.prod_comm", self.fam.of("Finset.sum_comm", "Mathlib.Algebra.Foo"))
        self.assertIn("add_le_add_left", self.fam.linked("mul_le_mul_left'"))

    def test_aliases_and_deprecations_both_ways(self):
        self.assertEqual(self.fam.linked("Foo.new_name"), {"Foo.old_name"})
        self.assertEqual(self.fam.linked("Foo.old_name"), {"Foo.new_name"})
        self.assertIn("CompRel.of_rel", self.fam.linked("SymmGen.of_rel"))

    def test_stem_siblings_stay_in_their_module(self):
        fam = self.fam.of("Finset.sum_comm'", "Mathlib.Algebra.Foo")
        self.assertIn("Finset.sum_comm", fam)              # same module, same stem
        self.assertNotIn("Finset.sum_comm'", fam)          # never itself
        self.assertNotIn("Multiset.sum_comm", fam)         # same stem, other module
        self.assertEqual(self.fam.of("Multiset.sum_comm", "Mathlib.Other"), set())


if __name__ == "__main__":
    unittest.main()
