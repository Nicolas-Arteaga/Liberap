"""Regresión: los derivados cacheados deben igualar las fórmulas vigentes."""
from __future__ import annotations

import unittest
import tempfile
import os

from audit_context import AuditContext, _adx14_schedule, _rv20_mid_schedule
import lab_audit
from research_loop import _adx14, _realized_vol_mid


def hours(n=90):
    rows = []
    price = 100.0
    for index in range(n):
        # Trayectoria determinista, no monótona, con volatilidad suficiente.
        price *= 1.0 + ((index % 7) - 3) * 0.002
        rows.append((index * 3_600_000, price * 1.01, price * 0.99, price))
    return rows


class CachedIndicatorRegressionTests(unittest.TestCase):
    def test_adx_schedule_equals_direct_formula(self):
        rows, schedule = hours(), _adx14_schedule(hours())
        for end in range(28, len(rows) + 1):
            self.assertAlmostEqual(schedule[end], _adx14(rows[:end]), places=12)

    def test_realized_vol_schedule_equals_direct_formula(self):
        rows, schedule = hours(), _rv20_mid_schedule(hours())
        for end in range(41, len(rows) + 1):
            self.assertEqual(schedule[end], _realized_vol_mid(rows[:end]))

    def test_context_audit_matches_uncached_and_reuses_trade_paths(self):
        class Adapter:
            bar_ms, cost_pct, population = 3_600_000, 0.08, "raw"
            fidelity_result = {}
            fidelity_note = "test"
            definition = type("Definition", (), {"display_name": "test"})()
            candle_source = type("Source", (), {"key": "test", "db_path": "synthetic", "table": "t", "interval": "1h", "start_ms": 0, "end_ms": None})()
            def __init__(self):
                self._rows = hours(100)
                self._entries = [
                    {"symbol": "T", "open_ms": 40 * 3_600_000, "entry": self._rows[39][3], "side": 0,
                     "sl": self._rows[39][3] * .95, "tp": self._rows[39][3] * 1.1},
                    {"symbol": "T", "open_ms": 45 * 3_600_000, "entry": self._rows[44][3], "side": 1,
                     "sl": self._rows[44][3] * 1.05, "tp": self._rows[44][3] * .9},
                ]
            def entries(self): return list(self._entries)
            def candles(self, _symbol): return self._rows
            def split_of(self, _open_ms): return "TRAIN"
        plain, cached = Adapter(), Adapter()
        expected, _, _ = lab_audit.audit_adapter(plain, execution_variant="giveback_25")
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        try:
            context = AuditContext(cached, max_symbols=1, feature_cache_path=tmp.name)
            actual, _, _ = lab_audit.audit_adapter(cached, execution_variant="giveback_25", audit_context=context)
            for key in ("net_expectancy_pct", "gross_edge_pct", "severity", "reasons", "split_metrics"):
                self.assertEqual(actual[key], expected[key])
            self.assertGreater(context.stats["trade_misses"], 0)
            lab_audit.audit_adapter(cached, execution_variant="giveback_10", audit_context=context)
            self.assertGreater(context.stats["trade_hits"], 0)
        finally:
            os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()
