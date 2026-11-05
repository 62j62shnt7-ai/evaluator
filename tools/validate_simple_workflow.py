"""Exercise the default simple workflow on actual workbooks in a NEW test project."""
import hashlib,io,json,zipfile
from pathlib import Path
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlencode,urlsplit,parse_qs
from evaluator.app_services import ProjectService
from evaluator.webapp import make_handler

ROOT=Path(__file__).resolve().parents[1]

def run(destination):
    destination=Path(destination).resolve()
    if (destination/'project.sqlite').exists():raise ValueError('Use a fresh destination')
    service=ProjectService(destination)
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service));thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    client=HTTPConnection('127.0.0.1',server.server_port,timeout=60)
    def request(path,data=None):
        client.request('GET' if data is None else 'POST',path,None if data is None else urlencode(data),{} if data is None else {'Content-Type':'application/x-www-form-urlencoded'})
        r=client.getresponse();body=r.read();assert r.status in (200,303),(r.status,path,body[:300]);return body,r.getheader('Location')
    evidence={'purpose':'Software acceptance; test confirmations do not establish physical continuity','cases':[]}
    try:
        for filename,old,old_campaign,new,new_campaign,expected in [
            ('Separator-204 Inspection Report.xlsx','UT Aug-2024','current','UT Jan 2026','current',29),
            ('Separator-204 Inspection Report.xlsm','UT Aug-2024','current','UT Jan 2026','current',29),
            ('TL-B from SAG Gas MFD to GP.xlsx','10-2022','10-2022','UT 5-2025','05-2025',19)]:
            path=ROOT/'sources/workbooks'/filename;original=path.read_bytes();sid=hashlib.sha256(original).hexdigest()
            boundary='WholeInspectionWorkflowAcceptance'
            upload=(f'--{boundary}\r\nContent-Disposition: form-data; name="workbook"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()+original+f'\r\n--{boundary}--\r\n'.encode()
            client.request('POST','/upload',upload,{'Content-Type':f'multipart/form-data; boundary={boundary}'})
            response=client.getresponse();upload_body=response.read();assert response.status==303,(response.status,upload_body[:500])
            page,_=request('/');assert b'Import both sheets &amp; find matches' in page
            _,location=request('/workflow/quick-import',dict(source_id=sid,previous_sheet=old,current_sheet=new,revision=service.workflow.revision()))
            cid=parse_qs(urlsplit(location).query)['comparison'][0]
            page,_=request(location);assert b'name="reviewer"' not in page
            assert sum(r['kind']=='lifecycle_mismatch' for r in service.workflow.comparison(cid)['rows'])==expected
            _,location=request('/workflow/quick-report',dict(comparison_id=cid,revision=service.workflow.revision(),confirm='yes'))
            values=parse_qs(urlsplit(location).query);cid=values['comparison'][0];name=values['report'][0]
            page,_=request(location);assert b'Your report is ready' in page
            if filename.startswith('TL-B'):assert b'need inspection dates before rates can be calculated' in page
            body,_=request('/export/revision?name='+name)
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                manifest=json.loads(z.read('manifest.json'))
                assert all(hashlib.sha256(z.read(k)).hexdigest()==v for k,v in manifest['files'].items())
                snap=json.loads(z.read('project_snapshot.json'));whole=json.loads(z.read('whole_sheets.json'))
                assert snap['comparison_scope']==cid and len(snap['comparisons'])==1
                assert {s['sheet_name'] for s in whole}=={old,new}
                if filename.startswith('Separator'): assert all({x['name'] for x in s['sections']}=={'CMLS','NOZZLES'} for s in whole)
                assert z.read(next(n for n in z.namelist() if n.startswith('source_workbooks/')))==original
                evaluation=snap['evaluations'][0];computed=sum(r['apparent_rate_mm_year'] is not None for r in evaluation['rows'])
                assert computed==(29 if filename.startswith('Separator') else 0)
                assert all(r['remaining_life_years'] is None for r in evaluation['rows'])
            request('/sheet?'+urlencode(dict(source=sid,sheet=new)))
            entry=dict(file=filename,upload='HTTP multipart',import_action='both whole sheets and match in one request',comparison=cid,match_candidates=expected,computed_rates=computed,whole_sheets=[dict(sheet=s['sheet_name'],cells=len(s['cells']),parts=len(s['related_parts'])) for s in whole],report=name)
            evidence['cases'].append(entry);print(entry,flush=True)
            assert path.read_bytes()==original
        assert all(not c['stale'] for c in service.workflow.comparisons()),'Unrelated workbook imports must not invalidate earlier comparisons'
        assert all(not e['stale'] for e in service.workflow.evaluations()),'Unrelated workbook imports must not invalidate earlier reports'
        (destination/'verification.json').write_text(json.dumps(evidence,indent=2)+'\n')
    finally:client.close();server.shutdown();server.server_close();thread.join()

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('destination');args=p.parse_args();run(args.destination)
