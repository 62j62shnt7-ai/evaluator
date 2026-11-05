"""Component-aware, revisioned batch evaluation using explicit source records."""
from evaluator.inspection_time import elapsed_days
from collections import Counter,defaultdict
from datetime import date
from decimal import Decimal,InvalidOperation
import hashlib
import json
import re
import uuid
from copy import deepcopy

from evaluator.storage.database import connection
from evaluator.workflow import _LOCK
from evaluator.engineering.records import import_records,identity
from evaluator.engineering.batch_rules import outputs,convert,VERSION
from evaluator.engineering.draft import evaluate as pressure_thickness

ADAPTER_VERSION='records-6'
NUMERIC_OVERRIDES={'required_thickness_mm','adopted_rate_mm_year','structural_minimum_mm','allowance_mm','interval_fraction','interval_cap_years','selected_interval_years','forecast_years','forecast_factor','year_days','F_class','E_weld','T_temp','E_quality','W_reduction','Y_coefficient','F_design','E_joint'}
PROFILE_FIELDS={'material','P_psi','temperature_F','S_allow_psi','SMYS_psi','D_outside_in','D_inside_in','nominal_thickness_mm','schedule','nps'}
PROFILE_TEXT={'component','geometry','code_family','code_edition','segment'}
NUMERIC_OVERRIDES.update({'P_psi','temperature_F','S_allow_psi','SMYS_psi','D_outside_in','D_inside_in','nominal_thickness_mm'})
TEXT_OVERRIDES={'profile_id','rule','code_edition','material','geometry','code_family','segment','schedule','nps','reviewed','reconcile_conflict','review_note','dimension_reference','component','material_reference','source_config_reference','allow_increase'}
RULES={'VIII_SHELL','VIII_UG27_HOOP','VIII_UG27_LONG','VIII_UG32_ELLIP','VIII_UG32_TORI','B31_3_304_1_2','B31_4_403_2_1','B31_8_841_1_1'}


def _hash(value):return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()
def _num(value,positive=False):
    if value in ('',None) or isinstance(value,bool):return None
    try:n=Decimal(str(value))
    except (InvalidOperation,ValueError):return None
    return n if n.is_finite() and n>=0 and (not positive or n>0) else None

def _value(profile,key):return profile.get('fields',{}).get(key,{}).get('value')
def _location(reading):return json.loads(reading.get('effective_location',reading['location_candidates']))
def _current(reading):return reading.get('effective_value',reading['raw_value'])


