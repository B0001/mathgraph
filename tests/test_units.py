"""Pure-logic tests. No corpus, no numpy heavy lifting, runs in under a second.

Everything here is load-bearing in a way that is easy to break silently. The
stemmer in particular is deliberately conservative -- an over-eager stemmer
destroys the direct-match path to the mathlib token of the same name -- so the
cases that must NOT change are as important as the ones that must.

These pin behaviour, not literals. A test asserting `typ_weight == 0.15` would
only restate the source; these assert the properties the constants and
algorithms were chosen for.
"""

import unittest

import numpy as np

from mathgraph.align import Aligner, MARGIN_TAIL
from mathgraph.graph import build_graph
from mathgraph.index import (STOP, GroundTruth, doc_words, expand_to_additive,
                             stem, type_tokens)
from mathgraph.latex import extract_math, parse
from mathgraph.names import (additive_tokens, parse_to_additive_attr,
                             split_name, to_additive_name)


class Stem(unittest.TestCase):
    def test_does_not_destroy_direct_matches(self):
        """The whole approach rests on a query word hitting the mathlib token
        spelled the same way. `continuous` -> `continuou` would break that."""
        for w in ("continuous", "analysis", "series", "topos", "gas"):
            self.assertEqual(stem(w), w, f"{w} must survive stemming intact")

    def test_irregulars(self):
        self.assertEqual(stem("bases"), "basis")
        self.assertEqual(stem("matrices"), "matrix")
        self.assertEqual(stem("indices"), "index")

    def test_sibilant_plural_drops_two(self):
        """Only `-es` after a sibilant drops both characters."""
        self.assertEqual(stem("classes"), "class")
        self.assertEqual(stem("boxes"), "box")

    def test_plain_plural_drops_one(self):
        self.assertEqual(stem("mappings"), "mapping")

    def test_suffix_rewrites(self):
        self.assertEqual(stem("compactness"), "compact")
        self.assertEqual(stem("boundedly"), "bounded")

    def test_short_words_untouched(self):
        for w in ("set", "map", "le"):
            self.assertEqual(stem(w), w)


class SplitName(unittest.TestCase):
    def test_snake_and_dots(self):
        self.assertEqual(split_name("MeasureTheory.integral_add"),
                         ["measure", "theory", "integral", "add"])

    def test_camel(self):
        self.assertEqual(split_name("IsCompact.isClosed"),
                         ["is", "compact", "is", "closed"])

    def test_primes_are_separators_not_tokens(self):
        self.assertNotIn("'", "".join(split_name("foo'")))


class ToAdditive(unittest.TestCase):
    def test_snake_translation(self):
        self.assertEqual(to_additive_name("mul_comm"), "add_comm")

    def test_camel_translation(self):
        self.assertEqual(to_additive_name("Monoid.foo"), "AddMonoid.foo")

    def test_untranslatable_returns_none(self):
        """None means mathlib would not have generated an additive version --
        it is a real signal, not a failure, and callers branch on it."""
        self.assertIsNone(to_additive_name("continuous_foo"))

    def test_attr_parsing(self):
        self.assertEqual(parse_to_additive_attr("@[to_additive]"), (True, None))
        self.assertEqual(parse_to_additive_attr("@[to_additive add_foo]"),
                         (True, "add_foo"))
        self.assertEqual(parse_to_additive_attr("@[simp]"), (False, None))

    def test_attr_keywords_are_not_names(self):
        """`existing`, `reorder` and friends are to_additive options, not the
        name of the generated declaration."""
        self.assertEqual(parse_to_additive_attr("@[to_additive existing]"),
                         (True, None))

    def test_additive_tokens_translate_type_vocabulary(self):
        self.assertEqual(additive_tokens(["mul", "one"]), ["add", "zero"])

    def test_additive_tokens_expand_structures(self):
        """`Monoid` becomes `AddMonoid`, which is two tokens once split."""
        self.assertEqual(additive_tokens(["monoid"]), ["add", "monoid"])

    def test_additive_tokens_pass_unknowns_through(self):
        """Approximate by construction: it has exactly the coverage of
        mathlib's naming dictionary, and an unlisted structure is left alone."""
        self.assertEqual(additive_tokens(["continuous", "zzz"]),
                         ["continuous", "zzz"])


