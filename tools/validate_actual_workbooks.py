"""Repeatable isolated acceptance workflow over the supplied source workbooks.

Never modifies originals or the user's default project. Test confirmations are
labelled as software-test decisions, not certified physical continuity.
"""
from pathlib import Path
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlencode,urlsplit,parse_qs
from collections import Counter
import hashlib,io,json,zipfile
from decimal import Decimal
from datetime import date
from openpyxl import load_workbook
from evaluator.app_services import ProjectService
from evaluator.webapp import make_handler

ROOT=Path(__file__).resolve().parents[1]

def run(destination):
    destination=Path(destination).resolve()
    if (destination/'project.sqlite').exists(): raise ValueError('Choose a fresh validation destination')
    service=ProjectService(destination)
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    client=HTTPConnection('127.0.0.1',server.server_port,timeout=90)
    def request(path,data=None):
        if data is None: client.request('GET',path)
        else: client.request('POST',path,urlencode(data,doseq=True),{'Content-Type':'application/x-www-form-urlencoded'})
        response=client.getresponse(); body=response.read()
        if response.status not in (200,303): raise AssertionError((path,response.status,body[:1000]))
        return body,response.getheader('Location')
    evidence={'purpose':'Software acceptance with actual source readings; not engineering certification','files':[],'cases':[]}
    try:
        sources={}
        for path in sorted((ROOT/'sources/workbooks').glob('*')):
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            boundary='ActualWorkbookAcceptance'
            body=(f'--{boundary}\r\nContent-Disposition: form-data; name="workbook"; filename="{path.name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
            client.request('POST','/upload',body,{'Content-Type':f'multipart/form-data; boundary={boundary}'})
            response=client.getresponse(); raw=response.read();assert response.status==303,(response.status,raw[:500])
            sources[path.name]=digest
            scan=[]
            for sheet in service.sheet_statuses(digest):
                name=sheet['sheet']
                if name.upper().startswith('UT') or ('TL-B' in path.name and name in ('2019',' 2021','10-2022')):
                    request('/extract',dict(source_id=digest,sheet_name=name,revision=service.workflow.revision()))
                    records=[r for r in service.readings() if r['source_id']==digest and r['sheet_name']==name]
                    scan.append(dict(sheet=name,count=len(records),campaigns=dict(Counter(r['campaign'] for r in records))))
            evidence['files'].append(dict(name=path.name,sha256=digest,extracted=scan))
            print(path.name,scan,flush=True)
        for filename in ('Separator-204 Inspection Report.xlsx','Separator-204 Inspection Report.xlsm'):
            sid=sources[filename]
            cases=[('UT Aug-2024','current','UT Jan 2026','current'),('UT Jan 2026','2024-08-25','UT Jan 2026','current'),('UT Jan 2026','current','UT 10-2026','current')]
            for old,oc,new,nc in cases:
                evaluate_case(service,request,evidence,sid,filename,old,oc,new,nc)
        sid=sources['TL-B from SAG Gas MFD to GP.xlsx']
        for old,oc,new,nc in [('10-2022','10-2022','UT 5-2025','05-2025'),('UT 5-2025','10-2022','UT 5-2025','05-2025'),('UT 5-2025','05-2025','UT 4- 2026','4-2026')]:
            evaluate_case(service,request,evidence,sid,'TL-B',old,oc,new,nc)
        body,_=request('/workflow/export',{})
        archive_path=destination/'actual-workbook-report.zip';archive_path.write_bytes(body)
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            manifest=json.loads(archive.read('manifest.json'))
            for name,digest in manifest['files'].items(): assert hashlib.sha256(archive.read(name)).hexdigest()==digest,name
            wb=load_workbook(io.BytesIO(archive.read('evaluation.xlsx')),data_only=True)
            assert {'coverage','comparisons','evaluations','revision'}.issubset(wb.sheetnames)
            wb.close()
            (destination/'actual-workbook-report.html').write_bytes(archive.read('summary.html'))
        evidence['report']=str(archive_path)
        for f in evidence['files']: assert hashlib.sha256((ROOT/'sources/workbooks'/f['name']).read_bytes()).hexdigest()==f['sha256']
        (destination/'verification.json').write_text(json.dumps(evidence,indent=2))
        return evidence
    finally: client.close();server.shutdown();server.server_close();thread.join()

def evaluate_case(service,request,evidence,sid,label,old,oc,new,nc):
    flow=service.workflow
    _,location=request('/workflow/compare',dict(revision=flow.revision(),baseline=json.dumps([sid,old,oc]),current=json.dumps([sid,new,nc]),asset=label,lifecycle='SOFTWARE-TEST / verify actual lifecycle',continuity='yes',reviewer='Acceptance test',reason='Software-only mapping test using exact source labels; physical continuity requires user verification'))
    cid=parse_qs(urlsplit(location).query)['comparison'][0]
    request(location)
    for p in flow.proposals(cid):
        if p['action']=='accept_matches': request('/workflow/proposal',dict(comparison_id=cid,proposal_id=p['id'],revision=p['expected_revision'],reviewer='Acceptance test',reason='Test exact-label matching; not physical certification'));break
    comp=flow.comparison(cid); ids=[r['id'] for r in comp['rows'] if r['accepted']]
    if ids:
        request('/workflow/evaluate',dict(comparison_id=cid,revision=flow.revision(),pair_ids=ids,year_days='365.2425',basis='ACTUAL READINGS / TEST MAPPING. Required thickness and adopted rate were not supplied; remaining life is withheld.',reviewer='Acceptance test',reason='Historical comparison and explicit exceptions; no invented engineering inputs',scope='yes'))
        evaluation=flow.evaluations()[0]
        included=[r for r in evaluation['rows'] if 'NOT_IN_EVALUATION_SCOPE' not in r['issues']]
        computed=sum(r['apparent_rate_mm_year'] is not None for r in included)
        assert all(r['remaining_life_years'] is None for r in included)
        issues=dict(Counter(i for r in included for i in r['issues']))
    else: computed=0;issues={'NO_AUTOMATIC_MATCHES':len(comp['rows'])}
    if label.startswith('Separator') and new=='UT Jan 2026':
        assert Counter(r['kind'] for r in comp['rows'])=={'matched':29,'current_only':6,'ambiguous':1}
        assert computed==29,computed
        pair=next(r for r in comp['rows'] if r.get('current') and r['current']['cell']=='H91')
        assert pair['previous']['raw_value']=='16' and pair['current']['raw_value']=='15.5'
        measured=next(r for r in included if r['pair_id']==pair['id'])
        expected=(Decimal('16')-Decimal('15.5'))*Decimal('365.2425')/Decimal((date(2026,1,20)-date(2024,8,25)).days)
        assert Decimal(measured['apparent_rate_mm_year'])==expected
    elif label.startswith('Separator'):
        assert len(ids)==13 and computed==0
        assert issues.get('DATE_UNRESOLVED')==13
    elif new=='UT 4- 2026':
        assert not ids and Counter(r['kind'] for r in comp['rows'])=={'previous_only':77,'ambiguous':2,'current_only':2}
    else:
        assert len(ids)==19 and computed==0
        assert Counter(r['kind'] for r in comp['rows'])=={'matched':19,'current_only':58,'ambiguous':2}
        assert issues.get('DATE_UNRESOLVED')==19
    result=dict(file=label,previous=[old,oc],current=[new,nc],comparison=cid,groups=dict(Counter(r['kind'] for r in comp['rows'])),confirmed_test_pairs=len(ids),computed_rates=computed,exceptions=issues)
    evidence['cases'].append(result);print(result,flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('destination',type=Path)
    args=parser.parse_args();run(args.destination)
