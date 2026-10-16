from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_queue import PENDING, RUNNING, ResearchQueue, clone_seed_revision, safe_worker_limit
from research_loop import materialize_factory_candidate, verify_revision


class ResearchQueueTests(unittest.TestCase):
    def test_memory_plan_refuses_second_7g_worker_without_headroom(self):
        plan = safe_worker_limit(3, available_bytes=11 * 1024**3)
        self.assertEqual(plan["allowed"], 1)
        self.assertEqual(plan["worker_rss_bytes"], 7 * 1024**3)

    def test_enqueue_is_idempotent_and_claim_is_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "research_loop"; rev = root / "candidate" / "1"; rev.mkdir(parents=True)
            db = Path(tmp) / "queue.db"; catalog = Path(tmp) / "catalog.md"; catalog.write_text("x")
            queue = ResearchQueue(db)
            with patch("research_queue.verify_revision") as verify:
                one = queue.enqueue(root, "candidate", catalog)
                two = queue.enqueue(root, "candidate", catalog)
            self.assertEqual(one["status"], PENDING); self.assertEqual(two["status"], PENDING)
            self.assertEqual(verify.call_count, 2)
            claimed = queue.claim("worker-a")
            self.assertEqual(claimed["status"], RUNNING)
            self.assertIsNone(queue.claim("worker-b"))

    def test_clone_preserves_entries_and_records_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source" / "original" / "1"; source.mkdir(parents=True)
            entries = b'{"open_ms":1}\n'
            (source / "entries.jsonl").write_bytes(entries)
            (source / "candidate.json").write_text(
                '{"candidate_id":"original","entries_artifact":{"sha256":"' +
                __import__("hashlib").sha256(entries).hexdigest() + '","count":1}}\n')
            dest = clone_seed_revision(Path(tmp) / "source", "original", Path(tmp) / "dest", "copy")
            self.assertEqual((dest / "entries.jsonl").read_bytes(), entries)
            manifest = __import__("json").loads((dest / "candidate.json").read_text())
            self.assertEqual(manifest["queue_e2e_provenance"]["source_candidate_id"], "original")

    def test_factory_candidate_is_a_formal_verifiable_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            entries = [
                {"open_ms": 1, "symbol": "BTCUSDT", "entry": 1.0, "side": 0, "sl": 0.9, "tp": 1.3},
                {"open_ms": 2, "symbol": "ETHUSDT", "entry": 2.0, "side": 1, "sl": 2.2, "tp": 1.4},
            ]
            revision = materialize_factory_candidate(
                Path(tmp), "factory-test", entries,
                {"display_name": "Factory test", "condition": "regla fija", "genome": {}},
            )
            manifest, actual, _fingerprint = verify_revision(revision)
            self.assertEqual(manifest["adapter_definition"]["name"], "factory_entries")
            self.assertEqual(manifest["adapter_definition"]["base_candle_adapter"], "rsi_reversal")
            self.assertEqual(actual, entries)


if __name__ == "__main__":
    unittest.main()
