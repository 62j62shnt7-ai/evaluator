"""Repeat the requested UT single-sheet path in an isolated local project."""
from decimal import Decimal
from hashlib import sha256
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode, urlsplit, parse_qs
import csv
import io
import html
import re
from openpyxl import load_workbook
import json
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from evaluator.app_services import ProjectService
from evaluator.webapp import make_handler


def run(destination):
    destination=Path(destination).resolve()
    if (destination/'project.sqlite').exists():raise ValueError('Use a fresh test project')
    service=ProjectService(destination)
    workbook=ROOT/'sources/workbooks/TL-B from SAG Gas MFD to GP.xlsx'
    original=sha256(workbook.read_bytes()).hexdigest()
    source=service.add_source(workbook);service.inspect(source.sha256)
    flow=service.workflow
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    client=HTTPConnection('127.0.0.1',server.server_port,timeout=30)
    def request(path,values=None):
        client.request('GET' if values is None else 'POST',path,None if values is None else urlencode(values,doseq=True),{} if values is None else {'Content-Type':'application/x-www-form-urlencoded'})
        response=client.getresponse();body=response.read()
        expected=200 if values is None or path=='/workflow/quick-export' else 303
        assert response.status==expected,(path,response.status,body[:500])
        return body,response.getheader('Location')
    def row15(result):return next(r for r in result['rows'] if r['current_cell']=='K158')
    def close(actual,expected):
        assert actual is not None and abs(Decimal(actual)-expected)<Decimal('1e-12'),(actual,str(expected))
    try:
        _,location=request('/workflow/quick-import-single',dict(source_id=source.sha256,sheet_name='UT 5-2025',revision=flow.revision()))
        assert not flow.comparisons()
        page,_=request(location)
        assert b'value="01-2021"' in page and b'value="05-2025"' in page
        _,location=request('/workflow/quick-match-single',dict(source_id=source.sha256,sheet_name='UT 5-2025',previous_campaign='01-2021',current_campaign='05-2025',revision=flow.revision()))
        cid=parse_qs(urlsplit(location).query)['comparison'][0]
        request(location)
        # Use only UT column-header months; no exact day or evaluation date supplied.
        _,location=request('/workflow/quick-report',dict(comparison_id=cid,revision=flow.revision(),confirm='yes'))
        cid=parse_qs(urlsplit(location).query)['comparison'][0]
        request(location)
        request('/workflow/batch?'+urlencode(dict(comparison=cid)))
        request('/workflow/batch-prepare',dict(comparison_id=cid,revision=flow.revision()))
        opts=dict(profile_sheet='Evalation 4-2026',confirm_records=True,confirm_history=True,confirm_conflicts=True,confirm_rules=True,basis='provided',year_days='365')
        def calculate():
            preview=service.batch.preview(cid,opts['profile_sheet'],opts)
            payload=dict(opts,comparison_id=cid,revision=flow.revision(),preview_token=preview['preview_token'])
            for key in ('confirm_records','confirm_history','confirm_conflicts','confirm_rules'):payload[key]='yes'
            _,location=request('/workflow/batch-evaluate',payload)
            request(location)
            return service.batch.results(cid)[0]
        actual=calculate();r=row15(actual)
        assert r['inspection_date']=='2025-05'
        assert actual['source_snapshot']['rows'][0]['previous']['inspection_date']=='2021-01'
        close(r['apparent_rate_mm_year'],Decimal('.2')*12/52)
        life=(Decimal('6.8')-Decimal('3.949669471153846'))/(Decimal('.2')*12/52)
        close(r['remaining_life_years'],life)
        close(r['inspection_interval_years'],Decimal(10))
        close(r['mawp_MPa'],Decimal('1500')*Decimal('0.006894757293'))
        assert r['mawp_MPa']==r['forecast_mawp_MPa']
        assert r['profile']['code_edition']=='2020'
        # Independent arithmetic checks for every emitted historical/life/interval value.
        checked=dict(cr=0,life=0,interval=0)
        for item in actual['rows']:
            if item['apparent_rate_mm_year'] is not None:
                close(item['apparent_rate_mm_year'],(Decimal(item['previous_thickness_mm'])-Decimal(item['current_thickness_mm']))*365/Decimal(item['elapsed_days']));checked['cr']+=1
            if item['remaining_life_years'] is not None:
                minimum=Decimal(item['required_thickness_mm'] or item['pressure_thickness_mm'])
                expected=(Decimal(item['current_thickness_mm'])-minimum)/Decimal(item['adopted_rate_mm_year'])
                close(item['remaining_life_years'],expected);checked['life']+=1
            if item['inspection_interval_years'] is not None:
                policy=item['input_trace']['interval_policy']
                expected=Decimal(item['selected_interval_years']) if item['selected_interval_years'] is not None else min(Decimal(item['remaining_life_years'])*Decimal(str(policy['fraction'])),Decimal(str(policy['cap_years'])))
                close(item['inspection_interval_years'],expected);checked['interval']+=1
        # Source formula supplies the design factor and implicit unity E/T.
        pressure=actual;p=r
        expected_psi=2*Decimal('.8')*52000*Decimal('3.949669471153846')/(Decimal('8.625')*Decimal('25.4'))
        expected_mpa=expected_psi*Decimal('0.006894757293')
        close(p['mawp_MPa'],expected_mpa);close(p['forecast_mawp_MPa'],expected_mpa)
        close(p['outputs']['trace']['mawp_MPa']['forecast_years'],life)
        close(p['outputs']['trace']['forecast_mawp_MPa']['forecast_years'],life)
        service.batch.apply_overrides(cid,flow.revision(),[],[r['current_id']],dict(selected_interval_years='5'),opts['profile_sheet'])
        manual=calculate();m=row15(manual)
        expected_manual=2*Decimal('.8')*52000*(Decimal('6.8')-2*(Decimal('.2')*12/52)*5)/(Decimal('8.625')*Decimal('25.4'))
        close(m['forecast_mawp_MPa'],expected_manual*Decimal('0.006894757293'))
        close(m['mawp_MPa'],expected_mpa)
        close(m['inspection_interval_years'],Decimal(5))
        checked['mawp']=0
        for result in (actual,manual):
            for item in result['rows']:
                if item['current_cell']:assert item['current_cell'].startswith('K')
                if item['previous_cell']:assert item['previous_cell'].startswith('F')
                for key in ('mawp_MPa','forecast_mawp_MPa'):
                    if item[key] is None:continue
                    trace=item['outputs']['trace'][key]
                    v=item['input_trace']['design_inputs']
                    net=Decimal(item['current_thickness_mm'])-Decimal(trace['allowance_mm'])-Decimal(item['adopted_rate_mm_year'])*Decimal(trace['forecast_years'])*Decimal(trace['forecast_factor'])
                    expected=2*net*Decimal(v['SMYS_MPa'])*Decimal(v['F_class'])*Decimal(v['E_weld'])*Decimal(v['T_temp'])/Decimal(v['D_outside_mm'])
                    close(item[key],expected);checked['mawp']+=1
        raw,_=request('/workflow/quick-export',dict(comparison_id=cid))
        archive=destination/'verified-export.zip';archive.write_bytes(raw)
        with zipfile.ZipFile(archive) as z:
            manifest=json.loads(z.read('manifest.json'))
            for name,digest in manifest['files'].items():assert sha256(z.read(name)).hexdigest()==digest
            snapshot=json.loads(z.read('project_snapshot.json'))
            assert 'batch_evaluations.csv' in z.namelist()
            assert len(snapshot['batch_evaluations'])==2
            for saved in snapshot['batch_evaluations']:
                exported_row=row15(saved)
                reference=next(item for item in (actual,pressure,manual) if item['id']==saved['id'])
                assert exported_row==row15(reference)
            columns=['apparent_rate_mm_year','adopted_rate_mm_year','remaining_life_years','inspection_interval_years','mawp_MPa','forecast_mawp_MPa']
            csv_rows=list(csv.DictReader(io.StringIO(z.read('batch_evaluations.csv').decode('utf-8-sig'))))
            excel=load_workbook(io.BytesIO(z.read('evaluation.xlsx')),data_only=True)
            sheet=excel['batch_evaluations'];values=list(sheet.values)
            excel_rows=[dict(zip(values[0],v)) for v in values[1:]]
            report=z.read('summary.html').decode()
            report_rows=[[html.unescape(re.sub('<[^>]+>','',cell)) for cell in re.findall(r'<td>(.*?)</td>',tr,re.S)] for tr in re.findall(r'<tr>(.*?)</tr>',report,re.S)]
            report_columns=['asset','location','current_sheet','current_cell','current_thickness_mm','profile_id','required_thickness_mm','apparent_rate_mm_year','adopted_rate_mm_year','remaining_life_years','inspection_interval_years','maximum_interval_years','due_date','mawp_MPa','forecast_mawp_MPa','issues','stale','evaluation_status']
            for result in (actual,manual):
                target=row15(result)
                expected={key:format(Decimal(target[key]),'.4f' if key.endswith('_mm_year') else '.2f').rstrip('0').rstrip('.') for key in columns}
                for records in (csv_rows,excel_rows):
                    exported=next(v for v in records if v['batch_id']==result['id'] and v['current_cell']=='K158')
                    for key in columns:assert str(exported[key])==expected[key],(key,exported[key],expected[key])
                assert any(len(v)==len(report_columns) and v[3]=='K158' and all(v[report_columns.index(key)]==expected[key] for key in columns) for v in report_rows),expected
            # Both CR fields must use the calculated value; the old 0.15 source
            # literal must not appear as the selected rate for this point.
            assert row15(actual)['adopted_rate_mm_year']==row15(actual)['apparent_rate_mm_year']
            assert row15(actual)['selected_interval_years'] is None
            checked['export_formats']=['HTML','CSV','XLSX','JSON']
            excel.close()

        assert sha256(workbook.read_bytes()).hexdigest()==original
        evidence=dict(selection=['UT 5-2025','01-2021','05-2025'],exact_dates=['2021-01','2025-05'],source_sha256=original,
                      independent_checks=checked,actual_source_summary=actual['summary'],actual_row=r,
                      pressure_test_row=p,manual_interval_test_row=m,
                      default_mawp_formula_psi=str(expected_psi),manual_5_year_formula_psi=str(expected_manual),export=str(archive),
                      limitation='Workbook code year is retained as provenance and does not block arithmetic. Recognized source pressure formula supplies F=0.8 and implicit E=T=1; scenario and physical continuity confirmations here are software-test confirmations.')
        (destination/'verification.json').write_text(json.dumps(evidence,indent=2))
        print(json.dumps({k:evidence[k] for k in ['independent_checks','actual_source_summary','default_mawp_formula_psi','manual_5_year_formula_psi','limitation']},indent=2))
        return evidence
    finally:client.close();server.shutdown();server.server_close();thread.join()

if __name__=='__main__':run(sys.argv[1])
