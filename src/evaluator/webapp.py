"""Small dependency-light localhost UI for inspection intake and review."""
from __future__ import annotations

from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit
import mimetypes
import zipfile
import json
import tempfile
import threading
import webbrowser

from evaluator.app_services import ProjectService


def page(service, notice=''):
    from evaluator.desk_ui import workspace_page

    return workspace_page()


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        def _reply(self,body,status=200,content_type='text/html; charset=utf-8',headers=()):
            raw=body.encode('utf-8') if isinstance(body,str) else body
            self.send_response(status); self.send_header('Content-Type',content_type); self.send_header('Content-Length',str(len(raw))); self.send_header('X-Content-Type-Options','nosniff')
            for k,v in headers:self.send_header(k,v)
            self.end_headers(); self.wfile.write(raw)
        def _redirect(self,message):
            self._reply('',303,'text/plain',(('Location','/?'+urlencode({'notice':message})),))
        def do_GET(self):
            path=self.path.split('?',1)[0]
            if path == '/workspace/calculation':
                from evaluator.calculation_trace_ui import page as calculation_page

                params = parse_qs(urlsplit(self.path).query)
                result_id = params.get('result', [''])[0]
                row_id = params.get('row', [''])[0]
                batch = next((entry for entry in service.batch.results() if entry['id'] == result_id), None)
                row = next((entry for entry in batch['rows'] if entry['id'] == row_id), None) if batch else None
                if row is None:
                    self._reply('Saved calculation not found', 404, 'text/plain')
                else:
                    self._reply(calculation_page(batch, row))
                return
            if path == '/codes':
                from evaluator.code_guide import page as code_guide
                from evaluator.code_sample_ui import code_rule

                params = parse_qs(urlsplit(self.path).query)
                sample = code_rule(params.get('code', [''])[0], params.get('geometry', [''])[0])
                self._reply(code_guide(sample or params.get('sample', [''])[0]))
                return
            if path == '/vessels':
                from evaluator.vessel_ui import page as vessel_page
                self._reply(vessel_page(service))
                return
            if path == '/vessels/results.csv':
                import csv
                import io
                from evaluator.engineering.vessel_assessment import history
                ident = parse_qs(urlsplit(self.path).query).get('id', [''])[0]
                record = next((row for row in history(service.workflow) if row['id'] == ident), None)
                if record is None:
                    self._reply('Vessel assessment not found', 404, 'text/plain')
                    return
                metadata = dict(record)
                components = metadata.pop('components')
                metadata['governing_components'] = ' | '.join(record['governing_components'])
                rows = [dict(metadata, **component) for component in components]
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
                self._reply(output.getvalue(), 200, 'text/csv; charset=utf-8',
                            (('Content-Disposition', 'attachment; filename="vessel-assessment.csv"'),))
                return
            if path == '/pipeline':
                from evaluator.pipeline_ui import page as pipeline_page
                query = parse_qs(urlsplit(self.path).query)
                self._reply(pipeline_page(service, {'comparison_id': query.get('comparison', [''])[0]}))
                return
            if path == '/pipeline/results.csv':
                import csv
                import io
                from evaluator.engineering.pipeline_corrosion import history
                query = parse_qs(urlsplit(self.path).query)
                record = next((record for record in history(service.workflow)
                               if record['id'] == query.get('id', [''])[0]), None)
                if record is None:
                    self._reply('Pipeline assessment not found', 404, 'text/plain')
                    return
                fields = dict(record)
                inputs = fields.pop('inputs')
                if record.get('assessment_type') == 'documented_limits':
                    fields['governing_limits'] = ' | '.join(record['governing_limits'])
                    for key, item in inputs.items():
                        fields[key] = item['psi']
                        fields[key + '_disposition'] = item['disposition']
                        fields[key + '_reference'] = item['reference']
                else:
                    fields.update(inputs)
                    ut = fields.pop('ut_trace', {})
                    fields.update({'ut_' + key: value for key, value in ut.items()})
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=list(fields))
                writer.writeheader()
                writer.writerow(fields)
                self._reply(output.getvalue(), 200, 'text/csv; charset=utf-8',
                            (('Content-Disposition', 'attachment; filename="pipeline-assessment.csv"'),))
                return
            if path == '/tanks/forecast':
                from evaluator.tank_forecast_ui import page as forecast_page
                self._reply(forecast_page(service))
                return
            if path == '/tanks/forecast.csv':
                import csv
                import io
                from evaluator.tanks import history
                ident = parse_qs(urlsplit(self.path).query).get('id', [''])[0]
                record = next((row for row in history(service.workflow)
                               if row['id'] == ident and row['method'] == 'api653_forecast'), None)
                if record is None:
                    self._reply('Tank forecast not found', 404, 'text/plain')
                    return
                metadata = dict(record['inputs'], **record['outputs'], tank=record['tank'],
                                reviewer=record['reviewer'], design_basis=record['reason'],
                                rule=record['reference'], status=record['status'], id=record['id'])
                metadata['governing_shell_courses'] = ' | '.join(record['outputs']['governing_shell_courses'])
                for key in ('governing_local_areas', 'pit_exclusion_failed_courses'):
                    metadata[key] = ' | '.join(metadata.get(key, []))
                rows = [dict(metadata, **{key: value for key, value in course.items() if key not in {'api653', 'local_checks', 'pit_check'}},
                             local_checks=json.dumps(course.get('local_checks', [])),
                             pit_check=json.dumps(course.get('pit_check', {})),
                             **{key: course['api653']['outputs'][key] for key in ('allowable_stress_MPa', 'minimum_mm')})
                        for course in record['courses']]
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
                self._reply(output.getvalue(), 200, 'text/csv; charset=utf-8',
                            (('Content-Disposition', 'attachment; filename="tank-forecast.csv"'),))
                return
            if path == '/tanks':
                from evaluator.tank_ui import page as tank_page
                self._reply(tank_page(service))
                return
            if path not in {'/','/workspace','/api/workspace','/workspace/results.csv','/workspace/results.xlsx','/workspace/results.json','/source-workbook','/sheet-object','/sheet'} and not path.startswith('/assets/'):
                self._reply('Not found',404,'text/plain');return
            if path in {'/workspace/results.csv', '/workspace/results.xlsx', '/workspace/results.json'}:
                from evaluator.result_export import result_rows, review_rows, workbook_bytes
                import csv
                import io
                q=parse_qs(urlsplit(self.path).query)
                result=service.batch.result_by_id(q.get('result',[''])[0])
                if not result or result.get('stale'):
                    if path == '/workspace/results.json':
                        self._reply(json.dumps({'error': 'Calculate the current readings before reviewing results.'}), 400, 'application/json')
                        return
                    self._reply('Calculate the current readings before exporting.',400,'text/plain');return
                if path == '/workspace/results.json':
                    self._reply(json.dumps(review_rows(result)), 200, 'application/json')
                    return
                if path == '/workspace/results.xlsx':
                    self._reply(workbook_bytes(result), 200,
                                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                (('Content-Disposition', 'attachment; filename="UT-calculations.xlsx"'),))
                    return
                output=io.StringIO();writer=csv.writer(output)
                writer.writerows(result_rows(result))
                self._reply(output.getvalue(),200,'text/csv; charset=utf-8',(('Content-Disposition','attachment; filename="UT-evaluation.csv"'),));return
            if path in {'/','/workspace'}:
                self._reply(page(service));return
            if path.startswith('/assets/'):
                name=path.removeprefix('/assets/')
                if name not in {'workspace.css','workspace.js','integrity-desk.css','code-sample.js'}:self._reply('Not found',404,'text/plain');return
                self._reply((Path(__file__).parent/'static'/name).read_bytes(),200,'text/css' if name.endswith('.css') else 'text/javascript');return
            if path=='/api/workspace':
                from evaluator.workspace import Workspace
                q=parse_qs(urlsplit(self.path).query)
                try:
                    ids=q.get('ids',[None])[0]
                    row_ids=ids.split(',') if ids else None
                    self._reply(json.dumps(Workspace(service).state(q.get('comparison',[None])[0],q.get('scenario',[None])[0],row_ids)),200,'application/json')
                except (ValueError,KeyError) as exc:self._reply(json.dumps({'error':str(exc)}),400,'application/json')
                return
            if path=='/sheet':
                from evaluator.sheet_ui import sheet_page
                q=parse_qs(urlsplit(self.path).query)
                try:self._reply(sheet_page(service,q.get('source',[''])[0],q.get('sheet',[''])[0]))
                except (KeyError,ValueError):self._reply('Imported sheet not found',404,'text/plain')
                return
            if path in {'/source-workbook','/sheet-object'}:
                q=parse_qs(urlsplit(self.path).query);sid=q.get('source',[''])[0]
                record=next((r for r in service.repository.sources() if r.sha256==sid),None)
                if not record:self._reply('Source not found',404,'text/plain');return
                if path=='/source-workbook':
                    self._reply(record.stored_path.read_bytes(),200,'application/octet-stream',(('Content-Disposition','attachment; filename="original'+record.stored_path.suffix+'"'),));return
                sheet=service.imported_sheet(sid,q.get('sheet',[''])[0]);part=q.get('part',[''])[0]
                if not sheet or part not in {p['part'] for p in sheet['related_parts']}:
                    self._reply('Sheet object not found',404,'text/plain');return
                with zipfile.ZipFile(record.stored_path) as z:content=z.read(part)
                mime=mimetypes.guess_type(part)[0] or 'application/octet-stream'
                if mime not in {'image/png','image/jpeg','image/gif','image/bmp','image/webp'}:mime='application/octet-stream'
                self._reply(content,200,mime,() if mime.startswith('image/') else (('Content-Disposition','attachment; filename="sheet-object"'),));return
            self._reply('Not found',404,'text/plain')

        def do_POST(self):
            try:
                expected_host=f'127.0.0.1:{self.server.server_port}'
                if self.headers.get('Host') not in {expected_host,f'localhost:{self.server.server_port}'}: raise ValueError('This app only accepts local requests')
                origin=self.headers.get('Origin')
                if origin and origin not in {'http://'+expected_host,f'http://localhost:{self.server.server_port}'}: raise ValueError('Cross-origin project changes are blocked')
                path=self.path.split('?',1)[0]
                if path == '/codes':
                    from evaluator.code_guide import page as code_guide

                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 8192:
                        raise ValueError('Invalid sample calculation form size')
                    form = {key: vals[0] for key, vals in parse_qs(self.rfile.read(length).decode()).items()}
                    self._reply(code_guide(form.get('sample', ''), form))
                    return
                if path == '/vessels':
                    from evaluator.vessel_ui import page as vessel_page
                    from evaluator.engineering.vessel_assessment import save
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 32768:
                        raise ValueError('Invalid vessel form size')
                    form = dict(parse_qsl(self.rfile.read(length).decode()))
                    try:
                        save(service.workflow, form)
                    except (ValueError, KeyError) as exc:
                        self._reply(vessel_page(service, form, str(exc)), 400)
                        return
                    self._reply('', 303, 'text/plain', (('Location', '/vessels#saved-vessels'),))
                    return
                if path == '/pipeline':
                    from evaluator.pipeline_ui import page as pipeline_page
                    from evaluator.engineering.pipeline_corrosion import save
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 8192:
                        raise ValueError('Invalid pipeline form size')
                    form = dict(parse_qsl(self.rfile.read(length).decode()))
                    try:
                        save(service.workflow, form)
                    except (ValueError, KeyError) as exc:
                        self._reply(pipeline_page(service, form, str(exc)), 400)
                        return
                    self._reply('', 303, 'text/plain', (('Location', '/pipeline#saved-pipeline'),))
                    return
                if path == '/tanks/forecast':
                    from evaluator.tank_forecast_ui import page as forecast_page
                    from evaluator.tanks import save
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 32768:
                        raise ValueError('Invalid tank form size')
                    form = dict(parse_qsl(self.rfile.read(length).decode()))
                    form.update(method='api653_forecast', component='Shell courses')
                    try:
                        save(service.workflow, form)
                    except (ValueError, KeyError) as exc:
                        self._reply(forecast_page(service, form, str(exc)), 400)
                        return
                    self._reply('', 303, 'text/plain', (('Location', '/tanks/forecast#saved-tank-forecasts'),))
                    return
                if path == '/tanks':
                    from evaluator.tanks import save
                    from evaluator.tank_ui import page as tank_page
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 32_768:
                        raise ValueError('Invalid tank form size')
                    form = {key: vals[0] for key, vals in parse_qs(self.rfile.read(length).decode()).items()}
                    try:
                        save(service.workflow, form)
                    except ValueError as exc:
                        self._reply(tank_page(service, str(exc), active_method=form.get('method')), 400)
                        return
                    self._reply('', 303, 'text/plain', (('Location', '/tanks#saved-tank-calculations'),))
                    return
                if path!='/workspace/upload' and not path.startswith('/api/workspace/'):
                    self._reply('Not found',404,'text/plain');return
                if path.startswith('/api/workspace/'):
                    if path.rsplit('/',1)[-1] not in {'prior_code_bases','location_preview','reference_preview','import','apply','apply_code_basis','prefill_sheet_materials','review_workbook_pipes','review_fittings','record_sleeve_assessment','evaluate','correct','dates','pair','identity','undo','delete_source','reset_project','restore_cleanup'}:
                        self._reply(json.dumps({'error':'Workspace action not found.'}),404,'application/json');return
                    from evaluator.workspace_api import action
                    length=int(self.headers.get('Content-Length','0'))
                    if length<=0 or length>2_000_000:raise ValueError('Invalid workspace request size')
                    result=action(service,path.rsplit('/',1)[-1],json.loads(self.rfile.read(length)))
                    self._reply(json.dumps(result),200,'application/json');return
                if path=='/workspace/upload':
                    length=int(self.headers.get('Content-Length','0'))
                    if length<=0 or length>110_000_000:raise ValueError('Upload must be under 100 MB.')
                    ctype=self.headers.get('Content-Type','')
                    msg=BytesParser(policy=policy.default).parsebytes((f'MIME-Version: 1.0\r\nContent-Type: {ctype}\r\n\r\n').encode()+self.rfile.read(length))
                    part=next((p for p in msg.iter_parts() if p.get_filename()),None)
                    if part is None:raise ValueError('Choose a workbook to upload.')
                    filename=Path(part.get_filename()).name
                    if Path(filename).suffix.lower() not in {'.xlsx','.xlsm'}:raise ValueError('Only .xlsx and .xlsm workbooks are supported.')
                    temp=service.project_dir/'incoming';temp.mkdir(exist_ok=True)
                    with tempfile.NamedTemporaryFile(prefix='upload-',suffix=Path(filename).suffix.lower(),dir=temp,delete=False) as stream:
                        stream.write(part.get_payload(decode=True));staged=Path(stream.name)
                    try:
                        from evaluator.importing.package_inventory import inventory
                        validated = inventory(staged, sheet_names_only=True)
                        if not validated.sheets:
                            raise ValueError('This workbook contains no readable worksheets.')
                        record = service.add_source(staged, filename)
                        if service.inventory_for(record.sha256) is None:
                            service.inspect(record.sha256, validated_inventory=validated)
                    finally:staged.unlink(missing_ok=True)
                    result = {'source_id': record.sha256,
                              'message': 'Workbook imported. Choose the UT sheet with your readings.'}
                    self._reply(json.dumps(result),200,'application/json');return
            except (ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
                self._reply(json.dumps({'error':str(exc)}),400,'application/json')
        def log_message(self,format,*args): pass
    return Handler


def serve(project_dir: Path, port: int = 8765, open_browser: bool = True):
    service=ProjectService(project_dir)
    server=ThreadingHTTPServer(('127.0.0.1',port),make_handler(service))
    if open_browser: threading.Timer(.6,lambda:webbrowser.open(f'http://127.0.0.1:{port}/')).start()
    print(f'UT Review is running at http://127.0.0.1:{port}/  (Ctrl+C to stop)')
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
