"""Pure-logic tests. No corpus, no numpy heavy lifting, runs in under a second.

Everything here is load-bearing in a way that is easy to break silently. The
stemmer in particular is deliberately conservative -- an over-eager stemmer
destroys the direct-match path to the mathlib token of the same name -- so the
cases that must NOT change are as important as the ones that must.

These pin behaviour, not literals. A test asserting `typ_weight == 0.15` would
only restate the source; these assert the properties the constants and
algorithms were chosen for.
"""

import json
import os
import tempfile
import unittest

import numpy as np

from mathgraph.align import Aligner, MARGIN_TAIL
from mathgraph.graph import build_graph
from mathgraph.index import (STOP, GroundTruth, doc_words, expand_to_additive,
                             stem, type_tokens)
from mathgraph.latex import extract_math, parse, read_project
from mathgraph.names import (additive_tokens, explicit_additive_name,
                             parse_to_additive_attr, split_name,
                             to_additive_name)
from mathgraph.index import INDEX_VERSION
from mathgraph.setup_cmd import needs_build


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


class Project(unittest.TestCase):
    """mathgraph-cxh.1: the files given to `graph` are one paper."""
    FILES = {
        "preamble.tex": "\\newtheorem{metatheorem}{Metatheorem}\n",
        "a.tex": "\\section{A}\n\\begin{lemma}\\label{a} x \\end{lemma}\n"
                 "\\begin{proof} y \\end{proof}\n",
        "b.tex": "\\begin{proof} orphan \\end{proof}\n"
                 "\\begin{metatheorem} z \\end{metatheorem}\n\\begin{proof} w \\end{proof}\n",
    }

    def setUp(self):
        with tempfile.TemporaryDirectory() as d:
            paths = [os.path.join(d, f) for f in self.FILES]
            for p, src in zip(paths, self.FILES.values()):
                with open(p, "w") as fh:
                    fh.write(src)
            self.g = build_graph(read_project(paths))
            self.twice = build_graph(read_project(paths[1:2] * 2))
        self.proofs = [n for n in self.g["nodes"] if n["kind"] == "proof"]

    def test_proof_ids_are_unique_across_files(self):
        """Each file used to restart the counter, so both files had a
        `proof:2` and a reader by id merged them."""
        self.assertEqual(len({n["id"] for n in self.proofs}), 3)
        self.assertEqual(self.g["summary"]["duplicate_ids"], [])

    def test_a_preamble_newtheorem_applies_to_every_file(self):
        (meta,) = [n for n in self.g["nodes"] if n["env"] == "metatheorem"]
        self.assertEqual(meta["kind"], "theorem")
        self.assertIn({"src": self.proofs[-1]["id"], "dst": meta["id"], "type": "proves"},
                      self.g["edges"])

    def test_no_file_inherits_the_last_ones_section_or_statement(self):
        """Files usually arrive in glob order, not \\input order."""
        orphan = self.proofs[1]
        self.assertEqual((os.path.basename(orphan["file"]), orphan["line"], orphan["section"]),
                         ("b.tex", 1, ""))
        self.assertNotIn(orphan["id"], {e["src"] for e in self.g["edges"]})

    def test_a_label_used_twice_is_reported(self):
        self.assertEqual(self.twice["summary"]["duplicate_ids"], ["a"])


