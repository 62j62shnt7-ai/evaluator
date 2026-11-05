import json
import unittest
from tests.integration import test_workflow as fixtures
from evaluator.storage.database import connection
from tests.source_config import SOURCE_ROOT

class QuickWorkflowTests(unittest.TestCase):
    setUp=fixtures.WorkflowTests.setUp
    tearDown=fixtures.WorkflowTests.tearDown

    def test_single_sheet_http_selects_dates_before_matching_and_reports_selected_pair(self):
        import tempfile
        from pathlib import Path
        from http.client import HTTPConnection
        from http.server import ThreadingHTTPServer
        from threading import Thread
        from urllib.parse import urlencode
        from evaluator.app_services import ProjectService
        from evaluator.webapp import make_handler
        with tempfile.TemporaryDirectory() as td:
            service=ProjectService(Path(td)/'project')
            path=SOURCE_ROOT/'workbooks/TL-B from SAG Gas MFD to GP.xlsx'
            source=service.add_source(path,path.name);service.inspect(source.sha256)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service))
            thread=Thread(target=server.serve_forever,daemon=True);thread.start()
            client=HTTPConnection('127.0.0.1',server.server_port,timeout=20)
            def request(path,values=None):
                client.request('GET' if values is None else 'POST',path,None if values is None else urlencode(values),{} if values is None else {'Content-Type':'application/x-www-form-urlencoded'})
                r=client.getresponse();return r.status,r.read().decode(),r.getheader('Location')
            try:
                for sheet,dates in [('UT 5-2025',['01-2021','10-2022','02-2025','05-2025']),('Evalation 4-2026',['2021-01-22','2022-10-21','2025-06-08'])]:
                    status,_,location=request('/workflow/quick-import-single',dict(source_id=source.sha256,sheet_name=sheet,revision=service.workflow.revision()))
                    self.assertEqual(status,303)
                    self.assertEqual(service.workflow.comparisons(),[])
                    status,body,_=request(location)
                    self.assertEqual(status,200)
                    for date in dates:self.assertIn('value="'+date+'"',body)
                    self.assertNotIn('data-historical hidden',body)
                form=dict(source_id=source.sha256,sheet_name='Evalation 4-2026',previous_campaign='2021-01-22',current_campaign='2025-06-08',revision=service.workflow.revision())
                for previous,current in [('2021-01-22','2021-01-22'),('2025-06-08','2021-01-22'),('bogus','2025-06-08')]:
                    status,_,_=request('/workflow/quick-match-single',dict(form,previous_campaign=previous,current_campaign=current))
                    self.assertEqual(status,400)
                    self.assertEqual(service.workflow.comparisons(),[])
                status,_,location=request('/workflow/quick-match-single',form)
                self.assertEqual(status,303)
                comp=service.workflow.comparisons()[0]
                self.assertEqual(comp['baseline'][2],'2021-01-22')
                self.assertEqual(comp['current_selection'][2],'2025-06-08')
                self.assertNotIn('data-historical hidden',request(location)[1])
                status,_,_=request('/workflow/quick-report',dict(comparison_id=comp['id'],revision=service.workflow.revision(),confirm='yes'))
                self.assertEqual(status,303)
                row=next(r for r in service.workflow.evaluations()[0]['rows'] if r.get('current_id') and any(p['id']==r['pair_id'] and p['current'] and p['current']['cell']=='N15' for p in service.workflow.comparison(comp['id'])['rows']))
                self.assertAlmostEqual(float(row['apparent_rate_mm_year']),.2 * 365.2425 / 1598,places=9)
                # Change dates without reimporting; the report must use the newly selected pair.
                status,_,location=request('/workflow/quick-match-single',dict(form,previous_campaign='2022-10-21',revision=service.workflow.revision()))
                self.assertEqual(status,303)
                changed=service.workflow.comparisons()[0]
                self.assertEqual(changed['baseline'][2],'2022-10-21')
                self.assertEqual(request(location)[0],200)
                # UT headers provide month-only dates; resolving dates affects only the selected campaigns.
                status,_,location=request('/workflow/quick-match-single',dict(form,sheet_name='UT 5-2025',previous_campaign='01-2021',current_campaign='05-2025',revision=service.workflow.revision()))
                self.assertEqual(status,303)
                ut=service.workflow.comparisons()[0]
                status,_,location=request('/workflow/quick-report',dict(comparison_id=ut['id'],revision=service.workflow.revision(),confirm='yes',previous_date='2021-01-22',current_date='2025-06-08'))
                self.assertEqual(status,303)
                self.assertEqual(request(location)[0],200)
                report=service.workflow.evaluations()[0]
                self.assertTrue(any(r['apparent_rate_mm_year'] is not None for r in report['rows']))
                for campaign in ['10-2022','02-2025']:
                    self.assertTrue(all(r['inspection_date']=={'10-2022':'2022-10','02-2025':'2025-02'}[campaign] for r in service.workflow._selection(source.sha256,'UT 5-2025',campaign)))
            finally:client.close();server.shutdown();server.server_close();thread.join()

    def test_life_defaults_to_calculated_rate_and_export_uses_same_result(self):
        from evaluator.quick_workflow import match,generate
        import zipfile
        comp=match(self.service,['source','old','current'],['source','new','current'],self.flow.revision())
        result=generate(self.service,comp['id'],self.flow.revision(),confirm=True,include_life=True,required_thickness='6',profile_confirmed=True)
        row=next(r for r in result['evaluation']['rows'] if r['current_id']=='b')
        self.assertEqual(row['adopted_rate_mm_year'],row['apparent_rate_mm_year'])
        self.assertAlmostEqual(float(row['remaining_life_years']),3*731/365.2425)
        with zipfile.ZipFile(self.flow.export_revision(comp['id'])) as z:
            saved=json.loads(z.read('project_snapshot.json'))['evaluations'][0]['rows']
            self.assertEqual(next(r for r in saved if r['current_id']=='b')['remaining_life_years'],row['remaining_life_years'])

    def test_report_needs_no_typed_audit_fields_and_confirms_only_exact_matches(self):
        from evaluator.quick_workflow import match, generate
        comp=match(self.service,['source','old','current'],['source','new','current'],self.flow.revision())
        self.assertFalse(comp['continuity'])
        result=generate(self.service,comp['id'],self.flow.revision(),confirm=True)
        evaluation=result['evaluation']
        ready=next(r for r in evaluation['rows'] if r['current_id']=='b')
        self.assertIsNotNone(ready['apparent_rate_mm_year'])
        self.assertIsNone(ready['remaining_life_years'])
        self.assertIn('CURRENT_MISSING',next(r for r in evaluation['rows'] if r['previous_id']=='c')['issues'])
        self.assertTrue(all(not r['accepted'] for r in result['comparison']['rows'] if r['kind']!='matched'))
        self.assertTrue(evaluation['reviewer'])

    def test_dates_and_rebuild_are_one_atomic_action(self):
        from evaluator.quick_workflow import match, generate
        comp=match(self.service,['source','old','current'],['source','new','current'],self.flow.revision())
        with self.assertRaises(ValueError):
            generate(self.service,comp['id'],self.flow.revision(),confirm=True,current_date='2024-01-01',include_life=True,required_thickness='6',adopted_rate='-1',profile_confirmed=True)
        self.assertEqual(next(r for r in self.service.readings() if r['observation_id']=='b')['inspection_date'],'2022-01-01')
        self.service.resolve_sheet_date('source','new','2023-01-01','reviewer','source changed')
        result=generate(self.service,comp['id'],self.flow.revision(),confirm=True,current_date='2024-01-01')
        self.assertNotEqual(result['comparison']['id'],comp['id'])
        self.assertEqual(next(r for r in result['evaluation']['rows'] if r['current_id']=='b')['elapsed_days'],1461)

    def test_unconfirmed_report_never_calculates_rates(self):
        from evaluator.quick_workflow import match,generate
        comp=match(self.service,['source','old','current'],['source','new','current'],self.flow.revision())
        result=generate(self.service,comp['id'],self.flow.revision(),confirm=False)
        self.assertTrue(all(r['apparent_rate_mm_year'] is None for r in result['evaluation']['rows']))
        self.assertTrue(all(not r['accepted'] for r in result['comparison']['rows']))

    def test_life_profile_requires_one_scope_confirmation(self):
        from evaluator.quick_workflow import match,generate
        comp=match(self.service,['source','old','current'],['source','new','current'],self.flow.revision())
        with self.assertRaises(ValueError):
            generate(self.service,comp['id'],self.flow.revision(),confirm=True,include_life=True,required_thickness='6',adopted_rate='.5')
        result=generate(self.service,comp['id'],self.flow.revision(),confirm=True,include_life=True,required_thickness='6',adopted_rate='.5',profile_confirmed=True)
        self.assertEqual(next(r for r in result['evaluation']['rows'] if r['current_id']=='b')['remaining_life_years'],'6')

    def test_simple_page_has_two_selectors_and_no_audit_typing(self):
        from evaluator.quick_ui import quick_page
        from evaluator.quick_workflow import match
        comp=match(self.service,['source','old','current'],['source','new','current'],self.flow.revision())
        page=quick_page(self.service,comp['id'])
        self.assertIn('Generate report',page)
        self.assertNotIn('name="reviewer"',page)
        self.assertNotIn('name="reason"',page)
        self.assertNotIn('name="lifecycle"',page)
        self.assertIn('name="previous_date"',page)
        self.assertIn('/advanced?',page)

    def test_generate_rejects_stale_revision(self):
        from evaluator.quick_workflow import match,generate
        comp=match(self.service,['source','old','current'],['source','new','current'],self.flow.revision())
        with self.assertRaises(ValueError):generate(self.service,comp['id'],0,confirm=True)

    def test_download_is_scoped_to_selected_comparison(self):
        import zipfile
        from evaluator.quick_workflow import match,generate
        comp=match(self.service,['source','old','current'],['source','new','current'],self.flow.revision())
        first=generate(self.service,comp['id'],self.flow.revision(),confirm=True)
        other=match(self.service,['source','old','current'],['source','new','current'],self.flow.revision())
        generate(self.service,other['id'],self.flow.revision(),confirm=True)
        with zipfile.ZipFile(self.flow.export_revision(first['comparison']['id'])) as archive:
            report=json.loads(archive.read('project_snapshot.json'))
            self.assertEqual([c['id'] for c in report['comparisons']],[comp['id']])
            self.assertEqual([e['comparison_id'] for e in report['evaluations']],[comp['id']])

    def test_whole_sheet_evidence_is_undoable_without_copying_payload_into_each_action(self):
        payload=json.dumps({'cells':{'A1':{'value':'large evidence '*1000}}})
        with connection(self.service.repository.path) as db:
            db.execute('INSERT INTO imported_sheets VALUES(?,?,?)',('source','old',payload))
        self.service.bulk_review(['a'],'reviewed','checked')
        with connection(self.service.repository.path) as db:
            action=db.execute('SELECT before_json FROM wf_actions ORDER BY revision DESC LIMIT 1').fetchone()[0]
            self.assertNotIn('large evidence',action)
            db.execute("DELETE FROM imported_sheets")
        self.flow.undo(self.flow.revision(),'reviewer','restore')
        self.assertEqual(self.service.imported_sheet('source','old'),json.loads(payload))

    def test_changed_locations_refresh_preview_before_confirmation(self):
        from evaluator.quick_workflow import match,generate
        comp=match(self.service,['source','old','current'],['source','new','current'],self.flow.revision())
        self.service.correct_reading('b','9','S4','J4','B1','','reviewer','different physical location')
        result=generate(self.service,comp['id'],self.flow.revision(),confirm=True)
        self.assertTrue(result['needs_review'])
        self.assertIsNone(result['evaluation'])
        self.assertFalse(any(r['accepted'] for r in result['comparison']['rows']))
        self.assertEqual(self.flow.evaluations(),[])

    def test_simple_http_match_report_and_download_without_manual_metadata(self):
        import io,zipfile
        from http.client import HTTPConnection
        from http.server import ThreadingHTTPServer
        from threading import Thread
        from urllib.parse import urlencode,urlsplit,parse_qs
        from evaluator.webapp import make_handler
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.service))
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        client=HTTPConnection('127.0.0.1',server.server_port,timeout=10)
        def request(path,values=None):
            client.request('GET' if values is None else 'POST',path,None if values is None else urlencode(values),{} if values is None else {'Content-Type':'application/x-www-form-urlencoded'})
            r=client.getresponse();return r.status,r.read(),r.getheader('Location')
        try:
            status,_,location=request('/workflow/quick-match',dict(revision=self.flow.revision(),baseline=json.dumps(['source','old','current']),current=json.dumps(['source','new','current'])))
            self.assertEqual(status,303)
            cid=parse_qs(urlsplit(location).query)['comparison'][0]
            status,body,_=request(location)
            self.assertEqual(status,200);self.assertNotIn(b'name="reviewer"',body)
            status,_,location=request('/workflow/quick-report',dict(comparison_id=cid,revision=self.flow.revision(),confirm='yes'))
            self.assertEqual(status,303);self.assertIn('report=',location)
            self.assertIn(b'Your report is ready',request(location)[1])
            name=parse_qs(urlsplit(location).query)['report'][0]
            status,body,_=request('/export/revision?name='+name)
            self.assertEqual(status,200)
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                self.assertEqual(json.loads(z.read('project_snapshot.json'))['comparison_scope'],cid)
                self.assertIn('whole_sheets.json',z.namelist())
            self.assertEqual(request('/advanced?comparison='+cid)[0],200)
        finally:client.close();server.shutdown();server.server_close();thread.join()

    def test_default_inspection_choices_do_not_mix_all_historical_columns(self):
        from evaluator.quick_ui import quick_page
        with connection(self.service.repository.path) as db:
            db.execute("INSERT INTO readings SELECT 'historic',source_id,sheet_name,'H1',raw_value,raw_unit,'2010-01','2010-01-01',date_candidates,location_candidates,review_status FROM readings WHERE observation_id='a'")
        page=quick_page(self.service)
        self.assertIn('data-historical hidden',page)
        self.assertIn('Show historical columns',page)

    def test_report_explains_missing_dates_without_sending_user_to_detailed_tools(self):
        from evaluator.quick_workflow import match,generate
        from evaluator.quick_ui import quick_page
        with connection(self.service.repository.path) as db:db.execute("UPDATE readings SET inspection_date=NULL WHERE observation_id='b'")
        comp=match(self.service,['source','old','current'],['source','new','current'],self.flow.revision())
        result=generate(self.service,comp['id'],self.flow.revision(),confirm=True)
        page=quick_page(self.service,result['comparison']['id'])
        self.assertIn('need inspection dates before rates can be calculated',page)
        self.assertIn('href="#reportDates"',page)

    def test_another_workbook_does_not_force_my_report_to_be_rebuilt(self):
        from evaluator.quick_workflow import match,generate
        from pathlib import Path
        comp=match(self.service,['source','old','current'],['source','new','current'],self.flow.revision())
        result=generate(self.service,comp['id'],self.flow.revision(),confirm=True)
        path=Path(self.temp.name)/'another.xlsx';path.write_bytes(b'original unrelated source bytes')
        self.service.add_source(path)
        with connection(self.service.repository.path) as db:
            db.execute("INSERT INTO workbooks(source_id,file_name) VALUES ('source2','other.xlsx')")
            db.execute("INSERT INTO readings SELECT 'other', 'source2',sheet_name,cell,raw_value,raw_unit,campaign,inspection_date,date_candidates,location_candidates,review_status FROM readings WHERE observation_id='b'")
        self.service.resolve_sheet_date('source2','new','2024-01-01','reviewer','other inspection date')
        self.assertFalse(self.flow.comparison(comp['id'])['stale'])
        self.assertFalse(next(e for e in self.flow.evaluations() if e['id']==result['evaluation']['id'])['stale'])
        self.service.resolve_sheet_date('source','new','2023-01-01','reviewer','my inspection date changed')
        self.assertTrue(self.flow.comparison(comp['id'])['stale'])
