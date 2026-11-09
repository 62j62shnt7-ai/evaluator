"""Revisioned comparison, review decisions, draft evaluations and portable exports."""
from evaluator.inspection_time import elapsed_days
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps
import inspect
from pathlib import Path
import csv
import hashlib
import html
import io
import json
import os
import threading
import uuid
import zipfile

from evaluator.storage.database import connection

_LOCK = threading.RLock()
TABLES = ('readings', 'workbook_sheets', 'sheet_dates', 'wf_comparisons', 'wf_evaluations', 'wf_designs', 'reading_overrides', 'campaign_dates', 'imported_sheets', 'wf_profiles', 'wf_profile_imports', 'wf_batch_settings', 'wf_batches', 'wf_templates', 'wf_campaign_sets','wf_match_identity')

def tracked(label, *, inputs=True, undoable=True):
    def decorate(fn):
        @wraps(fn)
        def wrapped(self, *args, **kwargs):
            expected=kwargs.pop('_expected_revision',None)
            args_by_name=inspect.signature(fn).bind(self,*args,**kwargs).arguments
            actor=args_by_name.get('reviewer','local reviewer')
            reason=args_by_name.get('justification',args_by_name.get('reason',args_by_name.get('note','')))
            with self.workflow.change(label, inputs=inputs, undoable=undoable, expected=expected, actor=actor, reason=reason, affected_source=args_by_name.get('source_id')):
                return fn(self, *args, **kwargs)
        return wrapped
    return decorate

def _id(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc).isoformat()
def _number(value, name, *, positive=False):
    try: result = Decimal(str(value))
    except (InvalidOperation, ValueError): raise ValueError(f'{name} must be a number')
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError(f'{name} must be finite and {"positive" if positive else "nonnegative"}')
    return result

def _safe(value):
    text = '' if value is None else str(value)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t','\r')) else text

