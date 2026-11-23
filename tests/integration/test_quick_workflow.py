import json
import unittest
from tests.integration import test_workflow as fixtures
from evaluator.storage.database import connection
from tests.source_config import original_workbook

class QuickWorkflowTests(unittest.TestCase):
    setUp=fixtures.WorkflowTests.setUp
    tearDown=fixtures.WorkflowTests.tearDown

    def test_single_sheet_selects_dates_before_matching_and_reports_selected_pair(self):
        import tempfile
        from pathlib import Path
        from evaluator.app_services import ProjectService
        from evaluator.quick_workflow import generate, import_single_dated_sheet, match_single_sheet

        path = original_workbook('TL-B from SAG Gas MFD to GP.xlsx')
        with tempfile.TemporaryDirectory() as td:
            service = ProjectService(Path(td) / 'project')
            source = service.add_source(path, path.name)
            service.inspect(source.sha256)
            flow = service.workflow
            for sheet, dates in (
                ('UT 5-2025', {'01-2021', '10-2022', '02-2025', '05-2025'}),
                ('Evalation 4-2026', {'2021-01-22', '2022-10-21', '2025-06-08'}),
            ):
                campaigns = import_single_dated_sheet(service, source.sha256, sheet, flow.revision())
                self.assertTrue(dates <= {item['campaign'] for item in campaigns})
                self.assertEqual(flow.comparisons(), [])

            def compare(sheet, previous, current):
                return match_single_sheet(service, source.sha256, sheet, previous, current, flow.revision())

            sheet = 'Evalation 4-2026'
            for previous, current in (
                ('2021-01-22', '2021-01-22'), ('2025-06-08', '2021-01-22'), ('bogus', '2025-06-08'),
            ):
                with self.assertRaises(ValueError):
                    compare(sheet, previous, current)
                self.assertEqual(flow.comparisons(), [])

            comparison = compare(sheet, '2021-01-22', '2025-06-08')
            self.assertEqual(comparison['baseline'][2], '2021-01-22')
            self.assertEqual(comparison['current_selection'][2], '2025-06-08')
            report = generate(service, comparison['id'], flow.revision(), confirm=True)
            pair_ids = {pair['id'] for pair in comparison['rows']
                        if pair['current'] and pair['current']['cell'] == 'N15'}
            row = next(row for row in report['evaluation']['rows'] if row['pair_id'] in pair_ids)
            self.assertAlmostEqual(float(row['apparent_rate_mm_year']), .2 * 365.2425 / 1598, places=9)
            self.assertEqual(compare(sheet, '2022-10-21', '2025-06-08')['baseline'][2], '2022-10-21')

            sheet = 'UT 5-2025'
            comparison = compare(sheet, '01-2021', '05-2025')
            report = generate(service, comparison['id'], flow.revision(), confirm=True,
                              previous_date='2021-01-22', current_date='2025-06-08')
            self.assertTrue(any(row['apparent_rate_mm_year'] is not None for row in report['evaluation']['rows']))
            for campaign, date in [('10-2022', '2022-10'), ('02-2025', '2025-02')]:
                self.assertTrue(all(row['inspection_date'] == date
                                    for row in flow._selection(source.sha256, sheet, campaign)))

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

    def test_simple_report_exports_selected_comparison_without_manual_metadata(self):
        import zipfile
        from evaluator.quick_workflow import generate, match

        comp = match(self.service, ['source', 'old', 'current'], ['source', 'new', 'current'],
                     self.flow.revision())
        report = generate(self.service, comp['id'], self.flow.revision(), confirm=True)
        self.assertIsNotNone(report['evaluation'])
        with zipfile.ZipFile(self.flow.export_revision(comp['id'])) as archive:
            snapshot = json.loads(archive.read('project_snapshot.json'))
            self.assertEqual(snapshot['comparison_scope'], comp['id'])
            self.assertIn('whole_sheets.json', archive.namelist())

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
