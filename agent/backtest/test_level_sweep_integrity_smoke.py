"""Smoke M1b de Level Sweep antes de una auditoría completa."""
from __future__ import annotations

import unittest

import lab_core as core
import lab_integrity as integrity
from lab_adapters.level_sweep import LevelSweepAdapter


class LevelSweepIntegritySmoke(unittest.TestCase):
    def test_replay_entries_are_observable_and_use_entry_time(self):
        adapter = LevelSweepAdapter()
        entries = adapter.entries()
        sample = entries[::max(1, len(entries) // 120)][:120]
        audit_rows, checks = [], []
        for trade in sample:
            rows = adapter.candles(trade["symbol"])
            opens = [row[0] for row in rows]
            hours = core.hourly_series(rows)
            audit = core.audit_trade(
                rows, opens, adapter.bar_ms, trade,
                core.atr_before(hours, [hour[0] for hour in hours], trade["open_ms"]),
                adapter.split_of(trade["open_ms"]), adapter.cost_pct,
            )
            audit_rows.append(audit)
            checks.append(integrity.check_trade(adapter, trade, rows, audit))
        report = integrity.summarize(adapter, checks, audit_rows)
        self.assertTrue(report["valid"], report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
