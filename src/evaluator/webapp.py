"""Small dependency-light localhost UI for inspection intake and review."""
from __future__ import annotations

from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
import html
import mimetypes
import zipfile
import json
import os
import re
import tempfile
import threading
import webbrowser

from evaluator.app_services import ProjectService
from evaluator.engineering.draft import REQUIRED, evaluate
from evaluator.workflow_ui import workflow_page, advanced_workflow_page, shell, standalone_calculator, field, hidden, person, E
from evaluator.workflow import _LOCK


def page(service: ProjectService, notice: str = '') -> str:
    sources=service.sources(); readings=service.readings()
    nav='<header><div class="brand">UT<span> / </span>Review</div><nav><a href="#intake">Intake</a><a href="#coverage">Coverage</a><a href="#readings">Readings</a><a href="/workflow">Evaluate readings</a></nav></header>'
    upload='<section class="panel" id="intake"><div class="eyebrow">01 / SOURCE INTAKE</div><h1>Bring inspection reports into view.</h1><p class="muted">Choose an .xlsx or .xlsm report. The app keeps the original bytes, inventories the package, and shows unsupported areas as unresolved.</p><form action="/upload" method="post" enctype="multipart/form-data"><label class="upload"><input type="file" name="workbook" accept=".xlsx,.xlsm" required><span>Choose a workbook</span><small>Stored in this local project by SHA-256</small></label><button class="primary">Add and inspect</button></form></section>'
    source_html=''.join(f'<article class="source"><div><strong>{html.escape(s["file_name"])}</strong><div class="hash">{html.escape(s["source_id"][:16])}… · {s["sheet_count"]} sheets · {s["object_count"]} drawing/media parts · {s["formula_count"]} formulas · {s["external_count"]} external links</div></div><form action="/inspect" method="post"><input type="hidden" name="source_id" value="{html.escape(s["source_id"])}"><button>Refresh inventory</button></form><form action="/delete-source" method="post" onsubmit="return confirm(\'Delete this workbook and its active extracted data? Existing exported snapshots and backups are retained.\')"><input type="hidden" name="source_id" value="{html.escape(s["source_id"])}">{hidden("revision",service.workflow.revision())}<button>Delete workbook</button></form></article>' for s in sources)
    coverage_html=''
    if sources:
        cards=[]
        for s in sources:
            cov=service.coverage(s['source_id']); inv=service.inventory_for(s['source_id'])
            sheets=(inv or {}).get('sheets',[])
            issues=''.join(f'<li><strong>{html.escape(x["sheet"])}</strong> · {html.escape(x["status"])}{": "+html.escape(x["reason"]) if x["reason"] else ""}</li>' for x in service.sheet_statuses(s['source_id']) if x['status'] in {'unresolved','needs_review','excluded'})
            sheet_options=''.join(f'<option value="{html.escape(x["name"])}">{html.escape(x["name"])} · {html.escape(x["state"])}</option>' for x in sheets)
            imports=[i for i in service.imported_sheets() if i['source_id']==s['source_id']]
            links=''.join('<li><a href="/sheet?'+urlencode({'source':i['source_id'],'sheet':i['sheet_name']})+'">'+html.escape(i['sheet_name'])+'</a> · whole sheet imported · '+str(i['cell_count'])+' cells</li>' for i in imports)
            dated_import=f'<form action="/workflow/quick-import-single" method="post"><input type="hidden" name="source_id" value="{html.escape(s["source_id"])}"><select name="sheet_name" required><option value="">Select one sheet with dated readings…</option>{sheet_options}</select>{hidden("revision",service.workflow.revision())}<button class="primary">Import one sheet &amp; choose dates</button></form><small>Imports Min-reading columns, then lets you choose which inspection dates to compare.</small>'
            advanced=f'<p><strong>{html.escape(s["file_name"])}</strong></p><ul>{links}</ul><article class="coverage"><div class="metric">{cov["detected"]}<small>detected sheets</small></div><div class="metric good">{cov["imported"]}<small>imported / review</small></div><div class="metric warn">{cov["unresolved"]}<small>unresolved</small></div><div><form action="/extract" method="post"><input type="hidden" name="source_id" value="{html.escape(s["source_id"])}"><select name="sheet_name" required><option value="">Select whole inspection sheet…</option>{sheet_options}</select>{hidden("revision",service.workflow.revision())}<button class="primary">Import whole inspection sheet</button></form><details><summary>Advanced: override every date on a sheet</summary><form action="/resolve-date" method="post" style="margin-top:8px"><input type="hidden" name="source_id" value="{html.escape(s["source_id"])}"><select name="sheet_name" required><option value="">Select sheet for date resolution…</option>{sheet_options}</select><input type="date" name="chosen_date" required><input name="reviewer" placeholder="Reviewer" required><input name="justification" placeholder="Date basis / reason" required>{hidden("revision",service.workflow.revision())}<button>Apply date to sheet</button><small style="display:block">Applies one selected inspection date to every extracted reading on that sheet; original candidates stay in the audit evidence.</small></form></details></div><details style="grid-column:1/-1"><summary>Sheet coverage details</summary><ul>{issues}</ul></details></article>'
            from evaluator.quick_ui import import_pair_form
            cards.append(import_pair_form(service,s)+dated_import+'<ul>'+links+'</ul><details><summary>Import one sheet or inspect coverage</summary>'+advanced+'</details>')
        coverage_html=''.join(cards)
    def date_display(r):
        candidates=json.loads(r['date_candidates'])
        return r['inspection_date'] or ('Unresolved: '+', '.join(candidates) if candidates else 'Date unresolved')
    def location_display(r): return ' · '.join(json.loads(r.get('effective_location',r['location_candidates'])))
    reading_rows=''.join(f'<tr><td><input type="checkbox" form="batchreview" name="observation_ids" value="{html.escape(r["observation_id"])}"></td><td>{html.escape(r["file_name"])}</td><td>{html.escape(r["sheet_name"])}</td><td>{html.escape(r["cell"])}</td><td>{html.escape(r.get("effective_value",r["raw_value"]))}<small>{" (corrected; raw "+html.escape(r["raw_value"])+")" if r.get("corrected") else ""}</small></td><td>{html.escape(r["raw_unit"] or "")}</td><td>{html.escape(r["campaign"])}</td><td>{html.escape(date_display(r))}</td><td>{html.escape(location_display(r))}</td><td>{html.escape(r["review_status"])}</td><td><a href="/reading?id={html.escape(r["observation_id"])}">Correct / inspect</a></td></tr>' for r in readings)
    if not reading_rows: reading_rows='<tr><td colspan="11" class="muted">Import a whole inspection sheet to start reviewing readings.</td></tr>'
    notice_html=f'<div class="notice">{html.escape(notice)}</div>' if notice else ''
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UT / Review</title><style>
    :root{{--ink:#172b2a;--muted:#647673;--line:#dbe4df;--paper:#f5f7f3;--green:#23695d;--lime:#d9edb4;--orange:#ba693d}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}header{{height:64px;background:#fff;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 max(24px,calc((100vw - 1180px)/2));position:sticky;top:0;z-index:2}}.brand{{font-weight:800;letter-spacing:.02em}}.brand span{{color:var(--green)}}nav{{display:flex;gap:24px}}a{{color:var(--green);text-decoration:none}}main{{max-width:1180px;margin:34px auto;padding:0 24px}}.panel,section{{margin-bottom:28px}}.panel{{background:#173a35;color:#fff;padding:36px;border-radius:18px;position:relative;overflow:hidden}}.panel:after{{content:"";position:absolute;width:260px;height:260px;border:1px solid #ffffff30;border-radius:50%;right:7%;top:-100px;box-shadow:0 0 0 28px #ffffff08,0 0 0 56px #ffffff08}}h1{{font-size:clamp(30px,4vw,48px);line-height:1.06;max-width:590px;margin:12px 0}}h2{{font-size:22px;margin:8px 0 16px}}p{{max-width:700px}}.muted{{color:var(--muted)}}.panel .muted{{color:#c0d2cb}}.eyebrow{{font-size:11px;font-weight:750;letter-spacing:.13em;color:#b7d78d}}button,.button{{background:#fff;border:1px solid var(--line);border-radius:9px;padding:10px 14px;font-weight:650;color:var(--ink);cursor:pointer}}button:hover{{border-color:var(--green)}}button.primary{{background:var(--lime);border-color:var(--lime);color:#193c34}}.panel form{{display:flex;align-items:center;gap:12px;position:relative;z-index:1;margin-top:24px}}.upload{{display:flex;flex-direction:column;gap:3px;background:#ffffff12;border:1px dashed #ffffff80;border-radius:10px;padding:11px 14px;min-width:280px;cursor:pointer}}.upload input{{max-width:320px;color:#fff}}.upload small{{color:#c0d2cb}}.panel h1,.panel p,.panel form,.panel .eyebrow{{position:relative;z-index:1}}.card{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:20px;margin:12px 0}}.source{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;padding:15px 0;border-bottom:1px solid var(--line)}}.hash{{font:12px ui-monospace,monospace;color:var(--muted);margin-top:4px}}.coverage{{display:grid;grid-template-columns:repeat(3,1fr) 2fr;gap:14px;align-items:center;padding:16px 0;border-bottom:1px solid var(--line)}}.metric{{font-size:26px;font-weight:750}}.metric small{{display:block;font-size:11px;color:var(--muted);font-weight:500}}.good{{color:var(--green)}}.warn{{color:var(--orange)}}select{{border:1px solid var(--line);border-radius:8px;padding:10px;background:white;max-width:100%}}.pair-import{{display:grid;grid-template-columns:auto minmax(150px,1fr);gap:12px;align-items:center;max-width:820px}}.pair-import button{{grid-column:1/-1;justify-self:start}}.coverage form{{display:flex;gap:8px;flex-wrap:wrap}}.tablewrap{{overflow:auto;max-height:65vh;background:#fff;border:1px solid var(--line);border-radius:12px}}table{{width:100%;border-collapse:collapse;min-width:1050px}}th,td{{text-align:left;padding:11px 12px;border-bottom:1px solid var(--line);font-size:13px}}th{{background:#eef3ed;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em}}td form{{display:flex;gap:5px}}td button{{padding:7px}}.notice{{background:#e4efcf;border-radius:9px;padding:12px 16px;margin-bottom:16px}}.warning{{border-left:4px solid var(--orange);padding:14px 16px;background:#fff5eb;border-radius:6px}}footer{{color:var(--muted);font-size:12px;padding:28px 0}}@media(max-width:800px){{header{{padding:0 16px}}nav{{gap:10px;font-size:12px}}main{{padding:0 16px}}.coverage{{grid-template-columns:repeat(3,1fr)}}.coverage form{{grid-column:1/-1}}.panel form{{flex-wrap:wrap}}}}
    </style></head><body>{nav}<main>{notice_html}{upload}<section class="card"><div class="eyebrow">YOUR SOURCES</div><h2>Project workbooks</h2>{source_html or '<p class="muted">No workbooks added yet.</p>'}</section><section class="card" id="coverage"><div class="eyebrow">02 / COVERAGE</div><h2>Detected sheets and extraction progress</h2>{coverage_html or '<p class="muted">Add a workbook to see its sheet inventory.</p>'}<p class="muted">Each selected sheet is imported in full, including all table sections, cells and linked drawing evidence. Only supported MIN measurements are normalized for evaluation; image-only readings need review.</p></section><details><summary>Individual reading review and corrections</summary><section class="card" id="readings"><div class="eyebrow">03 / REVIEW</div><h2>Readings and source evidence</h2><div style="display:flex;gap:8px;margin-bottom:14px"><a class="button" href="/export/readings.csv">Download CSV</a><a class="button" href="/export/review.html">Download HTML evidence</a></div><form id="batchreview" action="/bulk-review" method="post">{hidden("revision",service.workflow.revision())}<input name="reviewer" placeholder="Reviewer" required><div style="display:flex;gap:8px;margin:10px 0"><select name="status"><option value="reviewed">Mark selected reviewed</option><option value="excluded">Exclude selected</option><option value="needs_review">Return selected to review</option></select><input name="note" placeholder="Reason for this batch decision" required><button class="primary">Apply to selected</button></div></form><div class="rowtools"><input id="readingSearch" placeholder="Filter readings by workbook, sheet, date or location" oninput="filterReadings()"><button type="button" onclick="selectVisible()">Select visible</button><button type="button" onclick="document.querySelectorAll('input[name=observation_ids]').forEach(x=>x.checked=false)">Clear selection</button></div><div class="tablewrap"><table id="readingTable"><thead><tr><th>Select</th><th>Workbook</th><th>Sheet</th><th>Cell</th><th>Reading</th><th>Unit</th><th>Campaign</th><th>Date candidates</th><th>Location candidates</th><th>Status</th><th>Action</th></tr></thead><tbody>{reading_rows}</tbody></table></div></section></details><section class="card" id="engineering"><div class="eyebrow">04 / EVALUATION</div><h2>Engineering evaluation</h2><a class="button" href="/workflow">Compare inspections</a> <a class="button" href="/calculator">Standalone formula calculator</a><div class="warning"><strong>Draft calculations available — engineering approval is waived for app completion.</strong><br>Choose previous/current inspections, review matches and generate a report. Remaining-life inputs are optional. Draft outputs do not declare equipment fitness.</div></section><footer>Local project · Source files retained by SHA-256 · No external services</footer></main><script>function filterReadings(){{const q=document.getElementById('readingSearch').value.toLowerCase();document.querySelectorAll('#readingTable tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));}}function selectVisible(){{document.querySelectorAll('#readingTable tbody tr:not([hidden]) input[name=observation_ids]').forEach(x=>x.checked=true);}}</script></body></html>'''


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
            if path in {'/','/workspace'}:
                self._reply((Path(__file__).parent/'static'/'workspace.html').read_text());return
            if path.startswith('/assets/'):
                name=path.removeprefix('/assets/')
                if name not in {'workspace.css','workspace.js'}:self._reply('Not found',404,'text/plain');return
                self._reply((Path(__file__).parent/'static'/name).read_bytes(),200,'text/css' if name.endswith('.css') else 'text/javascript');return
            if path=='/api/workspace':
                from evaluator.workspace import Workspace
                q=parse_qs(urlsplit(self.path).query)
                try:self._reply(json.dumps(Workspace(service).state(q.get('comparison',[None])[0],q.get('scenario',[None])[0])),200,'application/json')
                except (ValueError,KeyError) as exc:self._reply(json.dumps({'error':str(exc)}),400,'application/json')
                return
            if path=='/workspace/form':
                from evaluator.form_export import export_form
                q=parse_qs(urlsplit(self.path).query)
                result=next((r for r in service.batch.results() if r['id']==q.get('result',[''])[0]),None)
                try:
                    if not result:raise ValueError('Save an evaluation before exporting the form')
                    content,suffix=export_form(service,result)
                    self._reply(content,200,'application/octet-stream',(('Content-Disposition','attachment; filename="UT-evaluation'+suffix+'"'),))
                except ValueError as exc:self._reply(str(exc),400,'text/plain')
                return
            if path=='/legacy':
                q=parse_qs(urlsplit(self.path).query); self._reply(page(service,q.get('notice',[''])[0])); return
            if path=='/workflow':
                q=parse_qs(urlsplit(self.path).query)
                self._reply(workflow_page(service,q.get('comparison',[None])[0],q.get('notice',[''])[0],q.get('report',[None])[0])); return
            if path=='/workflow/single':
                from evaluator.quick_ui import single_sheet_page
                q=parse_qs(urlsplit(self.path).query)
                self._reply(single_sheet_page(service,q.get('source',[''])[0],q.get('sheet',[''])[0])); return
            if path=='/workflow/batch':
                from evaluator.batch_ui import batch_page
                q=parse_qs(urlsplit(self.path).query)
                try:
                    self._reply(batch_page(service,q.get('comparison',[''])[0],q.get('notice',[''])[0],q.get('result',[''])[0],q.get('profile_sheet',[None])[0]))
                except (KeyError,ValueError):
                    self._reply('Comparison not found',404,'text/plain')
                return
            if path=='/advanced':
                q=parse_qs(urlsplit(self.path).query)
                self._reply(advanced_workflow_page(service,q.get('comparison',[None])[0],q.get('notice',[''])[0]));return
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
            if path=='/reading':
                q=parse_qs(urlsplit(self.path).query); row=next((r for r in service.readings() if r['observation_id']==q.get('id',[''])[0]),None)
                if not row: self._reply('Reading not found',404,'text/plain'); return
                loc=json.loads(row.get('effective_location',row['location_candidates'])); loc=loc+['']*(4-len(loc))
                content='<h1>Inspect / correct reading</h1><p>'+E(row['file_name'])+' · '+E(row['sheet_name'])+'!'+E(row['cell'])+'</p><p>Original reading: '+E(row['raw_value'])+' '+E(row['raw_unit'])+' · original date candidates: '+E(row['date_candidates'])+'</p><form action="/workflow/correct" method="post">'+hidden('observation_id',row['observation_id'])+hidden('revision',service.workflow.revision())+field('value_mm','Corrected thickness · mm',row.get('effective_value',row['raw_value']),'number')+''.join(field(k,label,loc[i],required=i<3) for i,(k,label) in enumerate([('section','Section'),('joint','Joint / component'),('band','Band / CML'),('position','Physical position')]))+person()+'<button>Save correction overlay</button></form><p>The workbook and raw value remain unchanged. Correction is audited and can be undone.</p>'
                self._reply(shell('Reading evidence',content)); return
            if path=='/calculator':
                self._reply(standalone_calculator()); return
            if path=='/export/revision':
                name=parse_qs(urlsplit(self.path).query).get('name',[''])[0]
                if not re.fullmatch(r'revision-[0-9]{6,}-[a-f0-9]{8}\.zip',name): self._reply('Invalid export name',400,'text/plain'); return
                target=service.project_dir/'exports'/name
                if not target.is_file(): self._reply('Export not found',404,'text/plain'); return
                self._reply(target.read_bytes(),200,'application/zip',(('Content-Disposition','attachment; filename="'+name+'"'),)); return
            if path=='/export/readings.csv': self._reply(service.export_csv(),200,'text/csv; charset=utf-8',(('Content-Disposition','attachment; filename="readings.csv"'),)); return
            if path=='/export/review.html': self._reply(service.export_html(),200,'text/html; charset=utf-8',(('Content-Disposition','attachment; filename="review.html"'),)); return
            self._reply('Not found',404,'text/plain')
        def do_POST(self):
            try:
                expected_host=f'127.0.0.1:{self.server.server_port}'
                if self.headers.get('Host') not in {expected_host,f'localhost:{self.server.server_port}'}: raise ValueError('This app only accepts local requests')
                origin=self.headers.get('Origin')
                if origin and origin not in {'http://'+expected_host,f'http://localhost:{self.server.server_port}'}: raise ValueError('Cross-origin project changes are blocked')
                path=self.path.split('?',1)[0]
                if path.startswith('/api/workspace/'):
                    from evaluator.workspace_api import action
                    length=int(self.headers.get('Content-Length','0'))
                    if length<=0 or length>2_000_000:raise ValueError('Invalid workspace request size')
                    result=action(service,path.rsplit('/',1)[-1],json.loads(self.rfile.read(length)))
                    self._reply(json.dumps(result),200,'application/json');return
                if path.startswith('/workflow/') and path!='/workflow/restore':
                    length=int(self.headers.get('Content-Length','0'))
                    if length>2_000_000: raise ValueError('Action request too large')
                    form=parse_qs(self.rfile.read(length).decode())
                    get=lambda key,default='':form.get(key,[default])[0]
                    flow=service.workflow; cid=get('comparison_id')
                    if path=='/workflow/export':
                        target=flow.export_revision(); self._reply(target.read_bytes(),200,'application/zip',(('Content-Disposition','attachment; filename="'+target.name+'"'),)); return
                    if path=='/workflow/backup':
                        with _LOCK:
                            target=service.project_dir/('backup-'+str(flow.revision())+'.zip'); service.repository.backup(target)
                        self._reply(target.read_bytes(),200,'application/zip',(('Content-Disposition','attachment; filename="'+target.name+'"'),)); return
                    if path=='/workflow/quick-import':
                        from evaluator.quick_workflow import import_inspections
                        out=import_inspections(service,get('source_id'),get('previous_sheet'),get('current_sheet'),int(get('revision')))
                        if out['comparison']:
                            location='/workflow?'+urlencode({'comparison':out['comparison']['id'],'notice':'Both whole sheets imported. Review the matches and generate your report.'})
                        else: location='/?'+urlencode({'notice':'Both whole sheets were imported and preserved. A sheet has no supported measurement table; open its whole-sheet evidence below.'})
                        self._reply('',303,'text/plain',(('Location',location),));return
                    if path=='/workflow/quick-import-single':
                        from evaluator.quick_workflow import import_single_dated_sheet
                        import_single_dated_sheet(service,get('source_id'),get('sheet_name'),int(get('revision')))
                        location='/workflow/single?'+urlencode({'source':get('source_id'),'sheet':get('sheet_name')})
                        self._reply('',303,'text/plain',(('Location',location),));return
                    if path=='/workflow/quick-match-single':
                        from evaluator.quick_workflow import match_single_sheet
                        comp=match_single_sheet(service,get('source_id'),get('sheet_name'),get('previous_campaign'),get('current_campaign'),int(get('revision')))
                        location='/workflow?'+urlencode({'comparison':comp['id'],'notice':'Selected inspection dates matched. Review the readings and physical continuity below.'})
                        self._reply('',303,'text/plain',(('Location',location),));return
                    if path=='/workflow/batch-prepare':
                        service.batch.prepare(cid, int(get('revision')))
                        location='/workflow/batch?'+urlencode({'comparison':cid,'notice':'Source engineering records imported for review.'})
                        self._reply('',303,'text/plain',(('Location',location),));return
                    if path=='/workflow/batch-overrides':
                        keys=('required_thickness_mm','adopted_rate_mm_year','structural_minimum_mm','interval_fraction','interval_cap_years','selected_interval_years','forecast_years','forecast_factor','year_days','allowance_mm')
                        values={key:get(key) for key in keys if get(key)}
                        service.batch.apply_overrides(cid,int(get('revision')),form.get('group_ids',[]),[],values,get('profile_sheet') or None)
                        location='/workflow/batch?'+urlencode({'comparison':cid,'profile_sheet':get('profile_sheet'),'notice':'Grouped component inputs saved as revision '+str(flow.revision())+'.'})
                        self._reply('',303,'text/plain',(('Location',location),));return
                    if path=='/workflow/batch-assignment':
                        if get('confirm_assignment')!='yes':
                            raise ValueError('Confirm that the selected source record belongs to this physical component')
                        service.batch.apply_overrides(
                            cid, int(get('revision')), [], form.get('row_ids', []),
                            {'profile_id':get('profile_id')}, get('profile_sheet') or None,
                        )
                        location='/workflow/batch?'+urlencode({'comparison':cid,'profile_sheet':get('profile_sheet'),'notice':'Row source assignment saved as revision '+str(flow.revision())+'.'})
                        self._reply('',303,'text/plain',(('Location',location),));return
                    if path=='/workflow/batch-evaluate':
                        options={
                            'profile_sheet':get('profile_sheet'),
                            'confirm_records':get('confirm_records')=='yes',
                            'confirm_history':get('confirm_history')=='yes',
                            'confirm_rules':get('confirm_rules')=='yes',
                            'confirm_conflicts':get('confirm_conflicts')=='yes',
                            'basis':get('basis','provided'),
                            'year_days':get('year_days'),
                            'allow_increase':get('allow_increase')=='yes',
                        }
                        result=service.batch.evaluate(cid,int(get('revision')),options,get('preview_token'))
                        location='/workflow/batch?'+urlencode({'comparison':result['comparison_id'],'result':result['id'],'notice':'Draft component batch saved as revision '+str(flow.revision())+'.'})
                        self._reply('',303,'text/plain',(('Location',location),));return
                    if path=='/workflow/quick-match':
                        from evaluator.quick_workflow import match
                        out=match(service,json.loads(get('baseline')),json.loads(get('current')),int(get('revision')))
                        self._reply('',303,'text/plain',(('Location','/workflow?'+urlencode({'comparison':out['id']})),));return
                    if path in {'/workflow/quick-report','/workflow/quick-export'}:
                        if path=='/workflow/quick-report':
                            from evaluator.quick_workflow import generate
                            out=generate(service,cid,int(get('revision')),confirm=get('confirm')=='yes',previous_date=get('previous_date'),current_date=get('current_date'),include_life=get('include_life')=='yes',required_thickness=get('required_thickness'),adopted_rate=get('adopted_rate'),profile_confirmed=get('profile_confirmed')=='yes')
                            cid=out['comparison']['id']
                            if out.get('needs_review'):
                                self._reply('',303,'text/plain',(('Location','/workflow?'+urlencode({'comparison':cid,'notice':'Matches changed. Review the refreshed preview, then generate your report.'})),));return
                        target=flow.export_revision(cid)
                        if path=='/workflow/quick-export':
                            self._reply(target.read_bytes(),200,'application/zip',(('Content-Disposition','attachment; filename="'+target.name+'"'),));return
                        self._reply('',303,'text/plain',(('Location','/workflow?'+urlencode({'comparison':cid,'report':target.name,'notice':'Report ready'})),));return
                    if path=='/workflow/undo': flow.undo(int(get('revision')),get('reviewer'),get('reason'))
                    elif path=='/workflow/compare':
                        if int(get('revision'))!=flow.revision(): raise ValueError('Project changed; refresh comparison form')
                        old=json.loads(get('baseline')); new=json.loads(get('current'))
                        out=flow.compare(*old,*new,get('asset'),get('lifecycle'),get('continuity')=='yes',get('reviewer'),get('reason'),expected_revision=int(get('revision'))); cid=out['id']
                    elif path=='/workflow/rebuild':
                        out=flow.rebuild(cid,int(get('revision')),get('reviewer'),get('reason')); cid=out['id']
                    elif path=='/workflow/campaign-date':
                        selection=json.loads(get('campaign_selection')); service.resolve_campaign_date(*selection,get('chosen_date'),get('reviewer'),get('reason'),_expected_revision=int(get('revision')))
                    elif path=='/workflow/proposal': flow.apply_proposal(get('proposal_id'),int(get('revision')),get('reviewer'),get('reason'))
                    elif path=='/workflow/pair': flow.pair(cid,get('previous_id'),get('current_id'),get('continuity')=='yes',get('reviewer'),get('reason'),int(get('revision')))
                    elif path=='/workflow/correct':
                        service.correct_reading(get('observation_id'),get('value_mm'),get('section'),get('joint'),get('band'),get('position'),get('reviewer'),get('reason'),_expected_revision=int(get('revision')))
                    elif path=='/workflow/evaluate':
                        if int(get('revision'))!=flow.revision(): raise ValueError('Project changed; refresh calculation inputs')
                        flow.calculate(cid,get('required_thickness'),get('adopted_rate'),get('year_days'),get('basis'),get('reviewer'),get('reason'),get('scope')=='yes',form.get('pair_ids',[]),get('design_id') or None,get('structural_minimum'),expected_revision=int(get('revision')))
                    elif path=='/workflow/design':
                        if int(get('revision'))!=flow.revision(): raise ValueError('Project changed; refresh design inputs')
                        rule=get('rule'); inputs={k:get(k) for k in REQUIRED.get(rule,())}
                        flow.design(cid,rule,inputs,get('reviewer'),get('reason'),get('applicability')=='yes',expected_revision=int(get('revision')))
                    else: raise ValueError('Unknown workflow action')
                    self._reply('',303,'text/plain',(('Location','/workflow?'+urlencode({'comparison':cid,'notice':'Action saved as revision '+str(flow.revision())})),)); return
                if path in {'/upload','/workspace/upload','/workflow/restore'}:
                    ctype=self.headers.get('Content-Type',''); length=int(self.headers.get('Content-Length','0'))
                    if length<=0 or length>110_000_000: raise ValueError('Upload must be under 100 MB.')
                    content=self.rfile.read(length)
                    msg=BytesParser(policy=policy.default).parsebytes((f'MIME-Version: 1.0\r\nContent-Type: {ctype}\r\n\r\n').encode()+content)
                    part=next((p for p in msg.iter_parts() if p.get_filename()),None)
                    if part is None: raise ValueError('Choose a workbook to upload.')
                    filename=Path(part.get_filename()).name
                    if path=='/workflow/restore':
                        from evaluator.storage.repository import Repository
                        destination=service.project_dir.parent/('UT-restored-'+os.urandom(4).hex())
                        with tempfile.NamedTemporaryFile(suffix='.zip',delete=False) as backup:
                            backup.write(part.get_payload(decode=True)); backup_path=Path(backup.name)
                        try: Repository.restore_backup(backup_path,destination)
                        finally: backup_path.unlink(missing_ok=True)
                        self._reply(shell('Backup restored','<h1>Restored project</h1><p>'+E(destination)+'</p><p>Start the app with this folder selected using the launcher command:</p><code>python -m evaluator --project &quot;'+E(destination)+'&quot;</code><p><a href="/workflow">Back</a></p>')); return
                    if Path(filename).suffix.lower() not in {'.xlsx','.xlsm'}: raise ValueError('Only .xlsx and .xlsm workbooks are supported.')
                    temp=service.project_dir/'incoming'; temp.mkdir(exist_ok=True)
                    with tempfile.NamedTemporaryFile(prefix='upload-',suffix=Path(filename).suffix.lower(),dir=temp,delete=False) as stream:
                        stream.write(part.get_payload(decode=True)); staged=Path(stream.name)
                    try:
                        record=service.add_source(staged,filename); service.inspect(record.sha256)
                    finally: staged.unlink(missing_ok=True)
                    if path=='/workspace/upload':
                        from evaluator.workspace import Workspace
                        result=Workspace(service).auto_open(record.sha256,service.workflow.revision())
                        self._reply(json.dumps(result),200,'application/json');return
                    self._reply('',303,'text/plain',(('Location','/?'+urlencode({'notice':'Workbook added. Choose previous and current sheets below.'})+'#import-'+record.sha256),));return
                elif path=='/calculate':
                    form=parse_qs(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode())
                    result=evaluate(form['rule'][0],{k:form.get(k,[''])[0] for k in REQUIRED.get(form['rule'][0],())})
                    self._reply('<h1>Draft calculation result</h1><pre>'+html.escape(json.dumps(result,indent=2))+'</pre><a href="/calculator">Another calculation</a> · <a href="/">Project</a>')
                elif path=='/inspect':
                    form=parse_qs(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode()); service.inspect(form['source_id'][0]); self._redirect('Inventory refreshed.')
                elif path=='/extract':
                    form=parse_qs(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode()); out=service.extract(form['source_id'][0],form['sheet_name'][0],_expected_revision=int(form['revision'][0])); self._redirect(f"Imported whole sheet: {out['cell_count']} cells and {out['imported']} supported measurement candidates.")
                elif path=='/review':
                    form=parse_qs(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode()); service.mark_reviewed(form['observation_id'][0],form['status'][0]); self._redirect('Review status saved.')
                elif path=='/bulk-review':
                    form=parse_qs(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode()); n=service.bulk_review(form.get('observation_ids',[]),form['status'][0],form.get('note',[''])[0],form.get('reviewer',['local reviewer'])[0],_expected_revision=int(form['revision'][0])); self._redirect(f'Updated {n} selected readings.')
                elif path=='/resolve-date':
                    form=parse_qs(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode()); service.resolve_sheet_date(form['source_id'][0],form['sheet_name'][0],form['chosen_date'][0],form['reviewer'][0],form['justification'][0],_expected_revision=int(form['revision'][0])); self._redirect('Sheet date applied to extracted readings and recorded in the audit log.')
                elif path=='/delete-source':
                    form=parse_qs(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode()); service.delete_source(form['source_id'][0],_expected_revision=int(form['revision'][0])); self._redirect('Workbook and its project data deleted.')
                else:self._reply('Not found',404,'text/plain')
            except Exception as exc:
                if self.path.startswith(('/api/workspace/','/workspace/upload')):
                    self._reply(json.dumps({'error':str(exc)}),400,'application/json');return
                self._reply(shell('Action needs attention','<h1>Action could not be applied</h1><p class="warn">'+E(str(exc))+'</p><p>Your last committed project state is retained.</p><a href="/workflow">Return to workflow</a> · <a href="/">Reports & readings</a>'),400)
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