class ExplicitAdditiveName(unittest.TestCase):
    """`@[to_additive <name>]` names the twin's last components; the namespace
    it lands in is the source's, additively translated. Ported from mathlib's
    `targetName`, and every case here was checked against a real elaborated
    environment -- the names asserted below exist, the ones rejected do not."""

    def test_short_name_keeps_the_translated_namespace(self):
        """The case that exposed the bug. Appending to the scraped namespace
        gave a root-level `prod`, which is not a declaration."""
        self.assertEqual(
            explicit_additive_name("Submonoid.FG.prod", "prod"),
            "AddSubmonoid.FG.prod")
        self.assertEqual(
            explicit_additive_name("ContMDiffMul.prod", "prod"),
            "ContMDiffAdd.prod")

    def test_twin_keeps_the_depth_of_the_source(self):
        """A multi-part explicit name gives back one namespace component per
        component beyond its first, so the twin is as deep as the original."""
        self.assertEqual(
            explicit_additive_name("Foo.Submonoid.bar_mul", "Submonoid.bar_add"),
            "Foo.Submonoid.bar_add")

    def test_root_names_absolutely(self):
        self.assertEqual(
            explicit_additive_name("Submonoid.FG.prod", "_root_.sum"), "sum")

    def test_untranslatable_namespace_is_kept_as_is(self):
        """`translateNamespace` leaves components it has no translation for."""
        self.assertEqual(explicit_additive_name("Foo.bar_mul", "bar_add"),
                         "Foo.bar_add")

    def test_source_with_no_namespace(self):
        self.assertEqual(explicit_additive_name("one_lt_two", "zero_lt_two"),
                         "zero_lt_two")

    def test_scrape_artifacts_do_not_leak_into_the_name(self):
        """`_root_.Foo.bar` inside `namespace Baz` scrapes as
        `Baz._root_.Foo.bar`, and `abbrev GrpMax.{u}` as `GrpMax.` -- neither
        artifact is part of the declaration's actual name."""
        self.assertEqual(
            explicit_additive_name("QuotientGroup._root_.Subgroup.orderIsoCon",
                                   "AddSubgroup.orderIsoAddCon"),
            "AddSubgroup.orderIsoAddCon")
        self.assertEqual(explicit_additive_name("GrpMax.", "GrpMaxAux"),
                         "GrpMaxAux")


