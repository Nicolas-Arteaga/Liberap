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
    def test_batch_simulation_equals_individual_variants(self):
        rows = [(index * H, 101 + index % 4, 97 - index % 3, 99 + index % 3)
                for index in range(1, 80)]
        item = trade(side=1, sl=105, tp=90)
        variants = ("baseline", "giveback_10", "giveback_25", "giveback_50",
                    "break_even_1r", "trailing_2r", "time_exit_12h",
                    "time_exit_24h", "time_exit_36h", "time_stop_24h_if_losing",
                    "sl_atr_1.0", "sl_atr_1.5", "sl_atr_2.0")
        got = core.simulate_variants_batch(rows, [row[0] for row in rows], H, item,
                                           variants, "unconditional", -2.0, 3.0)
        for variant in variants:
            self.assertEqual(
                got[variant],
                core.simulate(rows, [row[0] for row in rows], H, item, variant,
                              "unconditional", -2.0, 3.0, with_close_ms=True),
                variant,
            )

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

    def test_compact_path_reproduces_baseline_and_lazy_variant(self):
        rows = [(index * H, 103 + index % 3, 97 - index % 2, 100 + (index % 5) - 2)
                for index in range(1, 100)]
        item = trade(open_ms=10 * H, tp=120)
        opens = [row[0] for row in rows]
        path = core.materialize_trade_path(rows, opens, H, item)
        self.assertEqual(
            core.audit_trade_from_path(path, H, item, None, "TRAIN", .08),
            core.audit_trade(rows, opens, H, item, None, "TRAIN", .08),
        )
        self.assertEqual(
            core.simulate_variants_from_path(path, H, item, ("giveback_25",), "unconditional", -2.0, None)["giveback_25"],
            core.simulate(rows, opens, H, item, "giveback_25", "unconditional", -2.0, None, with_close_ms=True),
        )


if __name__ == "__main__":
    unittest.main()
