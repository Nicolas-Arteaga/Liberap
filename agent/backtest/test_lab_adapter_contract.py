"""Regresión de la plantilla: el refactor no puede alterar MA3 ni Band Touch."""
from __future__ import annotations

import csv
import os
import pickle
import unittest

from lab_adapters import Adapter, get_adapter
from lab_adapters.band_touch import BandTouchAdapter, CSV_PATH
from lab_adapters.level_sweep import LevelSweepAdapter, rolling_atr
from lab_adapters.ma3 import HOUR, MA3Adapter, STREAM_CACHE


class AdapterTemplateContractTests(unittest.TestCase):
    def test_registered_adapters_implement_the_contract(self):
        for name in ("ma3", "band_touch", "level_sweep"):
            adapter = get_adapter(name)
            self.assertIsInstance(adapter, Adapter)
            self.assertEqual(adapter.definition.name, adapter.name)
            self.assertTrue(adapter.entry_definition.condition)

    def test_ma3_entries_match_the_frozen_stream_exactly(self):
        adapter = MA3Adapter()
        with open(STREAM_CACHE, "rb") as handle:
            stream = pickle.load(handle)["stream"]
        expected = [
            {"open_ms": b + HOUR, "symbol": symbol, "entry": entry, "sl": sl, "tp": tp, "side": side}
            for b, symbol, entry, sl, tp, side, _ in stream
        ]
        self.assertEqual(adapter.entries(), expected)

    def test_band_entries_match_the_frozen_csv_exactly(self):
        expected = []
        with open(CSV_PATH, encoding="utf8") as handle:
            for row in csv.DictReader(handle):
                try:
                    expected.append({
                        "open_ms": int(float(row["open_ms"])), "symbol": row["symbol"],
                        "entry": float(row["entry"]), "side": int(row["side"]),
                        "sl": float(row["sl"]), "tp": float(row["tp"]),
                    })
                except (ValueError, KeyError):
                    continue
        expected.sort(key=lambda item: item["open_ms"])
        actual = BandTouchAdapter().entries()
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 82)

    def test_level_sweep_uses_the_same_simple_rolling_atr(self):
        rows = [
            (index * 900_000, 0.0, float(index + 2), float(index), float(index + 1))
            for index in range(20)
        ]
        values = rolling_atr(rows, period=14)
        self.assertIsNone(values[13])
        self.assertAlmostEqual(values[14], 2.0)
        self.assertIsInstance(LevelSweepAdapter(), Adapter)


if __name__ == "__main__":
    unittest.main(verbosity=2)
