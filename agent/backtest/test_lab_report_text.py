import unittest
import lab_m1_ma3_audit as report

class ReportTextTests(unittest.TestCase):
    def test_importance_texts_are_unique(self):
        self.assertEqual(len(report.WHY), len(set(report.WHY.values())))
    def test_positive_expectancy_never_says_loses(self):
        title=report.headline(.04,.12,.08,'SALIDA',{'SALIDA':35})
        self.assertIn('GANA', title)
        self.assertNotIn('PIERDE', title)
    def test_cost_deficit_is_severe_when_gross_edge_cannot_pay_cost(self):
        self.assertGreaterEqual(report.severity_scores(0,.04,.08,50,50,0,0,0,0)['COSTOS'],20)

if __name__=='__main__': unittest.main()
