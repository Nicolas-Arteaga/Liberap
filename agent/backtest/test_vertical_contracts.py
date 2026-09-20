"""Contract checks for VIRE vertical evidence, runnable without live services."""
import unittest

from backtest import cross_venue_research, forced_flow_research, funding_research, liquidation_event_research, oi_research


class VerticalEvidenceContracts(unittest.TestCase):
    def test_metrics_include_execution_quality_fields(self):
        rows = [{"pnl": 3.0}, {"pnl": -1.0}, {"pnl": 2.0}]
        for module in (funding_research, oi_research, forced_flow_research, cross_venue_research, liquidation_event_research):
            metrics = module._metrics(rows)
            self.assertEqual(metrics["trades"], 3)
            self.assertIn("profit_factor", metrics)
            self.assertIn("max_drawdown", metrics)
            self.assertIn("avg_trade", metrics)

    def test_diagnostics_keep_trade_level_evidence(self):
        trade = {"pnl": -1.25, "side": "long", "entry_time_ms": 1,
                 "exit_time_ms": 2, "symbol": "TESTUSDT", "reason": "time_exit"}
        for module in (funding_research, oi_research, forced_flow_research):
            evidence = module._diagnostics([trade])
            self.assertEqual(evidence["trades"][0]["symbol"], "TESTUSDT")
            self.assertTrue(evidence["attribution_scope"])
        venue_evidence = cross_venue_research._diagnostics([trade])
        self.assertEqual(venue_evidence["trades"][0]["reason"], "time_exit")
        self.assertIn("by_exit", venue_evidence)

    def test_liquidation_gate_returns_explicit_non_strategy_result(self):
        result = liquidation_event_research._blocked({"status": "REJECTED_INSUFFICIENT_HISTORICAL_OVERLAP"})
        self.assertEqual(result["status"], "REJECTED_COVERAGE_GATE")
        self.assertIsNone(result["strategy"]["entry"])
        self.assertIn("per_symbol_historical_overlap_required", result["rejection_reasons"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
