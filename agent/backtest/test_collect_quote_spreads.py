from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from collect_quote_spreads import collect_once, refresh_hourly_stats


class QuoteSpreadCollectorTests(unittest.TestCase):
    def test_filters_universe_is_idempotent_and_aggregates(self):
        with tempfile.TemporaryDirectory() as directory:
            db = os.path.join(directory, "quotes.db")
            payload = lambda: [
                {"symbol": "BTCUSDT", "bidPrice": "100", "askPrice": "101", "bidQty": "2", "askQty": "3"},
                {"symbol": "OUTUSDT", "bidPrice": "10", "askPrice": "11", "bidQty": "1", "askQty": "1"},
                {"symbol": "ETHUSDT", "bidPrice": "0", "askPrice": "1", "bidQty": "1", "askQty": "1"},
            ]
            first = collect_once(db, {"BTCUSDT", "ETHUSDT"}, fetch=payload, observed_ms=3_600_000)
            second = collect_once(db, {"BTCUSDT", "ETHUSDT"}, fetch=payload, observed_ms=3_600_000)
            self.assertEqual((first["eligible"], first["inserted"], first["rejected"]), (1, 1, 1))
            self.assertEqual(second["inserted"], 0)
            self.assertEqual(refresh_hourly_stats(db)["hourly_groups"], 1)
            conn = sqlite3.connect(db)
            try:
                row = conn.execute("SELECT sample_count,median_spread_bps,p90_spread_bps FROM spread_stats").fetchone()
            finally:
                conn.close()
            self.assertEqual(row[0], 1)
            self.assertAlmostEqual(row[1], 99.5024875622, places=8)
            self.assertAlmostEqual(row[2], row[1], places=8)


if __name__ == "__main__":
    unittest.main()
