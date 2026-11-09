"""Small dependency-light localhost UI for inspection intake and review."""
from __future__ import annotations

from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
import mimetypes
import zipfile
import json
import tempfile
import threading
import webbrowser

from evaluator.app_services import ProjectService


def page(service, notice=''):
    return (Path(__file__).parent/'static'/'workspace.html').read_text(encoding='utf-8')


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
            if path not in {'/','/workspace','/api/workspace','/workspace/results.csv','/source-workbook','/sheet-object','/sheet'} and not path.startswith('/assets/'):
                self._reply('Not found',404,'text/plain');return
            if path=='/workspace/results.csv':
                import csv
                import io
                q=parse_qs(urlsplit(self.path).query)
                result=next((r for r in service.batch.results() if r['id']==q.get('result',[''])[0]),None)
                if not result or result.get('stale'):
                    self._reply('Calculate the current readings before exporting.',400,'text/plain');return
                output=io.StringIO();writer=csv.writer(output)
                writer.writerow(['Location','Previous date','Current date','Previous UT mm','Current UT mm','Material','Pd psi','OD in','Nominal mm','Structural mm','S psi','Pressure thickness mm','Required thickness mm','Calculated CR mm/year','CR used mm/year','CR basis','Remaining life years','Interval years','t in MAWP mm','MAWP psi','Result','Next inspection','Missing inputs'])
                for row in result['rows']:
                    if not row.get('current_id'):continue
                    i=row.get('input_trace',{}).get('inputs',{});r=row.get('row7') or {}
                    writer.writerow([row['location'],row.get('previous_inspection_date'),row.get('inspection_date'),row.get('previous_thickness_mm'),row.get('current_thickness_mm'),i.get('material'),i.get('pd_psi'),i.get('od_in'),i.get('nominal_mm'),i.get('structural_mm')]+[r.get(k) for k in ('s_psi','pressure_mm','required_mm','calculated_cr','cr_used','cr_basis','remaining_life','interval','mawp_thickness_mm','mawp_psi','result','next_inspection')]+['; '.join(row['issues'])])
                self._reply(output.getvalue(),200,'text/csv; charset=utf-8',(('Content-Disposition','attachment; filename="UT-evaluation.csv"'),));return
            if path in {'/','/workspace'}:
                self._reply((Path(__file__).parent/'static'/'workspace.html').read_text(encoding='utf-8'));return
            if path.startswith('/assets/'):
                name=path.removeprefix('/assets/')
                if name not in {'workspace.css','workspace.js'}:self._reply('Not found',404,'text/plain');return
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
                if path!='/workspace/upload' and not path.startswith('/api/workspace/'):
                    self._reply('Not found',404,'text/plain');return
                if path.startswith('/api/workspace/'):
                    if path.rsplit('/',1)[-1] not in {'import','apply','evaluate','correct','dates','pair','identity','undo','delete_source','reset_project','restore_cleanup'}:
                        self._reply('Not found',404,'text/plain');return
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
                        record=service.add_source(staged,filename);service.inspect(record.sha256)
                    finally:staged.unlink(missing_ok=True)
                    from evaluator.workspace import Workspace
                    workspace=Workspace(service)
                    result=workspace.auto_open(record.sha256,service.workflow.revision())
                    if result.get('comparison_id'):workspace.policy(result['comparison_id'],service.workflow.revision(),'row7')
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
