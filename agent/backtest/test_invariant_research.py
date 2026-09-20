"""E2E contract for VIRE, runnable inside the backtest image without pytest."""
import os
import sqlite3
import tempfile
import unittest

import numpy as np

from backtest import invariant_research as vire
from backtest import liquidation_research


class InvariantResearchE2E(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.conn = sqlite3.connect(self.tmp.name)
        self.conn.execute("CREATE TABLE klines_5m (symbol TEXT, interval TEXT, open_time INTEGER, close REAL)")
        rng = np.random.default_rng(7)
        base = np.cumsum(rng.normal(0, 0.002, 2200)) + np.log(100)
        # B tracks A with stationary residual. C is an independent random walk.
        stationary = np.zeros(2200)
        for i in range(1, len(stationary)):
            stationary[i] = .91 * stationary[i - 1] + rng.normal(0, .004)
        paired = 1.15 * base + .05 + stationary
        control = np.cumsum(rng.normal(0, 0.015, 2200)) + np.log(75)
        rows = []
        for i in range(2200):
            ts = 1735689600000 + i * 300000
            rows += [("AAAUSDT", "5m", ts, float(np.exp(base[i]))),
                     ("BBBUSDT", "5m", ts, float(np.exp(paired[i]))),
                     ("CCCUSDT", "5m", ts, float(np.exp(control[i])))]
        self.conn.executemany("INSERT INTO klines_5m VALUES (?,?,?,?)", rows)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tmp.name)

    def test_discovers_persists_and_stresses_without_production_dependencies(self):
        config = vire.ResearchConfig(
            start_date="2025-01-01", end_date="2025-01-10",
            symbols=("AAAUSDT", "BBBUSDT", "CCCUSDT"), max_pairs=3,
            min_bars=600, min_oos_trades=1, fee_bps_per_leg=1, slippage_bps_per_leg=1,
            perturbation_bps_per_leg=2,
        )
        result = vire.run_research(self.conn, config)
        self.assertEqual(result["mode"], "pair_relationship_price_only_v1")
        self.assertGreaterEqual(result["summary"]["relationships_eligible"], 1)
        self.assertEqual(result["summary"]["universe_symbols_represented"], 3)
        pairs = {(c["symbol_a"], c["symbol_b"]): c for c in result["candidates"]}
        self.assertIn(("AAAUSDT", "BBBUSDT"), pairs)
        candidate = pairs[("AAAUSDT", "BBBUSDT")]
        self.assertTrue(candidate["strategy"]["id"].startswith("vire:pair-mean-reversion:"))
        self.assertEqual(candidate["strategy"]["family"], "pair_mean_reversion")
        self.assertEqual(candidate["strategy"]["signal_sources"], ["price"])
        self.assertTrue(candidate["trade_diagnostics"]["oos"]["trades"])
        self.assertGreater(candidate["relationship"]["aligned_bars"], 600)
        self.assertGreaterEqual(candidate["stressed_oos"]["cost"], candidate["oos"]["cost"])
        self.assertFalse(result["promotion_policy"]["paper_ready_allowed"])
        self.assertEqual(result["summary"]["paper_ready"], 0)
        self.assertIsNotNone(vire.get_run(self.conn, result["run_id"]))
        self.assertEqual(vire.list_runs(self.conn)[0]["run_id"], result["run_id"])
        strategies = vire.list_strategies(self.conn)
        self.assertGreaterEqual(len(strategies), 1)
        self.assertEqual(strategies[0]["strategy_id"], candidate["strategy"]["id"])
        tables = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("StrategyProfiles", tables)

    def test_coverage_first_selector_represents_every_symbol_before_repeats(self):
        symbols = tuple(f"S{i}USDT" for i in range(6))
        eligible = [(symbols[i], symbols[j]) for i in range(6) for j in range(i + 1, 6)]
        pairs = vire._coverage_first_pairs(symbols, eligible, 6)
        self.assertEqual(len(pairs), 6)
        self.assertEqual({symbol for pair in pairs for symbol in pair}, set(symbols))

    def test_liquidation_coverage_reads_a_separate_read_only_research_db(self):
        live = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        live.close()
        other = sqlite3.connect(live.name)
        other.execute("CREATE TABLE liquidations_research (symbol TEXT, timestamp INTEGER)")
        other.execute("INSERT INTO liquidations_research VALUES ('AAAUSDT', 1735689600000)")
        other.commit(); other.close()
        coverage = vire.data_coverage(self.conn, live.name)
        self.assertTrue(coverage["liquidations"]["available"])
        self.assertEqual(coverage["liquidations"]["symbols"], 1)
        os.unlink(live.name)

    def test_liquidation_gate_requires_per_symbol_overlap_not_venue_wide_dates(self):
        live = tempfile.NamedTemporaryFile(suffix=".db", delete=False); live.close()
        canonical = tempfile.NamedTemporaryFile(suffix=".db", delete=False); canonical.close()
        try:
            events = sqlite3.connect(live.name)
            events.execute("CREATE TABLE liquidations_research (symbol TEXT, timestamp INTEGER)")
            # Each symbol has events spanning forty days, but their matching
            # candles cover only one day.  A venue-wide min/max would wrongly
            # join AAA's first candle to BBB's last candle and pass this gate.
            events.executemany("INSERT INTO liquidations_research VALUES (?, ?)", [
                ("AAAUSDT", 0), ("AAAUSDT", 40 * 86400000),
                ("BBBUSDT", 0), ("BBBUSDT", 40 * 86400000),
            ])
            events.commit(); events.close()
            prices = sqlite3.connect(canonical.name)
            prices.execute("CREATE TABLE klines_multi_exchange (exchange TEXT, symbol TEXT, interval TEXT, open_time INTEGER)")
            prices.executemany("INSERT INTO klines_multi_exchange VALUES ('bybit', ?, '5m', ?)", [
                ("AAAUSDT", 0), ("AAAUSDT", 86400000),
                ("BBBUSDT", 39 * 86400000), ("BBBUSDT", 40 * 86400000),
            ])
            prices.commit(); prices.close()
            liquidation_research._CACHE.clear()
            gate = liquidation_research.assess(self.conn, live.name, canonical.name, min_days=30, min_symbols=2)
            self.assertEqual(gate["price_symbols"], 2)
            self.assertEqual(gate["eligible_symbols"], 0)
            self.assertEqual(gate["status"], "REJECTED_INSUFFICIENT_HISTORICAL_OVERLAP")
        finally:
            os.unlink(live.name); os.unlink(canonical.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
