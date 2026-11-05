import json
import unittest
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from tests.integration import test_workflow as fixtures
from evaluator.app_services import ProjectService
from evaluator.storage.database import connection
from evaluator.batch_ui import batch_page
from tests.source_config import SOURCE_ROOT


def field(value,cell='A1',unit='mm',kind='literal'):
    return dict(cell=cell,raw=('=source' if kind=='formula' else value),cached=value,kind=kind,unit=unit,value=value)


def record(identifier,section,joint,point,current,required,rate):
    return dict(id=identifier,source_id='source',sheet='Design',row=int(identifier[-1]),family='pipeline',section=section,component=joint,point=point,
                key=[section,joint,point],geometry='straight_pipe',code_family='ASME B31.8',code_edition='2025',code_basis='synthetic test record',inspection_date='2022-01-01',
                fields=dict(current_mm=field(current),required_thickness_mm=field(required),adopted_rate_mm_year=field(rate,unit='mm/year'),material=field('synthetic',unit=None),
                            P_psi=field('100',unit='psi'),D_outside_in=field('8.625',unit='in'),SMYS_psi=field('52000',unit='psi')),
                interval_policy=dict(fraction=.5,cap_years=10),factor_candidates={})


class BatchTests(unittest.TestCase):
    def setUp(self):
        fixtures.WorkflowTests.setUp(self)
        self.comp=fixtures.WorkflowTests.compare(self)
        self.records=[record('p1','S1','J1','B1','9','6','.5'),record('p2','S3','J3','B1','7','4','.25')]
        with connection(self.service.repository.path) as db:
            for r in self.records:db.execute('INSERT INTO wf_profiles VALUES(?,?,?,?)',(r['id'],'source','Design',json.dumps(r)))
        self.service.batch.apply_overrides(self.comp['id'],self.flow.revision(),[],['b'],dict(adopted_rate_mm_year='.5'),'Design')
        self.service.batch.apply_overrides(self.comp['id'],self.flow.revision(),[],['d'],dict(adopted_rate_mm_year='.25'),'Design')
    tearDown=fixtures.WorkflowTests.tearDown

    def test_same_sheet_minimum_reading_history_drives_batch_corrosion_rate(self):
        with TemporaryDirectory() as td:
            path=SOURCE_ROOT/'workbooks/TL-B from SAG Gas MFD to GP.xlsx'
            service=ProjectService(Path(td)/'project')
            source=service.add_source(path,path.name);service.inspect(source.sha256)
            service.extract(source.sha256,'Evalation 4-2026')
            flow=service.workflow
            comparison=flow.compare(
                source.sha256,'Evalation 4-2026','2021-01-22',
                source.sha256,'Evalation 4-2026','2025-06-08',
                'TL-B','same component lifecycle',True,'reviewer','minimum readings from one worksheet',
            )
            proposal=flow.proposals(comparison['id'])[0]
            flow.apply_proposal(proposal['id'],proposal['expected_revision'],'reviewer','physical labels reviewed')
            service.batch.prepare(comparison['id'],flow.revision())
            options=dict(profile_sheet='Evalation 4-2026',confirm_records=True,confirm_history=True,confirm_conflicts=True,confirm_rules=True,basis='provided',year_days='365')
            preview=service.batch.preview(comparison['id'],'Evalation 4-2026',options)
            row=next(item for item in preview['rows'] if item['current_cell']=='N15')
            days=(date(2025,6,8)-date(2021,1,22)).days
            expected=(Decimal('7')-Decimal('6.8'))*Decimal(365)/Decimal(days)
            self.assertAlmostEqual(float(row['apparent_rate_mm_year']),float(expected),places=12)
            self.assertIsNotNone(row['remaining_life_years'])
            result=service.batch.evaluate(comparison['id'],flow.revision(),options,preview['preview_token'])
            saved=next(item for item in result['rows'] if item['current_cell']=='N15')
            self.assertAlmostEqual(float(saved['apparent_rate_mm_year']),float(expected),places=12)
            self.assertEqual(saved['current_thickness_mm'],'6.8')
            self.assertEqual(saved['profile']['code_edition'],'2020')
            self.assertIsNotNone(saved['mawp_MPa'])
            self.assertAlmostEqual(float(saved['mawp_MPa']),1500*.006894757293,places=10)
            self.assertEqual(saved['mawp_MPa'],saved['forecast_mawp_MPa'])
            self.assertEqual(saved['input_trace']['design_inputs']['E_weld'],'1')
            self.assertEqual(saved['input_trace']['design_inputs']['T_temp'],'1')
            page=batch_page(service,comparison['id'],profile_sheet='Evalation 4-2026')
            self.assertIn('10.34 / 10.34 MPa',page)
            self.assertEqual(saved['adopted_rate_mm_year'],saved['apparent_rate_mm_year'])
            self.assertAlmostEqual(float(saved['remaining_life_years']),(6.8-3.949669471153846)/float(expected),places=9)
            self.assertEqual(Decimal(saved['inspection_interval_years']),Decimal(10))
            service.batch.apply_overrides(comparison['id'],flow.revision(),[],[saved['current_id']],dict(E_weld='.9',T_temp='.95'),'Evalation 4-2026')
            adjusted=service.batch.evaluate(comparison['id'],flow.revision(),options)
            changed=next(item for item in adjusted['rows'] if item['current_cell']=='N15')
            self.assertAlmostEqual(float(changed['mawp_MPa']),1500*.006894757293*.9*.95,places=10)



    def test_batch_uses_distinct_profile_inputs_and_retains_all_current_and_history(self):
        result=self.service.batch.evaluate(self.comp['id'],self.flow.revision(),dict(profile_sheet='Design',confirm_records=True,confirm_history=True))
        by_current={r['current_id']:r for r in result['rows'] if r['current_id']}
        self.assertEqual(by_current['b']['required_thickness_mm'],'6')
        self.assertEqual(by_current['b']['remaining_life_years'],'6')
        self.assertEqual(by_current['d']['required_thickness_mm'],'4')
        self.assertEqual(by_current['d']['remaining_life_years'],'12')
        self.assertIsNotNone(by_current['b']['apparent_rate_mm_year'])
        self.assertIsNone(by_current['d']['apparent_rate_mm_year'])
        self.assertEqual(len(result['rows']),3)
        self.assertTrue(any(r['current_id'] is None for r in result['rows']))
        self.assertEqual(result['status'],'DRAFT / NOT VALIDATED')

    def test_pressure_only_record_supports_labeled_source_life_without_becoming_governing_minimum(self):
        r=self.records[0];r['fields']['pressure_thickness_mm']=r['fields'].pop('required_thickness_mm')
        with connection(self.service.repository.path) as db:db.execute('UPDATE wf_profiles SET payload=? WHERE id=?',(json.dumps(r),r['id']))
        settings=dict(profile_sheet='Design',confirm_records=True,confirm_history=True)
        result=self.service.batch.evaluate(self.comp['id'],self.flow.revision(),settings)
        row=next(r for r in result['rows'] if r['current_id']=='b')
        self.assertIsNone(row['required_thickness_mm'])
        self.assertEqual(row['remaining_life_years'],'6')
        self.assertIn('GOVERNING_MINIMUM_NOT_ESTABLISHED',row['issues'])
        self.assertIn('source pressure-thickness basis',row['required_basis'])
        preview=self.service.batch.preview(self.comp['id'],'Design')
        group=next(r['group_id'] for r in preview['rows'] if r['current_id']=='b')
        self.service.batch.apply_overrides(self.comp['id'],self.flow.revision(),[group],[],dict(structural_minimum_mm='7'))
        result=self.service.batch.evaluate(self.comp['id'],self.flow.revision(),settings)
        row=next(r for r in result['rows'] if r['current_id']=='b')
        self.assertEqual(row['required_thickness_mm'],'7');self.assertEqual(row['remaining_life_years'],'4')

    def test_one_invalid_or_missing_profile_does_not_abort_ready_rows(self):
        with connection(self.service.repository.path) as db:db.execute("DELETE FROM wf_profiles WHERE id='p2'")
        result=self.service.batch.evaluate(self.comp['id'],self.flow.revision(),dict(profile_sheet='Design',confirm_records=True))
        self.assertEqual(next(r for r in result['rows'] if r['current_id']=='b')['remaining_life_years'],'6')
        self.assertIn('PROFILE_MISSING',next(r for r in result['rows'] if r['current_id']=='d')['issues'])

    def test_conflicting_copied_current_needs_explicit_group_reconciliation(self):
        r=self.records[0];r['fields']['current_mm']=field('99')
        with connection(self.service.repository.path) as db:db.execute('UPDATE wf_profiles SET payload=? WHERE id=?',(json.dumps(r),r['id']))
        settings=dict(profile_sheet='Design',confirm_records=True)
        result=self.service.batch.evaluate(self.comp['id'],self.flow.revision(),settings)
        row=next(r for r in result['rows'] if r['current_id']=='b')
        self.assertIsNone(row['remaining_life_years']);self.assertIn('PROFILE_CURRENT_CONFLICT',row['issues'])
        settings['confirm_conflicts']=True
        result=self.service.batch.evaluate(self.comp['id'],self.flow.revision(),settings)
        row=next(r for r in result['rows'] if r['current_id']=='b')
        self.assertEqual(row['current_thickness_mm'],'9');self.assertEqual(row['remaining_life_years'],'6')
        self.assertEqual(row['profile']['fields']['current_mm']['value'],'99')

    def test_changes_and_undo_preserve_batch_revision_and_source_inputs(self):
        saved=self.service.batch.evaluate(self.comp['id'],self.flow.revision(),dict(profile_sheet='Design',confirm_records=True))
        self.service.resolve_sheet_date('source','new','2023-01-01','reviewer','changed')
        self.assertTrue(self.service.batch.results(self.comp['id'])[0]['stale'])
        self.flow.undo(self.flow.revision(),'reviewer','restore')
        self.assertTrue(self.service.batch.results(self.comp['id'])[0]['stale'])
        with self.assertRaises(ValueError):self.service.batch.evaluate(self.comp['id'],0,dict(profile_sheet='Design',confirm_records=True))
        self.assertEqual(self.service.batch.results(self.comp['id'])[0]['id'],saved['id'])

    def test_component_batch_review_page_and_revision_export_include_saved_rows(self):
        page=batch_page(self.service,self.comp['id'])
        self.assertIn('Component batch evaluation',page)
        self.assertIn('I reviewed the proposed source records',page)
        self.assertIn('Save group inputs',page)
        saved=self.service.batch.evaluate(self.comp['id'],self.flow.revision(),dict(profile_sheet='Design',confirm_records=True,confirm_history=True))
        target=self.flow.export_revision(self.comp['id'])
        try:
            with zipfile.ZipFile(target) as archive:
                self.assertIn('batch_evaluations.csv',archive.namelist())
                report=archive.read('summary.html').decode()
                rows=archive.read('batch_evaluations.csv').decode('utf-8-sig')
                self.assertIn('Component batch evaluation',report)
                self.assertIn(saved['id'],rows)
                self.assertIn('DRAFT / NOT VALIDATED',report)
        finally:
            Path(target).unlink(missing_ok=True)

    def test_manual_source_record_assignment_changes_only_selected_row(self):
        mismatched=self.records[1]
        mismatched['key']=['SECTION99','OTHER','P9']
        with connection(self.service.repository.path) as db:
            db.execute('UPDATE wf_profiles SET payload=? WHERE id=?',(json.dumps(mismatched),mismatched['id']))
        before=self.service.batch.preview(self.comp['id'],'Design')
        target=next(row for row in before['rows'] if row['current_id']=='d')
        untouched=next(row for row in before['rows'] if row['current_id']=='b')
        self.assertIsNone(target['profile_id'])
        self.assertEqual(untouched['profile_id'],'p1')
        page=batch_page(self.service,self.comp['id'])
        self.assertIn('Assign source record',page)
        self.service.batch.apply_overrides(
            self.comp['id'],self.flow.revision(),[],['d'],{'profile_id':'p2'},'Design'
        )
        after=self.service.batch.preview(self.comp['id'],'Design')
        target=next(row for row in after['rows'] if row['current_id']=='d')
        untouched=next(row for row in after['rows'] if row['current_id']=='b')
        self.assertEqual(target['profile_id'],'p2')
        self.assertEqual(target['assignment_basis'],'Manual component record assignment')
        self.assertEqual(untouched['profile_id'],'p1')
