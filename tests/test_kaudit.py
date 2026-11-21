"""The kernel audit's batch parser and certification rule (mathgraph-6vm).
Pure logic: the Lean log and dump lines below are synthetic, in the formats
`lean` and lean/KAudit.lean write."""

import os
import unittest

from mathgraph.kaudit import (NULL, batch_text, certify, check_cmd, parse_checks,
                               plan_followup)


class ParseAndCertify(unittest.TestCase):
    def test_batch_to_certified_units(self):
        path = os.path.abspath("check0.lean")
        cmds = [("c0", check_cmd("c0", "Nat.add_comm", "add_comm", [])),
                ("n0", check_cmd("n0", "Nat.add_comm", "", [], NULL)),
                ("c1", check_cmd("c1", "Foo.h", "Foo.t", ["Foo.h"])),
                ("n1", check_cmd("n1", "Foo.h", "", ["Foo.h"], NULL)),
                ("c2", check_cmd("c2", "Bar.h", "Bar.t", []))]
        text, at = batch_text(cmds)
        line = {cid: n for n, (cid, k) in at.items() if k == 0}
        lines = text.splitlines()
        self.assertTrue(lines[line["c1"] - 1].startswith(
            "attribute [-simp] Foo.h in theorem kaudit.c1 : type_of% @Foo.h := by intros; first"
            ' | kalt "K1" (exact Foo.t ..) |'))
        self.assertEqual(lines[line["c0"]], "#kdump kaudit.c0")
        self.assertEqual(lines[-1], "#kdump kaudit.end")
        log = "\n".join([
            f"{path}:{line['n0']}:60: error: unsolved goals",
            "n✝ m✝ : ℕ",                                       # a continuation line
            f"{path}:{line['c2']}:31: error(lean.unknownIdentifier): Unknown constant `Bar.h`",
            f"/elsewhere.lean:{line['c0']}:1: error: not ours"])
        dump = ['{"tag":"K1"}',
                '{"kdump":"kaudit.c0","used":["add_comm","instAddNat"]}',
                '{"kdump":"kaudit.n0","used":["sorryAx"]}',
                '{"tag":"D1"}',
                '{"kdump":"kaudit.c1","used":["Foo.t"]}',
                '{"tag":"N2"}',                                 # the null closes
                '{"kdump":"kaudit.n1","used":["Foo.simp_lemma"]}',
                '{"kdump":"kaudit.c2","absent":true}',
                '{"kdump":"kaudit.end","used":[]}',
                '{"kdump":"kaud']                               # cut short by a crash
        res = parse_checks(log, path, at, dump)
        self.assertEqual(res["c0"], {"tag": "K1", "absent": False, "closed": True,
                                     "used": ["add_comm", "instAddNat"]})
        self.assertFalse(res["n0"]["closed"])
        self.assertEqual(res["n0"]["error"], "unsolved goals")
        self.assertNotIn("tag", res["n0"])
        self.assertEqual((res["c1"]["tag"], res["n1"]["tag"]), ("D1", "N2"))
        self.assertTrue(res["c2"]["absent"] and not res["c2"]["closed"])
        self.assertTrue(res["end"]["closed"])

        facts = {n: {"const": n} for n in ("Nat.add_comm", "add_comm", "Foo.h", "Foo.t")}
        units = [{"status": "checked", "H": "Nat.add_comm", "T": "add_comm",
                  "cid": "c0", "nid": "n0"},
                 {"status": "checked", "H": "Foo.h", "T": "Foo.t", "cid": "c1", "nid": "n1"},
                 {"status": "checked", "H": "Foo.h", "T": "Foo.t", "cid": "c9", "nid": "n1"},
                 {"status": "H_private", "H": "Baz.h", "T": "Baz.t"},
                 {"status": "checked", "H": "Foo.h", "T": "Foo.t", "cid": "c1", "nid": "n9"}]
        certify(units, facts, res, res)        # real and follow-up ids are disjoint
        self.assertEqual([u["certified"] for u in units], [True, False, False, False, False])
        self.assertTrue(units[1]["closed"] and units[1]["null_closed"])
        self.assertEqual([units[2]["status"], units[4]["status"]], ["not_run", "null_not_run"])


class FollowupIds(unittest.TestCase):
    def test_ids_do_not_depend_on_unit_order(self):
        facts = {n: {"const": n, "simp": False} for n in ("A.h", "A.t", "B.h", "B.t")}
        real = {"c0": {"closed": True}, "c1": {"closed": True}}
        mk = lambda: [{"status": "checked", "H": "B.h", "T": "B.t", "cid": "c1",
                       "system": "lexical", "arm": "holdout"},
                      {"status": "checked", "H": "A.h", "T": "A.t", "cid": "c0",
                       "system": "lexical", "arm": "holdout"}]
        a, b = mk(), mk()[::-1]
        self.assertEqual(plan_followup(a, facts, real), plan_followup(b, facts, real))
        self.assertEqual({u["H"]: (u["nid"], u["rid"]) for u in a},
                         {u["H"]: (u["nid"], u["rid"]) for u in b})


if __name__ == "__main__":
    unittest.main()
