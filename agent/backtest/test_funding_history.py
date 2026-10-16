"""Selftest sin red del cache, cobertura y contabilidad de funding."""
from __future__ import annotations

import os
import tempfile
import unittest

from funding_history import BINANCE_USDM, FundingStore, validate_income_history


class FundingHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.store = FundingStore(self.tmp.name)
        self.symbol = "BTCUSDT"
        self.store.begin(BINANCE_USDM, self.symbol, 0, 40_000)
        self.store.persist_page(BINANCE_USDM, self.symbol, [
            {"fundingTime": 10_000, "fundingRate": "0.001", "markPrice": "100"},
            {"fundingTime": 20_000, "fundingRate": "-0.002", "markPrice": "100"},
            {"fundingTime": 30_000, "fundingRate": "0.0005", "markPrice": "100"},
        ], 30_001)
        self.store.complete(BINANCE_USDM, self.symbol)

    def tearDown(self):
        os.unlink(self.tmp.name)

    def pos(self, side=0):
        return {"symbol": self.symbol, "side": side, "entry": 100.0, "notional_usdt": 100.0}

    def test_no_funding_window(self):
        result = self.store.accrued_funding(self.pos(), 11_000, 19_000)
        self.assertTrue(result.complete)
        self.assertEqual(result.event_count, 0)
        self.assertEqual(result.cashflow_usdt, 0.0)

    def test_exactly_one_long(self):
        result = self.store.accrued_funding(self.pos(), 11_000, 20_000)
        self.assertTrue(result.complete)
        self.assertEqual(result.event_count, 1)
        self.assertAlmostEqual(result.cashflow_usdt, 0.2)  # long cobra si rate=-0.002
        self.assertAlmostEqual(result.return_pct, 0.2)

    def test_multiple_short(self):
        result = self.store.accrued_funding(self.pos(1), 5_000, 30_000)
        self.assertTrue(result.complete)
        self.assertEqual(result.event_count, 3)
        self.assertAlmostEqual(result.cashflow_usdt, -0.05)  # short: +rate, -rate, +rate

    def test_gap_is_never_zero(self):
        gap = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        gap.close()
        try:
            store = FundingStore(gap.name)
            store.begin(BINANCE_USDM, self.symbol, 0, 100_000)
            store.persist_page(BINANCE_USDM, self.symbol, [
                {"fundingTime": 10_000, "fundingRate": "0.001", "markPrice": "100"},
                {"fundingTime": 20_000, "fundingRate": "0.001", "markPrice": "100"},
                {"fundingTime": 80_000, "fundingRate": "0.001", "markPrice": "100"},
            ], 80_001)
            store.complete(BINANCE_USDM, self.symbol)
            result = store.accrued_funding(self.pos(), 15_000, 70_000)
            self.assertFalse(result.complete)
            self.assertEqual(result.status, "FUNDING_COVERAGE_INCOMPLETE")
            self.assertIn("OBSERVED_EVENT_GAP", result.coverage_reasons)
            self.assertIsNone(result.cashflow_usdt)
        finally:
            os.unlink(gap.name)

    def test_income_history_validation_is_persistable(self):
        sample = [{**self.pos(), "open_ms": 11_000, "close_ms": 20_000, "income_usdt": 0.2}]
        result = validate_income_history(self.store, sample)
        self.assertTrue(result["validated"])
        self.store.record_sign_validation(BINANCE_USDM, result)
        self.assertTrue(self.store.sign_validated(BINANCE_USDM))


if __name__ == "__main__":
    unittest.main()
