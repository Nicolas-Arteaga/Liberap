from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from cost_v2 import CostCoverageError, cost_bps


class CostV2Tests(unittest.TestCase):
    def test_requires_coverage_and_adds_p90_spread_to_fee(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'quotes.db')
            conn = sqlite3.connect(path)
            try:
                conn.execute("CREATE TABLE spread_stats(venue,symbol,utc_hour,sample_count,median_spread_bps,p90_spread_bps,median_top_notional_usdt,refreshed_at_ms)")
                conn.execute("INSERT INTO spread_stats VALUES ('binance_usdm','BTCUSDT',10,20,1.0,2.5,1000,1)")
                conn.commit()
            finally:
                conn.close()
            quote = cost_bps(path, 'btcusdt', 10)
            self.assertEqual(quote.conservative_roundtrip_bps, 10.5)
            with self.assertRaises(CostCoverageError):
                cost_bps(path, 'BTCUSDT', 11)


if __name__ == '__main__':
    unittest.main()
