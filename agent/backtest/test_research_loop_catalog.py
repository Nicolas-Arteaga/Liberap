"""Contract tests for catalog-completeness terminal metadata."""
import json
import tempfile
import unittest
from pathlib import Path

import research_loop


class CatalogCompletenessTests(unittest.TestCase):
    def test_partial_catalog_lists_unimplemented_variants_and_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "candidate"
            candidate.mkdir()
            (candidate / "history.json").write_text(json.dumps({
                "candidate_id": "candidate", "attempts": [{"variant_id": "x"}]
            }), encoding="utf8")
            result = research_loop._set_terminal(
                root, "candidate", "DISCARDED_CATALOG_PARTIAL", "test",
                {"SALIDA": ("exit_not_implemented",)}, ("COSTOS", "SALIDA"),
            )
            self.assertEqual("PARTIAL", result["catalog_completeness"])
            self.assertEqual(["exit_not_implemented"], result["missing_executors"]["SALIDA"])
            self.assertIn("ENTRADA", result["attempt_policy"]["executable_areas_not_reached_before_terminal"])
            self.assertEqual(1, result["attempt_policy"]["attempts_completed"])

    def test_complete_catalog_has_no_missing_executors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "candidate").mkdir()
            result = research_loop._set_terminal(root, "candidate", "DISCARDED", "test", {}, research_loop.RECIPES)
            self.assertEqual("COMPLETE", result["catalog_completeness"])
            self.assertEqual({}, result["missing_executors"])


if __name__ == "__main__":
    unittest.main()
