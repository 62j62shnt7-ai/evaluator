"""Application services shared by the offline web interface and CLI."""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import sqlite3
import shutil
from datetime import date
from pathlib import Path

from evaluator.importing.package_inventory import inventory
from evaluator.importing.whole_sheet import snapshot as snapshot_sheet
from evaluator.importing.regions import ExtractionResult
from evaluator.importing.separator import extract as extract_separator
from evaluator.importing.tlb import extract as extract_tlb
from evaluator.storage.repository import Repository
from evaluator.storage.assets import AssetStore
from evaluator.importing.normalize import observation_id
from evaluator.storage.database import connection
from evaluator.workflow import Workflow, tracked


def csv_safe(value):
    value='' if value is None else str(value)
    return "'"+value if (value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t','\r'))) else value


class ProjectService:
    def __init__(self, project_dir: Path):
        self.project_dir=Path(project_dir).resolve(); self.project_dir.mkdir(parents=True,exist_ok=True)
        self.repository=Repository(self.project_dir/'project.sqlite')
        self.assets=AssetStore(self.repository.path)
        with connection(self.repository.path) as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS workbooks (source_id TEXT PRIMARY KEY, file_name TEXT NOT NULL, inventory_json TEXT, warning TEXT NOT NULL DEFAULT '');
              CREATE TABLE IF NOT EXISTS workbook_sheets (source_id TEXT NOT NULL, sheet_name TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'unresolved', reason TEXT NOT NULL DEFAULT 'Not yet extracted', PRIMARY KEY(source_id,sheet_name));
              CREATE TABLE IF NOT EXISTS imported_sheets (source_id TEXT NOT NULL, sheet_name TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(source_id,sheet_name));
              CREATE TABLE IF NOT EXISTS readings (observation_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, sheet_name TEXT NOT NULL, cell TEXT NOT NULL, raw_value TEXT NOT NULL, raw_unit TEXT, campaign TEXT NOT NULL, inspection_date TEXT, date_candidates TEXT NOT NULL, location_candidates TEXT NOT NULL, review_status TEXT NOT NULL DEFAULT 'needs_review');
              CREATE TABLE IF NOT EXISTS audit_log (event_id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT, event TEXT NOT NULL, details TEXT NOT NULL, created_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
            """)
        self.workflow = Workflow(self)
        from evaluator.batch import BatchService
        self.batch = BatchService(self)

    @tracked('Add workbook', undoable=False, inputs=False)
    def add_source(self, path: Path, file_name: str | None = None):
        record=self.repository.register_source(Path(path))
        name=file_name or record.original_name
        with connection(self.repository.path) as db:
            db.execute("INSERT OR IGNORE INTO workbooks(source_id,file_name) VALUES (?,?)",(record.sha256,name))
            db.execute("INSERT INTO audit_log(source_id,event,details) VALUES (?,?,?)",(record.sha256,'source_added',json.dumps({'sha256':record.sha256,'file_name':name})))
        return record

    def sources(self):
        with connection(self.repository.path) as db:
            rows=db.execute("SELECT source_id,file_name,inventory_json,warning FROM workbooks ORDER BY file_name").fetchall()
        result=[]
        for a,b,c,d in rows:
            data=json.loads(c) if c else {}
            result.append({'source_id':a,'file_name':b,'inspected':bool(c),'warning':d,'sheet_count':len(data.get('sheets',[])),'object_count':len(data.get('objects',[])),'formula_count':len(data.get('formulas',[])),'external_count':len(data.get('links',[]))})
        return result

    def inspect(self, source_id: str):
        record=next((r for r in self.repository.sources() if r.sha256==source_id),None)
        if record is None: raise KeyError('unknown source')
        result=inventory(record.stored_path).to_dict()
        with connection(self.repository.path) as db:
            db.execute("UPDATE workbooks SET inventory_json=? WHERE source_id=?",(json.dumps(result,ensure_ascii=False),source_id))
            for sheet in result['sheets']:
                db.execute("INSERT OR IGNORE INTO workbook_sheets(source_id,sheet_name) VALUES (?,?)",(source_id,sheet['name']))
            db.execute("INSERT INTO audit_log(source_id,event,details) VALUES (?,?,?)",(source_id,'inventory_created',json.dumps({'sheets':len(result['sheets']),'objects':len(result['objects']),'formulas':len(result['formulas'])})))
        return result

    def inventory_for(self, source_id):
        with connection(self.repository.path) as db:
            row=db.execute("SELECT inventory_json FROM workbooks WHERE source_id=?",(source_id,)).fetchone()
        if not row or not row[0]: return None
        return json.loads(row[0])

    @tracked('Extract report sheet')
    def extract(self, source_id: str, sheet_name: str):
        record=next((r for r in self.repository.sources() if r.sha256==source_id),None)
        if record is None: raise KeyError('unknown source')
        with connection(self.repository.path) as db:
            row=db.execute("SELECT file_name FROM workbooks WHERE source_id=?",(source_id,)).fetchone()
        if not row: raise KeyError('unknown source')
        whole_sheet=snapshot_sheet(record.stored_path,sheet_name)
        from evaluator.importing.detect import extract as detect_layout
        result=detect_layout(record.stored_path,sheet_name,source_hash=source_id)
        items=[]
        for draft in result.observations:
            oid=observation_id(result.source_hash,draft.source.sheet,draft.source.cell,draft.campaign_label)
            items.append((oid,source_id,draft.source.sheet,draft.source.cell,draft.raw_value,draft.raw_unit,draft.campaign_label,draft.inspection_date,json.dumps(draft.date_candidates),json.dumps(draft.location_candidates)))
        reason='; '.join(result.unresolved)
        status='imported' if items else 'unresolved'
        if reason and status=='imported': status='needs_review'
        with connection(self.repository.path) as db:
            override=db.execute('SELECT chosen_date FROM sheet_dates WHERE source_id=? AND sheet_name=?',(source_id,sheet_name)).fetchone()
            campaign_dates={r['campaign']:r['chosen_date'] for r in db.execute('SELECT campaign,chosen_date FROM campaign_dates WHERE source_id=? AND sheet_name=?',(source_id,sheet_name))}
            previous={r['observation_id']:dict(r) for r in db.execute('SELECT * FROM readings WHERE source_id=? AND sheet_name=?',(source_id,sheet_name))}
            if override:
                items=[tuple(list(item[:7])+[override[0]]+list(item[8:])) for item in items]
                reason='; '.join(part for part in reason.split('; ') if 'date' not in part.lower())
                status='needs_review' if reason else ('imported' if items else 'unresolved')
            items=[tuple(list(item[:7])+[campaign_dates.get(item[6],item[7])]+list(item[8:])) for item in items]
            db.execute("INSERT INTO imported_sheets(source_id,sheet_name,payload) VALUES (?,?,?) ON CONFLICT(source_id,sheet_name) DO UPDATE SET payload=excluded.payload",(source_id,sheet_name,json.dumps(whole_sheet,ensure_ascii=False)))
            db.execute("DELETE FROM readings WHERE source_id=? AND sheet_name=?",(source_id,sheet_name))
            db.executemany("INSERT INTO readings(observation_id,source_id,sheet_name,cell,raw_value,raw_unit,campaign,inspection_date,date_candidates,location_candidates) VALUES (?,?,?,?,?,?,?,?,?,?)",items)
            for item in items:
                old=previous.get(item[0])
                if old and old['raw_value']==item[4] and old['inspection_date']==item[7]:
                    db.execute('UPDATE readings SET review_status=? WHERE observation_id=?',(old['review_status'],item[0]))
            db.execute("INSERT INTO workbook_sheets(source_id,sheet_name,state,reason) VALUES (?,?,?,?) ON CONFLICT(source_id,sheet_name) DO UPDATE SET state=excluded.state,reason=excluded.reason",(source_id,sheet_name,status,reason))
            db.execute("INSERT INTO audit_log(source_id,event,details) VALUES (?,?,?)",(source_id,'sheet_extracted',json.dumps({'sheet':sheet_name,'readings':len(items),'warnings':result.unresolved})))
        return {'imported':len(items),'unresolved':len(result.unresolved)+(1 if not items else 0),'warnings':result.unresolved,'date_conflict':result.date_conflict,'whole_sheet_imported':True,'cell_count':len(whole_sheet['cells'])}

    def imported_sheet(self, source_id, sheet_name):
        """Return full JSON evidence index, or None before whole-sheet import."""
        with connection(self.repository.path) as db:
            row=db.execute('SELECT payload FROM imported_sheets WHERE source_id=? AND sheet_name=?',(source_id,sheet_name)).fetchone()
        return json.loads(row[0]) if row else None

    def imported_sheets(self):
        """Compact summaries; use imported_sheet for cells and package evidence."""
        with connection(self.repository.path) as db:
            rows=db.execute('SELECT source_id,sheet_name,payload FROM imported_sheets ORDER BY source_id,sheet_name').fetchall()
        result=[]
        for source_id,sheet_name,payload in rows:
            data=json.loads(payload)
            result.append({'source_id':source_id,'sheet_name':sheet_name,'schema_version':data['schema_version'],
                'worksheet_part':data['worksheet_part'],'cell_count':len(data['cells']),
                'section_count':len(data['sections']),'related_part_count':len(data['related_parts'])})
        return result

    def coverage(self, source_id):
        with connection(self.repository.path) as db:
            rows=db.execute("SELECT state,COUNT(*) FROM workbook_sheets WHERE source_id=? GROUP BY state",(source_id,)).fetchall()
        count=dict(rows)
        return {'detected':sum(count.values()),'imported':count.get('imported',0)+count.get('needs_review',0),'excluded':count.get('excluded',0),'unresolved':count.get('unresolved',0),'needs_review':count.get('needs_review',0)}

    def sheet_statuses(self, source_id):
        with connection(self.repository.path) as db:
            rows=db.execute("SELECT sheet_name,state,reason FROM workbook_sheets WHERE source_id=? ORDER BY sheet_name",(source_id,)).fetchall()
        return [{'sheet':a,'status':b,'reason':c} for a,b,c in rows]

    def readings(self):
        with connection(self.repository.path) as db:
            db.row_factory=sqlite3.Row
            rows=[dict(x) for x in db.execute("SELECT r.*,w.file_name FROM readings r JOIN workbooks w USING(source_id) ORDER BY w.file_name,r.sheet_name,r.cell")]
            overrides={r['observation_id']:dict(r) for r in db.execute('SELECT * FROM reading_overrides')}
            for row in rows:
                override=overrides.get(row['observation_id'])
                row['effective_value']=override['value_mm'] if override else row['raw_value']
                row['effective_location']=override['location_json'] if override else row['location_candidates']
                row['corrected']=bool(override)
            return rows

    def mark_reviewed(self, observation_id_value, status, note=''):
        return self.bulk_review([observation_id_value], status, note)

    @tracked('Correct reading overlay')
    def correct_reading(self, observation_id_value, value_mm, section, joint, band, position, reviewer, reason):
        from evaluator.workflow import _number
        value=_number(value_mm,'Corrected thickness')
        if not reviewer.strip() or not reason.strip(): raise ValueError('Reviewer and correction basis are required')
        with connection(self.repository.path) as db:
            old=db.execute('SELECT * FROM readings WHERE observation_id=?',(observation_id_value,)).fetchone()
            if not old or old['raw_unit']!='mm': raise ValueError('Reading not found or units are unsupported')
            location=[section.strip(),joint.strip(),band.strip()]
            if position.strip(): location.append(position.strip())
            if not all(location[:3]): raise ValueError('Section, joint and band are required')
            db.execute('INSERT OR REPLACE INTO reading_overrides VALUES(?,?,?,?,?)',(observation_id_value,str(value),json.dumps(location),reviewer,reason))
            db.execute('UPDATE readings SET review_status=? WHERE observation_id=?',('needs_review',observation_id_value))
            db.execute('INSERT INTO audit_log(source_id,event,details) VALUES(?,?,?)',(old['source_id'],'reading_corrected',json.dumps({'observation_id':observation_id_value,'raw_value':old['raw_value'],'value_mm':str(value),'reviewer':reviewer,'reason':reason})))

    @tracked('Batch reading review')
    def bulk_review(self, observation_ids, status, note='', reviewer='local reviewer'):
        if status not in {'reviewed','excluded','needs_review'}: raise ValueError('invalid review status')
        if not note.strip() or not reviewer.strip(): raise ValueError('Reviewer and batch decision reason are required')
        ids=list(dict.fromkeys(observation_ids))
        if not ids: return 0
        with connection(self.repository.path) as db:
            db.execute('BEGIN IMMEDIATE') if not db.in_transaction else None
            marks=','.join('?' for _ in ids)
            rows=db.execute(f"SELECT observation_id,source_id FROM readings WHERE observation_id IN ({marks})",ids).fetchall()
            if len(rows)!=len(ids): raise KeyError('one or more observations are unknown')
            db.executemany("UPDATE readings SET review_status=? WHERE observation_id=?",[(status,oid) for oid,_ in rows])
            grouped={}
            for oid,source_id in rows: grouped.setdefault(source_id,[]).append(oid)
            db.executemany("INSERT INTO audit_log(source_id,event,details) VALUES (?,?,?)",[(source,'batch_reviewed',json.dumps({'observation_ids':obs,'status':status,'note':note,'reviewer':reviewer})) for source,obs in grouped.items()])
        return len(rows)

    @tracked('Resolve sheet inspection date')
    def resolve_sheet_date(self, source_id, sheet_name, chosen_date, reviewer, justification):
        chosen=date.fromisoformat(chosen_date).isoformat()
        if not reviewer.strip() or not justification.strip(): raise ValueError('reviewer and justification are required')
        with connection(self.repository.path) as db:
            db.execute('BEGIN IMMEDIATE') if not db.in_transaction else None
            row=db.execute("SELECT COUNT(*) FROM readings WHERE source_id=? AND sheet_name=?",(source_id,sheet_name)).fetchone()
            if not row or row[0]==0: raise ValueError('extract this sheet before resolving its date')
            db.execute('DELETE FROM campaign_dates WHERE source_id=? AND sheet_name=?',(source_id,sheet_name))
            db.execute('INSERT INTO sheet_dates VALUES(?,?,?,?,?) ON CONFLICT(source_id,sheet_name) DO UPDATE SET chosen_date=excluded.chosen_date,reviewer=excluded.reviewer,reason=excluded.reason',(source_id,sheet_name,chosen,reviewer,justification))
            db.execute("UPDATE readings SET inspection_date=? WHERE source_id=? AND sheet_name=?",(chosen,source_id,sheet_name))
            current=db.execute("SELECT reason FROM workbook_sheets WHERE source_id=? AND sheet_name=?",(source_id,sheet_name)).fetchone()
            remaining=[part for part in (current[0].split('; ') if current and current[0] else []) if 'date' not in part.lower()]
            new_reason='; '.join(remaining)
            new_state='needs_review' if new_reason else 'imported'
            db.execute("UPDATE workbook_sheets SET state=?,reason=? WHERE source_id=? AND sheet_name=?",(new_state,new_reason,source_id,sheet_name))
            db.execute("INSERT INTO audit_log(source_id,event,details) VALUES (?,?,?)",(source_id,'sheet_date_resolved',json.dumps({'sheet':sheet_name,'chosen_date':chosen,'reviewer':reviewer.strip(),'justification':justification.strip()})))

    @tracked('Resolve campaign inspection date')
    def resolve_campaign_date(self, source_id, sheet_name, campaign, chosen_date, reviewer, justification):
        chosen=date.fromisoformat(chosen_date).isoformat()
        if not reviewer.strip() or not justification.strip(): raise ValueError('Reviewer and date basis are required')
        with connection(self.repository.path) as db:
            count=db.execute('SELECT COUNT(*) FROM readings WHERE source_id=? AND sheet_name=? AND campaign=?',(source_id,sheet_name,campaign)).fetchone()[0]
            if not count: raise ValueError('Selected campaign has no extracted readings')
            db.execute('INSERT OR REPLACE INTO campaign_dates VALUES(?,?,?,?,?,?)',(source_id,sheet_name,campaign,chosen,reviewer,justification))
            db.execute('UPDATE readings SET inspection_date=? WHERE source_id=? AND sheet_name=? AND campaign=?',(chosen,source_id,sheet_name,campaign))
            db.execute('INSERT INTO audit_log(source_id,event,details) VALUES(?,?,?)',(source_id,'campaign_date_resolved',json.dumps({'sheet':sheet_name,'campaign':campaign,'date':chosen,'reviewer':reviewer,'basis':justification})))

    @tracked('Delete workbook', undoable=False)
    def delete_source(self, source_id):
        record=next((r for r in self.repository.sources() if r.sha256==source_id),None)
        if record is None: raise KeyError('unknown source')
        custody=record.stored_path.parent
        if not record.stored_path.resolve().is_relative_to((self.project_dir/'sources').resolve()) or custody.name!=source_id or custody.is_symlink():
            raise ValueError('Invalid source custody path; no files were deleted')
        with connection(self.repository.path) as db:
            db.execute('BEGIN IMMEDIATE') if not db.in_transaction else None
            db.execute('DELETE FROM reading_overrides WHERE observation_id IN (SELECT observation_id FROM readings WHERE source_id=?)',(source_id,))
            for table in ('readings','imported_sheets','workbook_sheets','workbooks','audit_log','sheet_dates','campaign_dates','wf_profiles','wf_profile_imports','wf_campaign_sets','wf_match_identity'):
                db.execute(f"DELETE FROM {table} WHERE source_id=?",(source_id,))
            dependent_ids={r['id'] for r in db.execute('SELECT id,payload FROM wf_comparisons') if source_id in r['payload']}
            for table in ('wf_comparisons','wf_evaluations','wf_designs','wf_batches'):
                for record_row in db.execute(f'SELECT id,payload FROM {table}').fetchall():
                    if source_id in record_row['payload'] or json.loads(record_row['payload']).get('comparison_id') in dependent_ids:
                        db.execute(f'DELETE FROM {table} WHERE id=?',(record_row['id'],))
            for cid in dependent_ids:db.execute('DELETE FROM wf_batch_settings WHERE comparison_id=?',(cid,))
            db.execute('DELETE FROM wf_proposals')
            db.execute('UPDATE wf_actions SET before_json=NULL')
            db.execute('DELETE FROM wf_sheet_blobs')
            db.execute("DELETE FROM sources WHERE sha256=?",(source_id,))
        shutil.rmtree(custody)
        try: custody.parent.rmdir()
        except OSError: pass

    def export_csv(self):
        output=io.StringIO(newline=''); writer=csv.writer(output)
        writer.writerow(['project_revision','source_file','source_sha256','sheet','cell','raw_value','unit','campaign','inspection_date','date_candidates','location_candidates','effective_value','effective_location','review_status'])
        for row in self.readings():
            writer.writerow([self.workflow.revision()]+[csv_safe(row[k]) for k in ('file_name','source_id','sheet_name','cell','raw_value','raw_unit','campaign','inspection_date','date_candidates','location_candidates','effective_value','effective_location','review_status')])
        return output.getvalue()

    def export_html(self):
        records=self.readings()
        body=''.join('<tr>'+''.join(f'<td>{html.escape(str(row[k] or ""))}</td>' for k in ('file_name','source_id','sheet_name','cell','raw_value','raw_unit','campaign','inspection_date','review_status'))+'</tr>' for row in records)
        return '<!doctype html><meta charset="utf-8"><title>UT review export</title><h1>UT review export</h1><p>Draft extraction and review evidence. Integrated calculations are available in the revision export.</p><table><thead><tr><th>Source</th><th>SHA-256</th><th>Sheet</th><th>Cell</th><th>Reading</th><th>Unit</th><th>Campaign</th><th>Date</th><th>Review</th></tr></thead><tbody>'+body+'</tbody></table>'
