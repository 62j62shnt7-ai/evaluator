import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from evaluator.app_services import ProjectService
from evaluator.storage.database import connection
from evaluator.workflow import Workflow

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = ProjectService(Path(self.temp.name))
        self.flow = Workflow(self.service)
        with connection(self.service.repository.path) as db:
            db.execute("INSERT INTO workbooks(source_id,file_name) VALUES ('source','TL-B.xlsx')")
            for sheet in ('old','new'):
                db.execute('INSERT INTO workbook_sheets(source_id,sheet_name) VALUES (?,?)', ('source',sheet))
            for oid,sheet,cell,value,day,loc in [
                ('a','old','E1','10','2020-01-01',['S1','J1','B1']),
                ('b','new','E2','9','2022-01-01',['S1','J1','B1']),
                ('c','old','E3','8','2020-01-01',['S2','J2','B1']),
                ('d','new','E4','7','2022-01-01',['S3','J3','B1'])]:
                db.execute('INSERT INTO readings VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (oid,'source',sheet,cell,value,'mm','current',day,json.dumps([day]),json.dumps(loc),'needs_review'))
    def tearDown(self): self.temp.cleanup()
    def compare(self):
        return self.flow.compare('source','old','current','source','new','current','asset-1','life-1',True,'reviewer','same equipment and lifecycle')
    def test_comparison_proposals_calculations_export_and_undo(self):
        comp=self.compare()
        self.assertEqual(sorted(r['kind'] for r in comp['rows']),['current_only','matched','previous_only'])
        proposal=self.flow.proposals(comp['id'])[0]
        rev=self.flow.revision()
        self.flow.apply_proposal(proposal['id'],rev,'reviewer','location mapping checked')
        result=self.flow.calculate(comp['id'],'6','0.5','365.2425','API 570 / owner input','reviewer','basis verified for draft',True)
        ready=next(x for x in result['rows'] if x['current_id']=='b')
        self.assertEqual(ready['remaining_life_years'],'6')
        self.assertIsNone(next(x for x in result['rows'] if x['kind']=='previous_only')['remaining_life_years'])
        export=self.flow.export_revision()
        with zipfile.ZipFile(export) as archive:
            self.assertIn('evaluation.xlsx',archive.namelist())
            manifest=json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['revision'],self.flow.revision())
        self.service.bulk_review(['b'],'excluded','exclude')
        self.assertTrue(self.flow.evaluations()[0]['stale'])
        self.flow.undo(self.flow.revision(),'reviewer','undo exclusion')
        self.assertEqual(next(r for r in self.service.readings() if r['observation_id']=='b')['review_status'],'needs_review')
        self.assertTrue(self.flow.evaluations()[0]['stale'])
    def test_rebuild_reuses_campaigns_but_requires_fresh_confirmation(self):
        comp=self.compare()
        proposal=self.flow.proposals(comp['id'])[0]
        self.flow.apply_proposal(proposal['id'],self.flow.revision(),'reviewer','checked')
        self.service.resolve_sheet_date('source','new','2023-01-01','reviewer','date corrected')
        rebuilt=self.flow.rebuild(comp['id'],self.flow.revision(),'reviewer','refresh changed readings')
        self.assertNotEqual(rebuilt['id'],comp['id'])
        self.assertEqual(rebuilt['baseline'],comp['baseline'])
        self.assertEqual(rebuilt['current_selection'],comp['current_selection'])
        self.assertEqual(rebuilt['rebuilt_from'],comp['id'])
        pair=next(r for r in rebuilt['rows'] if r['kind']=='matched')
        self.assertEqual(pair['current']['inspection_date'],'2023-01-01')
        self.assertFalse(pair['accepted'])
        self.assertTrue(self.flow.comparison(comp['id'])['stale'])
        with self.assertRaises(ValueError):
            self.flow.rebuild(rebuilt['id'],0,'reviewer','stale submit')

    def test_readiness_explains_missing_dates_confirmation_and_unmatched_locations(self):
        comp=self.compare()
        status=self.flow.readiness(comp['id'])
        self.assertEqual(status['ready'],0)
        self.assertEqual(status['unconfirmed'],1)
        self.assertEqual(status['unmatched'],2)
        self.assertIn('Confirm', ' '.join(status['steps']))
        proposal=self.flow.proposals(comp['id'])[0]
        self.flow.apply_proposal(proposal['id'],self.flow.revision(),'reviewer','checked')
        self.assertEqual(self.flow.readiness(comp['id'])['ready'],1)
        self.service.resolve_sheet_date('source','new','2019-01-01','reviewer','earlier current')
        comp=self.flow.rebuild(comp['id'],self.flow.revision(),'reviewer','refresh')
        status=self.flow.readiness(comp['id'])
        self.assertEqual(status['invalid_dates'],1)
        self.assertEqual(status['ready'],0)

    def test_repeated_rebuild_keeps_previous_profile_as_unconfirmed_quick_fill(self):
        from evaluator.workflow_ui import advanced_workflow_page as workflow_page
        comp=self.compare()
        proposal=self.flow.proposals(comp['id'])[0]
        self.flow.apply_proposal(proposal['id'],self.flow.revision(),'reviewer','checked')
        self.flow.calculate(comp['id'],'6.123','0.456','365','saved profile basis','reviewer','verified',True)
        for _ in range(2):
            comp=self.flow.rebuild(comp['id'],self.flow.revision(),'reviewer','refresh')
        proposal=self.flow.proposals(comp['id'])[0]
        self.flow.apply_proposal(proposal['id'],self.flow.revision(),'reviewer','checked again')
        page=workflow_page(self.service,comp['id'])
        self.assertIn('name="required_thickness" value=""',page)
        self.assertIn('name="adopted_rate" value=""',page)
        self.assertIn('name="year_days" value="365"',page)
        self.assertIn('saved profile basis',page)
        self.assertNotIn('name="scope" value="yes" checked',page)

    def test_guided_page_prefills_selection_and_explains_enablement(self):
        from evaluator.workflow_ui import advanced_workflow_page as workflow_page
        comp=self.compare()
        page=workflow_page(self.service,comp['id'])
        self.assertIn('Evaluate inspection readings',page)
        self.assertIn('Rebuild these pairs',page)
        self.assertIn('What is missing?',page)
        self.assertIn('Confirm matches to enable evaluation',page)
        self.assertIn('selected',page)
        self.assertIn('value="asset-1"',page)
        self.assertIn('name="comparison_id"',page)

    def test_comparison_report_does_not_require_invented_engineering_inputs(self):
        comp=self.compare(); proposal=self.flow.proposals(comp['id'])[0]
        self.flow.apply_proposal(proposal['id'],self.flow.revision(),'reviewer','test mapping')
        pair=next(r for r in comp['rows'] if r['kind']=='matched')
        result=self.flow.calculate(comp['id'],'','','365.2425','Historical comparison only; minima/rate not supplied','reviewer','test',True,[pair['id']])
        row=next(r for r in result['rows'] if r['pair_id']==pair['id'])
        self.assertIsNotNone(row['apparent_rate_mm_year'])
        self.assertIsNone(row['remaining_life_years'])
        self.assertIsNone(result['required_thickness_mm'])
        self.assertIn('REQUIRED_THICKNESS_MISSING',row['issues'])
        self.assertEqual(row['adopted_rate_mm_year'],row['apparent_rate_mm_year'])
        with zipfile.ZipFile(self.flow.export_revision()) as archive:
            records=list(csv.DictReader(io.StringIO(archive.read('evaluations.csv').decode('utf-8-sig'))))
            record=next(r for r in records if r['pair_id']==pair['id'])
            self.assertEqual(record['previous_thickness_mm'],'10')
            self.assertEqual(record['current_thickness_mm'],'9')
            self.assertEqual(record['current_cell'],'E2')
            self.assertEqual(record['previous_date'],'2020-01-01')
            self.assertIn('J1',record['location'])
            self.assertIn('coverage.csv',archive.namelist())
            self.assertIn('Current thickness',archive.read('summary.html').decode())

    def test_unrelated_comparison_does_not_stale_existing_report(self):
        comp=self.compare(); proposal=self.flow.proposals(comp['id'])[0]
        self.flow.apply_proposal(proposal['id'],self.flow.revision(),'reviewer','mapping')
        saved=self.flow.calculate(comp['id'],'','','365','history only','reviewer','test',True)
        other=self.compare();proposal=self.flow.proposals(other['id'])[0]
        self.flow.apply_proposal(proposal['id'],self.flow.revision(),'reviewer','other mapping')
        self.assertFalse(next(e for e in self.flow.evaluations() if e['id']==saved['id'])['stale'])
        self.service.resolve_sheet_date('source','new','2023-01-01','reviewer','changed source')
        self.assertTrue(next(e for e in self.flow.evaluations() if e['id']==saved['id'])['stale'])

    def test_saved_results_are_scoped_to_open_comparison(self):
        from evaluator.workflow_ui import advanced_workflow_page as workflow_page
        comp=self.compare();p=self.flow.proposals(comp['id'])[0]
        self.flow.apply_proposal(p['id'],self.flow.revision(),'reviewer','mapping')
        self.flow.calculate(comp['id'],'','','365','FIRST_COMPARISON_ONLY','reviewer','test',True)
        other=self.compare();p=self.flow.proposals(other['id'])[0]
        self.flow.apply_proposal(p['id'],self.flow.revision(),'reviewer','mapping')
        self.flow.calculate(other['id'],'','','365','OTHER_COMPARISON_ONLY','reviewer','test',True)
        page=workflow_page(self.service,comp['id'])
        self.assertIn('FIRST_COMPARISON_ONLY',page)
        self.assertNotIn('OTHER_COMPARISON_ONLY',page)

    def test_unchanged_proposal_previews_are_reused(self):
        comp=self.compare()
        first=self.flow.proposals(comp['id']);second=self.flow.proposals(comp['id'])
        self.assertEqual([p['id'] for p in first],[p['id'] for p in second])
        with connection(self.service.repository.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM wf_proposals').fetchone()[0],len(first))

    def test_stale_proposals_and_invalid_dates_are_blocked(self):
        comp=self.compare(); p=self.flow.proposals(comp['id'])[0]
        self.service.resolve_sheet_date('source','new','2019-01-01','reviewer','wrong date for test')
        with self.assertRaises(ValueError): self.flow.apply_proposal(p['id'],p['expected_revision'],'reviewer','test')
        self.assertTrue(self.flow.comparisons()[0]['stale'])
    def test_duplicate_and_cross_section_locations_do_not_automatch(self):
        with connection(self.service.repository.path) as db:
            db.execute("INSERT INTO readings SELECT 'dup',source_id,sheet_name,'F1',raw_value,raw_unit,campaign,inspection_date,date_candidates,location_candidates,review_status FROM readings WHERE observation_id='a'")
        comp=self.compare()
        self.assertTrue(any(r['kind']=='ambiguous' for r in comp['rows']))
    def test_date_override_survives_reimport_and_undo_rejects_stale_revision(self):
        self.service.resolve_sheet_date('source','new','2023-01-01','reviewer','date evidence')
        with self.assertRaises(ValueError): self.flow.undo(0,'reviewer','test')
        self.flow.undo(self.flow.revision(),'reviewer','restore')
        self.assertEqual(next(r for r in self.service.readings() if r['observation_id']=='b')['inspection_date'],'2022-01-01')


class WorkflowHTTPTests(unittest.TestCase):
    setUp=WorkflowTests.setUp
    tearDown=WorkflowTests.tearDown

    def test_workspace_dates_and_undo_are_revision_checked(self):
        from http.client import HTTPConnection
        from http.server import ThreadingHTTPServer
        from threading import Thread
        from evaluator.webapp import make_handler

        cid = WorkflowTests.compare(self)['id']
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.service))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = HTTPConnection('127.0.0.1', server.server_port, timeout=10)

        def post(action, revision, **fields):
            payload = json.dumps(dict(comparison_id=cid, revision=revision, **fields))
            client.request('POST', '/api/workspace/' + action, payload,
                           {'Content-Type': 'application/json'})
            response = client.getresponse()
            return response.status, json.loads(response.read())

        def current_date():
            comparison = self.flow.comparison(cid)
            return next(row['current']['inspection_date'] for row in comparison['rows']
                        if row['current_id'] == 'b')

        try:
            client.request('GET', '/api/workspace?comparison=' + cid)
            response = client.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())['workspace']['comparison']['id'], cid)

            original_date = current_date()
            revision = self.flow.revision()
            status, result = post('dates', revision, campaign_dates={'current': '2024-01-01'})
            self.assertEqual(status, 200, result)
            self.assertEqual(result['comparison_id'], cid)
            self.assertEqual(current_date(), '2024-01-01')
            self.assertEqual(post('undo', revision)[0], 400)
            self.assertEqual(current_date(), '2024-01-01')
            self.assertEqual(post('undo', self.flow.revision())[0], 200)
            self.assertEqual(current_date(), original_date)
        finally:
            client.close()
            server.shutdown()
            server.server_close()
            thread.join()

    def test_atomic_rollback_and_export_failure_leave_last_commit_intact(self):
        from unittest.mock import patch
        comp=WorkflowTests.compare(self)
        proposal=self.flow.proposals(comp['id'])[0]
        rev=self.flow.revision()
        with self.assertRaises(ValueError):
            with self.flow.change('Simulated interrupted update') as db:
                db.execute("UPDATE readings SET raw_value='999' WHERE observation_id='b'")
                raise ValueError('interrupted')
        self.assertEqual(self.flow.revision(),rev)
        self.assertEqual(next(r for r in self.service.readings() if r['observation_id']=='b')['raw_value'],'9')
        good=self.flow.export_revision(); original=good.read_bytes()
        with patch('evaluator.workflow.os.replace',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.flow.export_revision()
        self.assertEqual(good.read_bytes(),original)
        self.assertEqual(list((self.service.project_dir/'exports').glob('*.tmp')),[])

    def test_negative_rate_missing_current_and_lifecycle_block_outputs(self):
        with connection(self.service.repository.path) as db:
            db.execute("UPDATE readings SET raw_value='11' WHERE observation_id='b'")
        comp=WorkflowTests.compare(self);p=self.flow.proposals(comp['id'])[0]
        self.flow.apply_proposal(p['id'],self.flow.revision(),'reviewer','mapping only')
        result=self.flow.calculate(comp['id'],'6','.5','365.2425','required thickness record','reviewer','rate basis',True)
        current=next(x for x in result['rows'] if x['current_id']=='b')
        self.assertLess(float(current['apparent_rate_mm_year']),0)
        self.assertEqual(float(current['remaining_life_years']),10)
        prior=next(x for x in result['rows'] if x['kind']=='previous_only')
        self.assertIn('CURRENT_MISSING',prior['issues'])
        other=self.flow.compare('source','old','current','source','new','current','asset','replaced',False,'reviewer','replacement present')
        self.assertTrue(any(x['kind']=='lifecycle_mismatch' for x in other['rows']))

    def test_manual_pairing_and_design_integration(self):
        comp=WorkflowTests.compare(self)
        self.flow.pair(comp['id'],'c','d',True,'reviewer','drawing confirms renamed point',self.flow.revision())
        pair=next(x for x in self.flow.comparison(comp['id'])['rows'] if x['previous_id']=='c')
        self.assertTrue(pair['accepted'])
        design=self.flow.design(comp['id'],'B31_3_304_1_2',dict(P_MPa='4',D_outside_mm='219.1',S_B313_MPa='138',E_quality='1',W_reduction='1',Y_coefficient='.4'),'reviewer','B31.3 synthetic design input',True)
        result=self.flow.calculate(comp['id'],'','0.5','365.2425','structural input','reviewer','same component scope',True,[pair['id']],design['id'],'4')
        self.assertEqual(result['required_thickness_mm'],'4')
        self.assertEqual(next(r['remaining_life_years'] for r in result['rows'] if r['pair_id']==pair['id']),'6')

    def test_conflicting_report_dates_withhold_integrated_outputs(self):
        from openpyxl import Workbook
        from datetime import datetime
        path=Path(self.temp.name)/'TL-B conflicting report dates.xlsx'
        wb=Workbook(); wb.remove(wb.active)
        for title,year,value in [('UT 1-2020',2020,10),('UT 1-2022',2022,9)]:
            sheet=wb.create_sheet(title)
            sheet['F1']=datetime(year,1,1)
            if year==2022: sheet['G1']=datetime(2021,1,1)
            sheet['A2']='SECTION 1'
            for col,text in enumerate(['Joint','Band','Nom D','SCH','min\n01-'+str(year)],1): sheet.cell(3,col,text)
            for col,v in enumerate([1,1,'8 inch',80,value],1): sheet.cell(4,col,v)
        wb.save(path); wb.close()
        record=self.service.add_source(path,path.name);self.service.inspect(record.sha256)
        self.service.extract(record.sha256,'UT 1-2020');self.service.extract(record.sha256,'UT 1-2022')
        current=next(r for r in self.service.readings() if r['source_id']==record.sha256 and r['sheet_name']=='UT 1-2022')
        self.assertEqual(current['inspection_date'],'2022-01')
        self.assertEqual(json.loads(current['date_candidates']),['2022-01'])
        comp=self.flow.compare(record.sha256,'UT 1-2020','01-2020',record.sha256,'UT 1-2022','01-2022','asset','same-life',True,'reviewer','fixture scope')
        p=self.flow.proposals(comp['id'])[0];self.flow.apply_proposal(p['id'],p['expected_revision'],'reviewer','locations only')
        result=self.flow.calculate(comp['id'],'6','.5','365.2425','fixture','reviewer','fixture',True)
        self.assertEqual(float(result['rows'][0]['remaining_life_years']),6)
        self.assertNotIn('DATE_UNRESOLVED',result['rows'][0]['issues'])

    def test_legacy_sheet_date_migrates_once_and_does_not_resurrect_after_undo(self):
        with connection(self.service.repository.path) as db:
            db.execute("DELETE FROM wf_migrations WHERE name='legacy_sheet_dates'")
            db.execute('INSERT INTO audit_log(source_id,event,details) VALUES(?,?,?)',('source','sheet_date_resolved',json.dumps({'sheet':'new','chosen_date':'2023-05-01','reviewer':'legacy','justification':'report date'})))
        reopened=ProjectService(self.service.project_dir)
        with connection(reopened.repository.path) as db:
            self.assertEqual(db.execute("SELECT chosen_date FROM sheet_dates WHERE source_id='source' AND sheet_name='new'").fetchone()[0],'2023-05-01')
            db.execute("DELETE FROM sheet_dates")
        ProjectService(self.service.project_dir)
        with connection(reopened.repository.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sheet_dates').fetchone()[0],0)

    def test_three_hundred_readings_review_and_undo(self):
        with connection(self.service.repository.path) as db:
            for i in range(300):
                db.execute("INSERT INTO readings SELECT ?,source_id,sheet_name,?,raw_value,raw_unit,campaign,inspection_date,date_candidates,location_candidates,review_status FROM readings WHERE observation_id='b'",(f'batch-{i}',f'F{i+1}'))
        ids=[f'batch-{i}' for i in range(300)]
        self.assertEqual(self.service.bulk_review(ids,'reviewed','compatible batch scope'),300)
        self.flow.undo(self.flow.revision(),'reviewer','restore batch')
        self.assertTrue(all(r['review_status']=='needs_review' for r in self.service.readings() if r['observation_id'] in ids))

if __name__=='__main__': unittest.main()