class ExpandToAdditive(unittest.TestCase):
    def _row(self, **kw):
        base = dict(name="mul_comm", namespace="", module="Mathlib.Algebra",
                    kind="theorem", attrs="@[to_additive]",
                    head="theorem mul_comm : forall {M} [CommMonoid M], ...")
        base.update(kw)
        return base

    def _expand(self, rows, truth=None):
        out, _ = expand_to_additive(rows, truth)
        return out

    def test_generates_the_twin(self):
        names = {r["name"] for r in self._expand([self._row()])}
        self.assertIn("add_comm", names)

    def test_twin_is_flagged_by_provenance(self):
        """A match must always be traceable to how the declaration got here."""
        twin = [r for r in self._expand([self._row()])
                if r["name"] == "add_comm"][0]
        self.assertTrue(twin["provenance"].startswith("to_additive"))

    def test_twin_has_no_source_text(self):
        """No source exists for a generated declaration; inventing one would
        make the provenance a lie."""
        twin = [r for r in self._expand([self._row()])
                if r["name"] == "add_comm"][0]
        self.assertEqual(twin["head"], "")

    def test_twin_still_gets_a_translated_type_field(self):
        """Regression guard. Twins used to carry no type tokens at all, which
        made the third index field structurally unable to fire for any additive
        lemma -- 10,875 declarations in idx_full."""
        twin = [r for r in self._expand([self._row()])
                if r["name"] == "add_comm"][0]
        self.assertTrue(twin["typ_tokens"], "twin must carry type tokens")
        self.assertIn("add", twin["typ_tokens"])
        self.assertNotIn("mul", twin["typ_tokens"])

    def test_explicit_name_is_honoured(self):
        out = self._expand([self._row(attrs="@[to_additive vadd_thing]")])
        self.assertIn("vadd_thing", {r["name"] for r in out})

    def test_existing_names_are_not_duplicated(self):
        rows = [self._row(), self._row(name="add_comm", attrs="")]
        out = self._expand(rows)
        self.assertEqual(sum(1 for r in out if r["name"] == "add_comm"), 1)


class ToAdditiveValidation(unittest.TestCase):
    """The reconstruction is ~29% wrong, so an elaborated environment is
    allowed to overrule it. What is pinned here is that the check is optional
    and that its absence is never silent."""

    def _row(self, **kw):
        base = dict(name="mul_comm", namespace="", module="Mathlib.Algebra",
                    kind="theorem", attrs="@[to_additive]",
                    head="theorem mul_comm : forall {M} [CommMonoid M], ...")
        base.update(kw)
        return base

    def _truth(self, names, modules=("Mathlib.Algebra",)):
        return GroundTruth(set(names), set(modules))

    def test_without_truth_nothing_is_dropped_and_it_says_so(self):
        """The laptop path. No toolchain means no check, and the provenance
        must not imply one happened."""
        out, stats = expand_to_additive([self._row()])
        twin = [r for r in out if r["name"] == "add_comm"][0]
        self.assertEqual(twin["provenance"], "to_additive:inferred:unvalidated")
        self.assertEqual(stats.get("inferred:dropped", 0), 0)

    def test_a_confirmed_name_is_marked_validated(self):
        out, stats = expand_to_additive([self._row()],
                                        self._truth(["add_comm"]))
        twin = [r for r in out if r["name"] == "add_comm"][0]
        self.assertEqual(twin["provenance"], "to_additive:inferred:validated")
        self.assertEqual(stats.get("inferred:validated"), 1)

    def test_an_invented_name_is_dropped(self):
        """`Filter.le_zero_iff` is one of ~3,000 the dictionary invents. Inside
        a covered module, absence from the environment is conclusive."""
        out, stats = expand_to_additive([self._row()], self._truth([]))
        self.assertNotIn("add_comm", {r["name"] for r in out})
        self.assertEqual(stats.get("inferred:dropped"), 1)

    def test_coverage_is_per_module_so_absence_is_not_overread(self):
        """A PFR declaration is missing from a mathlib environment because
        mathlib does not contain it, not because it does not exist. Outside a
        covered module the reconstruction stands, unvalidated."""
        row = self._row(module="PFR.Main")
        out, _ = expand_to_additive([row], self._truth([], ["Mathlib.Algebra"]))
        twin = [r for r in out if r["name"] == "add_comm"][0]
        self.assertEqual(twin["provenance"], "to_additive:inferred:unvalidated")

    def test_provenance_stays_prefix_compatible(self):
        """Every consumer tests `startswith("to_additive")`; the third
        component must not break them."""
        for truth in (None, self._truth(["add_comm"]), self._truth([])):
            out, _ = expand_to_additive([self._row()], truth)
            for r in out:
                if r["name"] != "mul_comm":
                    self.assertTrue(r["provenance"].startswith("to_additive"))


class TypeTokens(unittest.TestCase):
    HEAD = ("theorem f : forall {X} [T2Space X] {s : Set X}, "
            "IsCompact s -> IsClosed s")

    def test_reaches_hypotheses_the_name_never_mentions(self):
        """The entire reason the third field exists: `T2Space` is the Hausdorff
        hypothesis and appears nowhere in `IsCompact.isClosed`."""
        toks = type_tokens(self.HEAD)
        self.assertIn("t2", toks)
        self.assertIn("space", toks)

    def test_drops_syntax_and_single_letters(self):
        toks = type_tokens(self.HEAD)
        for junk in ("theorem", "X", "s"):
            self.assertNotIn(junk, toks)

    def test_strips_definition_bodies(self):
        """Load-bearing on regex-scraped heads, where 86% carry a `:=` followed
        by an implementation that is not part of the type."""
        self.assertEqual(type_tokens("def g : Nat := Foo.bar"), ["nat"])


