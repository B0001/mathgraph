"""mathgraph-8c3: the history replay's event labelling, on a tiny synthetic history."""

import os
import subprocess
import tempfile
import unittest

from mathgraph.replay import Repo, auroc, cut, statement_events, tag_events, transfer

TEX = "blueprint/src/content.tex"


def commit(d: str, files: dict, msg: str) -> None:
    for path, text in files.items():
        os.makedirs(os.path.dirname(os.path.join(d, path)), exist_ok=True)
        with open(os.path.join(d, path), "w", encoding="utf-8") as fh:
            fh.write(text)
    git = ["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
           "-c", "core.hooksPath=/dev/null"]
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", msg], check=True)


def stmt(label: str, tags: str = "") -> str:
    lean = "\\lean{%s}" % tags if tags else ""
    return "\\begin{theorem}\\label{%s}%s Statement %s about sums.\\end{theorem}\n" % (label, lean, label)


class ReplayEvents(unittest.TestCase):
    def test_labels_drops_and_statement_events(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            a = "namespace A\ntheorem foo : True := trivial\ntheorem _root_.eroot : True := trivial\nend A\n"
            body = stmt("t1", "A.foo, eroot")
            commit(d, {"P/A.lean": a, TEX: stmt("t1")}, "root: an untagged statement")
            commit(d, {TEX: body}, "tag two existing declarations")
            body += stmt("t2", "B.bar")
            commit(d, {TEX: body, "P/B.lean": "theorem B.bar : True := trivial\n"}, "tag and declare together")
            body += stmt("t3", "C.baz")
            commit(d, {TEX: body}, "tag a planned name")
            commit(d, {"P/C.lean": "theorem C.baz : True := trivial\n"}, "declare it later")
            body += stmt("t4", "D.never") + stmt("t5", "Nat.add_comm") + stmt("t6", "not an ident")
            commit(d, {TEX: body}, "three tags that drop")
            body += stmt("t7", "B.qux")
            commit(d, {TEX: body, "P/B.lean": "theorem B.qux : True := trivial\n"}, "rename B.bar to B.qux")
            commit(d, {TEX: body + stmt("t8", "C.baz")}, "tag C.baz a second time")

            repo = Repo(d)
            tags = tag_events(repo, mathlib={"Nat.add_comm"})
            got = sorted((t["name"], t["drop"] or t["label"]) for t in tags)
            self.assertEqual(got, sorted([
                ("A.foo", "pre"), ("eroot", "pre"),           # `A._root_.eroot` declares `eroot`
                ("B.bar", "same"), ("C.baz", "later"),
                ("D.never", "never"), ("Nat.add_comm", "mathlib_name"),
                ("not an ident", "not_identifier"),
                ("B.qux", "commit_removes_decls"),           # the commit deletes B.bar
                ("C.baz", "repeat")]))                       # only a tag's first addition counts

            events, drops = statement_events(repo, tags)
            self.assertEqual(dict(drops), {})
            self.assertEqual([(e["block"].split("#")[1], e["positive"], e["labels"], e["gold"]) for e in events], [
                ("t1", True, ["pre"], ["A.foo", "eroot"]),
                ("t2", False, ["same"], []),
                ("t3", False, ["later"], [])])
            self.assertEqual(events[0]["text"], "Statement t1 about sums.")   # no \lean in the query
            # the parent snapshot of t1 holds both golds as candidates, untagged
            self.assertEqual(sorted(repo.decls(events[0]["parent"])), ["A.foo", "eroot"])
            self.assertEqual(repo.tagged(events[0]["parent"]), set())


class ReplayMetrics(unittest.TestCase):
    def test_auroc_ties_and_coverage_cut(self):
        inf = float("inf")
        self.assertEqual(auroc([0.9, 0.8], [0.1]), 1.0)
        self.assertEqual(auroc([-inf], [-inf]), 0.5)                 # two abstentions tie
        self.assertEqual(cut([5, 4, 3, 1], 0.5), (4, True))
        self.assertEqual(cut([5, 4, 4, 1], 0.5), (4, False))        # a straddling tie group is left out

    def test_tau_frozen_on_pfr_transfers_to_the_rest(self):
        def ev(project, c, positive, top="g"):
            return {"project": project, "positive": positive, "gold": ["g"] if positive else [],
                    "bge": {"top": top, "cos": c}}
        evs = [ev("pfr", c / 10, False) for c in range(10)]          # tau = 0.9: the top 1 of 10
        evs += [ev("x", 0.95, True), ev("x", 0.92, False), ev("x", 0.95, True, top="h"), ev("x", 0.5, True)]
        t = transfer(evs, "cos")
        self.assertEqual((t["tau"], t["answered"], t["correct"], t["precision"]), (0.9, 3, 1, 0.3333))


if __name__ == "__main__":
    unittest.main()