class NeedsBuild(unittest.TestCase):
    """`setup` skips any stage whose output exists, which is what makes the
    bootstrap resumable and is what let an index built before `elaborate` stay
    unvalidated forever -- nothing rebuilt it and nothing said so."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.idx = os.path.join(self.d, "idx_mathlib")
        os.makedirs(self.idx)
        open(os.path.join(self.idx, "index.pkl.gz"), "w").close()

    def _meta(self, **kw):
        kw.setdefault("index_version", INDEX_VERSION)
        with open(os.path.join(self.idx, "meta.json"), "w") as fh:
            json.dump(kw, fh)

    def test_missing_index_is_built(self):
        self.assertTrue(needs_build(os.path.join(self.d, "nope"), 464208))

    def test_present_index_is_not_rebuilt_without_ground_truth(self):
        """The laptop path. Nothing to be stale against, so nothing to redo,
        however the index was built."""
        self._meta(ground_truth_decls=0)
        self.assertFalse(needs_build(self.idx, 0))

    def test_index_from_an_older_builder_is_stale(self):
        """Ground truth cannot catch this one: same environment, different
        code. Without the stamp an index built by the old to_additive rule
        looks current forever."""
        self._meta(ground_truth_decls=464208, index_version=INDEX_VERSION - 1)
        self.assertTrue(needs_build(self.idx, 464208))
        self._meta(ground_truth_decls=0, index_version=INDEX_VERSION - 1)
        self.assertTrue(needs_build(self.idx, 0))   # even on the laptop path

    def test_index_with_no_meta_is_stale(self):
        """The trap, and the shape it was actually found in: built by a
        version of `build` that had no ground truth to record."""
        self.assertTrue(needs_build(self.idx, 464208))

    def test_index_built_without_the_ground_truth_is_stale(self):
        self._meta(ground_truth_decls=0)
        self.assertTrue(needs_build(self.idx, 464208))

    def test_index_built_against_a_different_ground_truth_is_stale(self):
        """A re-elaborated mathlib is a different corpus, not the same one."""
        self._meta(ground_truth_decls=460000)
        self.assertTrue(needs_build(self.idx, 464208))

    def test_index_built_against_this_ground_truth_is_done(self):
        self._meta(ground_truth_decls=464208)
        self.assertFalse(needs_build(self.idx, 464208))


class PrecisionAtCoverageTest(unittest.TestCase):
    """mathgraph-br3: the headline metric. Absent-arm answers are always wrong."""

    def test_answers_highest_scores_first_and_counts_absent_as_wrong(self):
        from mathgraph.bench_pretrained import precision_at_coverage
        recs = ([{"score": 0.9, "ok": 1}, {"score": 0.8, "ok": 0}]    # present hit, absent answer
                + [{"score": 0.1, "ok": 0}] * 8)
        (r,) = precision_at_coverage(recs, "score", coverages=(0.2,))
        self.assertEqual((r["answered"], r["correct"], r["precision"]), (2, 1, 0.5))

    def test_ties_at_the_cut_never_inflate_coverage(self):
        from mathgraph.bench_pretrained import precision_at_coverage
        recs = [{"score": 0.9, "ok": 1}] + [{"score": 0.5, "ok": 0}] * 9
        (r,) = precision_at_coverage(recs, "score", coverages=(0.2,))
        self.assertEqual(r["answered"], 1)  # the 9-way tie at the cut is left out, not half-answered

    def test_wilson_interval_brackets_the_rate(self):
        from mathgraph.bench_pretrained import wilson
        lo, hi = wilson(9, 10)
        self.assertLess(lo, 0.9)
        self.assertGreater(hi, 0.9)
        self.assertAlmostEqual(lo, 0.5958, places=3)  # standard Wilson 95% for 9/10


class NeighbourAnchoredCompletion(unittest.TestCase):
    """mathgraph-fxh: candidates one Lean reference from a neighbour's tag."""

    def test_candidates_split_by_edge_direction(self):
        from mathgraph.complete import PilotRefs, graph_top, neighbourhoods
        refs = PilotRefs({"A.up": "theorem A.up : True := trivial",
                     "B.tgt": "theorem B.tgt : True := A.up",     # cites its upstream anchor
                     "C.down": "theorem C.down : True := B.tgt",  # its downstream anchor cites it
                     "D.sib": "theorem D.sib : True := X.up"})    # `X.up` mentions every `*.up`
        tags = {"u": {"A.up"}, "t": {"B.tgt"}, "d": {"C.down"}}
        (r,) = [x for x in neighbourhoods(tags, {"t": {"u"}, "d": {"t"}}, refs) if x["id"] == "t"]
        self.assertEqual(r["gold"], ["B.tgt"])
        self.assertEqual(dict(r["links"]["n1"]), {"B.tgt": 2, "D.sib": 1})   # anchors excluded
        self.assertEqual(set(r["links"]["up"]), {"B.tgt", "D.sib"})
        self.assertEqual(set(r["links"]["down"]), {"B.tgt"})
        self.assertEqual(graph_top(r["links"]["n1"], 2)[0], "B.tgt")
        self.assertIsNone(graph_top(r["links"]["up"], 1)[0])                 # flat: abstain

    def test_proof_uses_count_for_its_statement_and_unlabelled_ids_stay_apart(self):
        from mathgraph.complete import blueprint
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "blueprint"))
            for f, lean in (("a.tex", "A.x"), ("b.tex", "B.y")):
                with open(os.path.join(d, "blueprint", f), "w") as fh:
                    fh.write("\\begin{lemma}\\lean{%s} x \\end{lemma}\n"
                             "\\begin{proof}\\uses{dep-%s} \\end{proof}\n" % (lean, f))
            tags, uses, _ = blueprint(d)
        self.assertEqual(sorted(map(sorted, tags.values())), [["A.x"], ["B.y"]])
        self.assertEqual(sorted(map(sorted, uses.values())), [["dep-a.tex"], ["dep-b.tex"]])

    def test_tied_or_empty_ranking_abstains(self):
        from mathgraph.complete import pick
        names, s = ["a", "b", "c"], np.array([0.5, 0.5, 0.1])
        self.assertIsNone(pick(names, s, s, np.arange(3), 0.0)[0])
        self.assertEqual(pick(names, s, s, np.array([1, 2]), 0.0), ("b", 0.5))
        self.assertIsNone(pick(names, np.zeros(3), s, np.arange(3), 0.0)[0])  # nothing above the floor
        self.assertIsNone(pick(names, s, s, np.array([], dtype=int), 0.0)[0])

    def test_resolved_refs_invert_cites(self):
        from mathgraph.complete import Refs
        refs = Refs({"a": {"b"}, "b": set(), "c": {"b"}})
        self.assertEqual((refs.cites("a"), refs.cited_by("b"), refs.cited_by("a")), ({"b"}, {"a", "c"}, set()))
        self.assertIn("b", refs)                 # in the population even though it cites nothing
        self.assertNotIn("z", refs)

    def test_sign_test_is_exact_and_two_sided(self):
        from mathgraph.complete import sign_test
        rec = lambda a, b: {"gold": ["g"], "top": {"a": (a, 1.0), "b": (b, 1.0)}}   # noqa: E731
        recs = [rec("g", None)] * 5 + [rec("g", "g")] * 3 + [rec(None, "x")] * 2     # concordant pairs drop out
        self.assertEqual(sign_test(recs, "a", "b"), {"plus": 5, "minus": 0, "p": 0.0625})   # 2 / 2**5
        self.assertEqual(sign_test(recs, "b", "a")["p"], 0.0625)
        self.assertEqual(sign_test(recs[5:], "a", "b")["p"], 1.0)                 # no discordant pair

    def test_handcheck_scores_each_matcher_on_the_shared_candidates(self):
        from mathgraph.handcheck import score
        c = lambda new, pilot, genuine: {"new": new, "pilot": pilot, "genuine": genuine}   # noqa: E731
        s = score({"bodies": [{"candidates": {"a": c(True, True, True), "b": c(False, True, False),
                                              "c": c(True, False, True)}},
                              {"candidates": {"d": c(True, False, False)}}]})
        self.assertEqual((s["new"]["genuine"], s["new"]["extracted"], s["new"]["bodies_with_spurious"]), (2, 3, 1))
        self.assertEqual((s["pilot"]["genuine"], s["pilot"]["extracted"], s["pilot"]["bodies_with_spurious"]),
                         (1, 2, 1))
        self.assertEqual((s["genuine_new_only"], s["genuine_pilot_only"]), (1, 0))
        self.assertTrue(s["recall_not_lower"])
        self.assertFalse(s["precision_at_least_70"])          # 2/3


