"""Casos manuales para las primitivas de auditoría del laboratorio."""
from __future__ import annotations

import unittest

import lab_core as core

H = 3_600_000


def trade(**changes):
    value = {"symbol": "T", "open_ms": 0, "entry": 100.0, "side": 0,
             "sl": 95.0, "tp": 110.0}
    value.update(changes)
    return value


class AuditPrimitiveTests(unittest.TestCase):
    def test_simulate_detail_long_tp_records_path(self):
        rows = [(H, 104, 99, 103), (2 * H, 111, 102, 110)]
        got = core.simulate_detail(rows, [r[0] for r in rows], H, trade(), "unconditional", None)
        self.assertEqual(got["reason"], "TP")
        self.assertEqual(got["px"], 110)
        # La vela abierta en 2h cierra en 3h con este fixture de barras de 1h.
        self.assertEqual(got["age_h"], 3)
        self.assertEqual(got["mfe"], 11)
        self.assertEqual(got["mae"], -1)

    def test_no_sl_counterfactual_reaches_tp(self):
        rows = [(H, 94, 93, 94), (2 * H, 111, 100, 110)]
        got = core.audit_trade(rows, [r[0] for r in rows], H, trade(), None, "OOS", 0.08)
        self.assertEqual(got["reason"], "SL")
        self.assertTrue(got["cf_sl_reaches_tp"])
        self.assertAlmostEqual(got["ret"], -5.08)

    def test_forward_returns_are_directional_and_missing_is_none(self):
        # La función sólo toma velas cerradas: 3h..4h es el retorno a 4h.
        rows = [(H, 101, 99, 101), (3 * H, 99, 95, 96)]
        long = core.forward_returns(rows, [r[0] for r in rows], H, trade(),)
        short = core.forward_returns(rows, [r[0] for r in rows], H, trade(side=1, sl=105, tp=90))
        self.assertIsNone(long[1])
        self.assertAlmostEqual(long[4], -4)
        self.assertAlmostEqual(short[4], 4)
        self.assertIsNone(long[12])

    def test_forward_return_accepts_real_fill_offset_but_rejects_gap(self):
        # Entrada 17 min dentro de una vela 15m: el cierre más próximo previo
        # al horizonte es válido; una vela ausente completa es un hueco.
        q = 900_000
        t = trade(open_ms=17 * 60_000)
        rows = [(3*q, 101, 99, 101), (4*q, 102, 100, 102)]
        self.assertIsNotNone(core.forward_returns(rows, [r[0] for r in rows], q, t)[1])
        gap = [(q, 101, 99, 101)]
        self.assertIsNone(core.forward_returns(gap, [r[0] for r in gap], q, t)[4])

    def test_timeout_at_48h(self):
        rows = [(48 * H, 102, 98, 101)]
        got = core.simulate_detail(rows, [r[0] for r in rows], H, trade(tp=120), "unconditional", None)
        self.assertEqual(got["reason"], "timeout_48")
        self.assertEqual(got["px"], 101)


if __name__ == "__main__":
    unittest.main()