class BatchService:
    def __init__(self,service):self.service=service;self.flow=service.workflow;self.path=service.repository.path

    def profiles(self,source_id=None):
        with connection(self.path) as db:
            return [json.loads(r['payload']) for r in db.execute('SELECT * FROM wf_profiles ORDER BY source_id,sheet,id') if source_id is None or r['source_id']==source_id]

    def prepare(self,comparison_id,expected_revision=None):
        comp=self.flow.comparison(comparison_id);sid=comp['current_selection'][0]
        source=next((s for s in self.service.repository.sources() if s.sha256==sid),None)
        if source is None:return []
        with _LOCK,connection(self.path) as db:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            if expected_revision is not None and int(expected_revision)!=self.flow.revision():raise ValueError('Project changed; refresh before importing engineering records')
            if hashlib.sha256(source.stored_path.read_bytes()).hexdigest()!=sid:raise ValueError('Source integrity check failed')
            prior=db.execute('SELECT version FROM wf_profile_imports WHERE source_id=?',(sid,)).fetchone()
            if prior and prior[0]==ADAPTER_VERSION:return self.profiles(sid)
            records=import_records(source.stored_path)
            with self.flow.change('Import engineering record proposals',inputs=False,expected=self.flow.revision(),actor='Local source importer',reason='Read-only source design records; caches remain proposals') as tx:
                tx.execute('DELETE FROM wf_profiles WHERE source_id=?',(sid,))
                for record in records:tx.execute('INSERT INTO wf_profiles VALUES(?,?,?,?)',(record['id'],sid,record['sheet'],json.dumps(record)))
                tx.execute('INSERT OR REPLACE INTO wf_profile_imports VALUES(?,?)',(sid,ADAPTER_VERSION))
                affected=[r['id'] for r in tx.execute('SELECT id,payload FROM wf_comparisons').fetchall() if json.loads(r['payload'])['current_selection'][0]==sid]
                for cid in affected:self._stale(tx,cid)
            return records

    def settings(self,comparison_id):
        with connection(self.path) as db:
            row=db.execute('SELECT payload FROM wf_batch_settings WHERE comparison_id=?',(comparison_id,)).fetchone()
            return json.loads(row[0]) if row else {'group_overrides':{},'row_overrides':{}}

    @staticmethod
    def _stale(db,cid):
        for row in db.execute('SELECT id,payload FROM wf_batches').fetchall():
            if json.loads(row['payload'])['comparison_id']==cid:db.execute('UPDATE wf_batches SET stale=1 WHERE id=?',(row['id'],))

    def results(self,comparison_id=None):
        with connection(self.path) as db:
            results=[]
            for row in db.execute('SELECT * FROM wf_batches ORDER BY rowid DESC'):
                payload=json.loads(row['payload'])
                if comparison_id is None or payload['comparison_id']==comparison_id:
                    results.append(dict(payload,stale=bool(row['stale']) or payload.get('rule_version')!=VERSION))
            return results

    def _measurement_rows(self,comp):
        rows=[]
        for pair in comp['rows']:
            if pair['kind']=='ambiguous':
                for current in pair.get('current_candidates',[]):rows.append(dict(pair=pair,current=current,previous=None))
                if not pair.get('current_candidates'):
                    for old in pair.get('previous_candidates',[]):rows.append(dict(pair=pair,current=None,previous=old))
            else:rows.append(dict(pair=pair,current=pair['current'],previous=pair['previous']))
        return rows

    def _nominal(self,reading):
        if not reading:return None
        revision=self.flow.revision()
        if getattr(self,'_nominal_revision',None)!=revision:
            self._nominal_sheets={};self._nominal_revision=revision
        key=(reading['source_id'],reading['sheet_name'])
        if key not in self._nominal_sheets:self._nominal_sheets[key]=self.service.imported_sheet(*key)
        sheet=self._nominal_sheets[key]
        if not sheet:return None
        row=re.search(r'\d+',reading['cell'])[0]
        raw=sheet['cells'].get('C'+row,{}).get('value')
        return str(raw).strip() if raw not in ('',None) else None

    def _assign(self,comp,profiles,config):
        measurements=self._measurement_rows(comp);family=profiles[0]['family'] if profiles else ('separator' if any('separator' in (r['current'] or r['previous'] or {}).get('file_name','').lower() for r in measurements) else 'pipeline')
        by_key=defaultdict(list);by_current=defaultdict(list)
        for p in profiles:by_key[tuple(p['key'])].append(p)
        for item in measurements:
            if item['current']:
                key=identity(*(_location(item['current'])+['']*3)[:3],family)
                item['key']=key;by_current[key].append(item)
        # Learn nominal/OD correspondences from the same source's unique points.
        # These remain mapping proposals requiring the batch scope confirmation.
        size_map=defaultdict(set)
        for key,items in by_current.items():
            candidates=by_key.get(key,[])
            if len(items)==len(candidates)==1:
                nominal=self._nominal(items[0]['current']);od=_num(_value(candidates[0],'D_outside_in'),True)
                if nominal and od:size_map[nominal].add(str(od))
        assigned={}
        for key,items in by_current.items():
            candidates=by_key.get(key,[]);used=set()
            if len(items)==len(candidates)==1:
                assigned[items[0]['current']['observation_id']]=(candidates[0],'Unique component/point label proposal')
                continue
            for item in items:
                nominal=self._nominal(item['current']);known=size_map.get(nominal,set())
                compatible=[p for p in candidates if str(_num(_value(p,'D_outside_in'),True)) in known]
                if len(compatible)==1 and compatible[0]['id'] not in used:
                    assigned[item['current']['observation_id']]=(compatible[0],'Branch/size proposal from same-source nominal-to-OD evidence: '+str(nominal));used.add(compatible[0]['id'])
            remaining=[i for i in items if i['current']['observation_id'] not in assigned]
            remaining_profiles=[p for p in candidates if p['id'] not in used]
            if len(remaining)==len(remaining_profiles)==1 and used:
                assigned[remaining[0]['current']['observation_id']]=(remaining_profiles[0],'Remaining distinct branch/side proposal after unique source-size assignment')
        for item in measurements:
            current=item['current'];profile=None;basis='';candidates=[]
            if current:
                oid=current['observation_id'];candidates=by_key.get(item['key'],[])
                profile,basis=assigned.get(oid,(None,''))
                chosen=config.get('row_overrides',{}).get(oid,{}).get('profile_id')
                if chosen:
                    profile=next((p for p in profiles if p['id']==chosen),None)
                    if profile is None:raise ValueError('Manual assignment must use a record from the selected source scenario')
                    basis='Manual component record assignment'
            item.update(profile=profile,assignment_basis=basis,candidates=candidates,nominal_size=self._nominal(current))
        return measurements

    @staticmethod
    def _group(profile):
        if not profile:return 'unmapped'
        key=[profile.get(k) for k in ('code_family','code_edition','geometry')]+[_value(profile,k) for k in ('material','S_allow_psi','SMYS_psi','P_psi')]
        return _hash(key)[:16]

    def _select_sheet(self,comp,profiles,selected):
        sheets=sorted({p['sheet'] for p in profiles})
        if selected:
            if selected not in sheets:raise ValueError('Select an available engineering scenario from this workbook')
            return selected
        best=None;score=None
        for sheet in sheets:
            candidates=[p for p in profiles if p['sheet']==sheet];items=self._assign(comp,candidates,{})
            consistent=0;projected=0;mapped=0
            for item in items:
                p=item['profile'];c=item['current']
                if p and c:
                    mapped+=1
                    projected+=p['fields'].get('current_mm',{}).get('kind')=='formula'
                    consistent+=_num(_value(p,'current_mm'))==_num(_current(c)) and _num(_current(c)) is not None
            value=(consistent,-projected,mapped,sheet)
            if score is None or value>score:best,score=sheet,value
        return best

    def preview(self,comparison_id,profile_sheet=None,options=None):
        comp=self.flow.comparison(comparison_id);config=self.settings(comparison_id)
        profiles=self.profiles(comp['current_selection'][0])
        selected=self._select_sheet(comp,profiles,profile_sheet or config.get('profile_sheet'))
        if config.get('profile_sheet') and config['profile_sheet']!=selected:
            scenarios=deepcopy(config.get('scenarios',{}))
            scenarios[config['profile_sheet']]={k:deepcopy(v) for k,v in config.items() if k!='scenarios'}
            config=dict(scenarios.get(selected,{'group_overrides':{},'row_overrides':{}}),scenarios=scenarios)
        config.update({k:v for k,v in (options or {}).items() if k not in {'group_overrides','row_overrides'}})
        config['profile_sheet']=selected
        chosen=[p for p in profiles if p['sheet']==selected]
        assignments=self._assign(comp,chosen,config)
        proposal=dict(config,confirm_records=True,confirm_history=True)
        rows=[self._calculate_row(item,proposal) for item in assignments]
        groups={}
        for row in rows:
            p=row['profile'];gid=row['group_id']
            if p and gid not in groups:groups[gid]=dict(id=gid,material=_value(p,'material'),geometry=p['geometry'],code_family=p['code_family'],code_edition=p.get('code_edition'),pressure_psi=_value(p,'P_psi'),count=0,ready=0)
            if p:groups[gid]['count']+=1;groups[gid]['ready']+=row['remaining_life_years'] is not None
        token=_hash([[r['current_id'],r['previous_id'],r['current_thickness_mm'],r['location'],r['profile_id'],r['profile']] for r in rows])
        return dict(comparison=comp,profile_sheet=selected,sheets=sorted({p['sheet'] for p in profiles}),profiles=chosen,rows=rows,groups=list(groups.values()),settings=config,preview_token=token,
                    counts=dict(current=sum(r['current_id'] is not None for r in rows),life_ready=sum(r['remaining_life_years'] is not None for r in rows),historical_ready=sum(r['apparent_rate_mm_year'] is not None for r in rows),issues=dict(Counter(i for r in rows for i in r['issues']))))

    def apply_overrides(self,comparison_id,expected_revision,group_ids,row_ids,values,profile_sheet=None):
        clean={k:str(v).strip() for k,v in values.items() if v not in ('',None)}
        if not clean or not set(clean)<=(NUMERIC_OVERRIDES|TEXT_OVERRIDES):raise ValueError('Select valid grouped input changes')
        for k,v in clean.items():
            if k in NUMERIC_OVERRIDES and _num(v) is None:raise ValueError(k+' must be finite and nonnegative')
        for key in ('reviewed','reconcile_conflict'):
            if key in clean and clean[key] not in {'yes','no'}:raise ValueError('Invalid review decision')
        if clean.get('geometry') and clean['geometry'] not in {'straight_pipe','elbow','tee','reducer','branch','nozzle','shell','head_unspecified','unknown'}:raise ValueError('Unsupported component geometry')
        if clean.get('rule') and clean['rule'] not in RULES:raise ValueError('Unsupported rule')
        preview=self.preview(comparison_id,profile_sheet)
        if not set(group_ids)<={g['id'] for g in preview['groups']} or not set(row_ids)<={r['current_id'] for r in preview['rows'] if r['current_id']}:raise ValueError('Selected input scope changed; refresh the batch preview')
        if not group_ids and not row_ids:raise ValueError('Choose at least one compatible group or location')
        with self.flow.change('Set grouped component inputs',inputs=False,expected=expected_revision,actor='Local batch reviewer',reason='Explicit defaults/overrides for selected component scope') as db:
            original_row_overrides=deepcopy(preview['settings'].get('row_overrides',{}))
            config=deepcopy(preview['settings'])
            config['profile_sheet']=preview['profile_sheet']
            for scope,ids in [('group_overrides',group_ids),('row_overrides',row_ids)]:
                for identifier in ids:config.setdefault(scope,{}).setdefault(identifier,{}).update(clean)
            # Compare with the previous effective context, not just the original
            # source record: earlier lookup/manual overrides must also expire.
            context_keys=('material','temperature_F','code_family','code_edition','geometry')
            for row in preview['rows']:
                oid=row['current_id']
                if not oid or not (oid in row_ids or row['group_id'] in group_ids):continue
                profile=row['profile'] or {}
                entry=config.setdefault('row_overrides',{}).setdefault(oid,{})
                def previous(key):return profile.get(key) if key in PROFILE_TEXT else _value(profile,key)
                changed=any(key in clean and str(clean[key])!=str(previous(key)) and (oid in row_ids or key not in original_row_overrides.get(oid,{})) for key in context_keys)
                if changed:
                    for key in ('S_allow_psi','SMYS_psi'):
                        if key not in clean:entry[key]=None
                        elif oid not in row_ids:entry.pop(key,None)
                    if 'reviewed' not in clean:entry['reviewed']='no'
                if (changed or {'S_allow_psi','SMYS_psi'}&set(clean)) and 'material_reference' not in clean:entry['material_reference']=''
                elif changed and oid not in row_ids:entry.pop('material_reference',None)
            db.execute('INSERT OR REPLACE INTO wf_batch_settings VALUES(?,?)',(comparison_id,json.dumps(config)))
            self._stale(db,comparison_id)

    def _inputs(self,profile,overrides,config):
        issues=[];trace={};raw=lambda k:overrides.get(k,_value(profile,k))
        def converted(key,unit):
            v=raw(key)
            if v in ('',None):return None
            try:return str(convert(v,unit,'MPa' if unit=='psi' else 'mm'))
            except ValueError:issues.append('INVALID_'+key.upper());return None
        inputs={}
        for source,target,unit in [('P_psi','P_MPa','psi'),('D_outside_in','D_outside_mm','in'),('D_inside_in','D_inside_mm','in'),('S_allow_psi','S_allow_MPa','psi'),('SMYS_psi','SMYS_MPa','psi')]:
            value=converted(source,unit)
            if value is not None:inputs[target]=value;trace[target]=dict(source=profile.get('fields',{}).get(source),converted=value,unit='MPa' if unit=='psi' else 'mm')
        if inputs.get('D_inside_mm') is not None:inputs['R_inside_mm']=str(Decimal(inputs['D_inside_mm'])/2)
        if inputs.get('S_allow_MPa') is not None:inputs['S_B313_MPa']=inputs['S_allow_MPa']
        for factor in ('E_joint','E_quality','W_reduction','Y_coefficient','F_class','F_design','E_weld','T_temp'):
            value=raw(factor)
            if value not in ('',None):inputs[factor]=str(value)
        proposal=profile.get('factor_candidates',{}).get('design_factor')
        if 'F_class' not in inputs and proposal and config.get('confirm_rules'):inputs['F_class']=str(proposal['value']);trace['F_class']=dict(source_proposal=proposal)
        if proposal and config.get('confirm_rules') and profile.get('code_family')=='ASME B31.8':
            # This proposal exists only for the recognized source expression
            # t=P*D/(2*SMYS*0.8). Its omitted E and T multipliers are unity.
            for factor in ('E_weld','T_temp'):
                if factor not in inputs:
                    inputs[factor]='1'
                    trace[factor]=dict(value='1',source_cell=proposal['cell'],source_formula=proposal['raw'],
                                       basis='unit multiplier in recognized workbook pressure expression')
        return inputs,trace,issues

    def _calculate_row(self,item,config):
        current,old,pair,p=item['current'],item['previous'],item['pair'],item['profile']
        gid=self._group(p);oid=current['observation_id'] if current else None
        override=dict(config.get('group_overrides',{}).get(gid,{}));override.update(config.get('row_overrides',{}).get(oid,{}))
        config=dict(config)
        if config.get('workspace_review'):config.update(confirm_records=False,confirm_history=False,confirm_rules=False)
        if override.get('reviewed')=='yes':
            config.update(confirm_records=True,confirm_history=True,confirm_rules=True)
        if override.get('reconcile_conflict')=='yes':config['confirm_conflicts']=True
        if override.get('allow_increase')=='yes' and override.get('review_note'):config['allow_increase']=True
        if p is None and set(override)&PROFILE_FIELDS:
            p=dict(id='manual-'+str(oid),fields={},geometry='unknown',family='separator' if override.get('code_family')=='ASME VIII-1' else 'pipeline',code_family='',code_edition=None,section='',component='',row=None,sheet=current['sheet_name'] if current else '',source_id=current['source_id'] if current else '')
        source_profile=p
        if p is not None:
            p=deepcopy(p)
            for key in PROFILE_FIELDS:
                if key in override:
                    reference=override.get('dimension_reference') if key in {'D_outside_in','nominal_thickness_mm','nps','schedule'} else override.get('material_reference') if key=='S_allow_psi' else None
                    p.setdefault('fields',{})[key]=dict(value=override[key],kind='reference_derived' if reference else 'manual_override',unit=(p.get('fields',{}).get(key) or {}).get('unit'),source_record=(source_profile.get('fields',{}).get(key)),basis=reference or 'Explicit batch configuration')
            for key in PROFILE_TEXT:
                if key in override:p[key]=override[key]
            context_changed=any(key in override and str(override[key])!=str(source_profile.get(key) if key in PROFILE_TEXT else _value(source_profile,key)) for key in ('material','code_family','code_edition','temperature_F','geometry'))
            if context_changed:
                for key in ('S_allow_psi','SMYS_psi'):
                    if key not in override:p.setdefault('fields',{})[key]=dict(value=None,kind='invalidated',basis='Material/code/temperature changed; property must be supplied for this context')
        row=dict(id=oid or 'history-'+str(pair['id']),pair_id=pair['id'],current_id=oid,previous_id=old['observation_id'] if old else None,
                 location=' / '.join(_location(current or old)) if current or old else 'Ambiguous source location',group_id=gid,profile_id=p['id'] if p else None,profile=p,
                 candidate_profile_ids=[candidate['id'] for candidate in item.get('candidates',[])],
                 current_cell=current['cell'] if current else None,previous_cell=old['cell'] if old else None,current_sheet=current['sheet_name'] if current else None,
                 current_thickness_mm=str(_current(current)) if current else None,previous_thickness_mm=str(_current(old)) if old else None,
                 inspection_date=current['inspection_date'] if current else None,previous_inspection_date=old['inspection_date'] if old else None,nominal_size=item['nominal_size'],assignment_basis=item['assignment_basis'],
                 required_thickness_mm=None,pressure_thickness_mm=None,adopted_rate_mm_year=None,apparent_rate_mm_year=None,elapsed_days=None,issues=[],input_trace={},outputs={},output_readiness={})
        issues=row['issues'];blocked=False
        if not current:issues.append('CURRENT_MISSING');blocked=True
        elif current.get('review_status')=='excluded':issues.append('CURRENT_EXCLUDED');blocked=True
        elif current.get('raw_unit')!='mm':issues.append('UNIT_NOT_SUPPORTED');blocked=True
        elif _num(_current(current),True) is None:issues.append('CURRENT_VALUE_INVALID');blocked=True
        if not p:issues.append('PROFILE_AMBIGUOUS' if item['candidates'] else 'PROFILE_MISSING');blocked=True
        if p and p.get('property_conflicts'):issues.append('SOURCE_MATERIAL_PROPERTY_CONFLICT')
        if p and not config.get('confirm_records'):issues.append('PROFILE_SCOPE_NOT_CONFIRMED');blocked=True
        if p and current:
            copied=_num(_value(p,'current_mm'));measured=_num(_current(current));kind=p['fields'].get('current_mm',{}).get('kind')
            if kind=='formula':issues.append('PROFILE_CURRENT_PROJECTED_NOT_UT')
            if copied is not None and measured is not None and copied!=measured:
                issues.append('PROFILE_CURRENT_CONFLICT')
                if not config.get('confirm_conflicts'):blocked=True
            if p.get('inspection_date')!=current['inspection_date']:issues.append('PROFILE_EVENT_SCOPE_CONFIRMATION')
        # Historical rates are independent of engineering-record readiness.
        source_year_days=(p or {}).get('year_days')
        year_days=override.get('year_days') or config.get('year_days') or source_year_days or '365.2425'
        if current and old and pair['kind'] in {'matched','lifecycle_mismatch'} and (pair.get('accepted') or config.get('confirm_history')):
            if old['raw_unit']!=current['raw_unit'] or current['raw_unit']!='mm':issues.append('HISTORY_UNIT_MISMATCH')
            elif not old['inspection_date'] or not current['inspection_date']:issues.append('HISTORY_DATE_REQUIRED')
            else:
                try:
                    days=elapsed_days(old['inspection_date'],current['inspection_date'],year_days)
                    a,b=_num(_current(old)),_num(_current(current));row['elapsed_days']=float(days) if isinstance(days,Decimal) else days
                    if days<=0:issues.append('NONPOSITIVE_ELAPSED_TIME')
                    elif a is None or b is None:issues.append('HISTORY_VALUE_INVALID')
                    else:
                        rate=(a-b)*Decimal(str(year_days))/days
                        row['apparent_rate_mm_year']=str(rate)
                        if rate<0:issues.append('THICKNESS_INCREASE_REVIEW')
                        elif rate==0:issues.append('ZERO_APPARENT_RATE')
                except (ValueError,InvalidOperation):issues.append('HISTORY_DATE_INVALID')
        else:issues.append('HISTORY_UNCONFIRMED_OR_MISSING')
        raw=lambda key:override.get(key,_value(p,key) if p else None)
        required=_num(raw('required_thickness_mm'),True);pressure=_num(raw('pressure_thickness_mm'),True);structural=_num(raw('structural_minimum_mm'))
        design_changed=any(k in override and str(override[k])!=str(source_profile.get(k) if k in PROFILE_TEXT else _value(source_profile,k)) for k in PROFILE_FIELDS|{'geometry','code_family','code_edition'})
        adopted=(_num(override.get('adopted_rate_mm_year'),True) if 'adopted_rate_mm_year' in override
                 else _num(row['apparent_rate_mm_year'],True))
        inputs={};input_trace={};rule=override.get('rule') or config.get('rule')
        mode=config.get('basis','provided')
        if design_changed and mode=='provided':
            if 'required_thickness_mm' not in override:required=None
            pressure=None
            issues.append('SOURCE_MINIMUM_CONFIGURATION_CHANGED')
        source_life_basis=None
        if p:
            inputs,input_trace,input_issues=self._inputs(p,override,config);issues.extend(input_issues)
            if not rule:
                rule='VIII_SHELL' if p['geometry']=='shell' else 'B31_8_841_1_1' if p['geometry']=='straight_pipe' and p['code_family']=='ASME B31.8' else 'B31_3_304_1_2' if p['geometry']=='straight_pipe' and p['code_family']=='ASME B31.3' else 'B31_4_403_2_1' if p['geometry']=='straight_pipe' and p['code_family']=='ASME B31.4' else None
            geometry_unsupported=p['geometry'] in {'nozzle','elbow','tee','reducer','branch','unknown'}
            if geometry_unsupported:issues.append('GEOMETRY_RULE_UNSUPPORTED')
            if not config.get('confirm_rules'):rule=None;issues.append('DESIGN_SCOPE_NOT_CONFIRMED')
            elif geometry_unsupported:rule=None
            elif p['geometry']=='head_unspecified' and rule not in {'VIII_UG32_ELLIP','VIII_UG32_TORI'}:rule=None;issues.append('HEAD_GEOMETRY_REQUIRED')
            elif (p['family']=='separator') != bool(rule and rule.startswith('VIII')):rule=None;issues.append('RULE_FAMILY_MISMATCH')
        if rule and p:
            code_for_rule='ASME VIII-1' if rule.startswith('VIII_') else {'B31_3':'ASME B31.3','B31_4':'ASME B31.4','B31_8':'ASME B31.8'}.get(rule[:5])
            if code_for_rule!=p.get('code_family'):rule=None;issues.append('RULE_CODE_MISMATCH')
        if p and not p.get('code_edition'):
            issues.append('CODE_EDITION_REQUIRED')
            if mode=='recalculate':rule=None
        if p and p.get('code_edition'):
            supplied={'ASME B31.8':'2025','ASME B31.3':'2024','ASME B31.4':'2025','ASME VIII-1':'2025'}.get(p.get('code_family'))
            if supplied and p['code_edition']!=supplied:
                issues.append('CODE_EDITION_REFERENCE_UNAVAILABLE')
                if mode=='recalculate':rule=None
        if mode=='recalculate':
            required=None;pressure=None
            if rule:
                values=[]
                for candidate in (('VIII_UG27_HOOP','VIII_UG27_LONG') if rule=='VIII_SHELL' else (rule,)):
                    try:
                        result=pressure_thickness(candidate,inputs)
                        if result['value'] is not None:values.append(Decimal(result['value']))
                        else:issues.extend(result['issues'])
                    except (ValueError,InvalidOperation,KeyError) as exc:issues.append('PRESSURE_INPUTS: '+str(exc))
                if values:pressure=max(values)
            if structural is None:issues.append('STRUCTURAL_MINIMUM_REQUIRED')
            elif pressure is not None:required=max(pressure,structural)
        elif required is None and pressure is not None:
            if structural is None and mode=='provided':
                source_life_basis=pressure
                issues.append('GOVERNING_MINIMUM_NOT_ESTABLISHED')
            elif structural is None:issues.append('STRUCTURAL_MINIMUM_REQUIRED')
            else:required=max(pressure,structural)
        life_required=required if required is not None else source_life_basis
        if life_required is None:issues.append('REQUIRED_THICKNESS_MISSING')
        if adopted is None:issues.append('ADOPTED_RATE_REQUIRED')
        if 'THICKNESS_INCREASE_REVIEW' in issues and not config.get('allow_increase'):
            issues.append('ADOPTED_RATE_POLICY_REVIEW');adopted=None
        interval=(p or {}).get('interval_policy') or {}
        fraction=override.get('interval_fraction',interval.get('fraction',.5));cap=override.get('interval_cap_years',interval.get('cap_years',10))
        if config.get('workspace_review') and not interval and not {'interval_fraction','interval_cap_years'}<=set(override):
            fraction=cap=None;issues.append('INSPECTION_POLICY_REQUIRED')
        interval_field=(p or {}).get('fields',{}).get('selected_interval_years',{})
        inherited_interval_policy=(p or {}).get('interval_policy_basis')=='neighbor_formula'
        selected_interval=(override.get('selected_interval_years') if 'selected_interval_years' in override else
                           None)
        manual_interval_override='selected_interval_years' in override
        manual_selected_interval=manual_interval_override
        if manual_selected_interval and selected_interval is None:
            issues.append('MANUAL_INTERVAL_OVERRIDE_INVALID')
        schedule_field=(p or {}).get('fields',{}).get('scheduled_date',{})
        cached_schedule=schedule_field.get('value')
        scheduled_date=None
        if config.get('confirm_records') and cached_schedule not in (None,'') and scheduled_date is None:
            issues.append('SOURCE_SCHEDULE_CELL_IS_NOT_A_DATE')
        forecast_policy=(p or {}).get('forecast_policy') or {}
        allowance=override.get('allowance_mm')
        forecast=override.get('forecast_years')
        factor=override.get('forecast_factor')
        if factor is None:
            factor=(forecast_policy.get('factor',2) if manual_selected_interval else 1)
        year_days=override.get('year_days') or config.get('year_days') or (p or {}).get('year_days') or '365.2425'
        next_inspection_years=None
        if manual_selected_interval:next_inspection_years=selected_interval
        else:next_inspection_years='remaining_life'
        if blocked:required=adopted=None;rule=None
        row.update(required_thickness_mm=str(required) if required is not None else None,pressure_thickness_mm=str(pressure) if pressure is not None else None,
                   adopted_rate_mm_year=str(adopted) if adopted is not None else None,required_basis='recalculated draft pressure plus structural minimum' if mode=='recalculate' else 'provided governing source record' if _num(raw('required_thickness_mm'),True) is not None else 'provided pressure candidate plus explicit structural minimum' if structural is not None else 'source pressure-thickness basis for remaining-life estimate; governing minimum not established',
                   rule=rule,maximum_interval_years=None,selected_interval_years=str(selected_interval) if selected_interval is not None else None,
                   scheduled_due_date=scheduled_date,next_inspection_years=str(next_inspection_years) if next_inspection_years is not None else None,forecast_policy=forecast_policy,
                   input_trace=dict(history=dict(formula='(previous thickness - current thickness) / elapsed years',source_reference='API 570 fifth edition 7.1.2',previous_date=old['inspection_date'] if old else None,current_date=current['inspection_date'] if current else None,elapsed_basis='calendar months / 12' if old and current and len(old.get('inspection_date') or '')==len(current.get('inspection_date') or '')==7 else 'elapsed days / year_days'),profile_fields=(p or {}).get('fields',{}),normalized_design=input_trace,design_inputs=inputs,overrides=override,basis=mode,interval_policy=dict(fraction=fraction,cap_years=cap),forecast_policy=forecast_policy,year_days=year_days,source_rate_selected=False,rate_basis='manual override' if 'adopted_rate_mm_year' in override else 'calculated historical CR'))
        values=outputs(row['current_thickness_mm'] if current and current.get('review_status')!='excluded' else None,life_required,adopted,row['inspection_date'],year_days,fraction,cap,
                       'VIII_UG27_HOOP' if rule=='VIII_SHELL' else rule,inputs,allowance,forecast,factor,selected_interval,scheduled_date,next_inspection_years,manual_interval_override,manual_selected_interval)
        if rule=='VIII_SHELL':
            other=outputs(row['current_thickness_mm'],life_required,adopted,row['inspection_date'],year_days,fraction,cap,'VIII_UG27_LONG',inputs,allowance,forecast,factor,selected_interval,scheduled_date,next_inspection_years,manual_interval_override,manual_selected_interval)
            for key in ('mawp_MPa','forecast_mawp_MPa'):
                if values[key] is not None and other[key] is not None:
                    values[key]=str(min(Decimal(values[key]),Decimal(other[key])));values['trace'][key]['longitudinal_check']=other['trace'][key]
                else:values[key]=None;values['issues'][key]+=other['issues'][key]
        row['maximum_interval_years']=values['maximum_inspection_interval_years']
        if 'SELECTED_INTERVAL_EXCEEDS_CALCULATED_MAXIMUM' in values['issues']['inspection_interval_years']:
            issues.append('SELECTED_INTERVAL_EXCEEDS_CALCULATED_MAXIMUM')
        for key in ('thickness_margin_mm','remaining_life_years','inspection_interval_years','maximum_inspection_interval_years','due_date','mawp_MPa','forecast_mawp_MPa'):
            row[key]=values[key]
            row['output_readiness'][key]=dict(state='evaluated' if values[key] is not None else 'withheld',issues=values['issues'][key])
        if required is not None and current and _num(_current(current)) is not None and _num(_current(current))<=required:issues.append('BELOW_OR_AT_REQUIRED_THICKNESS')
        row['outputs']=values
        done=sum(row[k] is not None for k in ('remaining_life_years','inspection_interval_years','due_date','mawp_MPa','forecast_mawp_MPa'))
        row['evaluation_status']='NEEDS_REVIEW' if blocked else 'EVALUATED' if done==5 else 'PARTIAL' if done else 'MISSING_INPUTS'
        row['issues']=list(dict.fromkeys(issues))
        return row

    def evaluate(self,comparison_id,expected_revision,options,preview_token=None):
        if not options.get('confirm_records'):raise ValueError('Confirm the proposed component records and their applicability before batch evaluation')
        with _LOCK,connection(self.path) as db:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            if int(expected_revision)!=self.flow.revision():raise ValueError('Project changed. Refresh the batch preview.')
            original=self.flow.comparison(comparison_id)
            if original['stale']:raise ValueError('Inspection inputs changed. Refresh the batch preview before confirming its assignments.')
            preview=self.preview(comparison_id,options.get('profile_sheet'),options)
            if preview_token and preview_token!=preview['preview_token']:raise ValueError('Component assignments changed. Refresh the batch preview.')
            config=preview['settings'];config.update(options)
            for value,selection in [(options.get('previous_date'),original['baseline']),(options.get('current_date'),original['current_selection'])]:
                if value and {r['inspection_date'] for r in self.flow._selection(*selection)}!={value}:
                    self.service.resolve_campaign_date(*selection,value,'Local batch reviewer','Inspection event date supplied for batch evaluation',_expected_revision=self.flow.revision())
            comp=original
            if self.flow.comparison(comparison_id)['stale']:
                comp=self.flow.rebuild(comparison_id,self.flow.revision(),'Local batch reviewer','Refresh explicitly supplied campaign dates for batch')
                comparison_id=comp['id']
            profiles=[p for p in self.profiles(comp['current_selection'][0]) if p['sheet']==config['profile_sheet']]
            assignments=self._assign(comp,profiles,config)
            rows=[self._calculate_row(item,config) for item in assignments]
            current_ids={r['observation_id'] for r in self.flow._selection(*comp['current_selection'])}
            if current_ids!={r['current_id'] for r in rows if r['current_id']}:raise ValueError('Batch coverage did not reconcile to current observations')
            result=dict(id=str(uuid.uuid4()),comparison_id=comparison_id,asset=comp['asset'],input_revision=self.flow.revision(),status='DRAFT / NOT VALIDATED',rule_version=VERSION,
                        profile_sheet=config['profile_sheet'],settings=config,rows=rows,source_snapshot=comp,profiles=profiles,
                        summary=dict(current=len(current_ids),life_evaluated=sum(r['remaining_life_years'] is not None for r in rows),interval_evaluated=sum(r['inspection_interval_years'] is not None for r in rows),mawp_evaluated=sum(r['mawp_MPa'] is not None for r in rows),date_evaluated=sum(r['due_date'] is not None for r in rows),issues=dict(Counter(i for r in rows for i in r['issues']))))
            with self.flow.change('Calculate component batch evaluation',inputs=False,expected=self.flow.revision(),actor='Local batch reviewer',reason='Component-specific source profiles and explicit grouped policy') as tx:
                tx.execute('INSERT OR REPLACE INTO wf_batch_settings VALUES(?,?)',(comparison_id,json.dumps(config)))
                tx.execute('INSERT INTO wf_batches VALUES(?,?,0)',(result['id'],json.dumps(result)))
            return result