def lean_refs(files: dict, mathlib=()) -> dict:
    """leanrefs.Project(...).refs over Lean sources {module: text}, every
    named declaration a row; `mathlib` names the Mathlib declarations."""
    from mathgraph.leanrefs import Mathlib, Project
    with tempfile.TemporaryDirectory() as d:
        ml = os.path.join(d, "mathlib.jsonl")
        with open(ml, "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps({"name": n, "head": ""}) + "\n" for n in mathlib)
        paths = {}
        for m, src in files.items():
            paths[m] = os.path.join(d, m + ".lean")
            with open(paths[m], "w", encoding="utf-8") as fh:
                fh.write(src)
        proj = Project(paths, Mathlib(ml))
    return proj.refs([{"name": x.name, "module": x.module, "line": x.line} for x in proj.decls if x.name])


class LeanRefs(unittest.TestCase):
    """mathgraph-ydf: an identifier links to the declaration Lean's name
    resolution would pick, not to every namesake (the pilot's 39.5%)."""

    def test_strip_blanks_comments_and_strings_but_keeps_positions(self):
        from mathgraph.leanrefs import strip
        src = 'theorem a : True := by\n  -- uses b\n  /- nested /- c -/ d -/\n  exact "e" ▸ trivial\n'
        out = strip(src)
        self.assertEqual((len(out), out.count("\n")), (len(src), src.count("\n")))
        self.assertEqual(out.split(), ["theorem", "a", ":", "True", ":=", "by", "exact", "▸", "trivial"])

    def test_body_ends_at_the_next_column0_command(self):
        r = lean_refs({"M": "def b : Nat := 1\ntheorem a : True := trivial\nattribute [simp] b\n"
                            "/-- see `b` -/\ntheorem c : b = 1 := rfl\n"})
        self.assertEqual((r["a"], r["c"]), (set(), {"b"}))   # neither the attribute nor the docstring is a's

    def test_innermost_namespace_first_and_own_name_opens_its_namespace(self):
        r = lean_refs({"M": "def foo : Nat := 0\nnamespace A\ndef foo : Nat := 1\nnamespace B\n"
                            "theorem t : foo = 1 := rfl\nend B\nend A\ntheorem u : foo = 0 := rfl\n"
                            "def Foo.baz : Nat := 0\ntheorem Foo.bar : baz = 0 := rfl\n"
                            "theorem other : baz = 0 := rfl\n"})
        self.assertEqual((r["A.B.t"], r["u"]), ({"A.foo"}, {"foo"}))
        self.assertEqual((r["Foo.bar"], r["other"]), ({"Foo.baz"}, set()))

    def test_open_in_explicit_hiding_and_renaming(self):
        r = lean_refs({"M": "namespace X\ndef f : Nat := 0\ndef g : Nat := 1\nend X\n"
                            "open X in\ntheorem t1 : f = 0 := rfl\ntheorem t2 : f = 0 := rfl\n"
                            "section\nopen X (g)\ntheorem t3 : g = f := rfl\nend\n"
                            "section\nopen X hiding f\ntheorem t4 : g = f := rfl\nend\n"
                            "section\nopen X renaming g → gg\ntheorem t5 : gg = 1 := rfl\nend\n"})
        self.assertEqual([r[t] for t in ("t1", "t2", "t3", "t4", "t5")],
                         [{"X.f"}, set(), {"X.g"}, {"X.g"}, {"X.g"}])   # `open X in` covers t1 only

    def test_protected_private_and_export(self):
        r = lean_refs({"A": "namespace Y\nprotected def p : Nat := 0\nend Y\nopen Y\n"
                            "theorem t5 : p = 0 := rfl\ntheorem t6 : Y.p = 0 := rfl\n"
                            "private def h : Nat := 0\ntheorem ta : h = 0 := rfl\n"
                            "namespace Z\ndef e : Nat := 0\nend Z\nnamespace W\nexport Z (e)\nend W\n"
                            "theorem t7 : W.e = 0 := rfl\n",
                       "B": "theorem tb : h = 0 := rfl\n"})
        self.assertEqual((r["t5"], r["t6"]), (set(), {"Y.p"}))      # a protected name needs its qualifier
        self.assertEqual((r["ta"], r["tb"]), ({"h"}, set()))        # private stays in its file
        self.assertEqual(r["t7"], {"Z.e"})                          # the export alias is the original

    def test_locals_shadow_globals_and_anonymous_suffices_binds_nothing(self):
        r = lean_refs({"M": "def x : Nat := 0\ntheorem t8 (x : Nat) : x = x := rfl\n"
                            "theorem t9 : ∀ x : Nat, x = x := fun x => rfl\n"
                            "section\nvariable (x : Nat)\ntheorem t10 : x = x := rfl\nend\n"
                            "theorem t11 : x = 0 := rfl\n"
                            "def s : Prop := True\ntheorem t12 : s ∧ True := by\n  suffices s by exact ⟨this, trivial⟩\n"
                            "  exact trivial\ntheorem t13 : True := by\n  obtain ⟨s, hs⟩ : ∃ n : Nat, n = n := ⟨0, rfl⟩\n"
                            "  exact trivial\n"})
        self.assertEqual([r[t] for t in ("t8", "t9", "t10", "t11")], [set(), set(), set(), {"x"}])
        self.assertEqual((r["t12"], r["t13"]), ({"s"}, set()))

    def test_dot_notation(self):
        r = lean_refs({"M": "structure S where\n  n : Nat\ndef S.double (a : S) : Nat := 2 * a.n\n"
                            "theorem t14 (a : S) : a.double = 2 * a.n := rfl\n"
                            "def Foo.go : Nat := 0\ndef Bar.go : Nat := 0\ndef Baz.solo : Nat := 0\n"
                            "theorem t15 (h) : h.solo = h.go ∧ True := sorry\n"})
        self.assertEqual(r["t14"], {"S", "S.double"})               # the written binder type picks S.double
        self.assertEqual(r["t15"], {"Baz.solo"})                    # untyped: only a field with one owner

    def test_a_mathlib_name_shadows_a_project_namesake(self):
        r = lean_refs({"M": "def card_le : Nat := 0\nnamespace Finset\ntheorem t : card_le = card_le := rfl\n"
                            "end Finset\ntheorem u : card_le = 0 := rfl\n"}, mathlib=["Finset.card_le"])
        self.assertEqual((r["Finset.t"], r["u"]), (set(), {"card_le"}))


if __name__ == "__main__":
    unittest.main()
