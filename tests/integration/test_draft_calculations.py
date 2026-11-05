import csv, io, json, sys, unittest, zipfile
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'src'))
from evaluator.engineering.draft import evaluate

class DraftCalculationTests(unittest.TestCase):
    def test_supplied_synthetic_numeric_vectors(self):
        with zipfile.ZipFile(ROOT/'engineering-calculations/evaluator_calculations_verified.zip') as archive:
            vectors=list(csv.DictReader(io.StringIO(archive.read('tests/synthetic_calculation_vectors.csv').decode())))
        checked=0
        for row in vectors:
            try: expected=Decimal(row['expected_result'])
            except Exception: continue
            inputs=dict(part.split('=',1) for part in row['inputs'].split(';'))
            result=evaluate(row['case_id'],inputs)
            self.assertLess(abs(Decimal(result['value'])-expected),Decimal('.00001'),row['case_id'])
            self.assertEqual(result['status'],'DRAFT / NOT VALIDATED')
            checked+=1
        self.assertEqual(checked,8)
    def test_missing_zero_and_invalid_domains(self):
        self.assertIsNone(evaluate('REMAINING_LIFE',{'t_current_mm':8,'t_required_mm':6,'approved_governing_CR_mm_per_year':0})['value'])
        self.assertIsNone(evaluate('CR_ST',{})['value'])
        with self.assertRaises(ValueError): evaluate('CR_ST',{'t_previous_mm':8,'t_current_mm':7,'elapsed_years':0})
        with self.assertRaises(ValueError): evaluate('B31_4_403_2_1',dict(P_MPa=6,D_outside_mm=323.9,F_design=.9,E_weld=1,SMYS_MPa=359))
        with self.assertRaises(ValueError): evaluate('VIII_UG27_HOOP',dict(P_MPa='NaN',R_inside_mm=1,S_allow_MPa=1,E_joint=1))

if __name__=='__main__': unittest.main()
