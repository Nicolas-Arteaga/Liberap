from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from quote_spread_coverage import coverage_report


class QuoteSpreadCoverageTests(unittest.TestCase):
    def test_counts_distinct_utc_days_without_filling_gaps(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "quotes.db")
            conn = sqlite3.connect(path)
            try:
                conn.execute("CREATE TABLE quote_spreads(venue,symbol,observed_ms,bid,ask,bid_qty,ask_qty,source)")
                # Day 0 and day 2: two observed days, deliberately no fabricated day 1.
                conn.executemany("INSERT INTO quote_spreads VALUES (?,?,?,?,?,?,?,?)", [
                    ("binance_usdm", "BTCUSDT", 1, 1, 2, 1, 1, "test"),
                    ("binance_usdm", "BTCUSDT", 2 * 86400000 + 1, 1, 2, 1, 1, "test"),
                ])
                conn.commit()
            finally:
                conn.close()
            report = coverage_report(path, {"BTCUSDT", "ETHUSDT"}, min_days=2)
            self.assertFalse(report["ready"])
            self.assertEqual(report["symbols_meeting_required_days"], 1)
            self.assertEqual(report["symbols"]["BTCUSDT"]["distinct_utc_days"], 2)
            self.assertNotIn("ETHUSDT", report["symbols"])


if __name__ == "__main__":
    unittest.main()