class Workflow:
    def __init__(self, service):
        self.service = service
        self.path = service.repository.path
        with connection(self.path) as db:
            for sql in (
                'CREATE TABLE IF NOT EXISTS wf_match_identity (observation_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, payload TEXT NOT NULL)',
                'CREATE TABLE IF NOT EXISTS wf_campaign_sets (id TEXT PRIMARY KEY, source_id TEXT NOT NULL, sheet TEXT NOT NULL, payload TEXT NOT NULL)',
                'CREATE TABLE IF NOT EXISTS wf_templates (id TEXT PRIMARY KEY, payload TEXT NOT NULL)',
                'CREATE TABLE IF NOT EXISTS wf_profiles (id TEXT PRIMARY KEY, source_id TEXT NOT NULL, sheet TEXT NOT NULL, payload TEXT NOT NULL)',
                'CREATE TABLE IF NOT EXISTS wf_profile_imports (source_id TEXT PRIMARY KEY, version TEXT NOT NULL)',
                'CREATE TABLE IF NOT EXISTS wf_batch_settings (comparison_id TEXT PRIMARY KEY, payload TEXT NOT NULL)',
                'CREATE TABLE IF NOT EXISTS wf_batches (id TEXT PRIMARY KEY, payload TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0)',
                'CREATE TABLE IF NOT EXISTS wf_meta (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL)',
                'INSERT OR IGNORE INTO wf_meta VALUES(1,0)',
                'CREATE TABLE IF NOT EXISTS wf_sheet_blobs (digest TEXT PRIMARY KEY, payload TEXT NOT NULL)',
                'CREATE TABLE IF NOT EXISTS wf_migrations (name TEXT PRIMARY KEY)',
                'CREATE TABLE IF NOT EXISTS wf_actions (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, label TEXT NOT NULL, before_json TEXT, actor TEXT NOT NULL, reason TEXT NOT NULL, created TEXT NOT NULL, undone INTEGER NOT NULL DEFAULT 0)',
                'CREATE TABLE IF NOT EXISTS wf_comparisons (id TEXT PRIMARY KEY, payload TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0)',
                'CREATE TABLE IF NOT EXISTS reading_overrides (observation_id TEXT PRIMARY KEY, value_mm TEXT NOT NULL, location_json TEXT NOT NULL, reviewer TEXT NOT NULL, reason TEXT NOT NULL)',
                'CREATE TABLE IF NOT EXISTS wf_designs (id TEXT PRIMARY KEY, payload TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0)',
                'CREATE TABLE IF NOT EXISTS wf_proposals (id TEXT PRIMARY KEY, payload TEXT NOT NULL)',
                'CREATE TABLE IF NOT EXISTS wf_evaluations (id TEXT PRIMARY KEY, payload TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0)',
                'CREATE TABLE IF NOT EXISTS campaign_dates (source_id TEXT NOT NULL, sheet_name TEXT NOT NULL, campaign TEXT NOT NULL, chosen_date TEXT NOT NULL, reviewer TEXT NOT NULL, reason TEXT NOT NULL, PRIMARY KEY(source_id,sheet_name,campaign))',
                'CREATE TABLE IF NOT EXISTS sheet_dates (source_id TEXT NOT NULL, sheet_name TEXT NOT NULL, chosen_date TEXT NOT NULL, reviewer TEXT NOT NULL, reason TEXT NOT NULL, PRIMARY KEY(source_id,sheet_name))',
            ): db.execute(sql)
            if not db.execute("SELECT 1 FROM wf_migrations WHERE name='legacy_sheet_dates'").fetchone():
                for event in db.execute("SELECT source_id,details FROM audit_log WHERE event='sheet_date_resolved' ORDER BY event_id DESC").fetchall():
                    try:
                        payload=json.loads(event['details']); chosen=date.fromisoformat(payload['chosen_date']).isoformat()
                        if db.execute('SELECT 1 FROM workbook_sheets WHERE source_id=? AND sheet_name=?',(event['source_id'],payload['sheet'])).fetchone():
                            db.execute('INSERT OR IGNORE INTO sheet_dates VALUES(?,?,?,?,?)',(event['source_id'],payload['sheet'],chosen,payload.get('reviewer','legacy reviewer'),payload.get('justification','Retained previous app date choice')))
                    except (ValueError,KeyError,TypeError): continue
                db.execute("INSERT INTO wf_migrations VALUES('legacy_sheet_dates')")

    def revision(self):
        with connection(self.path) as db: return db.execute('SELECT revision FROM wf_meta WHERE id=1').fetchone()[0]

    def _snapshot(self, db):
        snapshot={table: [dict(r) for r in db.execute(f'SELECT * FROM {table}')] for table in TABLES}
        for row in snapshot['imported_sheets']:
            payload=row['payload'];digest=hashlib.sha256(payload.encode()).hexdigest()
            db.execute('INSERT OR IGNORE INTO wf_sheet_blobs VALUES(?,?)',(digest,payload))
            row['payload']={'evidence_hash':digest}
        return snapshot

    @contextmanager
    def change(self, label, *, inputs=True, undoable=True, expected=None, actor='local reviewer', reason='', affected_source=None):
        with _LOCK, connection(self.path) as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
            rev = self.revision()
            if expected is not None and int(expected) != rev: raise ValueError('Project changed. Refresh the preview before applying this action.')
            before = json.dumps(self._snapshot(db)) if undoable else None
            if inputs and affected_source is not None:
                affected=[]
                for stored in db.execute('SELECT id,payload FROM wf_comparisons').fetchall():
                    comp=json.loads(stored['payload'])
                    if affected_source in {comp['baseline'][0],comp['current_selection'][0]}: affected.append(stored['id'])
                for cid in affected:
                    db.execute('UPDATE wf_comparisons SET stale=1 WHERE id=?',(cid,))
                    self._stale_comparison_results(db,cid)
            elif inputs:
                db.execute('UPDATE wf_comparisons SET stale=1')
                db.execute('UPDATE wf_evaluations SET stale=1')
                db.execute('UPDATE wf_designs SET stale=1')
                db.execute('UPDATE wf_batches SET stale=1')
            yield db
            db.execute('UPDATE wf_meta SET revision=? WHERE id=1', (rev+1,))
            db.execute('INSERT INTO wf_actions(id,revision,label,before_json,actor,reason,created) VALUES(?,?,?,?,?,?,?)',
                       (_id(),rev+1,label,before,actor,reason,_now()))

    def actions(self):
        with connection(self.path) as db:
            return [dict(r) for r in db.execute('SELECT id,revision,label,actor,reason,created,undone FROM wf_actions ORDER BY revision DESC LIMIT 50')]

    def undo(self, expected_revision, actor, reason):
        if not actor.strip() or not reason.strip(): raise ValueError('Reviewer and reason are required')
        with _LOCK, connection(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            rev=self.revision()
            if int(expected_revision)!=rev: raise ValueError('Project changed. Refresh before undo.')
            action=db.execute('SELECT * FROM wf_actions WHERE undone=0 ORDER BY revision DESC LIMIT 1').fetchone()
            if not action or not action['before_json']: raise ValueError('No reversible action remains. Adding or deleting a workbook creates an undo boundary.')
            snapshot=json.loads(action['before_json'])
            for table in TABLES:
                db.execute(f'DELETE FROM {table}')
                for record in snapshot.get(table,[]):
                    if table=='imported_sheets' and isinstance(record['payload'],dict):
                        blob=db.execute('SELECT payload FROM wf_sheet_blobs WHERE digest=?',(record['payload']['evidence_hash'],)).fetchone()
                        if not blob: raise ValueError('Undo sheet evidence is missing')
                        record['payload']=blob[0]
                    columns=list(record)
                    db.execute(f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})',tuple(record[c] for c in columns))
            db.execute('UPDATE wf_evaluations SET stale=1')
            db.execute('UPDATE wf_designs SET stale=1')
            db.execute('UPDATE wf_batches SET stale=1')
            db.execute('UPDATE wf_actions SET undone=1 WHERE id=?',(action['id'],))
            db.execute('UPDATE wf_meta SET revision=? WHERE id=1',(rev+1,))
            db.execute('INSERT INTO wf_actions(id,revision,label,before_json,actor,reason,created,undone) VALUES(?,?,?,?,?,?,?,1)',
                       (_id(),rev+1,'Undo: '+action['label'],None,actor,reason,_now()))

    @staticmethod
    def _stale_comparison_results(db, comparison_id):
        for table in ('wf_evaluations','wf_designs','wf_batches'):
            for row in db.execute(f'SELECT id,payload FROM {table}').fetchall():
                if json.loads(row['payload'])['comparison_id']==comparison_id:
                    db.execute(f'UPDATE {table} SET stale=1 WHERE id=?',(row['id'],))

    def campaigns(self):
        with connection(self.path) as db:
            return [dict(r) for r in db.execute('SELECT r.source_id,w.file_name,r.sheet_name,r.campaign,COUNT(*) AS count FROM readings r JOIN workbooks w USING(source_id) GROUP BY r.source_id,w.file_name,r.sheet_name,r.campaign ORDER BY w.file_name,r.sheet_name,r.campaign')]

    def _selection(self, source, sheet, campaign):
        if campaign.startswith('auto:'):
            with connection(self.path) as db:
                record=db.execute('SELECT payload FROM wf_campaign_sets WHERE id=? AND source_id=? AND sheet=?',(campaign,source,sheet)).fetchone()
            ids=set(json.loads(record[0])['observation_ids']) if record else set()
            return [r for r in self.service.readings() if r['observation_id'] in ids and r['source_id']==source and r['sheet_name']==sheet]
        return [r for r in self.service.readings() if r['source_id']==source and r['sheet_name']==sheet and r['campaign']==campaign]

    def match_identity(self,reading):
        from evaluator.importing.reading_identity import identity,component
        revision=self.revision()
        if getattr(self,'_identity_revision',None)!=revision:
            self._identity_sheets={}
            with connection(self.path) as db:self._identity_overrides={r['observation_id']:json.loads(r['payload']) for r in db.execute('SELECT observation_id,payload FROM wf_match_identity')}
            self._identity_revision=revision
        key=(reading['source_id'],reading['sheet_name'])
        if key not in self._identity_sheets:self._identity_sheets[key]=self.service.imported_sheet(*key) or {}
        result=identity(reading,self._identity_sheets[key]);overrides=self._identity_overrides.get(reading['observation_id'],{});result.update(overrides)
        if 'band' in overrides and 'component' not in overrides:result['component'],result['material']=component(result['band'])
        return result

    def _key(self,reading):
        from evaluator.importing.reading_identity import key
        return key(self.match_identity(reading))

    def compare(self, baseline_source, baseline_sheet, baseline_campaign, current_source, current_sheet,
                current_campaign, asset, lifecycle, continuity, actor, reason, expected_revision=None):
        if not asset.strip() or not lifecycle.strip() or not actor.strip() or not reason.strip():
            raise ValueError('Asset, lifecycle, reviewer and comparison basis are required')
        before=self._selection(baseline_source,baseline_sheet,baseline_campaign)
        after=self._selection(current_source,current_sheet,current_campaign)
        if not before or not after: raise ValueError('Both selected campaigns must contain extracted readings')
        if {r['observation_id'] for r in before} & {r['observation_id'] for r in after}: raise ValueError('Select two different campaigns')
        rows=self._match_records(before,after,continuity)
        comp={'id':_id(),'asset':asset.strip(),'lifecycle':lifecycle.strip(),'continuity':bool(continuity),'actor':actor,'reason':reason,'baseline':[baseline_source,baseline_sheet,baseline_campaign],'current_selection':[current_source,current_sheet,current_campaign],'rows':rows,'created':_now()}
        with self.change('Create history comparison',inputs=False,actor=actor,reason=reason,expected=expected_revision) as db:
            comp['revision']=self.revision()+1
            db.execute('INSERT INTO wf_comparisons VALUES(?,?,0)',(comp['id'],json.dumps(comp)))
        return comp

    def _match_records(self,before,after,continuity):
        by_old=defaultdict(list); by_new=defaultdict(list); rows=[]
        for label, records, target in [('previous_only',before,by_old),('current_only',after,by_new)]:
            for record in records:
                key=self._key(record)
                if key is None:
                    rows.append(self._row('invalid_location',record if label=='previous_only' else None,record if label=='current_only' else None,'Location evidence is incomplete'))
                else: target[key].append(record)
        for key in sorted(set(by_old)|set(by_new)):
            olds,news=by_old[key],by_new[key]
            if len(olds)>1 or len(news)>1:
                rows.append({'id':_id(),'kind':'ambiguous','previous_id':None,'current_id':None,'previous':None,'current':None,'previous_candidates':olds,'current_candidates':news,'basis':'Duplicate location labels; select a physical pair explicitly','accepted':False})
            elif olds and news:
                kind='matched' if continuity else 'lifecycle_mismatch'
                if olds[0]['review_status']=='excluded' or news[0]['review_status']=='excluded': kind='excluded'
                if olds[0]['raw_unit']!=news[0]['raw_unit']: kind='unit_mismatch'
                rows.append(self._row(kind,olds[0],news[0],'Normalized section, joint, band, size and position'))
            else:
                rows.append(self._row('previous_only' if olds else 'current_only',olds[0] if olds else None,news[0] if news else None,'Historical union retained'))
        return rows

    def rebuild(self, comparison_id, expected_revision, actor, reason):
        """Create a fresh comparison without rewriting its historical snapshot."""
        with _LOCK, connection(self.path) as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
            old=self.comparison(comparison_id)
            rebuilt=self.compare(*old['baseline'],*old['current_selection'],old['asset'],old['lifecycle'],
                                 old['continuity'],actor,reason,expected_revision=expected_revision)
            rebuilt['rebuilt_from']=comparison_id
            for key in ('baseline_per_location','baseline_label'):
                if key in old:rebuilt[key]=old[key]
            db.execute('UPDATE wf_comparisons SET payload=? WHERE id=?',(json.dumps(rebuilt),rebuilt['id']))
            return rebuilt

    def readiness(self, comparison_id):
        comp=self.comparison(comparison_id)
        status=dict(ready=0,unconfirmed=0,missing_dates=0,invalid_dates=0,unsupported_units=0,unmatched=0,stale=comp['stale'],steps=[],pair_issues={},ready_ids=[])
        for pair in comp['rows']:
            issues=[]
            status['pair_issues'][pair['id']]=issues
            if pair['kind']!='matched':
                issues.append(pair['basis'])
                status['unmatched']+=1
                continue
            old,new=pair['previous'],pair['current']
            if not pair['accepted']:
                status['unconfirmed']+=1; issues.append('Confirm this location match')
            dates_ok=False
            if not old['inspection_date'] or not new['inspection_date']:
                status['missing_dates']+=1; issues.append('Set missing inspection dates and rebuild')
            else:
                try: dates_ok=elapsed_days(old['inspection_date'],new['inspection_date'],'365')>0
                except ValueError: pass
                if not dates_ok:
                    status['invalid_dates']+=1; issues.append('Current date must be later than previous; correct dates and rebuild')
            units_ok=old['raw_unit']==new['raw_unit']=='mm'
            if not units_ok:
                status['unsupported_units']+=1; issues.append('Units must be mm')
            if comp['stale']: issues.append('Rebuild these pairs')
            if dates_ok and units_ok and pair['accepted'] and not comp['stale']:
                status['ready']+=1; status['ready_ids'].append(pair['id'])
        steps=status['steps']
        if comp['stale']: steps.append('Click Rebuild these pairs to use the latest readings and dates, then confirm the refreshed matches.')
        if status['unconfirmed']: steps.append(f"Confirm {status['unconfirmed']} exact location matches below to enable evaluation.")
        if status['missing_dates'] or status['invalid_dates']: steps.append('Set previous and current inspection dates below; current must be later. Save dates, then rebuild these pairs.')
        if status['unsupported_units']: steps.append('Correct unsupported units in the source; evaluation requires millimetres.')
        if status['unmatched']: steps.append(f"{status['unmatched']} unmatched or ambiguous locations need manual pairing or source correction; other ready pairs can proceed.")
        steps.append('Select confirmed pairs and enter input basis, reviewer and scope confirmation to save a historical comparison report. Required thickness and an adopted rate are needed for remaining life.')
        return status

    @staticmethod
    def _row(kind, old, new, basis):
        return {'id':_id(),'kind':kind,'previous_id':old['observation_id'] if old else None,'current_id':new['observation_id'] if new else None,'previous':old,'current':new,'basis':basis,'accepted':False}

    def comparisons(self):
        with connection(self.path) as db:
            return [dict(json.loads(r['payload']),stale=bool(r['stale'])) for r in db.execute('SELECT * FROM wf_comparisons ORDER BY rowid DESC')]

    def comparison(self, identifier):
        comp=next((c for c in self.comparisons() if c['id']==identifier),None)
        if comp is None: raise ValueError('Unknown comparison')
        return comp

    def proposals(self, comparison_id):
        with _LOCK, connection(self.path) as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
            comp=self.comparison(comparison_id)
            if comp['stale']: return []
            previews=[]
            eligible=[r['id'] for r in comp['rows'] if r['kind']=='matched' and not r['accepted']]
            if eligible:
                previews.append({'action':'accept_matches','eligible_ids':eligible,'title':'Confirm exact location matches','basis':'Same asset/lifecycle, exact physical location evidence and matching units. No thickness or rate is changed.'})
            grouped=defaultdict(list)
            for row in comp['rows']:
                if row['kind'] not in {'matched','excluded'}: grouped[row['kind']].append(row)
            for kind,rows in grouped.items():
                ids=set()
                for row in rows:
                    ids.update(x for x in (row['previous_id'],row['current_id']) if x)
                    for key in ('previous_candidates','current_candidates'):
                        ids.update(x['observation_id'] for x in row.get(key,[]))
                if ids: previews.append({'action':'flag_review','issue':kind,'eligible_ids':sorted(ids),'pair_ids':[r['id'] for r in rows],'title':'Record follow-up: '+kind.replace('_',' '),'basis':'Keep this issue group visible and mark existing source readings for review. Missing measurements are not created; calculation readiness is not approved.'})
            for preview in previews:
                included=set(preview.get('pair_ids',preview['eligible_ids']))
                preview_key=json.dumps([comparison_id,self.revision(),preview['action'],preview.get('issue',''),preview['eligible_ids']],sort_keys=True)
                preview.update(id=str(uuid.uuid5(uuid.NAMESPACE_URL,preview_key)),comparison_id=comparison_id,expected_revision=self.revision(),excluded=[{'id':r['id'],'reason':r['kind']} for r in comp['rows'] if r['id'] not in included])
                db.execute('INSERT OR REPLACE INTO wf_proposals VALUES(?,?)',(preview['id'],json.dumps(preview)))
            return previews

    def apply_proposal(self, proposal_id, expected_revision, actor, reason):
        if not actor.strip() or not reason.strip(): raise ValueError('Reviewer and reason are required')
        with _LOCK, connection(self.path) as db:
            if not db.in_transaction: db.execute('BEGIN IMMEDIATE')
            r=db.execute('SELECT payload FROM wf_proposals WHERE id=?',(proposal_id,)).fetchone()
            if not r: raise ValueError('Unknown proposal')
            proposal=json.loads(r[0])
            if int(expected_revision)!=proposal['expected_revision']: raise ValueError('Proposal revision mismatch')
            comp=self.comparison(proposal['comparison_id'])
            if comp['stale']: raise ValueError('Comparison is stale. Rebuild it from current readings.')
            follow_up=proposal['action']=='flag_review'
            with self.change('Record grouped follow-up' if follow_up else 'Accept grouped location matches',inputs=follow_up,expected=expected_revision,actor=actor,reason=reason) as tx:
                if follow_up:
                    for oid in proposal['eligible_ids']:
                        if not tx.execute('SELECT 1 FROM readings WHERE observation_id=?',(oid,)).fetchone(): raise ValueError('Proposal contains a missing reading')
                        tx.execute('UPDATE readings SET review_status=? WHERE observation_id=?',('needs_review',oid))
                    tx.execute('INSERT INTO audit_log(source_id,event,details) VALUES(?,?,?)',(None,'group_follow_up',json.dumps({'proposal':proposal,'reviewer':actor,'reason':reason})))
                else:
                    self._stale_comparison_results(tx,comp['id'])
                    for row in comp['rows']:
                        if row['id'] in proposal['eligible_ids']:
                            if row['kind']!='matched': raise ValueError('Proposal eligibility changed')
                            row['accepted']=True
                    tx.execute('UPDATE wf_comparisons SET payload=? WHERE id=?',(json.dumps(comp),comp['id']))

    def pair(self, comparison_id, previous_id, current_id, same_lifecycle, actor, reason, expected_revision):
        if not same_lifecycle or not actor.strip() or not reason.strip(): raise ValueError('Confirm lifecycle continuity and supply reviewer/evidence')
        with self.change('Confirm manual physical-location pair',inputs=False,expected=expected_revision,actor=actor,reason=reason) as db:
            comp=self.comparison(comparison_id)
            if comp['stale']: raise ValueError('Rebuild stale comparison first')
            self._stale_comparison_results(db,comparison_id)
            old=next((r for r in self._selection(*comp['baseline']) if r['observation_id']==previous_id),None)
            new=next((r for r in self._selection(*comp['current_selection']) if r['observation_id']==current_id),None)
            if not old or not new: raise ValueError('Pair must belong to the selected baseline/current campaigns')
            if old['review_status']=='excluded' or new['review_status']=='excluded': raise ValueError('Excluded readings cannot be paired')
            if old['raw_unit']!=new['raw_unit']: raise ValueError('Units differ')
            for row in comp['rows']:
                if row['accepted'] and (row['previous_id']==previous_id or row['current_id']==current_id): raise ValueError('A reading is already paired; undo or rebuild the comparison')
            remaining_old=[]; remaining_new=[]; keep=[]
            for row in comp['rows']:
                if row['kind']=='ambiguous' and (any(r['observation_id']==previous_id for r in row['previous_candidates']) or any(r['observation_id']==current_id for r in row['current_candidates'])):
                    remaining_old.extend(r for r in row['previous_candidates'] if r['observation_id']!=previous_id)
                    remaining_new.extend(r for r in row['current_candidates'] if r['observation_id']!=current_id)
                elif row['previous_id']==previous_id or row['current_id']==current_id:
                    if row['previous'] and row['previous_id']!=previous_id: remaining_old.append(row['previous'])
                    if row['current'] and row['current_id']!=current_id: remaining_new.append(row['current'])
                else: keep.append(row)
            keep.extend(self._row('previous_only',r,None,'Unpaired after manual resolution') for r in remaining_old)
            keep.extend(self._row('current_only',None,r,'Unpaired after manual resolution') for r in remaining_new)
            row=self._row('matched',old,new,'Manual physical-location confirmation: '+reason); row['accepted']=True
            comp['rows']=keep+[row]
            db.execute('UPDATE wf_comparisons SET payload=? WHERE id=?',(json.dumps(comp),comparison_id))

    def calculate(self, comparison_id, required_thickness, adopted_rate, year_days, basis, actor, reason, scope_confirmed, pair_ids=None, design_id=None, structural_minimum=None, expected_revision=None):
        if design_id:
            design=next((d for d in self.designs() if d['id']==design_id),None)
            if not design or design['stale'] or design['comparison_id']!=comparison_id or design['result']['value'] is None:
                raise ValueError('Select a current design result from this comparison')
            required=max(_number(design['result']['value'],'Pressure thickness',positive=True),_number(structural_minimum,'Structural minimum',positive=True))
        else:
            required=_number(required_thickness,'Required thickness',positive=True) if required_thickness not in ('',None) else None
        adopted=_number(adopted_rate,'Adopted rate',positive=True) if adopted_rate not in ('',None) else None
        year=_number(year_days,'Days per year',positive=True)
        if not all(str(s).strip() for s in (basis,actor,reason)) or not scope_confirmed: raise ValueError('Confirm component/rule scope and provide reviewer and engineering input basis')
        with self.change('Calculate integrated draft evaluation',inputs=False,actor=actor,reason=reason,expected=expected_revision) as db:
            comp=self.comparison(comparison_id)
            if comp['stale']: raise ValueError('Comparison inputs changed. Rebuild comparison and confirm matches first.')
            if pair_ids is not None and (not pair_ids or not set(pair_ids).issubset({r['id'] for r in comp['rows']})):
                raise ValueError('Select valid rows for this calculation profile')
            rows=[]
            for pair in comp['rows']:
                row={'pair_id':pair['id'],'kind':pair['kind'],'previous_id':pair['previous_id'],'current_id':pair['current_id'],'apparent_rate_mm_year':None,'adopted_rate_mm_year':None,'remaining_life_years':None,'elapsed_days':None,'issues':[]}
                if pair_ids is not None and pair['id'] not in pair_ids:
                    row['issues'].append('NOT_IN_EVALUATION_SCOPE'); rows.append(row); continue
                if required is None: row['issues'].append('REQUIRED_THICKNESS_MISSING')
                old,new=pair['previous'],pair['current']
                if not new: row['issues'].append('CURRENT_UNRESOLVED' if pair['kind']=='ambiguous' else 'CURRENT_MISSING')
                if pair['kind']!='matched' or not pair['accepted']: row['issues'].append('MATCH_NOT_CONFIRMED')
                if old and new and pair['kind']=='matched' and pair['accepted']:
                    if new['raw_unit']!='mm': row['issues'].append('UNIT_NOT_SUPPORTED')
                    elif not old['inspection_date'] or not new['inspection_date']: row['issues'].append('DATE_UNRESOLVED')
                    else:
                        days=elapsed_days(old['inspection_date'],new['inspection_date'],year)
                        row['elapsed_days']=float(days) if isinstance(days,Decimal) else days
                        if days<=0: row['issues'].append('NONPOSITIVE_ELAPSED_TIME')
                        else:
                            previous=_number(old.get('effective_value',old['raw_value']),'Previous thickness')
                            current=_number(new.get('effective_value',new['raw_value']),'Current thickness')
                            apparent=(previous-current)*year/Decimal(days)
                            row['apparent_rate_mm_year']=str(apparent)
                            if apparent<0: row['issues'].append('NEGATIVE_APPARENT_RATE')
                            elif apparent==0: row['issues'].append('ZERO_APPARENT_RATE')
                            if required is not None and current<=required: row['issues'].append('BELOW_OR_AT_REQUIRED_THICKNESS')
                            selected=adopted if adopted is not None else apparent if apparent>0 else None
                            row['rate_basis']='manual override' if adopted is not None else 'calculated historical CR'
                            if selected is not None:
                                row['adopted_rate_mm_year']=str(selected)
                                if required is not None and current>required: row['remaining_life_years']=str((current-required)/selected)
                            else: row['issues'].append('POSITIVE_RATE_OR_MANUAL_OVERRIDE_REQUIRED')
                rows.append(row)
            result={'id':_id(),'comparison_id':comparison_id,'input_revision':self.revision(),'status':'DRAFT / NOT VALIDATED','rule_version':'API510-570-candidate-0.1','source_reference':'API 510 11th edition §7.1–7.2 / API 570 5th edition §7.1–7.2','rate_formula':'(previous_mm-current_mm)*year_days/elapsed_days','remaining_life_formula':'(current_mm-required_mm)/selected_rate_mm_year','asset':comp['asset'],'lifecycle':comp['lifecycle'],'selected_pair_ids':pair_ids,'design_id':design_id,'structural_minimum_mm':structural_minimum,'required_thickness_mm':str(required) if required is not None else None,'adopted_rate_mm_year':str(adopted) if adopted else None,'year_days':str(year),'basis':basis,'reviewer':actor,'justification':reason,'rows':rows,'source_snapshot':comp,'created':_now()}
            db.execute('INSERT INTO wf_evaluations VALUES(?,?,0)',(result['id'],json.dumps(result)))
        return result

    def evaluations(self):
        with connection(self.path) as db:
            return [dict(json.loads(r['payload']),stale=bool(r['stale'])) for r in db.execute('SELECT * FROM wf_evaluations ORDER BY rowid DESC')]

    def designs(self):
        with connection(self.path) as db:
            return [dict(json.loads(r['payload']),stale=bool(r['stale'])) for r in db.execute('SELECT * FROM wf_designs ORDER BY rowid DESC')]

    def design(self, comparison_id, rule, inputs, actor, reason, applicability_confirmed, expected_revision=None):
        from evaluator.engineering.draft import evaluate
        if not applicability_confirmed or not actor.strip() or not reason.strip():
            raise ValueError('Confirm geometry/applicability and provide reviewer and input source basis')
        if rule.startswith('CR_') or rule in {'REMAINING_LIFE','API570_T_REQUIRED'}:
            raise ValueError('Use the integrated history calculation for rates and remaining life')
        result=evaluate(rule,inputs)
        with self.change('Calculate draft component pressure thickness',inputs=False,actor=actor,reason=reason,expected=expected_revision) as db:
            comp=self.comparison(comparison_id)
            if comp['stale']: raise ValueError('Comparison is stale')
            design={'id':_id(),'comparison_id':comparison_id,'input_revision':self.revision(),'rule':rule,'inputs':inputs,'result':result,'reviewer':actor,'basis':reason,'created':_now()}
            db.execute('INSERT INTO wf_designs VALUES(?,?,0)',(design['id'],json.dumps(design)))
        return design

    def export_revision(self, comparison_id=None):
        from openpyxl import Workbook
        with _LOCK, connection(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            revision=self.revision()
            readings=self.service.readings(); comparisons=self.comparisons(); evaluations=self.evaluations(); designs=self.designs()
            batches=[dict(json.loads(r['payload']),stale=bool(r['stale'])) for r in db.execute('SELECT payload,stale FROM wf_batches ORDER BY rowid DESC')]
            if comparison_id:
                selected=self.comparison(comparison_id)
                comparisons=[selected]
                evaluations=[e for e in evaluations if e['comparison_id']==comparison_id]
                designs=[d for d in designs if d['comparison_id']==comparison_id]
                batches=[b for b in batches if b['comparison_id']==comparison_id]
            audit=[dict(r) for r in db.execute('SELECT id,revision,label,actor,reason,created,undone FROM wf_actions ORDER BY revision')]
            sources=self.service.sources()
            events=[dict(r) for r in db.execute('SELECT * FROM audit_log ORDER BY event_id')]
            whole_sheets=self.service.imported_sheets()
            if comparison_id:
                selections={(selected['baseline'][0],selected['baseline'][1]),(selected['current_selection'][0],selected['current_selection'][1])}
                ids={sid for sid,_ in selections}
                whole_sheets=[i for i in whole_sheets if (i['source_id'],i['sheet_name']) in selections]
                sources=[s for s in sources if s['source_id'] in ids]
                readings=[r for r in readings if (r['source_id'],r['sheet_name']) in selections]
            whole_evidence=[self.service.imported_sheet(i['source_id'],i['sheet_name']) for i in whole_sheets]
            source_records={r.sha256:r for r in self.service.repository.sources()}
            source_files={}
            for source in sources:
                record=source_records.get(source['source_id'])
                if record:
                    content=record.stored_path.read_bytes()
                    if hashlib.sha256(content).hexdigest()!=record.sha256: raise ValueError('Source integrity check failed during export')
                    source_files['source_workbooks/'+record.sha256+'/'+Path(record.original_name).name]=content
        def pair_evidence(pair):
            old,new=pair.get('previous'),pair.get('current')
            ref=new or old
            record={'location':' / '.join(json.loads(ref.get('effective_location',ref['location_candidates']))) if ref else 'Ambiguous location; see candidate evidence'}
            for side,reading in [('previous',old),('current',new)]:
                record.update({side+'_file':reading['file_name'] if reading else None,
                               side+'_sheet':reading['sheet_name'] if reading else None,
                               side+'_cell':reading['cell'] if reading else None,
                               side+'_date':reading['inspection_date'] if reading else None,
                               side+'_thickness_mm':reading.get('effective_value',reading['raw_value']) if reading else None})
            return record
        comparison_records=[dict(comparison_id=c['id'],asset=c['asset'],lifecycle=c['lifecycle'],stale=c['stale'],**pair_evidence(r),**r) for c in comparisons for r in c['rows']]
        evaluation_records=[]
        for e in evaluations:
            pairs={r['id']:r for r in e['source_snapshot']['rows']}
            for row in e['rows']:
                evaluation_records.append(dict(evaluation_id=e['id'],asset=e['asset'],lifecycle=e['lifecycle'],input_revision=e['input_revision'],stale=e['stale'],status=e['status'],required_thickness_mm=e['required_thickness_mm'],basis=e['basis'],reviewer=e['reviewer'],**pair_evidence(pairs[row['pair_id']]),**row))
        batch_records=[]
        for batch in batches:
            for row in batch['rows']:
                batch_records.append(dict(batch_id=batch['id'],comparison_id=batch['comparison_id'],asset=batch['asset'],input_revision=batch['input_revision'],stale=batch['stale'],status=batch['status'],rule_version=batch['rule_version'],profile_sheet=batch['profile_sheet'],**row))
        coverage=[dict(source_id=s['source_id'],file_name=s['file_name'],**sheet) for s in sources for sheet in self.service.sheet_statuses(s['source_id'])]
        datasets={'sheet_imports':whole_sheets,'readings':readings,'comparisons':comparison_records,'evaluations':evaluation_records,'batch_evaluations':batch_records,'coverage':coverage,'designs':designs,'audit':audit,'source_events':events,'sources':sources}
        def value(x): return json.dumps(x,ensure_ascii=False,sort_keys=True) if isinstance(x,(dict,list,tuple)) else x
        def display(key, item):
            if item is not None and (key.endswith(('_mm_year','_mm','_years','_MPa')) or key=='maximum_interval_years'):
                try:
                    places=4 if key.endswith('_mm_year') else 2
                    return format(Decimal(str(item)),f'.{places}f').rstrip('0').rstrip('.')
                except (InvalidOperation,ValueError): pass
            return value(item)
        files=dict(source_files)
        files['whole_sheets.json']=json.dumps(whole_evidence,ensure_ascii=False,indent=2).encode()
        wb=Workbook(); wb.remove(wb.active)
        for name,records in datasets.items():
            columns=list(dict.fromkeys(k for r in records for k in r)) or ['status']
            buf=io.StringIO(newline=''); writer=csv.writer(buf); writer.writerow(columns)
            sheet=wb.create_sheet(name)
            sheet.append(columns)
            for record in records:
                values=[_safe(display(k,record.get(k))) for k in columns]
                writer.writerow(values); sheet.append(values)
            sheet.freeze_panes='A2'; sheet.auto_filter.ref=sheet.dimensions
            files[name+'.csv']=buf.getvalue().encode('utf-8-sig')
        cover=wb.create_sheet('revision',0)
        cover.append(['Project revision',revision]); cover.append(['Calculation status','DRAFT / NOT VALIDATED']); cover.append(['Source files',len(sources)])
        for sheet in wb:
            for col in sheet.columns:
                letter=col[0].column_letter
                sheet.column_dimensions[letter].width=min(50,max(14,max(len(str(c.value or '')) for c in col[:100])+2))
        xlsx=io.BytesIO(); wb.save(xlsx); files['evaluation.xlsx']=xlsx.getvalue()
        overview={'comparison_scope':comparison_id,'whole_sheet_imports':whole_sheets,'coverage':coverage,'revision':revision,'created':_now(),'status':'DRAFT / NOT VALIDATED','sources':sources,'comparisons':comparisons,'evaluations':evaluations,'batch_evaluations':batches,'designs':designs,'readings':readings}
        files['project_snapshot.json']=json.dumps(overview,ensure_ascii=False,indent=2).encode()
        def report_table(title, records, columns):
            heading='<h2>'+html.escape(title)+'</h2>'
            if not records: return heading+'<p>No records.</p>'
            return heading+'<table><thead><tr>'+''.join('<th>'+html.escape(k.replace('_',' '))+'</th>' for k in columns)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(display(k,r.get(k,''))))+'</td>' for k in columns)+'</tr>' for r in records)+'</tbody></table>'
        summary='<!doctype html><html><head><meta charset="utf-8"><title>UT Review revision '+str(revision)+'</title><style>body{font:14px/1.5 system-ui;margin:32px;color:#173a35}table{border-collapse:collapse;width:100%;font-size:12px}td,th{padding:8px;border:1px solid #d7e0da;text-align:left;overflow-wrap:anywhere}th{background:#eef4e8}pre{white-space:pre-wrap;overflow-wrap:anywhere}@media print{tr{break-inside:avoid}}</style></head><body><h1>UT Review · Revision '+str(revision)+'</h1><p>DRAFT / NOT VALIDATED. Stale results are retained with their stale flag. This report does not declare equipment fitness.</p>'
        summary+=report_table('Source custody',sources,['file_name','source_id'])
        summary+=report_table('Extraction coverage / unresolved sheets',coverage,['file_name','sheet','status','reason'])
        summary+=report_table('Evaluation results · Current thickness and historical rates',datasets['evaluations'],['asset','location','previous_sheet','previous_cell','previous_date','previous_thickness_mm','current_sheet','current_cell','current_date','current_thickness_mm','required_thickness_mm','apparent_rate_mm_year','adopted_rate_mm_year','remaining_life_years','issues','stale','basis'])
        summary+=report_table('Component batch evaluation · draft outputs and readiness',datasets['batch_evaluations'],['asset','location','current_sheet','current_cell','current_thickness_mm','profile_id','required_thickness_mm','apparent_rate_mm_year','adopted_rate_mm_year','remaining_life_years','inspection_interval_years','maximum_interval_years','due_date','mawp_MPa','forecast_mawp_MPa','issues','stale','evaluation_status'])
        summary+=report_table('Location comparison',datasets['comparisons'],['asset','lifecycle','location','kind','previous_sheet','previous_cell','previous_thickness_mm','current_sheet','current_cell','current_thickness_mm','accepted','stale','basis'])
        summary+=report_table('Readings and corrections',readings,['file_name','sheet_name','cell','raw_value','effective_value','raw_unit','campaign','inspection_date','effective_location','review_status'])
        summary+='<details><summary>Complete calculation inputs, source snapshots and trace</summary><pre>'+html.escape(json.dumps(overview,indent=2,ensure_ascii=False))+'</pre></details></body></html>'
        files['summary.html']=summary.encode()
        manifest={'revision':revision,'created':_now(),'files':{name:hashlib.sha256(content).hexdigest() for name,content in files.items()},'sources':[{ 'file_name':s['file_name'],'sha256':s['source_id']} for s in sources]}
        files['manifest.json']=json.dumps(manifest,indent=2).encode()
        exports=self.service.project_dir/'exports'; exports.mkdir(exist_ok=True)
        target=exports/f'revision-{revision:06d}-{uuid.uuid4().hex[:8]}.zip'
        temp=target.with_suffix('.tmp')
        try:
            with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as archive:
                for name,content in files.items(): archive.writestr(name,content)
            os.replace(temp,target)
        finally: temp.unlink(missing_ok=True)
        return target
