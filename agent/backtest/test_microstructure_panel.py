from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from microstructure_panel import FIVE_MIN_MS, PanelPaths, build_5m_panel


class MicrostructurePanelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.price = os.path.join(self.temp.name, "price.db")
        self.oi = os.path.join(self.temp.name, "oi.db")
        self.funding = os.path.join(self.temp.name, "funding.db")
        conn = sqlite3.connect(self.price)
        try:
            conn.executescript("""
                CREATE TABLE klines_clean(symbol, interval, open_time, open, high, low, close, volume);
                CREATE TABLE taker_flow(symbol, interval, open_time, volume, quote_volume, trade_count, taker_buy_volume, taker_buy_quote);
            """)
            conn.executemany("INSERT INTO klines_clean VALUES ('BTCUSDT','5m',?,?,?,?,?,?)", [
                (700_000, 10, 11, 9, 10, 1), (1_000_000, 10, 11, 9, 10, 1),
                (1_300_000, 10, 12, 10, 11, 1),
            ])
            conn.execute("INSERT INTO taker_flow VALUES ('BTCUSDT','5m',1000000,1,1,1,1,1)")
            conn.commit()
        finally:
            conn.close()
        conn = sqlite3.connect(self.oi)
        try:
            conn.execute("CREATE TABLE oi_metrics(symbol,open_time,sum_oi,sum_oi_value,toptrader_ls_acct,toptrader_ls_pos,global_ls_acct,taker_ls_vol)")
            conn.execute("INSERT INTO oi_metrics VALUES ('BTCUSDT',1000000,1,2,3,4,5,6)")
            conn.commit()
        finally:
            conn.close()
        conn = sqlite3.connect(self.funding)
        try:
            conn.execute("CREATE TABLE funding_events(venue,symbol,funding_time_ms,rate_type,funding_rate)")
            conn.execute("INSERT INTO funding_events VALUES ('binance_usdm','BTCUSDT',1000000,'settlement_rate',0.01)")
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_external_observations_are_lagged_one_completed_bucket(self):
        rows = build_5m_panel('BTCUSDT', 1_000_000, 1_300_000, PanelPaths(self.price, self.oi, self.funding))
        self.assertIsNone(rows[0]['oi'])
        self.assertIsNone(rows[0]['taker_flow'])
        self.assertEqual(rows[1]['oi']['observed_at'], 1_000_000)
        self.assertEqual(rows[1]['taker_flow']['observed_at'], 1_000_000)

    def test_funding_is_not_visible_before_settlement(self):
        rows = build_5m_panel('BTCUSDT', 700_000, 1_300_000, PanelPaths(self.price, self.oi, self.funding))
        self.assertIsNone(rows[0]['funding'])
        self.assertEqual(rows[1]['funding']['settled_at'], 1_000_000)


if __name__ == '__main__':
    unittest.main()
