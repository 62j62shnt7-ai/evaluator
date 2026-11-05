import csv, io, sys, tempfile, unittest
import sqlite3
from datetime import date
from decimal import Decimal
from openpyxl import Workbook
from pathlib import Path
from http.client import HTTPConnection
from threading import Thread
from tests.source_config import SOURCE_ROOT
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'src'))
from evaluator.app_services import ProjectService, csv_safe
from evaluator.storage.database import connection
from evaluator.webapp import page, make_handler
from http.server import ThreadingHTTPServer

class AppServiceTests(unittest.TestCase):
    def test_one_evaluation_sheet_supplies_both_dates_for_corrosion_rate(self):
        with tempfile.TemporaryDirectory() as td:
            src=SOURCE_ROOT/'workbooks/TL-B from SAG Gas MFD to GP.xlsx'
            service=ProjectService(Path(td)/'project')
            source=service.add_source(src,src.name)
            service.inspect(source.sha256)
            imported=service.extract(source.sha256,'Evalation 4-2026')
            self.assertEqual(imported['imported'],153)
            flow=service.workflow
            comparison=flow.compare(
                source.sha256,'Evalation 4-2026','2021-01-22',
                source.sha256,'Evalation 4-2026','2025-06-08',
                'TL-B','same component lifecycle',True,'reviewer','dated minimum UT columns in the same worksheet',
            )
            row=next(item for item in comparison['rows'] if item.get('current') and item['current']['cell']=='N15')
            self.assertEqual(row['kind'],'matched')
            self.assertEqual(row['previous']['cell'],'K15')
            self.assertEqual(row['previous']['sheet_name'],row['current']['sheet_name'])
            proposal=flow.proposals(comparison['id'])[0]
            flow.apply_proposal(proposal['id'],proposal['expected_revision'],'reviewer','same physical point verified')
            evaluation=flow.calculate(
                comparison['id'],'','','365','rate calculated from dated readings on this sheet',
                'reviewer','dates and point identity checked',True,[row['id']],
            )
            calculated=next(item for item in evaluation['rows'] if item['pair_id']==row['id'])
            days=(date(2025,6,8)-date(2021,1,22)).days
            expected=(Decimal('7')-Decimal('6.8'))*Decimal(365)/Decimal(days)
            self.assertAlmostEqual(float(calculated['apparent_rate_mm_year']),float(expected),places=12)

    def test_upload_inventory_extract_and_csv_export(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=SOURCE_ROOT/'workbooks/TL-B from SAG Gas MFD to GP.xlsx'
            service=ProjectService(root/'project')
            record=service.add_source(src,src.name)
            result=service.inspect(record.sha256)
            self.assertIn('10-2022',[s['name'] for s in result['sheets']])
            summary=service.extract(record.sha256,'10-2022')
            self.assertGreater(summary['imported'],0)
            newest=service.extract(record.sha256,'UT 4- 2026')
            self.assertEqual(newest['imported'],2)
            self.assertTrue(newest['date_conflict'])
            service.resolve_sheet_date(record.sha256,'UT 4- 2026','2026-04-30','reviewer','confirmed report date')
            chosen=[x for x in service.readings() if x['sheet_name']=='UT 4- 2026']
            self.assertTrue(all(x['inspection_date']=='2026-04-30' for x in chosen))
            self.assertTrue(all('2026-04' in x['date_candidates'] for x in chosen))
            self.assertTrue(all('date' not in x['reason'].lower() for x in service.sheet_statuses(record.sha256) if x['sheet']=='UT 4- 2026'))
            self.assertEqual(next(x['status'] for x in service.sheet_statuses(record.sha256) if x['sheet']=='UT 4- 2026'),'imported')
            service.extract(record.sha256,'UT 4- 2026')
            self.assertTrue(all(x['inspection_date']=='2026-04-30' for x in service.readings() if x['sheet_name']=='UT 4- 2026'))
            candidates=service.readings()
            changed=service.bulk_review([x['observation_id'] for x in candidates[:2]],'reviewed','test batch')
            self.assertEqual(changed, min(2,len(candidates)))
            coverage=service.coverage(record.sha256)
            self.assertEqual(coverage['detected'],len(result['sheets']))
            self.assertGreater(coverage['unresolved'],0)
            html_page=page(service)
            self.assertIn('Engineering evaluation',html_page)
            self.assertIn('approval is waived for app completion',html_page)
            self.assertIn('2026-04-30',html_page)
            self.assertIn('Delete workbook',html_page)
            self.assertIn('Apply date to sheet',html_page)
            self.assertIn('<th>Location candidates</th>',html_page)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service))
            thread=Thread(target=server.serve_forever,daemon=True); thread.start()
            try:
                client=HTTPConnection('127.0.0.1',server.server_port,timeout=3)
                client.request('GET','/')
                response=client.getresponse()
                self.assertEqual(response.status,200)
                self.assertIn(b'UT',response.read())
                client.request('GET','/workflow')
                response=client.getresponse()
                self.assertEqual(response.status,200)
                self.assertIn(b'Choose previous and current readings',response.read())
                wb=Workbook(); wb.active.title='Raw'; buffer=io.BytesIO(); wb.save(buffer)
                boundary='CodexBoundary123'; payload=buffer.getvalue()
                body=(f'--{boundary}\r\nContent-Disposition: form-data; name="workbook"; filename="TL-B upload.xlsx"\r\nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n').encode()+payload+f'\r\n--{boundary}--\r\n'.encode()
                client.request('POST','/upload',body,{'Content-Type':f'multipart/form-data; boundary={boundary}','Content-Length':str(len(body))})
                response=client.getresponse()
                self.assertEqual(response.status,303)
                self.assertIn('TL-B upload.xlsx',[s['file_name'] for s in service.sources()])
            finally:
                client.close(); server.shutdown(); server.server_close(); thread.join()
            rows=list(csv.reader(io.StringIO(service.export_csv())))
            self.assertGreater(len(rows),1)
            self.assertEqual(csv_safe('=1+1'),"'=1+1")
            service.delete_source(record.sha256)
            self.assertNotIn(record.sha256,[s['source_id'] for s in service.sources()])
            self.assertFalse(record.stored_path.exists())
            with connection(service.repository.path) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM audit_log WHERE source_id=?',(record.sha256,)).fetchone()[0],0)

if __name__=='__main__': unittest.main()
