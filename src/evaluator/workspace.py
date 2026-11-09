"""Single-sheet intake and batch workspace over the existing audited services."""
from collections import Counter
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import re
import uuid

from evaluator.batch import PROFILE_FIELDS, PROFILE_TEXT, NUMERIC_OVERRIDES, TEXT_OVERRIDES, _value
from evaluator.engineering.references import dimensions, dimension, material_stresses, material_stress
from evaluator.quick_workflow import import_single_dated_sheet, match_single_sheet, single_sheet_campaigns, local_actor
from evaluator.storage.database import connection
from evaluator.workflow import _LOCK

CONFIG_FIELDS=PROFILE_FIELDS|PROFILE_TEXT|NUMERIC_OVERRIDES|{'rule','dimension_reference','material_reference','source_config_reference'}


class Workspace:
    def __init__(self, service):
        self.service=service
        self.flow=service.workflow

    def sources(self):
        return [dict(s,sheets=[x['name'] for x in (self.service.inventory_for(s['source_id']) or {}).get('sheets',[])]) for s in self.service.sources()]

    def open_sheet(self, source_id, sheet, revision, previous='', current=''):
        with _LOCK, connection(self.service.repository.path) as db:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            campaigns=import_single_dated_sheet(self.service,source_id,sheet,revision)
            dated=[c for c in campaigns if c['date_rank']]
            if len(dated)<2:
                return dict(comparison_id=None,campaigns=campaigns,message='Whole sheet preserved. Two dated measured campaigns were not found; choose another sheet or use detailed date-resolution tools.')
            current=current or dated[-1]['campaign']
            if not previous or previous.startswith('auto:'):
                chosen=next(c for c in dated if c['campaign']==current)
                ranks={c['campaign']:c['date_rank'] for c in dated if c['date_rank']<chosen['date_rank']}
                by_location={}
                for reading in self.service.readings():
                    if reading['source_id']!=source_id or reading['sheet_name']!=sheet or reading['campaign'] not in ranks:continue
                    key=self.flow._key(reading)
                    if key is None:continue
                    rank=ranks[reading['campaign']]
                    prior=by_location.get(key)
                    if not prior or rank>prior[0]:by_location[key]=(rank,[reading['observation_id']])
                    elif rank==prior[0]:prior[1].append(reading['observation_id'])
                ids=[oid for _,group in by_location.values() for oid in group]
                if not ids:raise ValueError('No earlier measured locations were found')
                selection='auto:'+str(uuid.uuid4())
                with self.flow.change('Select latest previous readings per location',inputs=False,expected=self.flow.revision(),actor=local_actor(),reason='Actual source observations and their own dates; duplicates remain ambiguous') as tx:
                    tx.execute('INSERT INTO wf_campaign_sets VALUES(?,?,?,?)',(selection,source_id,sheet,json.dumps(dict(observation_ids=ids,basis='Latest earlier dated campaign for each exact physical label; continuity requires confirmation'))))
                comp=self.flow.compare(source_id,sheet,selection,source_id,sheet,current,
                    next(s['file_name'] for s in self.service.sources() if s['source_id']==source_id).rsplit('.',1)[0],
                    'Continuity not yet confirmed',False,local_actor(),'Automatic per-location previous measurements; original campaigns and dates retained',expected_revision=self.flow.revision())
                comp.update(baseline_per_location=True,baseline_label='Latest previous measurement per location')
                db.execute('UPDATE wf_comparisons SET payload=? WHERE id=?',(json.dumps(comp),comp['id']))
            else:
                comp=match_single_sheet(self.service,source_id,sheet,previous,current,self.flow.revision())
            self.service.batch.prepare(comp['id'],self.flow.revision())
            return dict(comparison_id=comp['id'],campaigns=campaigns,message='Latest measured campaign selected with previous measurements chosen per location. Review assignments and physical continuity before evaluating.')

    def auto_open(self, source_id, revision):
        """Inspect actual adapters, then select the latest measured multi-date UT sheet."""
        from evaluator.importing.detect import extract as detect
        source=next((s for s in self.service.repository.sources() if s.sha256==source_id),None)
        if source is None:raise ValueError('Workbook not found')
        inv=self.service.inventory_for(source_id) or {}
        candidates=[]
        from openpyxl import load_workbook
        wb=load_workbook(source.stored_path,data_only=False,keep_links=False)
        try:
            for s in inv.get('sheets',[]):
                name=s['name']
                if re.search(r'photo|visual|preview|history|eval|reassess|control',name,re.I):continue
                result=detect(source.stored_path,name,workbook=wb,source_hash=source_id)
                campaigns={o.campaign_label for o in result.observations if o.date_candidates}
                dates=[d for o in result.observations for d in o.date_candidates]
                if len(campaigns)>=2 and dates:
                    candidates.append((max(dates),len(result.observations),name))
        finally:wb.close()
        if not candidates:return dict(comparison_id=None,message='No supported sheet with two dated measured campaigns detected. Choose a sheet below; original evidence is preserved.')
        return self.open_sheet(source_id,max(candidates)[2],revision)

    def templates(self):
        with connection(self.service.repository.path) as db:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM wf_templates ORDER BY id')]

    def state(self, cid=None, sheet=None, row_ids=None):
        partial=row_ids is not None
        requested=set(row_ids or ())
        comparisons=self.flow.comparisons()
        cid=cid or (comparisons[0]['id'] if comparisons else None)
        base={'revision':self.flow.revision()}
        if not partial:
            base.update(sources=self.sources(),comparisons=[dict(id=c['id'],asset=c['asset'],sheet=c['current_selection'][1]) for c in comparisons],templates=self.templates(),dimensions=dimensions(),material_stresses=material_stresses(),reference_gaps=['Allowable-stress lookups currently cover B31.3-2024 A106 Grade B pipe and A234 WPB fittings at exact 100–600°F table points. Other contexts require a checked record; workbook properties remain proposals.'])
            from evaluator.project_cleanup import latest_backup
            base['cleanup_backup_available']=latest_backup(self.service) is not None
        if not cid:return dict(base,workspace=None)
        comp=self.flow.comparison(cid)
        preview=self.service.batch.preview(cid,sheet,dict(basis='row7',confirm_records=False,confirm_history=False,confirm_rules=False,workspace_review=True))
        config=preview['settings']
        profiles=preview['profiles']
        rows=preview['rows']
        rows=[row for row in rows if row['current_id']]
        if partial:rows=[row for row in rows if row['current_id'] in requested]
        settings=config.get('row_overrides',{})
        for row in rows:
            p=row['profile'] or {};over=settings.get(row['current_id'],{})
            row['reviewed']=over.get('reviewed')=='yes'
            row['segment']=over.get('segment') or p.get('segment') or p.get('section') or row['location'].split(' / ')[0]
            row['component']=p.get('component') or ' / '.join(row['location'].split(' / ')[1:3])
            row['material']=over.get('material',_value(p,'material'));row['schedule']=_value(p,'schedule');row['nps']=_value(p,'nps')
            row['nominal_thickness_mm']=_value(p,'nominal_thickness_mm')
            row['geometry']=over.get('geometry') or p.get('geometry','unknown');row['code_family']=p.get('code_family');row['code_edition']=p.get('code_edition')
            od=_value(p,'D_outside_in')
            if not row['nps'] and od:
                matches={d['nps'] for d in dimensions() if abs(Decimal(d['od_in'])-Decimal(str(od)))<Decimal('.001')}
                if len(matches)==1:row['nps']=matches.pop();row['size_basis']='API 574 OD correspondence; schedule requires source evidence or confirmation'
            row['status']='Below minimum' if 'BELOW_OR_AT_REQUIRED_THICKNESS' in row['issues'] else 'Review' if row['issues'] else (row.get('row7') or {}).get('result','Calculated')
            row['attention']=bool(row['issues']) or not row['reviewed']
        readings={r['observation_id']:r for r in self.flow._selection(*comp['current_selection'])}
        previous=self.flow._selection(*comp['baseline'])
        previous_choices=[dict(id=r['observation_id'],identity=self.flow.match_identity(r),cell=r['cell'],date=r['inspection_date'],value=r.get('effective_value',r['raw_value'])) for r in previous if r.get('review_status')!='excluded']
        previous_by_section={}
        for choice in previous_choices:previous_by_section.setdefault(choice['identity']['section'],[]).append(choice)
        for row in rows:
            identity=self.flow.match_identity(readings[row['current_id']])
            identity['component']=settings.get(row['current_id'],{}).get('geometry') or identity['component']
            row['match_identity']=identity
            row['previous_section']=identity['section']
            row['match_flags']=[]
            if not identity['size']:row['match_flags'].append('Size missing; verify physical location')
            if identity['component']=='unknown':row['match_flags'].append('Component type unclear; choose pipe or fitting')
            if not row['previous_id']:row['match_flags'].append('No unique previous reading; review identity or choose a previous reading')
            elif row['previous_id']:
                prior=next((r for r in previous if r['observation_id']==row['previous_id']),None)
                if prior and self.flow._key(prior)!=self.flow._key(readings[row['current_id']]):row['match_flags'].append('Manually selected previous reading has different identity fields; review the assignment')
            if row['match_flags']:row['attention']=True
        def natural(row):return [int(t) if t.isdigit() else t.casefold() for t in re.split(r'(\d+)',row['location'])]
        rows.sort(key=natural)
        catalog={}
        for p in profiles:
            values={k:str(_value(p,k)) for k in PROFILE_FIELDS if _value(p,k) not in ('',None)}
            values.update({k:str(p[k]) for k in PROFILE_TEXT-{'component','segment'} if p.get(k) not in ('',None)})
            signature=json.dumps(values,sort_keys=True)
            if signature not in catalog:catalog[signature]=dict(id=p['id'],values=values,label=' · '.join(str(v) for v in [values.get('material'),values.get('geometry'),values.get('D_outside_in','?')+' in OD',values.get('schedule'),values.get('code_family'),values.get('code_edition')] if v),source=dict(sheet=p['sheet'],row=p['row'],source_id=p['source_id']))
        campaigns=single_sheet_campaigns(self.service,*comp['current_selection'][:2])
        if comp.get('baseline_per_location'):campaigns.append(dict(campaign=comp['baseline'][2],label=comp['baseline_label'],count=len(self.flow._selection(*comp['baseline'])),date_rank=''))
        if partial:return dict(revision=base['revision'],workspace=dict(rows=rows))
        return dict(base,workspace=dict(comparison=comp,profile_sheet=preview['profile_sheet'],profile_sheets=preview['sheets'],campaigns=campaigns,rows=rows,previous_choices_by_section=previous_by_section,catalog=list(catalog.values()),assignment_choices=[dict(id=p['id'],label=f"{p['section']} / {p['component']} / {p['point']} · {_value(p,'D_outside_in')} in OD · row {p['row']}") for p in profiles],settings=config,counts=dict(locations=sum(bool(r['current_id']) for r in rows),review=sum(r['attention'] for r in rows),below=sum(r['status']=='Below minimum' for r in rows),life=sum(r['remaining_life_years'] is not None for r in rows)),results=[r for r in self.service.batch.results(cid) if r['profile_sheet']==preview['profile_sheet']][:5]))

    def apply(self, cid, revision, ids, values=None, template_id=None, dimension_key=None, sheet=None, clear=False, fill_missing=False):
        values=dict(values or {})
        with _LOCK,connection(self.service.repository.path) as db:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            if int(revision)!=self.flow.revision():raise ValueError('Project changed; refresh before applying changes')
            if template_id:
                template=next((t for t in self.templates() if t['id']==template_id),None)
                if template is None:raise ValueError('Configuration template not found')
                values=dict(template['values'],**values)
            if dimension_key:
                d=dimension(*dimension_key)
                values.update(nps=d['nps'],schedule=d['schedule'],D_outside_in=d['od_in'],nominal_thickness_mm=d['nominal_mm'],dimension_reference=f"{d['reference']}; PDF page {d['pdf_page']}; SHA256 {d['source_sha256']}")
            stress=material_stress(values.get('material'),values.get('geometry'),values.get('code_family'),values.get('code_edition'),values.get('temperature_F'))
            if stress and 'S_allow_psi' not in values and 'material' in values:
                values.update(S_allow_psi=stress['S_allow_psi'],material_reference=stress['reference']+'; SHA256 '+stress['source_sha256'])
            if clear:
                preview=self.service.batch.preview(cid,sheet)
                valid={r['current_id'] for r in preview['rows'] if r['current_id']}
                if not ids or not set(ids)<=valid:raise ValueError('Choose existing current locations')
                with self.flow.change('Reset selected configuration overrides',inputs=False,expected=revision,actor=local_actor(),reason='Restore detected source configuration') as tx:
                    config=preview['settings']
                    for oid in ids:config.get('row_overrides',{}).pop(oid,None)
                    tx.execute('INSERT OR REPLACE INTO wf_batch_settings VALUES(?,?)',(cid,json.dumps(config)))
                    self.service.batch._stale(tx,cid)
            else:
                if values.get('allow_increase')=='yes':
                    existing=self.service.batch.settings(cid).get('row_overrides',{})
                    if not values.get('review_note','').strip():raise ValueError('Document a review basis for an increasing-reading rate override')
                    if any(Decimal(str(values.get('adopted_rate_mm_year',existing.get(oid,{}).get('adopted_rate_mm_year','0'))))<=0 for oid in ids):raise ValueError('An increasing-reading override requires an explicit positive adopted rate for every selected row')
                if not set(values)<=NUMERIC_OVERRIDES|TEXT_OVERRIDES:raise ValueError('Unknown engineering field')
                # A manual material/temperature/code change cannot inherit a stress silently.
                if set(values)&{'material','temperature_F','code_family','code_edition'}:
                    values.setdefault('review_note','Changed material/code/temperature; confirm property applicability')
                if fill_missing:
                    current={r['current_id']:r for r in self.state(cid,sheet)['workspace']['rows']}
                    if not ids or not set(ids)<=set(current):raise ValueError('Choose existing current locations')
                    aliases=dict(P_psi='pd_psi',D_outside_in='od_in',nominal_thickness_mm='nominal_mm',structural_minimum_mm='structural_mm',adopted_rate_mm_year='selected_cr',material='material',S_allow_psi='s_allow_psi')
                    per_row={}
                    for oid in ids:
                        row=current[oid];inputs=row.get('input_trace',{}).get('inputs',{})
                        missing={k:v for k,v in values.items() if (inputs.get(aliases[k]) if k in aliases else (row.get('geometry') if k=='geometry' else row.get(k))) in (None,'','unknown') or (k=='S_allow_psi' and row.get('input_trace',{}).get('inputs',{}).get('s_allow_psi')!=v)}
                        if missing:per_row[oid]=missing
                    if per_row:self.service.batch.apply_overrides(cid,revision,[],[],{},sheet,per_row_values=per_row)
                else:self.service.batch.apply_overrides(cid,revision,[],ids,values,sheet)
        return dict(comparison_id=cid,refresh_ids=list(ids))

    def save_template(self, revision, name, values):
        values={k:str(v) for k,v in values.items() if k in CONFIG_FIELDS and v not in ('',None)}
        if not name.strip() or not values:raise ValueError('Provide a configuration name and engineering values')
        for key,val in values.items():
            if key in NUMERIC_OVERRIDES:
                from evaluator.batch import _num
                if _num(val) is None:raise ValueError('Invalid template input: '+key)
        record=dict(id=str(uuid.uuid4()),name=name.strip()[:120],values=values,basis='User saved engineering configuration; review applicability for each new scope')
        with self.flow.change('Save reusable configuration',inputs=False,expected=revision,actor=local_actor(),reason='Reusable batch inputs') as db:
            db.execute('INSERT INTO wf_templates VALUES(?,?)',(record['id'],json.dumps(record)))
        return record

    def policy(self,cid,revision,basis,sheet=None):
        if basis not in {'provided','recalculate','row7'}:raise ValueError('Unsupported calculation basis')
        with self.flow.change('Change workspace calculation basis',inputs=False,expected=revision,actor=local_actor(),reason='Explicit source or recalculation method') as db:
            config=self.service.batch.preview(cid,sheet)['settings'];config['basis']=basis
            db.execute('INSERT OR REPLACE INTO wf_batch_settings VALUES(?,?)',(cid,json.dumps(config)))
            self.service.batch._stale(db,cid)

    def evaluate(self,cid,revision,sheet=None,basis=None):
        # Saved review flags apply per row, keeping unconfirmed rows withheld.
        return self.service.batch.evaluate(cid,revision,dict(profile_sheet=sheet,confirm_records=True,confirm_history=False,confirm_rules=False,basis='row7',workspace_review=True))

    def _refresh(self, db, comp, changed_ids):
        readings={r['observation_id']:r for r in self.service.readings()}
        config=self.service.batch.settings(comp['id'])
        for pair in comp['rows']:
            candidate_ids={r['observation_id'] for key in ('previous_candidates','current_candidates') for r in pair.get(key,[])}
            touched=bool(changed_ids & ({pair.get('previous_id'),pair.get('current_id')}|candidate_ids))
            for key in ('previous','current'):
                if pair.get(key):pair[key]=readings.get(pair[key]['observation_id'],pair[key])
            for key in ('previous_candidates','current_candidates'):
                if key in pair:pair[key]=[readings.get(r['observation_id'],r) for r in pair[key]]
            if touched:
                pair['accepted']=False
                current_ids={pair.get('current_id')}|{r['observation_id'] for r in pair.get('current_candidates',[])}
                for oid in current_ids:
                    config.get('row_overrides',{}).get(oid,{}).pop('reviewed',None)
                    for archived in config.get('scenarios',{}).values():archived.get('row_overrides',{}).get(oid,{}).pop('reviewed',None)
        db.execute('UPDATE wf_comparisons SET payload=?,stale=0 WHERE id=?',(json.dumps(comp),comp['id']))
        db.execute('INSERT OR REPLACE INTO wf_batch_settings VALUES(?,?)',(comp['id'],json.dumps(config)))

    def correct(self,cid,revision,oid,value):
        row=next((r for r in self.service.readings() if r['observation_id']==oid),None)
        comp=self.flow.comparison(cid)
        if row is None or oid not in {r['observation_id'] for selection in (comp['baseline'],comp['current_selection']) for r in self.flow._selection(*selection)}:raise ValueError('Reading does not belong to this comparison')
        if comp['stale']:raise ValueError('Comparison is stale; re-open the sheet before correcting readings')
        loc=json.loads(row.get('effective_location',row['location_candidates']))+['']*4
        with self.flow.change('Correct workspace reading',expected=revision,actor=local_actor(),reason='Inline correction; original retained',affected_source=row['source_id']) as db:
            self.service.correct_reading.__wrapped__(self.service,oid,value,*loc[:4],local_actor(),'Inline workspace correction; original retained')
            self._refresh(db,comp,{oid})
        return cid

    def dates(self,cid,revision,previous='',current=''):
        comp=self.flow.comparison(cid)
        if previous and comp.get('baseline_per_location') and len({r['inspection_date'] for r in self.flow._selection(*comp['baseline'])})>1:raise ValueError('Previous dates vary by location; correct the individual source campaigns in detailed tools')
        if not previous and not current:raise ValueError('Enter at least one confirmed inspection date')
        with self.flow.change('Resolve workspace campaign dates',expected=revision,actor=local_actor(),reason='Explicit inspection event dates',affected_source=comp['current_selection'][0]) as db:
            ids=set()
            for chosen,selection in [(previous,comp['baseline']),(current,comp['current_selection'])]:
                if chosen:
                    ids.update(r['observation_id'] for r in self.flow._selection(*selection))
                    campaigns={r['campaign'] for r in self.flow._selection(*selection)}
                    for campaign in campaigns:self.service.resolve_campaign_date.__wrapped__(self.service,*selection[:2],campaign,chosen,local_actor(),'Inspection date confirmed in workspace')
            self._refresh(db,comp,ids)
        return cid

    def campaign_dates(self,cid,revision,dates):
        comp=self.flow.comparison(cid)
        selections=[comp['baseline'],comp['current_selection']]
        readings=[r for selection in selections for r in self.flow._selection(*selection)]
        allowed={r['campaign'] for r in readings}
        if not dates or not set(dates)<=allowed:raise ValueError('Choose dates for inspection campaigns in this comparison')
        with self.flow.change('Confirm individual campaign dates',expected=revision,actor=local_actor(),reason='Exact inspection dates entered per reading campaign') as db:
            for campaign,chosen in dates.items():
                self.service.resolve_campaign_date.__wrapped__(self.service,*comp['current_selection'][:2],campaign,chosen,local_actor(),'Exact campaign date confirmed in workspace')
            self._refresh(db,comp,{r['observation_id'] for r in readings if r['campaign'] in dates})
        return cid

    def pair_source_row(self,cid,revision,oid):
        comp=self.flow.comparison(cid)
        current=next((r for r in self.flow._selection(*comp['current_selection']) if r['observation_id']==oid),None)
        if not current:raise ValueError('Choose a current reading')
        matches=[r for r in self.flow._selection(*comp['baseline']) if (r['source_id'],r['sheet_name'],re.search(r'\d+',r['cell'])[0])==(current['source_id'],current['sheet_name'],re.search(r'\d+',current['cell'])[0])]
        if len(matches)!=1:raise ValueError('No unique previous measurement exists on this source row')
        self.flow.pair(cid,matches[0]['observation_id'],oid,True,local_actor(),'Confirmed same physical UT source row: '+matches[0]['cell']+' to '+current['cell'],revision)
        return cid

    def rematch(self,cid,revision,oid=None,values=None,previous_id=None):
        from evaluator.importing.reading_identity import normalize
        comp=self.flow.comparison(cid)
        current={r['observation_id']:r for r in self.flow._selection(*comp['current_selection'])}
        if oid and oid not in current:raise ValueError('Choose a current reading in this comparison')
        if previous_id:
            available={r['observation_id'] for r in self.flow._selection(*comp['baseline'])}
            if previous_id not in available:raise ValueError('Previous reading is outside this comparison')
            if any(r.get('accepted') and r.get('previous_id')==previous_id and r.get('current_id')!=oid for r in comp['rows']):raise ValueError('That previous reading is already assigned to another location')
            with _LOCK,connection(self.service.repository.path) as db:
                if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
                with self.flow.change('Review inline previous-reading assignment',inputs=False,expected=revision,actor=local_actor(),reason='Replace selected current reading match'):
                    for pair in comp['rows']:
                        if pair.get('current_id')==oid:pair['accepted']=False
                    db.execute('UPDATE wf_comparisons SET payload=? WHERE id=?',(json.dumps(comp),cid))
                self.flow.pair(cid,previous_id,oid,True,local_actor(),'Previous UT selected inline after review of section, joint, band and size',self.flow.revision())
            return cid
        allowed={'section','joint','band','size','component'}
        if values and (not set(values)<=allowed or any(not str(v).strip() for v in values.values())):raise ValueError('Enter nonempty identity fields')
        if values and values.get('component') and values['component'] not in {'straight_pipe','elbow','tee','reducer','fitting','unknown'}:raise ValueError('Unknown component type')
        with self.flow.change('Review reading identity and rematch',inputs=False,expected=revision,actor=local_actor(),reason='Inline identity correction; raw source labels retained') as db:
            if oid and values:
                old=db.execute('SELECT payload FROM wf_match_identity WHERE observation_id=?',(oid,)).fetchone()
                corrected=json.loads(old[0]) if old else {}
                corrected.update({k:normalize(v) if k!='component' else v for k,v in values.items()})
                db.execute('INSERT OR REPLACE INTO wf_match_identity VALUES(?,?,?)',(oid,current[oid]['source_id'],json.dumps(corrected)))
                if 'component' in values:
                    config=self.service.batch.settings(cid)
                    entry=config.setdefault('row_overrides',{}).setdefault(oid,{})
                    entry['geometry']=values['component']
                    if values['component']!='unknown':entry['material']='A106 B' if values['component']=='straight_pipe' else 'A234 WPB'
                    db.execute('INSERT OR REPLACE INTO wf_batch_settings VALUES(?,?)',(cid,json.dumps(config)))
            self.flow._identity_revision=None
            comp['rows']=self.flow._match_records(self.flow._selection(*comp['baseline']),self.flow._selection(*comp['current_selection']),True)
            db.execute('UPDATE wf_comparisons SET payload=?,stale=0 WHERE id=?',(json.dumps(comp),cid))
            self.flow._stale_comparison_results(db,cid)
        return cid
