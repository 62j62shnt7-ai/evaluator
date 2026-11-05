import sys, unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime
from openpyxl import Workbook
from tests.source_config import SOURCE_ROOT
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'src'))
from evaluator.importing.tlb import extract as extract_tlb
from evaluator.importing.separator import extract as extract_separator

class AdapterTests(unittest.TestCase):
    def test_tlb_2022_extracts_readings_with_cell_provenance(self):
        path=SOURCE_ROOT/'workbooks/TL-B from SAG Gas MFD to GP.xlsx'
        result=extract_tlb(path,'10-2022')
        obs=[o for o in result.observations if o.source.cell=='E29']
        self.assertEqual(len(obs),1)
        self.assertEqual(obs[0].raw_value,'12')
        self.assertEqual(obs[0].campaign_label,'1-2021')
        self.assertEqual(obs[0].location_candidates,('SECTION 1','1','S'))

    def test_tlb_duplicate_historical_headers_remain_separate_and_flagged(self):
        result=extract_tlb(SOURCE_ROOT/'workbooks/TL-B from SAG Gas MFD to GP.xlsx','UT 5-2025')
        cells={o.source.cell for o in result.observations}
        self.assertIn('G151',cells); self.assertNotIn('H151',cells)
        self.assertTrue(any('Repeated campaign headers' in note for note in result.unresolved))
        self.assertTrue(any(o.source.cell=='K151' and o.inspection_date=='2025-05' for o in result.observations))

    def test_tlb_april_2026_text_joint_labels_are_imported_and_date_conflict_kept(self):
        result=extract_tlb(SOURCE_ROOT/'workbooks/TL-B from SAG Gas MFD to GP.xlsx','UT 4- 2026')
        first=next(o for o in result.observations if o.source.cell=='F151')
        self.assertEqual(first.raw_value,'12')
        self.assertEqual(first.location_candidates,('SECTION 1','Point F','1'))
        self.assertTrue(result.date_conflict)
        self.assertEqual(first.date_candidates,('2026-04',))

    def test_tlb_evaluation_history_dates_map_to_minimum_reading_columns(self):
        result=extract_tlb(SOURCE_ROOT/'workbooks/TL-B from SAG Gas MFD to GP.xlsx','Evalation 4-2026')
        readings={o.source.cell:o for o in result.observations}
        self.assertEqual(readings['K15'].inspection_date,'2021-01-22')
        self.assertEqual(readings['L15'].inspection_date,'2022-10-21')
        self.assertEqual(readings['N15'].inspection_date,'2025-06-08')
        self.assertNotIn('O15',readings)  # Forecast formula, not a measured UT reading.
        self.assertEqual(readings['N15'].campaign_label,'2025-06-08')
        self.assertEqual(readings['N15'].location_candidates,('SECTION 1 [From SAG MFD Side]','8','1'))
        self.assertTrue(all(o.inspection_date==o.campaign_label for o in result.observations))

    def test_tlb_top_row_dates_are_column_scoped_and_max_columns_are_ignored(self):
        with TemporaryDirectory() as td:
            path=Path(td)/'TL-B multi-date.xlsx'
            wb=Workbook(); ws=wb.active; ws.title='UT multi-date'
            ws['F1']=datetime(2021,1,1); ws['G1']=datetime(2023,1,1); ws['H1']=datetime(2025,1,1)
            ws['A2']='SECTION 1'
            for c,value in enumerate(['Joint','Band','Nom D','SCH','Comments','Min UT Reading','Min UT Reading','Max UT Reading'],1):
                ws.cell(3,c,value)
            for c,value in enumerate([1,'S','8 inch',80,None,10,9,12],1): ws.cell(4,c,value)
            wb.save(path); wb.close()
            result=extract_tlb(path,'UT multi-date')
            self.assertEqual([(o.source.cell,o.inspection_date) for o in result.observations],[('F4','2021-01-01'),('G4','2023-01-01')])
            self.assertEqual([o.raw_value for o in result.observations],['10','9'])

    def test_separator_conflicting_dates_are_retained_as_unresolved(self):
        path=SOURCE_ROOT/'workbooks/Separator-204 Inspection Report.xlsx'
        result=extract_separator(path,'UT 10-2026')
        self.assertTrue(result.date_conflict)
        obs=next(o for o in result.observations if o.source.cell=='E12')
        self.assertEqual(obs.date_candidates,('2026-01-20','2026-10-20'))
        self.assertIsNone(obs.inspection_date)

    def test_separator_merged_components_and_nozzle_tables_keep_separate_scope(self):
        result=extract_separator(SOURCE_ROOT/'workbooks/Separator-204 Inspection Report.xlsx','UT 10-2026')
        readings={o.source.cell:o for o in result.observations}
        self.assertEqual(readings['E14'].location_candidates[:3],('CMLS','PLATE 1','2'))
        self.assertEqual(readings['E34'].location_candidates[:3],('NOZZLES','M.H','S'))
        self.assertEqual(len(readings),len(result.observations))

    def test_separator_dated_min_columns_are_distinct_campaigns(self):
        result=extract_separator(SOURCE_ROOT/'workbooks/Separator-204 Inspection Report.xlsx','UT Jan 2026')
        rows={o.source.cell:o for o in result.observations}
        self.assertIn('H91',rows)
        self.assertEqual(rows['H91'].raw_value,'15.5')
        self.assertEqual(rows['H91'].campaign_label,'current')
        self.assertEqual(rows['H91'].inspection_date,'2026-01-20')
        self.assertEqual(rows['E91'].campaign_label,'2024-08-25')
        self.assertEqual(rows['E91'].inspection_date,'2024-08-25')
        self.assertEqual(rows['H91'].location_candidates[:3],('CMLS','PLATE #1 CML','#8'))
        self.assertTrue(any(o.location_candidates[0]=='NOZZLES' for o in result.observations))
        self.assertFalse(any(o.source.cell.startswith('K') for o in result.observations))

    def test_separator_calculation_sheet_is_not_a_measurement_table(self):
        result=extract_separator(SOURCE_ROOT/'workbooks/Separator-204 Inspection Report.xlsx','Evaluation 2026')
        self.assertEqual(result.observations,())

    def test_tlb_nominal_and_schedule_columns_are_not_raw_ut(self):
        result=extract_tlb(SOURCE_ROOT/'workbooks/TL-B from SAG Gas MFD to GP.xlsx','2019')
        self.assertTrue(result.observations)
        self.assertFalse(any(o.source.cell.startswith(('E','F')) for o in result.observations))

if __name__=='__main__': unittest.main()