class DocWords(unittest.TestCase):
    def test_drops_inline_code_and_math(self):
        out = doc_words("the `Foo.bar` lemma about $x + y$ continuity")
        self.assertNotIn("foo", out)
        self.assertNotIn("x", out)
        self.assertIn("continuity", out)

    def test_drops_stopwords(self):
        self.assertEqual(doc_words("the of and for theorem lemma"), [])

    def test_stopwords_include_the_boilerplate_of_statements(self):
        for w in ("theorem", "lemma", "proof", "we", "shows"):
            self.assertIn(w, STOP)


class Separation(unittest.TestCase):
    """The abstention margin. Measured against the mean of the tail rather than
    against rank 2, because rank-1-vs-2 cannot tell one close rival from nine
    and is destroyed by a single near-duplicate (mathlib is full of `foo`/`foo'`
    pairs and to_additive twins that score identically)."""

    sep = staticmethod(Aligner._separation)

    def test_nothing_else_retrieved(self):
        self.assertEqual(self.sep(np.array([1.0])), 1.0)

    def test_one_duplicate_does_not_collapse_the_statistic(self):
        """The documented case: a lone duplicate is one of nine competitors, so
        it moves the mean by about a ninth instead of pinning it at zero. The
        old rank-1-vs-2 margin read 0.0 on this vector."""
        v = np.array([1.0, 1.0] + [0.1] * 8)
        self.assertAlmostEqual(float(self.sep(v)), 0.80, places=4)

    def test_genuine_tie_reads_zero(self):
        """A real nine-way tie is exactly what the statistic should refuse to
        answer on.

        Note: the README says this case 'still reads 0.01'. It reads 0.0 --
        (1.0 - mean(ones)) / 1.0 is identically zero. The behaviour is correct
        and the documented figure is wrong."""
        self.assertEqual(float(self.sep(np.array([1.0] * 9))), 0.0)

    def test_tail_depth_is_bounded(self):
        """Beyond MARGIN_TAIL the tail stops carrying signal, so competitors
        past it must not move the statistic."""
        short = np.array([1.0] + [0.1] * (MARGIN_TAIL - 1))
        longer = np.array([1.0] + [0.1] * (MARGIN_TAIL - 1) + [0.9] * 20)
        self.assertAlmostEqual(float(self.sep(short)), float(self.sep(longer)))


class Latex(unittest.TestCase):
    SRC = r"""
\begin{theorem}[Nice thm]\label{thm:a}
The sum $a+b$ is continuous.
\lean{Continuous.add}\uses{thm:b}
\end{theorem}
\begin{proof}\uses{thm:a} trivial \end{proof}
"""

    def setUp(self):
        self.blocks = parse(self.SRC)

    def test_authored_edges_are_extracted_verbatim(self):
        """`\\label`, `\\ref` and `\\uses` are authored, not inferred. That
        distinction is the point of the graph command."""
        thm = self.blocks[0]
        self.assertEqual(thm.id, "thm:a")
        self.assertEqual(thm.uses, ["thm:b"])

    def test_lean_annotation(self):
        self.assertEqual(self.blocks[0].declared_lean, ["Continuous.add"])

    def test_title_and_kind(self):
        self.assertEqual(self.blocks[0].title, "Nice thm")
        self.assertEqual(self.blocks[0].kind, "theorem")
        self.assertEqual(self.blocks[1].kind, "proof")

    def test_math_is_kept_verbatim_and_removed_from_prose(self):
        """Formulas carry more signal than the prose, so they are kept as raw
        segments while the prose view sees a placeholder."""
        self.assertEqual(self.blocks[0].math, ["a+b"])
        self.assertNotIn("a+b", self.blocks[0].text)

    def test_comments_are_stripped(self):
        self.assertEqual(parse("% \\begin{theorem}\\label{x}\\end{theorem}"), [])

    def test_extract_math_handles_display_and_inline(self):
        got = extract_math(r"inline $x$ and display \[y\]")
        self.assertIn("x", got)
        self.assertIn("y", got)


class Graph(unittest.TestCase):
    def setUp(self):
        self.g = build_graph(parse(Latex.SRC))

    def test_dangling_reference_is_reported_not_invented(self):
        """A `\\uses` pointing outside the project is recorded as dangling
        rather than dropped or resolved to a guess."""
        self.assertIn("thm:a", {n["id"] for n in self.g["nodes"]})
        self.assertEqual([d["dst"] for d in self.g["dangling_refs"]], ["thm:b"])

    def test_internal_edge_records_which_command_authored_it(self):
        dep = [e for e in self.g["edges"] if e["type"] == "depends_on"]
        self.assertEqual([e["source"] for e in dep], ["uses"])

    def test_proof_is_linked_to_its_theorem(self):
        self.assertIn({"src": "proof:2", "dst": "thm:a", "type": "proves"},
                      self.g["edges"])

    def test_alignment_is_absent_without_an_aligner(self):
        """`graph --no-align` must produce pure authored structure: no
        inference, nothing that could be mistaken for an authored edge."""
        self.assertTrue(all("alignment" not in n for n in self.g["nodes"]))
        self.assertEqual(self.g["summary"]["alignment_status"],
                         {"not_attempted": 1})


if __name__ == "__main__":
    unittest.main()
