import unittest
import lab_integrity as integrity

class BadAdapter:
    def split_of(self, _): return 'TRAIN'

class IntegrityTests(unittest.TestCase):
    def test_desalineated_entry_invalidates(self):
        rows=[(0, 11, 9, 10), (300000, 12, 10, 11)]
        # Precio 11 pertenece a una vela futura; el instante de entrada es 0.
        trade={'open_ms':0,'entry':11.0}
        audit={'age_h':1,'split':'TRAIN','day':'2026-01-01','fwd':{1:0.0}}
        one=integrity.check_trade(BadAdapter(),trade,rows,audit)
        report=integrity.summarize(BadAdapter(),[one],[audit, audit])
        self.assertEqual(one['entry_price_observable'], False)
        self.assertFalse(report['valid'])

if __name__=='__main__': unittest.main()
