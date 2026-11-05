import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from evaluator.importing.normalize import convert, CoverageSummary, observation_id, measurement_summary
from evaluator.importing.normalize import ExtractionResult, RegionStatus, persist_extraction, coverage
from evaluator.storage.repository import Repository
import tempfile
from decimal import Decimal

class CoverageTests(unittest.TestCase):
    def test_unit_conversions_and_reconciliation(self):
        self.assertEqual(convert("1", "in", "mm"), convert("25.4", "mm", "mm"))
        self.assertAlmostEqual(float(convert("32", "F", "C")), 0.0)
        self.assertAlmostEqual(float(convert("1", "MPa", "psi")), 145.03773773020923)
        with self.assertRaises(ValueError): convert("1", "widgets", "mm")
        self.assertEqual(CoverageSummary(4, 2, 1, 1).detected, 4)
        with self.assertRaises(ValueError): CoverageSummary(4, 3, 0, 0)
        self.assertEqual(observation_id('abc','S','E10','2026'),observation_id('abc','S','E10','2026'))
        self.assertNotEqual(observation_id('abc','S','E10','2026'),observation_id('abc','S','F10','2026'))
        self.assertEqual(measurement_summary([('a',Decimal('2')),('b',Decimal('1'))]),(Decimal('1'),('b',)))

    def test_persisted_regions_reconcile_and_reimport_idempotently(self):
        with tempfile.TemporaryDirectory() as td:
            repo=Repository(Path(td)/'project.sqlite')
            result=ExtractionResult('src-1', (
                RegionStatus('r1','imported', observations=({'id':'o1','raw':'25.4','unit':'mm'},)),
                RegionStatus('r2','unresolved', reason='ambiguous date'),
                RegionStatus('r3','excluded', reason='derived evaluation'),
            ))
            self.assertEqual(persist_extraction(repo,result,0).revision,1)
            self.assertEqual(persist_extraction(repo,result,1).revision,1)
            self.assertEqual(coverage(repo,'src-1'),CoverageSummary(3,1,1,1))

if __name__ == "__main__": unittest.main()
