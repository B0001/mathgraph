"""Unit tests for CADE integration (mathgraph/cade.py)."""

import json
import os
import tempfile
import unittest

from mathgraph.cade import (
    CandidateMolecule,
    IterationFeedback,
    generate_hypotheses,
    consume_feedback,
    extract_candidates_from_text,
)


class TestCADE(unittest.TestCase):
    def test_extract_explicit_macro(self):
        text = r"Here is a candidate: \molecule{H4_chain}[H 0 0 0; H 0 0 1.0; H 0 0 2.0; H 0 0 3.0]"
        candidates = extract_candidates_from_text(text, source_id="test_doc")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].name, "H4_chain")
        self.assertEqual(candidates[0].atom_string, "H 0 0 0; H 0 0 1.0; H 0 0 2.0; H 0 0 3.0")
        self.assertEqual(candidates[0].source_id, "test_doc")
        self.assertEqual(candidates[0].metadata["extracted_via"], "macro")

    def test_extract_fallback_structure(self):
        text = "This paper proposes a structure: [H 0 0 0; H 0 0 1.5; H 0 0 3.0; H 0 0 4.5]"
        candidates = extract_candidates_from_text(text, source_id="test_doc")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].name, "Proposed_Structure")
        self.assertEqual(candidates[0].atom_string, "H 0 0 0; H 0 0 1.5; H 0 0 3.0; H 0 0 4.5")
        self.assertEqual(candidates[0].metadata["extracted_via"], "text_fallback")

    def test_generate_hypotheses_latex_parsing(self):
        latex_content = (
            r"\documentclass{article}"
            r"\begin{document}"
            r"\begin{theorem}"
            r"We consider the following candidate: \molecule{Ethylene}[C 0 0 0; C 0 0 1.33]"
            r"\end{theorem}"
            r"\end{document}"
        )
        with tempfile.NamedTemporaryFile(suffix=".tex", mode="w", delete=False, encoding="utf-8") as f:
            f.write(latex_content)
            temp_path = f.name

        try:
            candidates = generate_hypotheses(temp_path)
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].name, "Ethylene")
            self.assertEqual(candidates[0].atom_string, "C 0 0 0; C 0 0 1.33")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_generate_hypotheses_fallback_keyword(self):
        text_content = "This paper studies a simple H4 chain configuration."
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False, encoding="utf-8") as f:
            f.write(text_content)
            temp_path = f.name

        try:
            candidates = generate_hypotheses(temp_path)
            # Should fall back to generating H4 test fixtures
            self.assertEqual(len(candidates), 4)
            self.assertTrue(all(c.metadata.get("generated_test_fixture") for c in candidates))
            self.assertEqual(candidates[0].name, "H4_spacing_0.800")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_consume_feedback(self):
        candidate = CandidateMolecule(
            id="cand_test_01",
            name="Test Molecule",
            atom_string="H 0 0 0",
            source_id="test_source"
        )
        feedback = IterationFeedback(
            candidate_id="cand_test_01",
            verdict_ok=True,
            actuation_success=True,
            reason="Perfect alignment and synthesis successful"
        )
        result = consume_feedback(candidate, feedback)
        self.assertEqual(result["candidate_id"], "cand_test_01")
        self.assertEqual(result["certificate_status"], "VERIFIED")
        self.assertEqual(result["actuation_status"], "SUCCESSFUL")
        self.assertTrue(result["loop_closed"])


if __name__ == "__main__":
    unittest.main()
