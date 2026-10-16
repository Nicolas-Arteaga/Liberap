"""Prueba de frontera: selección TV no recorre ni calcula OOS."""
from __future__ import annotations

import unittest

import lab_audit as A
from lab_adapters import AdapterDefinition, EntryDefinition


class SplitAdapter:
    name = 'split-smoke'; aliases = (); population = 'raw'; bar_ms = 3_600_000; cost_pct = .08
    definition = AdapterDefinition(name=name, display_name=name, aliases=(), population='raw', bar_ms=bar_ms)
    entry_definition = EntryDefinition(source='test', condition='test', execution_time='close')
    fidelity_result = {}; fidelity_note = ''
    def __init__(self): self.seen_splits = []
    def entries(self):
        return [
            {'open_ms': 3_600_000, 'symbol': 'TV', 'entry': 100., 'side': 0, 'sl': 95., 'tp': 110.},
            {'open_ms': 7_200_000, 'symbol': 'OOS', 'entry': 100., 'side': 0, 'sl': 95., 'tp': 110.},
        ]
    def split_of(self, open_ms):
        return 'OOS' if open_ms >= 7_200_000 else 'TRAIN'
    def candles(self, symbol):
        self.seen_splits.append(symbol)
        return [(i * 3_600_000, 101., 99., 100.) for i in range(1, 30)]


class OosIsolationSmoke(unittest.TestCase):
    def test_train_validation_does_not_visit_oos_entries(self):
        adapter = SplitAdapter()
        result, _report, _rows = A.audit_adapter(adapter, allowed_splits=('TRAIN', 'VALIDATION'))
        self.assertEqual(adapter.seen_splits, ['TV'])
        self.assertNotIn('OOS', result['split_metrics'])
        self.assertEqual(result['integrity']['checks']['sample_counts']['splits'], {'TRAIN': 1})


if __name__ == '__main__':
    unittest.main(verbosity=2)
