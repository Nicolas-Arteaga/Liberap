"""Regresión Band Touch: reproduce Fase 2c contra su resultado congelado."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "/app/backtest" if os.path.exists("/app/backtest") else HERE


class BandTouchFase2cSelftest(unittest.TestCase):
    def test_fase2c_reference_has_zero_differences(self):
        """La misma población y velas debe reproducir los 65 paths de Fase 2c."""
        frozen_path = os.path.join(ROOT, "lab_artifacts", "f2c-band-path.json")
        legacy = os.path.join(ROOT, "fase2c_band_path_metrics.py")
        trades = os.path.join(ROOT, "lab_inputs", "band_touch_real_trades.csv")
        db = "/app/live-research/klines.db" if os.path.exists("/app/live-research/klines.db") else os.path.join(HERE, "..", "data", "klines.db")
        with open(frozen_path, encoding="utf8") as h:
            frozen = json.load(h)
        with tempfile.TemporaryDirectory() as td:
            actual_path = os.path.join(td, "fase2c-rerun.json")
            completed = subprocess.run(
                [sys.executable, legacy, "--trades", trades, "--db", db, "--output", actual_path],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with open(actual_path, encoding="utf8") as h:
                actual = json.load(h)
        self.assertEqual(len(frozen["trades"]), 65)
        self.assertEqual(len(actual["trades"]), 65)
        fields = ("symbol", "life_h", "mfe_pct", "mae_pct", "final_return_pct", "giveback_pct", "time_to_mfe_h", "censored_last10pct", "exit_reason")
        mismatches = []
        for index, (old, new) in enumerate(zip(frozen["trades"], actual["trades"])):
            for field in fields:
                if isinstance(old[field], float):
                    if abs(old[field] - new[field]) > 1e-12:
                        mismatches.append((index, field, old[field], new[field]))
                elif old[field] != new[field]:
                    mismatches.append((index, field, old[field], new[field]))
        self.assertEqual(mismatches, [], f"Fase 2c divergió: {mismatches[:3]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
