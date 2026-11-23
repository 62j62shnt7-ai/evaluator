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

ADAPTER_VERSION='records-10'
NUMERIC_OVERRIDES={'required_thickness_mm','adopted_rate_mm_year','structural_minimum_mm','allowance_mm','interval_fraction','interval_cap_years','selected_interval_years','forecast_years','forecast_factor','year_days','F_class','E_weld','T_temp','E_quality','W_reduction','Y_coefficient','F_design','E_joint'}
PROFILE_FIELDS={'material','P_psi','temperature_F','S_allow_psi','SMYS_psi','D_outside_in','D_inside_in','nominal_thickness_mm','schedule','nps'}
PROFILE_TEXT={'component','geometry','code_family','code_edition','segment','product_form','material_thickness_mm','material_condition_reference'}
NUMERIC_OVERRIDES.update({'P_psi','temperature_F','S_allow_psi','SMYS_psi','D_outside_in','D_inside_in','nominal_thickness_mm'})
TEXT_OVERRIDES={'profile_id','rule','code_edition','material','geometry','code_family','segment','schedule','nps','reviewed','reconcile_conflict','review_note','dimension_reference','component','material_reference','source_config_reference','allow_increase','product_form'}
TEXT_OVERRIDES.update({'code_evidence','code_owner_confirmed'})
TEXT_OVERRIDES.update({'code_asset_type', 'gas_basic_class', 'pipe_method'})
TEXT_OVERRIDES.add('api570_ut_class')
TEXT_OVERRIDES.add('fitting_life_reference')
TEXT_OVERRIDES.add('inspection_code_reference')
NUMERIC_OVERRIDES.add('material_thickness_mm')
TEXT_OVERRIDES.add('material_condition_reference')
NUMERIC_OVERRIDES.update({'fitting_pressure_psi','fitting_minimum_mm','fitting_interval_years','bend_radius_in'})
TEXT_OVERRIDES.update({'fitting_minimum_basis','fitting_reference','fitting_geometry','bend_position','bend_design_reference','bend_tag','qualification_points','qualification_reference','qualification_temperature_F'})
TEXT_OVERRIDES.update({'qualification_tag','qualification_location_key','qualification_reviewed'})
TEXT_OVERRIDES.add('workbook_code_correction_reference')
TEXT_OVERRIDES.add('sleeve_assessment_record')
CODE_DEPENDENT_INPUTS = {
    'rule', 'pipe_method', 'E_joint', 'E_quality', 'W_reduction', 'Y_coefficient',
    'F_class', 'F_design', 'E_weld', 'T_temp', 'gas_basic_class', 'api570_ut_class',
    'required_thickness_mm', 'fitting_life_reference', 'interval_fraction', 'interval_cap_years',
    'selected_interval_years', 'forecast_years', 'forecast_factor', 'inspection_code_reference',
}
RULES={'VIII_SHELL','VIII_UG27_HOOP','VIII_UG27_LONG','VIII_UG32_ELLIP','VIII_UG32_TORI','B31_3_304_1_2','B31_4_403_2_1','B31_8_841_1_1'}


def _hash(value):return hashlib.sha256(json.dumps(value,sort_keys=True,default=str).encode()).hexdigest()
def _num(value,positive=False, *, signed=False):
    if value in ('',None) or isinstance(value,bool):return None
    try:n=Decimal(str(value))
    except (InvalidOperation,ValueError):return None
    return n if n.is_finite() and (signed or n>=0) and (not positive or n>0) else None

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
        db.execute("UPDATE wf_batches SET stale=1 WHERE stale=0 AND json_extract(payload, '$.comparison_id')=?", (cid,))

    def latest_result(self, comparison_id, profile_sheet):
        with connection(self.path) as db:
            row = db.execute(
                """SELECT payload, stale FROM wf_batches
                   WHERE json_extract(payload, '$.comparison_id')=?
                     AND json_extract(payload, '$.profile_sheet') IS ?
                   ORDER BY rowid DESC LIMIT 1""",
                (comparison_id, profile_sheet),
            ).fetchone()
        if row is None:
            return []
        result = json.loads(row['payload'])
        result.pop('source_snapshot', None)
        result['stale'] = bool(row['stale']) or result.get('rule_version') != VERSION
        return [result]

    def result_by_id(self, result_id):
        with connection(self.path) as db:
            row = db.execute('SELECT payload, stale FROM wf_batches WHERE id=?', (result_id,)).fetchone()
        if row is None:
            return None
        result = json.loads(row['payload'])
        result['stale'] = bool(row['stale']) or result.get('rule_version') != VERSION
        return result

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
        from evaluator.importing.ut_defaults import UTTableIndex, defaults
        if key not in self._nominal_sheets:
            sheet = self.service.imported_sheet(*key)
            self._nominal_sheets[key] = (
                UTTableIndex(sheet)
                if sheet and str(sheet['cells'].get('C2', {}).get('value', '')).strip().upper() == 'MATERIAL'
                else sheet
            )
        sheet=self._nominal_sheets[key]
        if not sheet:return None
        row=re.search(r'\d+',reading['cell'])[0]
        if isinstance(sheet, UTTableIndex):
            return defaults(sheet, reading['cell'], '').get('nps')
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
                current = item['current']
                same_row = [p for p in candidates if p['source_id'] == current['source_id']
                            and p['sheet'] == current['sheet_name']
                            and p['fields'].get('current_mm', {}).get('cell') == current['cell']]
                if len(same_row) == 1 and same_row[0]['id'] not in used:
                    assigned[current['observation_id']] = (same_row[0], 'Same worksheet and current UT cell')
                    used.add(same_row[0]['id'])
                    continue
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
                chosen = None if config.get('selected_ut_only') else config.get('row_overrides',{}).get(oid,{}).get('profile_id')
                if chosen:
                    profile=next((p for p in profiles if p['id']==chosen),None)
                    if profile is None:raise ValueError('Manual assignment must use a record from the selected source scenario')
                    basis='Manual component record assignment'
            detected = self.flow.match_identity(current)['component'] if current else 'unknown'
            item.update(profile=profile,assignment_basis=basis,candidates=candidates,nominal_size=self._nominal(current),
                        detected_geometry=detected)
        if config.get('workspace_review') and comp.get('baseline_per_location'):
            source_id, sheet_name, _ = comp['current_selection']
            history = defaultdict(list)
            for reading in self.service.readings():
                if (reading['source_id'] == source_id and reading['sheet_name'] == sheet_name
                        and reading['raw_unit'] == 'mm' and reading.get('inspection_date')
                        and reading.get('review_status') != 'excluded'):
                    identity_key = self.flow._key(reading)
                    if identity_key:
                        history[identity_key].append(reading)
            for item in measurements:
                current, previous = item['current'], item['previous']
                if not current or not previous or not previous.get('inspection_date'):
                    continue
                key = self.flow._key(current)
                if not key or key != self.flow._key(previous):
                    continue
                earlier = [reading for reading in history[key]
                           if reading['inspection_date'][:7] < previous['inspection_date'][:7]]
                earliest = min((reading['inspection_date'][:7] for reading in earlier), default=None)
                matches = [reading for reading in earlier if reading['inspection_date'][:7] == earliest]
                if len(matches) == 1:
                    item['initial'] = matches[0]
        return measurements

    @staticmethod
    def _group(profile):
        if not profile:return 'unmapped'
        key=[profile.get(k) for k in ('code_family','code_edition','geometry','product_form','material_thickness_mm','material_condition_reference')]+[_value(profile,k) for k in ('material','S_allow_psi','SMYS_psi','P_psi')]
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

    def preview(self,comparison_id,profile_sheet=None,options=None, *, draft=None):
        comp=self.flow.comparison(comparison_id);config=self.settings(comparison_id)
        config['selected_ut_only'] = bool(comp.get('selected_ut_only'))
        profiles=[] if config['selected_ut_only'] else self.profiles(comp['current_selection'][0])
        selected=comp['current_selection'][1] if config['selected_ut_only'] else self._select_sheet(comp,profiles,profile_sheet or config.get('profile_sheet'))
        if not config['selected_ut_only'] and config.get('profile_sheet') and config['profile_sheet']!=selected:
            scenarios=deepcopy(config.get('scenarios',{}))
            scenarios[config['profile_sheet']]={k:deepcopy(v) for k,v in config.items() if k!='scenarios'}
            config=dict(scenarios.get(selected,{'group_overrides':{},'row_overrides':{}}),scenarios=scenarios)
        config.update({k:v for k,v in (options or {}).items() if k not in {'group_overrides','row_overrides'}})
        config['selected_ut_only'] = bool(comp.get('selected_ut_only'))
        config['straight_pipe_fitting_screen'] = bool(comp.get('straight_pipe_fitting_screen'))
        config['profile_sheet']=selected
        chosen=[p for p in profiles if p['sheet']==selected]
        assignments=self._assign(comp,chosen,config)
        proposal=dict(config,confirm_records=True,confirm_history=True)
        if draft is not None:
            oid, values, readings = draft
            item = next((item for item in assignments if item['current'] and
                         item['current']['observation_id'] == oid), None)
            if item is None:
                raise ValueError('Location is unavailable in this comparison.')
            proposal = deepcopy(proposal)
            overrides = proposal.setdefault('row_overrides', {}).setdefault(oid, {})
            overrides.update(values)
            item = dict(item)
            for key in ('current', 'previous'):
                if key in readings and item[key]:
                    item[key] = dict(item[key], effective_value=readings[key])
            return self._calculate_row(item, proposal)
        rows=[self._calculate_row(item,proposal) for item in assignments]
        groups={}
        for row in rows:
            p=row['profile'];gid=row['group_id']
            if p and gid not in groups:groups[gid]=dict(id=gid,material=_value(p,'material'),geometry=p['geometry'],code_family=p['code_family'],code_edition=p.get('code_edition'),pressure_psi=_value(p,'P_psi'),count=0,ready=0)
            if p:groups[gid]['count']+=1;groups[gid]['ready']+=row['remaining_life_years'] is not None
        token=_hash([[r['current_id'],r['previous_id'],r['current_thickness_mm'],r['location'],r['profile_id'],r['profile']] for r in rows])
        return dict(comparison=comp,profile_sheet=selected,sheets=sorted({p['sheet'] for p in profiles}),profiles=chosen,rows=rows,groups=list(groups.values()),settings=config,preview_token=token,
                    counts=dict(current=sum(r['current_id'] is not None for r in rows),life_ready=sum(r['remaining_life_years'] is not None for r in rows),historical_ready=sum(r['apparent_rate_mm_year'] is not None for r in rows),issues=dict(Counter(i for r in rows for i in r['issues']))))

    def apply_overrides(self,comparison_id,expected_revision,group_ids,row_ids,values,profile_sheet=None,per_row_values=None, *, assign_code=False):
        clean={k:str(v).strip() for k,v in values.items() if v not in ('',None) or (k=='code_edition' and v=='')}
        per_row_values={oid:{k:str(v).strip() for k,v in row_values.items() if v not in ('',None) or k.startswith('qualification_')} for oid,row_values in (per_row_values or {}).items()}
        allowed=NUMERIC_OVERRIDES|TEXT_OVERRIDES
        if (not clean and not per_row_values) or not set(clean)<=allowed or any(not set(row_values)<=allowed for row_values in per_row_values.values()):raise ValueError('Select valid grouped input changes')
        for k,v in {**clean,**{k:v for row_values in per_row_values.values() for k,v in row_values.items()}}.items():
            if k in NUMERIC_OVERRIDES and _num(v) is None:raise ValueError(k+' must be finite and nonnegative')
        if clean.get('nps') and clean.get('schedule') == 'Unspecified' and 'nominal_thickness_mm' not in clean:
            clean.update(nominal_thickness_mm=None, dimension_reference='')
        elif clean.get('schedule') == 'Custom':
            clean.setdefault('dimension_reference', '')
        for key in ('reviewed','reconcile_conflict'):
            if key in clean and clean[key] not in {'yes','no'}:raise ValueError('Invalid review decision')
        if any('code_owner_confirmed' in values and values['code_owner_confirmed'] not in {'yes','no'} for values in [clean,*per_row_values.values()]):raise ValueError('Invalid code applicability confirmation')
        from evaluator.engineering.reference_rules import GAS_BASIC_CLASS_F
        for changes in (clean, *per_row_values.values()):
            if changes.get('gas_basic_class') in GAS_BASIC_CLASS_F and 'F_class' not in changes:
                changes['F_class'] = None
        all_values={**clean,**{k:v for row_values in per_row_values.values() for k,v in row_values.items()}}
        if all_values.get('geometry') and all_values['geometry'] not in {'straight_pipe','elbow','tee','reducer','branch','nozzle','shell','cylindrical_shell','ellipsoidal_head_2to1','standard_torispherical_head','head_unspecified','unknown'}:raise ValueError('Unsupported component geometry')
        if all_values.get('rule') and all_values['rule'] not in RULES:raise ValueError('Unsupported rule')
        preview=self.preview(comparison_id,profile_sheet)
        if not set(group_ids)<={g['id'] for g in preview['groups']} or not (set(row_ids)|set(per_row_values))<={r['current_id'] for r in preview['rows'] if r['current_id']}:raise ValueError('Selected input scope changed; refresh the batch preview')
        if not group_ids and not row_ids and not per_row_values:raise ValueError('Choose at least one compatible group or location')
        with self.flow.change('Set grouped component inputs',inputs=False,expected=expected_revision,actor='Local batch reviewer',reason='Explicit defaults/overrides for selected component scope') as db:
            original_row_overrides=deepcopy(preview['settings'].get('row_overrides',{}))
            config=deepcopy(preview['settings'])
            config['profile_sheet']=preview['profile_sheet']
            if assign_code:
                config['basis'] = 'assigned'
            for scope,ids in [('group_overrides',group_ids),('row_overrides',row_ids)]:
                for identifier in ids:config.setdefault(scope,{}).setdefault(identifier,{}).update(clean)
            for identifier,row_values in per_row_values.items():
                config.setdefault('row_overrides',{}).setdefault(identifier,{}).update(row_values)
            # Compare with the previous effective context, not just the original
            # source record: earlier lookup/manual overrides must also expire.
            context_keys=('material','temperature_F','code_family','code_edition','geometry','product_form','material_thickness_mm','material_condition_reference')
            for row in preview['rows']:
                oid=row['current_id']
                if not oid or not (oid in row_ids or oid in per_row_values or row['group_id'] in group_ids):continue
                row_clean={**clean,**per_row_values.get(oid,{})}
                profile=row['profile'] or {}
                entry=config.setdefault('row_overrides',{}).setdefault(oid,{})
                def previous(key):
                    if key == 'code_asset_type':
                        return profile.get(key)
                    return profile.get(key) if key in PROFILE_TEXT else _value(profile, key)

                if assign_code and any(str(row_clean[key]) != str(previous(key))
                                       for key in ('code_family', 'code_edition', 'code_asset_type')):
                    # Row-level blanks also mask incompatible inherited group inputs.
                    for key in CODE_DEPENDENT_INPUTS - row_clean.keys():
                        if key in entry or key in (config.get('group_overrides', {}).get(row['group_id'], {})):
                            entry[key] = None
                    if 'rule' not in row_clean:
                        entry['rule'] = None
                    entry['reviewed'] = 'no'
                changed=any(key in row_clean and str(row_clean[key])!=str(previous(key)) and (oid in row_ids or key in per_row_values.get(oid,{}) or key not in original_row_overrides.get(oid,{})) for key in context_keys)
                if changed:
                    for key in ('S_allow_psi','SMYS_psi'):
                        if key not in row_clean:entry[key]=None
                        elif oid not in row_ids and key not in per_row_values.get(oid, {}):entry.pop(key,None)
                    if 'reviewed' not in row_clean:entry['reviewed']='no'
                    try:
                        references = json.loads(original_row_overrides.get(oid, {}).get('source_config_reference', '{}'))
                    except (TypeError, ValueError):
                        references = {}
                    if isinstance(references, dict):
                        for key in {'E_quality', 'W_reduction', 'Y_coefficient'} & references.keys():
                            if key not in row_clean:
                                entry.pop(key, None)
                                references.pop(key)
                        if assign_code:
                            references = {key: value for key, value in references.items()
                                          if key not in CODE_DEPENDENT_INPUTS or entry.get(key) is not None}
                        if 'source_config_reference' not in row_clean:
                            entry['source_config_reference'] = json.dumps(references, sort_keys=True)
                if (changed or {'S_allow_psi','SMYS_psi'}&set(row_clean)) and 'material_reference' not in row_clean:entry['material_reference']=''
                elif changed and oid not in row_ids and 'material_reference' not in per_row_values.get(oid, {}):
                    entry.pop('material_reference', None)
            db.execute('INSERT OR REPLACE INTO wf_batch_settings VALUES(?,?)',(comparison_id,json.dumps(config)))
            self._stale(db,comparison_id)

    def _inputs(self,profile,overrides,config):
        issues=[];trace={}
        def raw(key):
            return _value(profile, key) if key in {'S_allow_psi', 'temperature_F'} else overrides.get(key, _value(profile, key))
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
        from evaluator.engineering.references import b313_reference_factors
        for key, (value, reference) in b313_reference_factors(
            raw('material'), profile.get('geometry'), profile.get('code_family'),
            profile.get('code_edition'), raw('temperature_F'),
        ).items():
            if key not in inputs:
                inputs[key] = value
                trace[key] = dict(value=value, reference=reference)
        gas_2025 = profile.get('code_family') == 'ASME B31.8' and profile.get('code_edition') == '2025'
        if (profile.get('code_family') == 'ASME B31.4' and profile.get('code_edition') == '2025'
                and profile.get('geometry') == 'straight_pipe'
                and 'SMYS_MPa' not in inputs and config.get('confirm_rules')):
            from evaluator.engineering.reference_rules import LIQUID_PIPE_SMYS, LIQUID_PIPE_SMYS_REFERENCE
            grade = LIQUID_PIPE_SMYS.get(raw('material'))
            if grade:
                smys, line = grade
                inputs['SMYS_MPa'] = str(convert(smys, 'psi', 'MPa'))
                trace['SMYS_MPa'] = dict(reference=f'{LIQUID_PIPE_SMYS_REFERENCE}, line {line}',
                                        value_psi=smys, converted=inputs['SMYS_MPa'], unit='MPa',
                                        material=raw('material'))
        if gas_2025 and 'SMYS_MPa' not in inputs and config.get('confirm_rules'):
            from evaluator.engineering.reference_rules import GAS_SMYS_REFERENCE, gas_pipe_smys
            smys = gas_pipe_smys(raw('material'), profile.get('product_form'))
            if smys is not None:
                inputs['SMYS_MPa'] = str(convert(smys, 'psi', 'MPa'))
                trace['SMYS_MPa'] = dict(**GAS_SMYS_REFERENCE, value_psi=smys,
                                        converted=inputs['SMYS_MPa'], unit='MPa',
                                        material=raw('material'), product_form=profile['product_form'])
        has_temperature = raw('temperature_F') not in ('', None)
        if gas_2025 and has_temperature and 'T_temp' not in inputs and config.get('confirm_rules'):
            from evaluator.engineering.reference_rules import GAS_TEMPERATURE_REFERENCE, gas_temperature_factor
            try:
                factor = str(gas_temperature_factor(raw('temperature_F')))
            except (ValueError, InvalidOperation):
                issues.append('B31_8_TEMPERATURE_REFERENCE_UNAVAILABLE')
            else:
                inputs['T_temp'] = factor
                trace['T_temp'] = dict(**GAS_TEMPERATURE_REFERENCE, value=factor,
                                       temperature_F=str(raw('temperature_F')))
        if gas_2025 and 'F_class' not in inputs and config.get('confirm_rules'):
            from evaluator.engineering.reference_rules import GAS_BASIC_CLASS_F, GAS_CLASS_REFERENCE
            location_class = overrides.get('gas_basic_class')
            factor = GAS_BASIC_CLASS_F.get(location_class)
            if factor is not None:
                inputs['F_class'] = factor
                trace['F_class'] = dict(**GAS_CLASS_REFERENCE, value=factor, location_class=location_class)
        proposal=profile.get('factor_candidates',{}).get('design_factor')
        use_workbook_factors = proposal and config.get('confirm_rules') and not config.get('workspace_review')
        if 'F_class' not in inputs and use_workbook_factors:
            inputs['F_class'] = str(proposal['value'])
            trace['F_class'] = dict(source_proposal=proposal)
        if use_workbook_factors and profile.get('code_family') == 'ASME B31.8':
            # This proposal exists only for the recognized source expression
            # t=P*D/(2*SMYS*0.8). Its omitted E and T multipliers are unity.
            for factor in ('E_weld','T_temp'):
                if factor not in inputs and not (factor == 'T_temp' and has_temperature):
                    inputs[factor]='1'
                    trace[factor]=dict(value='1',source_cell=proposal['cell'],source_formula=proposal['raw'],
                                       basis='unit multiplier in recognized workbook pressure expression')
        return inputs,trace,issues

    def _calculate_row(self,item,config):
        current,old,pair,p=item['current'],item['previous'],item['pair'],item['profile']
        gid=self._group(p);oid=current['observation_id'] if current else None
        override=dict(config.get('group_overrides',{}).get(gid,{}));override.update(config.get('row_overrides',{}).get(oid,{}))
        if config.get('selected_ut_only') and current:
            self._exclude_other_sheet_inputs(override, current['sheet_name'])
        config=dict(config)
        if config.get('workspace_review'):config.update(confirm_records=False,confirm_history=False,confirm_rules=False)
        if override.get('reviewed')=='yes':
            config.update(confirm_records=True,confirm_history=True,confirm_rules=True)
        elif config.get('selected_ut_only') and override.get('code_owner_confirmed') == 'yes':
            # The selected UT sheet supplies measurements only. Saved manual
            # inputs can produce a draft under the explicitly confirmed code.
            config.update(confirm_records=True, confirm_rules=True)
        if override.get('reconcile_conflict')=='yes':config['confirm_conflicts']=True
        if override.get('allow_increase')=='yes' and override.get('review_note'):config['allow_increase']=True
        detected_geometry = item.get('detected_geometry', 'unknown')
        if p is None and (set(override) & PROFILE_FIELDS or 'geometry' in override
                          or override.get('code_owner_confirmed') == 'yes'):
            vessel = override.get('code_family') == 'ASME VIII-1'
            p=dict(id='manual-'+str(oid),fields={},geometry='unknown' if vessel else detected_geometry,family='separator' if vessel else 'pipeline',code_family='',code_edition=None,section='',component='',row=None,sheet=current['sheet_name'] if current else '',source_id=current['source_id'] if current else '')
        source_profile=p
        if p is not None:
            p=deepcopy(p)
            if p['family'] == 'pipeline' and p['geometry'] == 'unknown':
                p['geometry'] = detected_geometry
            for key in PROFILE_FIELDS:
                if key in override:
                    reference=override.get('dimension_reference') if key in {'D_outside_in','nominal_thickness_mm','nps','schedule'} else override.get('material_reference') if key=='S_allow_psi' else None
                    p.setdefault('fields',{})[key]=dict(value=override[key],kind='reference_derived' if reference else 'manual_override',unit=(p.get('fields',{}).get(key) or {}).get('unit'),source_record=(source_profile.get('fields',{}).get(key)),basis=reference or 'Explicit batch configuration')
            for key in PROFILE_TEXT:
                if key in override:p[key]=override[key]
            if 'code_evidence' in override:p['code_evidence']=override['code_evidence']
            if 'code_owner_confirmed' in override:p['code_owner_confirmed']=override['code_owner_confirmed']=='yes'
            if 'code_asset_type' in override:p['code_asset_type']=override['code_asset_type']
            context_changed=any(key in override and str(override[key])!=str(source_profile.get(key) if key in PROFILE_TEXT else _value(source_profile,key)) for key in ('material','code_family','code_edition','temperature_F','geometry','product_form','material_thickness_mm','material_condition_reference'))
            if context_changed:
                for key in ('S_allow_psi','SMYS_psi'):
                    if key not in override:p.setdefault('fields',{})[key]=dict(value=None,kind='invalidated',basis='Material/code/temperature changed; property must be supplied for this context')
            if _value(p, 'S_allow_psi') in (None, ''):
                from evaluator.engineering.references import lowest_material_stress, material_stress
                args = (_value(p, 'material'), p['geometry'], p.get('code_family'), p.get('code_edition'))
                product = p.get('product_form')
                conditions = dict(material_thickness_mm=p.get('material_thickness_mm'),
                                  material_condition_reference=p.get('material_condition_reference'))
                temperature = _value(p, 'temperature_F')
                if temperature in (None, ''):
                    stress = lowest_material_stress(*args, product, **conditions)
                    if stress:
                        p['fields']['temperature_F'] = dict(
                            value=stress['temperature_F'], kind='reference_derived', unit='F',
                            basis='Lowest eligible library temperature; confirm actual design temperature.',
                        )
                else:
                    stress = material_stress(*args, temperature, product, **conditions)
                if stress:
                    p['fields']['S_allow_psi'] = dict(
                        value=stress['S_allow_psi'], kind='reference_derived', unit='psi',
                        basis=stress['reference'], source_sha256=stress['source_sha256'],
                    )
        row=dict(id=oid or 'history-'+str(pair['id']),pair_id=pair['id'],current_id=oid,previous_id=old['observation_id'] if old else None,
                 detected_geometry=detected_geometry,
                 location=' / '.join(_location(current or old)) if current or old else 'Ambiguous source location',group_id=gid,profile_id=p['id'] if p else None,profile=p,
                 candidate_profile_ids=[candidate['id'] for candidate in item.get('candidates',[])],
                 current_cell=current['cell'] if current else None,previous_cell=old['cell'] if old else None,current_sheet=current['sheet_name'] if current else None,previous_sheet=old['sheet_name'] if old else None,
                 current_thickness_mm=str(_current(current)) if current else None,previous_thickness_mm=str(_current(old)) if old else None,
                 inspection_date=current['inspection_date'] if current else None,previous_inspection_date=old['inspection_date'] if old else None,nominal_size=item['nominal_size'],assignment_basis=item['assignment_basis'],
                 required_thickness_mm=None,pressure_thickness_mm=None,adopted_rate_mm_year=None,apparent_rate_mm_year=None,elapsed_days=None,issues=[],input_trace={},outputs={},output_readiness={})
        issues=row['issues'];blocked=False
        fitting_geometry = (p or {}).get('geometry', detected_geometry)
        if fitting_geometry in {'elbow', 'tee', 'reducer'}:
            self._fitting_progress(row, item, p or {}, override, fitting_geometry,
                                   screen_as_pipe=(config.get('straight_pipe_fitting_screen', False)
                                                   and detected_geometry != 'sleeve_tee'))
        if detected_geometry == 'sleeve_tee':
            row['routing'] = dict(status='SLEEVE_T_REVIEW_REQUIRED', geometry='sleeve_tee')
            if override.get('sleeve_assessment_record'):
                row['sleeve_assessment'] = json.loads(override['sleeve_assessment_record'])
                row['input_trace']['documented_sleeve_assessment'] = row['sleeve_assessment']
                row['routing']['status'] = 'SLEEVE_T_DOCUMENTED_ASSESSMENT'
                row['issues'].append('Sleeve-T has a documented assembly assessment. The app withholds calculated pressure.')
            else:
                row['issues'].append('Sleeve-T requires an as-built drawing, sleeve and carrier details, mapped UT coverage, and an approved pressure assessment.')
            output_keys = ('remaining_life_years','inspection_interval_years','due_date','mawp_MPa','forecast_mawp_MPa')
            row.update(dict.fromkeys(output_keys))
            return self._withheld_row7(row, output_keys)
        is_straight_process_pipe = (p or {}).get('code_family') == 'ASME B31.3' and (p or {}).get('geometry') == 'straight_pipe'
        if (is_straight_process_pipe and override.get('pipe_method') == 'example'
                and (config.get('basis') == 'assigned' or
                     (config.get('workspace_review') and config.get('basis') == 'recalculate'))):
            config['basis'] = 'row7'
        elif config.get('basis') == 'assigned':
            config['basis'] = 'recalculate'
        if config.get('basis') == 'recalculate' and p:
            from evaluator.engineering.fitting_review import CLAUSES
            if (p.get('geometry') in CLAUSES and p.get('code_family') == 'ASME B31.3'
                    and p.get('code_edition') == '2024' and p.get('code_owner_confirmed')):
                result = self._fitting_check(row, item, override)
                progress = result['fitting_progress']
                if not result.get('fitting_check') and progress.get('remaining_life_years') is not None:
                    result['rule'] = 'API 570 §7.2 remaining life'
                    result['remaining_life_years'] = progress['remaining_life_years']
                    result['required_thickness_mm'] = progress['required_wall_mm']
                    result['adopted_rate_mm_year'] = progress['life_rate_mm_year']
                    result['outputs']['remaining_life_years'] = progress['remaining_life_years']
                    result['outputs']['issues']['remaining_life_years'] = []
                    result['outputs']['trace']['remaining_life_years'] = progress['life_trace']
                    result['output_readiness']['remaining_life_years'] = dict(state='evaluated', issues=[])
                return result
        if config.get('basis') == 'row7':
            return self._row7(row, item, override)
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
            if p.get('inspection_date') and p['inspection_date'] != current['inspection_date']:
                issues.append('PROFILE_EVENT_SCOPE_CONFIRMATION')
        route=None
        if p:
            from evaluator.engineering.code_context import CodeContext,route_code
            family=p.get('code_family') or ''
            asset_type=p.get('code_asset_type') or {'ASME B31.3':'process_piping','ASME B31.4':'liquid_transmission',
                        'ASME B31.8':'gas_transmission','ASME VIII-1':'pressure_vessel'}.get(family,'unknown')
            route=route_code(CodeContext(
                component_id=str(p.get('component') or (item.get('key') or [''])[0] or oid or ''),
                asset_type=asset_type,geometry={'shell':'cylindrical_shell'}.get(p.get('geometry'), p.get('geometry') or 'unknown'),
                construction_code=family or None,construction_edition=p.get('code_edition'),
                code_evidence=p.get('code_evidence'),owner_confirmed=bool(p.get('code_owner_confirmed'))))
            row['routing']=dict(status=route.status,code=family or None,edition=p.get('code_edition'),
                                geometry=p.get('geometry'),issues=list(route.issues),
                                candidate_rule_ids=list(route.candidate_rule_ids))
            if route.status!='ROUTE_SELECTED':issues.append('CODE_ROUTING_'+route.status)
        # Historical rates are independent of engineering-record readiness.
        source_year_days=(p or {}).get('year_days')
        year_days=override.get('year_days') or config.get('year_days') or source_year_days or '365.2425'
        selected_ut_pair = (config.get('selected_ut_only') and current and old
                            and (current['source_id'], current['sheet_name']) == (old['source_id'], old['sheet_name'])
                            and self.flow._key(current) is not None and self.flow._key(current) == self.flow._key(old))
        if current and old and pair['kind'] in {'matched','lifecycle_mismatch'} and (pair.get('accepted') or config.get('confirm_history') or selected_ut_pair):
            if any(reading.get('review_status') == 'excluded' for reading in (current, old)):
                issues.append('HISTORY_READING_EXCLUDED')
            elif old['raw_unit']!=current['raw_unit'] or current['raw_unit']!='mm':issues.append('HISTORY_UNIT_MISMATCH')
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
        observed = _num(row['apparent_rate_mm_year'], True)
        initial = item.get('initial')
        long_term = None
        if (is_straight_process_pipe and initial and current and row['apparent_rate_mm_year'] is not None
                and _num(_current(initial), True) is not None and _num(_current(current), True) is not None):
            try:
                initial_days = Decimal(elapsed_days(initial['inspection_date'], current['inspection_date'], year_days))
                if initial_days > 0:
                    long_term = (_num(_current(initial)) - _num(_current(current))) * Decimal(str(year_days)) / initial_days
            except (TypeError, ValueError, InvalidOperation):
                pass
        calculated = max((value for value in (observed, long_term) if value is not None and value > 0), default=None)
        selected_rate = _num(override.get('adopted_rate_mm_year'), True)
        use_selected = 'adopted_rate_mm_year' in override and not (
            is_straight_process_pipe and calculated is not None and 'THICKNESS_INCREASE_REVIEW' not in issues)
        adopted = selected_rate if use_selected else calculated
        rate_basis = ('Reviewed selected rate' if use_selected else 'Calculated from matched UT')
        measured_rate = _num(row['apparent_rate_mm_year'], signed=True)
        selected_fallback = measured_rate is not None and measured_rate <= 0 and selected_rate is not None
        if selected_fallback:
            adopted = selected_rate
            rate_basis = 'Selected rate used because measured corrosion rate is zero or negative'
            if 'THICKNESS_INCREASE_REVIEW' in issues:
                issues.remove('THICKNESS_INCREASE_REVIEW')
        if not use_selected and long_term is not None and calculated == long_term and long_term != observed:
            if not selected_fallback:
                rate_basis = 'Long-term rate gives the shorter draft remaining life'
        inputs={};input_trace={};rule=override.get('rule', config.get('rule'))
        mode=config.get('basis','provided')
        if design_changed and mode=='provided':
            if 'required_thickness_mm' not in override:required=None
            pressure=None
            issues.append('SOURCE_MINIMUM_CONFIGURATION_CHANGED')
        source_life_basis=None
        if p:
            inputs,input_trace,input_issues=self._inputs(p,override,config);issues.extend(input_issues)
            candidates = route.candidate_rule_ids
            if len(candidates) > 1:
                # Shell capacity must include both stress directions.
                allowed_rules = {'VIII_SHELL'}
                default_rule = 'VIII_SHELL'
            else:
                allowed_rules = set(candidates)
                default_rule = candidates[0] if candidates else None
            if p['geometry'] in {'nozzle','elbow','tee','reducer','branch','unknown'}:
                issues.append('GEOMETRY_RULE_UNSUPPORTED')
            if blocked or not config.get('confirm_rules'):
                rule = None
                if not config.get('confirm_rules'):
                    issues.append('DESIGN_SCOPE_NOT_CONFIRMED')
            elif rule and rule not in allowed_rules:
                issues.append('RULE_CODE_MISMATCH')
                rule = None
            else:
                rule = rule or default_rule
        else:
            rule = None
        if p and not p.get('code_edition'):
            issues.append('CODE_EDITION_REQUIRED')
            if mode=='recalculate':rule=None
        if p and p.get('code_edition'):
            supplied={'ASME B31.8':'2025','ASME B31.3':'2024','ASME B31.4':'2025','ASME VIII-1':'2025'}.get(p.get('code_family'))
            if supplied and p['code_edition']!=supplied:
                issues.append('CODE_EDITION_REFERENCE_UNAVAILABLE')
                if mode=='recalculate':rule=None
        pressure_checks = []
        if mode=='recalculate':
            required=None;pressure=None
            if rule:
                values=[]
                for candidate in (('VIII_UG27_HOOP','VIII_UG27_LONG') if rule=='VIII_SHELL' else (rule,)):
                    try:
                        result=pressure_thickness(candidate,inputs)
                        pressure_checks.append(result)
                        if result['value'] is not None:values.append(Decimal(result['value']))
                        else:issues.extend(result['issues'])
                    except (ValueError,InvalidOperation,KeyError) as exc:issues.append('PRESSURE_INPUTS: '+str(exc))
                if len(values) == (2 if rule == 'VIII_SHELL' else 1):
                    pressure=max(values)
            if structural is None:issues.append('STRUCTURAL_MINIMUM_REQUIRED')
            elif pressure is not None:
                mechanical = (_num(override.get('allowance_mm')) or Decimal(0)) if is_straight_process_pipe else Decimal(0)
                required=max(pressure + mechanical, structural)
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
            rate_basis = 'Withheld pending review of increased wall'
        interval=(p or {}).get('interval_policy') or {}
        interval_reference = None
        if interval:
            source_cell = interval.get('source_cell') or p['fields'].get('selected_interval_years', {}).get('cell')
            interval_reference = f"{p['sheet']}!{source_cell}" if source_cell else 'Recognized workbook interval policy'
        ut_class = override.get('api570_ut_class')
        if not ut_class and config.get('selected_ut_only') and p and p.get('code_owner_confirmed'):
            ut_class = 'conservative'
        if (not interval and is_straight_process_pipe and route and route.can_attempt_arithmetic
                and p.get('code_asset_type') in {'process_piping', 'production_flowline'}):
            from evaluator.engineering.reference_rules import API570_UT_CAP_YEARS, API570_UT_POLICY_REFERENCE
            if ut_class in API570_UT_CAP_YEARS:
                interval = {'fraction': '0.5', 'cap_years': API570_UT_CAP_YEARS[ut_class]}
                interval_reference = f'{API570_UT_POLICY_REFERENCE}, Class {ut_class} thickness measurements'
            elif ut_class == 'conservative':
                interval = {'fraction': '0.5', 'cap_years': min(API570_UT_CAP_YEARS.values(), key=Decimal)}
                interval_reference = (
                    f'{API570_UT_POLICY_REFERENCE}, conservative routine-UT planning limit '
                    'across Classes 1–3, pending confirmation of applicability'
                )
        default_fraction, default_cap = (None, None) if config.get('workspace_review') else (.5, 10)
        fraction = override.get('interval_fraction') or interval.get('fraction', default_fraction)
        cap = override.get('interval_cap_years') or interval.get('cap_years', default_cap)
        if config.get('workspace_review') and (fraction is None or cap is None):
            issues.append('INSPECTION_POLICY_REQUIRED')
        try:
            source_refs = json.loads(override.get('source_config_reference') or '{}')
        except (TypeError, ValueError):
            source_refs = {}
        if not isinstance(source_refs, dict):
            source_refs = {}
        policy_trace = dict(fraction=fraction, cap_years=cap, reference=interval_reference)
        for key in ('interval_fraction', 'interval_cap_years'):
            if key in override:
                policy_trace[key + '_reference'] = source_refs.get(key) or 'Reviewed input'
        interval_field=(p or {}).get('fields',{}).get('selected_interval_years',{})
        inherited_interval_policy=(p or {}).get('interval_policy_basis')=='neighbor_formula'
        selected_interval=(override.get('selected_interval_years') if 'selected_interval_years' in override else
                           None)
        manual_interval_override=override.get('selected_interval_years') is not None
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
        inspection_pressure = bool(config.get('workspace_review') and p and p.get('code_family') == 'ASME B31.3')
        if factor is None:
            factor = forecast_policy.get('factor', 2) if inspection_pressure or manual_selected_interval else 1
        year_days=override.get('year_days') or config.get('year_days') or (p or {}).get('year_days') or '365.2425'
        next_inspection_years=None
        if manual_selected_interval:next_inspection_years=selected_interval
        else:next_inspection_years='remaining_life'
        if blocked:required=adopted=None;rule=None
        row.update(required_thickness_mm=str(required) if required is not None else None,pressure_thickness_mm=str(pressure) if pressure is not None else None,
                   adopted_rate_mm_year=str(adopted) if adopted is not None else None,required_basis='recalculated draft pressure plus structural minimum' if mode=='recalculate' else 'provided governing source record' if _num(raw('required_thickness_mm'),True) is not None else 'provided pressure candidate plus explicit structural minimum' if structural is not None else 'source pressure-thickness basis for remaining-life estimate; governing minimum not established',
                   rule=rule,maximum_interval_years=None,selected_interval_years=str(selected_interval) if selected_interval is not None else None,
                   scheduled_due_date=scheduled_date,next_inspection_years=str(next_inspection_years) if next_inspection_years is not None else None,forecast_policy=forecast_policy,
                   input_trace=dict(history=dict(formula='(previous thickness - current thickness) / elapsed years',source_reference='Paired UT readings; see assigned pipeline assessment basis' if (p or {}).get('code_family') in {'ASME B31.4', 'ASME B31.8'} else 'API 570 fifth edition 7.1.2',previous_date=old['inspection_date'] if old else None,current_date=current['inspection_date'] if current else None,elapsed_basis='calendar months / 12' if old and current and len(old.get('inspection_date') or '')==len(current.get('inspection_date') or '')==7 else 'elapsed days / year_days'),profile_fields=(p or {}).get('fields',{}),normalized_design=input_trace,design_inputs=inputs,pressure_checks=pressure_checks,overrides=override,basis=mode,interval_policy=dict(fraction=fraction,cap_years=cap),forecast_policy=forecast_policy,year_days=year_days,source_rate_selected=False,rate_basis='manual override' if 'adopted_rate_mm_year' in override else 'calculated historical CR'))
        row['input_trace']['interval_policy'] = policy_trace
        row['input_trace']['rate_basis'] = rate_basis
        row['input_trace']['source_rate_selected'] = use_selected and adopted is not None
        if override.get('inspection_code_reference'):
            row['input_trace']['inspection_code_reference'] = override['inspection_code_reference']
        if long_term is not None:
            row['input_trace']['history'].update(
                long_term_rate_mm_year=str(long_term), initial_cell=initial['cell'],
                initial_date=initial['inspection_date'], initial_mm=str(_current(initial)),
            )
        values=outputs(row['current_thickness_mm'] if current and current.get('review_status')!='excluded' else None,life_required,adopted,row['inspection_date'],year_days,fraction,cap,
                       'VIII_UG27_HOOP' if rule=='VIII_SHELL' else rule,inputs,allowance,forecast,factor,selected_interval,scheduled_date,next_inspection_years,manual_interval_override,manual_selected_interval,inspection_pressure=inspection_pressure,structural_minimum_mm=structural)
        if route is None or not route.can_attempt_arithmetic or not rule:
            values['mawp_MPa']=None
            values['forecast_mawp_MPa']=None
            for key in ('mawp_MPa','forecast_mawp_MPa'):
                values.setdefault('issues',{}).setdefault(key,[]).append('CODE_ROUTING_REQUIRED')
        if rule=='VIII_SHELL':
            other=outputs(row['current_thickness_mm'],life_required,adopted,row['inspection_date'],year_days,fraction,cap,'VIII_UG27_LONG',inputs,allowance,forecast,factor,selected_interval,scheduled_date,next_inspection_years,manual_interval_override,manual_selected_interval,inspection_pressure=inspection_pressure)
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

    def _fitting_progress(self, row, item, profile, override, geometry, *, screen_as_pipe=False):
        from evaluator.engineering.code_context import CODES_BY_ASSET
        from evaluator.engineering.fitting_review import bend_pressure_psi, fitting_wall_progress, qualified_pressure_psi
        from evaluator.engineering.reference_rules import API570_UT_CAP_YEARS, API570_UT_POLICY_REFERENCE
        from evaluator.engineering.references import b313_reference_factors

        def usable(reading, value):
            return value if reading and reading['raw_unit'] == 'mm' and reading.get('review_status') != 'excluded' else None

        result = fitting_wall_progress(
            usable(item['previous'], row['previous_thickness_mm']),
            usable(item['current'], row['current_thickness_mm']),
            row['previous_inspection_date'], row['inspection_date'],
            interval=override.get('selected_interval_years'),
            adopted=override.get('adopted_rate_mm_year') if override.get('reviewed') == 'yes' else None,
        )
        row['fitting_progress'] = result
        row['apparent_rate_mm_year'] = result.get('observed_rate_mm_year')
        missing = result['pressure_missing'] = []
        routed = (profile.get('code_family') == 'ASME B31.3' and profile.get('code_edition') == '2024'
                  and profile.get('code_owner_confirmed') and profile.get('code_evidence')
                  and 'ASME B31.3' in CODES_BY_ASSET.get(profile.get('code_asset_type'), ()))
        if not routed:
            missing.append('Confirm the B31.3-2024 code basis for this fitting.')
        wall = usable(item['current'], row['current_thickness_mm'])
        factors = b313_reference_factors(_value(profile, 'material'), geometry,
                                         profile.get('code_family'), profile.get('code_edition'),
                                         _value(profile, 'temperature_F'))
        if screen_as_pipe:
            result['screening_missing'] = [] if routed else ['Confirm the B31.3-2024 code basis for this fitting.']
        if routed:
            benchmark = {
                'E_quality': override.get('E_quality') or '1',
                'W_reduction': override.get('W_reduction') or factors.get('W_reduction', (None,))[0],
                'Y_coefficient': override.get('Y_coefficient') or factors.get('Y_coefficient', (None,))[0],
            }
            for key, source, unit, target in (
                ('P_MPa', 'P_psi', 'psi', 'MPa'),
                ('S_B313_MPa', 'S_allow_psi', 'psi', 'MPa'),
                ('D_outside_mm', 'D_outside_in', 'in', 'mm'),
            ):
                value = _num(_value(profile, source), True)
                benchmark[key] = convert(value, unit, target) if value is not None else None
            if screen_as_pipe:
                labels = {
                    'P_MPa': 'Design pressure', 'S_B313_MPa': 'Allowable stress S',
                    'D_outside_mm': 'Outside diameter or NPS and schedule',
                    'W_reduction': 'Weld strength reduction factor', 'Y_coefficient': 'Y coefficient',
                }
                result['screening_missing'].extend(label for key, label in labels.items() if benchmark[key] is None)
            if all(value is not None for value in benchmark.values()):
                reference = pressure_thickness('B31_3_304_1_2', benchmark)
                if reference['value'] is not None:
                    pressure_wall = Decimal(reference['value'])
                    structural = _num(override.get('structural_minimum_mm', _value(profile, 'structural_minimum_mm')))
                    allowance = _num(override.get('allowance_mm')) or Decimal(0)
                    result['straight_pipe_screen'] = dict(
                        pressure_wall_mm=str(pressure_wall),
                        required_wall_mm=str(max(pressure_wall + allowance, structural)) if structural is not None else None,
                        quality_factor=str(benchmark['E_quality']),
                        assumed_quality_factor=not bool(override.get('E_quality')),
                        weld_reduction_factor=str(benchmark['W_reduction']),
                        y_coefficient=str(benchmark['Y_coefficient']),
                    )
        minimum = _num(override.get('required_thickness_mm'), True)
        life_reference = (override.get('fitting_life_reference') or '').strip()
        observed = _num(result.get('observed_rate_mm_year'), signed=True)
        selected = _num(override.get('adopted_rate_mm_year'), True)
        rate = observed if observed is not None and observed > 0 else None
        if selected is not None and observed is not None and observed <= 0:
            rate = selected
            result['missing'] = [issue for issue in result['missing'] if issue not in {
                'Verify the UT match and readings because the measured wall increased.',
                'Enter a reviewed positive corrosion rate to project wall thickness.',
            }]
        elif selected is not None and (override.get('reviewed') == 'yes' or override.get('allow_increase') == 'yes'):
            if observed is None or observed >= 0 or override.get('allow_increase') == 'yes':
                rate = max(rate or Decimal(0), selected)
        screen = result.get('straight_pipe_screen')
        if screen_as_pipe and routed:
            if override.get('structural_minimum_mm', _value(profile, 'structural_minimum_mm')) in (None, ''):
                result['screening_missing'].append('Structural minimum thickness')
            if observed is not None and observed <= 0 and selected is None:
                result['screening_missing'].append('Enter a positive selected corrosion rate')
        if (screen_as_pipe and screen and wall is not None
                and profile.get('code_asset_type') in {'process_piping', 'production_flowline'}):
            from evaluator.engineering.batch_rules import pressure_psi

            caps = API570_UT_CAP_YEARS
            cap = Decimal(caps.get(override.get('api570_ut_class'), min(caps.values(), key=Decimal)))
            cap = min(cap, _num(override.get('interval_cap_years'), True) or cap)
            fraction = min(Decimal('0.5'), _num(override.get('interval_fraction'), True) or Decimal('0.5'))
            pipe_rate = rate
            calculation = outputs(
                wall, screen['required_wall_mm'], pipe_rate, row['inspection_date'],
                interval_fraction=fraction, interval_cap_years=cap,
                rule='B31_3_304_1_2', design_inputs=benchmark, allowance_mm=allowance,
                selected_interval_years=override.get('selected_interval_years'),
                inspection_pressure=True, structural_minimum_mm=structural,
            )
            screen.update(assessment=True, remaining_life_years=calculation['remaining_life_years'],
                          rate_mm_year=str(pipe_rate) if pipe_rate is not None else None,
                          pressure_trace=calculation['trace']['forecast_mawp_MPa'],
                          interval_years=(calculation['inspection_interval_years'] if calculation['due_date'] else None),
                          due_date=calculation['due_date'], pressure_psi=pressure_psi(calculation['mawp_MPa']),
                          forecast_pressure_psi=pressure_psi(calculation['forecast_mawp_MPa']))
        if routed and wall is not None and minimum is not None and life_reference and override.get('reviewed') == 'yes':
            available_wall = Decimal(wall) - minimum
            if rate is not None or available_wall <= 0:
                life = available_wall / rate if available_wall > 0 else Decimal(0)
                result.update(remaining_life_years=str(life), required_wall_mm=str(minimum),
                              life_rate_mm_year=str(rate) if rate is not None else None,
                              life_trace=dict(source_reference='API 570 fifth edition + Addendum 1, §7.2',
                                              minimum_reference=life_reference, current_mm=wall,
                                              required_mm=str(minimum), adopted_rate=str(rate) if rate is not None else None))
        if result.get('remaining_life_years') is None:
            if minimum is None or not life_reference:
                result['missing'].append('For remaining life, enter the reviewed required wall and its reference for this exact fitting location.')
            elif rate is None:
                result['missing'].append('For remaining life, resolve the UT history or enter a reviewed positive corrosion rate.')
            elif override.get('reviewed') != 'yes':
                result['missing'].append('Confirm the fitting minimum and corrosion inputs.')
        if routed and profile.get('code_asset_type') in {'process_piping', 'production_flowline'}:
            ut_class = override.get('api570_ut_class') or 'conservative'
            default_cap = min(API570_UT_CAP_YEARS.values(), key=Decimal)
            cap = Decimal(API570_UT_CAP_YEARS.get(ut_class, default_cap))
            cap = min(cap, _num(override.get('interval_cap_years'), True) or cap)
            fraction = min(Decimal('0.5'), _num(override.get('interval_fraction'), True) or Decimal('0.5'))
            result['interval_reference'] = (
                f'{API570_UT_POLICY_REFERENCE}, conservative routine UT planning' if ut_class == 'conservative'
                else f'{API570_UT_POLICY_REFERENCE}, Class {ut_class} thickness measurements'
            )
            life = _num(result.get('remaining_life_years'))
            interval = _num(override.get('selected_interval_years'), True)
            for key in ('projection_years', 'projected_wall_mm', 'used_rate_mm_year'):
                result.pop(key, None)
            if life is not None and life > 0:
                maximum = min(cap, life * fraction)
                if interval is None:
                    interval = maximum
                if interval <= maximum:
                    result['next_interval_years'] = str(interval)
                else:
                    result['missing'].append('Entered interval exceeds the calculated draft inspection limit.')
                    interval = None
            elif life is None:
                interval = min(interval, cap) if interval is not None else cap
            else:
                interval = None
                result['missing'].append('Current wall is at or below the reviewed required wall.')
            if rate is not None and wall is not None and interval is not None:
                physical = Decimal(wall) - interval * rate
                result.update(projection_years=str(interval), projected_wall_mm=str(max(Decimal(0), physical)),
                              used_rate_mm_year=str(rate), planning_projection_only=life is None)
                result['missing'] = [issue for issue in result['missing']
                                     if issue not in {'Enter the next inspection interval to project wall thickness.',
                                                      'Enter a reviewed positive corrosion rate to project wall thickness.'}]
                if result.get('next_interval_years') is not None:
                    credited = Decimal(wall) - 2 * interval * rate
                    if credited >= minimum:
                        result['credited_wall_mm'] = str(credited)
                    else:
                        result['missing'].append('Credited wall falls below the reviewed required wall at the inspection interval.')
        if wall is None:
            missing.append('Current UT wall in mm')
        if geometry != 'elbow':
            for key, label in (
                ('qualification_tag', 'Physical fitting tag'),
                ('qualification_points', 'Approved minimum-wall and pressure pairs'),
                ('qualification_reference', 'Approved qualification and controlling UT coverage reference'),
            ):
                if not override.get(key, '').strip():
                    missing.append(label)
            temperature = _num(override.get('qualification_temperature_F'))
            if temperature is None or temperature != _num(_value(profile, 'temperature_F')):
                missing.append('Qualification temperature matching the design temperature')
            location_key = self.flow._key(item['current']) if item['current'] else None
            if (override.get('reviewed') != 'yes' or not location_key
                    or override.get('qualification_location_key') != json.dumps(location_key)):
                missing.append('Confirm the qualification applies to this UT location.')
            if not missing:
                try:
                    result['qualified_current_pressure_psi'] = qualified_pressure_psi(wall, override['qualification_points'])['pressure_psi']
                    if result.get('credited_wall_mm'):
                        result['qualified_forecast_pressure_psi'] = qualified_pressure_psi(
                            result['credited_wall_mm'], override['qualification_points'])['pressure_psi']
                except (ValueError, TypeError, InvalidOperation) as exc:
                    missing.append(str(exc))
            return
        fields = {
            'outside_diameter_in': (_value(profile, 'D_outside_in'), 'Outside diameter'),
            'stress_psi': (_value(profile, 'S_allow_psi'), 'Allowable stress at design temperature'),
            'position': (override.get('bend_position'), 'UT position on the bend'),
            'radius_in': (override.get('bend_radius_in'), 'Centerline bend radius'),
            'allowance_mm': (override.get('allowance_mm'), 'Remaining wall allowance'),
            'quality': (override.get('E_quality'), 'Quality factor E'),
            'weld': (override.get('W_reduction', factors.get('W_reduction', (None,))[0]), 'Weld reduction factor W'),
            'coefficient': (override.get('Y_coefficient', factors.get('Y_coefficient', (None,))[0]), 'Coefficient Y'),
        }
        missing.extend(label for value, label in fields.values() if value in (None, ''))
        if _value(profile, 'temperature_F') in (None, ''):
            missing.append('Design metal temperature for the allowable stress')
        if not override.get('bend_design_reference', '').strip():
            missing.append('Bend design basis confirming applicability of B31.3 §304.2.1')
        if override.get('reviewed') != 'yes':
            missing.append('Confirm the bend calculation inputs in Code and inputs.')
        if missing:
            return
        try:
            result['bend_pressure_psi'] = str(bend_pressure_psi(
                wall_mm=wall, **{key: value for key, (value, _) in fields.items()},
            ))
            if result.get('credited_wall_mm'):
                result['bend_forecast_pressure_psi'] = str(bend_pressure_psi(
                    wall_mm=result['credited_wall_mm'], **{key: value for key, (value, _) in fields.items()},
                ))
        except (ValueError, TypeError, InvalidOperation) as exc:
            missing.append(str(exc))

    def _fitting_check(self, row, item, override):
        from evaluator.engineering.code_context import CODES_BY_ASSET
        from evaluator.engineering.fitting_review import CLAUSES, assess_fitting, bend_minimum_from_inputs, bend_pressure_psi, qualified_pressure_psi

        profile = row['profile']
        geometry = profile['geometry']
        row.update({key: None for key in ('thickness_margin_mm','remaining_life_years',
                   'inspection_interval_years','maximum_inspection_interval_years','due_date',
                   'mawp_MPa','forecast_mawp_MPa')})
        row['input_trace'] = dict(basis='documented_fitting_pressure', overrides=override)
        row['rule'] = 'Documented fitting pressure check'
        row['routing'] = dict(status='FITTING_REVIEW_REQUIRED', code='ASME B31.3', edition='2024',
                              geometry=geometry, issues=[], candidate_rule_ids=[])
        try:
            if ('ASME B31.3' not in CODES_BY_ASSET.get(profile.get('code_asset_type'), ())
                    or not profile.get('code_evidence')):
                raise ValueError('Confirm the construction code and service boundary.')
            if not override.get('fitting_reference') and not override.get('fitting_pressure_psi'):
                row['issues'].append('Optional fitting rating check has not been run.')
                return self._withheld_row7(row, ('remaining_life_years','mawp_MPa','forecast_mawp_MPa'))
            if (override.get('reviewed') != 'yes' or override.get('fitting_geometry') != geometry
                    or not override.get('fitting_reference')):
                raise ValueError('Confirm the fitting rating check and its assessment reference.')
            if (not item['current'] or not item['previous'] or item['pair']['kind'] not in {'matched','lifecycle_mismatch'}
                    or any(reading['raw_unit'] != 'mm' or reading.get('review_status') == 'excluded'
                           for reading in (item['current'],item['previous']))):
                raise ValueError('A comparable previous and current UT pair in mm is required.')
            minimum_basis = override.get('fitting_minimum_basis', 'documented')
            minimum = (bend_minimum_from_inputs(profile, override)
                       if geometry == 'elbow' and minimum_basis == 'bend' else override['fitting_minimum_mm'])
            assessment = assess_fitting(
                row['previous_thickness_mm'], row['current_thickness_mm'],
                row['previous_inspection_date'], row['inspection_date'],
                minimum, override['fitting_pressure_psi'],
                override['fitting_interval_years'], override.get('adopted_rate_mm_year', '0'),
            )
        except (ValueError, TypeError, KeyError, InvalidOperation) as exc:
            row['issues'].append(str(exc))
            return self._withheld_row7(row, ('remaining_life_years','mawp_MPa','forecast_mawp_MPa'))
        assessment.update(reference=override['fitting_reference'], construction_reference=CLAUSES[geometry],
                          minimum_basis=minimum_basis)
        if geometry == 'elbow' and override.get('bend_position'):
            try:
                if not override.get('bend_design_reference', '').strip():
                    raise ValueError('Enter the record confirming applicability of B31.3 304.2.1.')
                if not assessment['projected_meets_minimum']:
                    raise ValueError('Projected wall is at or below the documented minimum.')
                pressure = bend_pressure_psi(
                    wall_mm=assessment['credited_wall_mm'], position=override['bend_position'],
                    radius_in=override.get('bend_radius_in'), allowance_mm=override.get('allowance_mm'),
                    outside_diameter_in=_value(profile, 'D_outside_in'),
                    stress_psi=_value(profile, 'S_allow_psi'), quality=override.get('E_quality'),
                    weld=override.get('W_reduction'), coefficient=override.get('Y_coefficient'),
                )
                assessment.update(bend_position=override['bend_position'],
                                  bend_pressure_psi=str(pressure), bend_design_reference=override['bend_design_reference'],
                                  bend_rule='B31.3-2024 304.2.1 eqs. (3c)-(3e)')
            except (ValueError, TypeError, InvalidOperation) as exc:
                row['issues'].append(str(exc))

        if geometry in {'tee', 'reducer'} and override.get('qualification_points'):
            try:
                evidence = override.get('qualification_reference', '').strip()
                temperature = _num(override.get('qualification_temperature_F'))
                design_temperature = _num(_value(profile, 'temperature_F'))
                location_key = json.dumps(self.flow._key(item['current']))
                saved_location = override.get('qualification_location_key')
                if saved_location and saved_location != location_key:
                    raise ValueError('The UT location changed. Review the fitting qualification link.')
                if not evidence or temperature is None or temperature != design_temperature:
                    raise ValueError('Provide qualification evidence and a temperature matching the fitting design temperature.')
                qualification = qualified_pressure_psi(assessment['credited_wall_mm'], override['qualification_points'])
                assessment.update(qualified_pressure_psi=qualification['pressure_psi'],
                                  qualification_required_wall_mm=qualification['qualification_required_wall_mm'],
                                  qualification_reference=evidence, qualification_temperature_F=str(temperature),
                                  qualification_points=override['qualification_points'],
                                  qualification_tag=override.get('qualification_tag'),
                                  qualification_ut_location=row['location'],
                                  qualification_basis='Highest documented pressure whose minimum wall is met')
            except (ValueError, TypeError, InvalidOperation) as exc:
                row['issues'].append(str(exc))

        row.update(fitting_check=assessment, required_thickness_mm=assessment['minimum_mm'],
                   apparent_rate_mm_year=assessment['observed_rate'], adopted_rate_mm_year=assessment['used_rate'],
                   remaining_life_years=assessment['remaining_life_years'], evaluation_status='EVALUATED')
        row['routing']['status'] = 'FITTING_CHECK_AVAILABLE'
        row['outputs'] = dict(fitting_check=assessment, remaining_life_years=row['remaining_life_years'])
        if not assessment['projected_meets_minimum']:
            row['issues'].append('FITTING_WALL_BELOW_OR_AT_REQUIRED_AT_PROJECTED_DATE')
        return row

    def _row7(self, row, item, override):
        from evaluator.engineering.row_example import calculate
        p = row['profile'] or {}
        raw = lambda key: _value(p, key) if key == 'S_allow_psi' else override.get(key, _value(p, key))
        output_keys = ('thickness_margin_mm','remaining_life_years','inspection_interval_years',
                       'maximum_inspection_interval_years','due_date','mawp_MPa','forecast_mawp_MPa')
        row.update({key: None for key in output_keys})
        row.update(maximum_interval_years=None, selected_interval_years=None, rule='ROW7',
                   required_basis='Row 7: MAX(pressure thickness, structural minimum)', row7=None)
        inputs = dict(material=raw('material'), s_allow_psi=raw('S_allow_psi'), pd_psi=raw('P_psi'), od_in=raw('D_outside_in'),
                      nominal_mm=raw('nominal_thickness_mm'), structural_mm=raw('structural_minimum_mm'),
                      selected_cr=raw('adopted_rate_mm_year'), previous_mm=row['previous_thickness_mm'],
                      current_mm=row['current_thickness_mm'], previous_date=row['previous_inspection_date'],
                      current_date=row['inspection_date'])
        row['input_trace'] = dict(basis='row7', inputs=inputs, overrides=override,
                                 history=dict(previous_cell=row['previous_cell'],current_cell=row['current_cell'],
                                              previous_date=row['previous_inspection_date'],current_date=row['inspection_date']))
        if not p:
            row['issues'].append('CODE_ROUTING_NOT_ASSESSED')
            return self._withheld_row7(row, output_keys)
        from evaluator.engineering.code_context import CodeContext,route_code
        family=p.get('code_family') or ''
        asset_type=p.get('code_asset_type') or {'ASME B31.3':'process_piping','ASME B31.4':'liquid_transmission',
                    'ASME B31.8':'gas_transmission','ASME VIII-1':'pressure_vessel'}.get(family,'unknown')
        routed=route_code(CodeContext(component_id=str(p.get('component') or row.get('location') or row['id']),
            asset_type=asset_type,geometry=str(p.get('geometry') or 'unknown'),construction_code=family or None,
            construction_edition=p.get('code_edition'),code_evidence=p.get('code_evidence'),
            owner_confirmed=bool(p.get('code_owner_confirmed'))))
        row['routing']=dict(status=routed.status,code=family or None,edition=p.get('code_edition'),
            geometry=p.get('geometry'),issues=list(routed.issues),candidate_rule_ids=list(routed.candidate_rule_ids))
        if not routed.can_attempt_arithmetic or routed.candidate_rule_ids!=('B31_3_304_1_2',):
            status=routed.status
            if routed.can_attempt_arithmetic:
                status='NOT_ASSESSED'
                row['routing']['status']='NOT_ASSESSED'
                row['routing']['issues'].append('Row 7 arithmetic is only routed for the reviewed B31.3 straight-pipe candidate.')
            row['issues'].append('CODE_ROUTING_'+status)
            return self._withheld_row7(row,output_keys)
        if override.get('reviewed')!='yes':
            row['issues'].append('PROFILE_SCOPE_NOT_CONFIRMED')
            return self._withheld_row7(row,output_keys)
        try:
            if not item['current'] or not item['previous'] or item['pair']['kind'] not in {'matched','lifecycle_mismatch'}:
                raise ValueError('A unique previous/current reading pair is required')
            if any(r.get('raw_unit') != 'mm' or r.get('review_status') == 'excluded' for r in (item['current'], item['previous'])):
                raise ValueError('Both readings must be included measurements in mm')
            missing = [key for key,value in inputs.items() if value in (None,'') and key not in {'selected_cr','nominal_mm'}]
            if missing:
                raise ValueError('Missing inputs: ' + ', '.join(missing))
            result = calculate(inputs)
            row.update(row7=result, elapsed_days=result['elapsed_days'],
                       pressure_thickness_mm=str(result['pressure_mm']), required_thickness_mm=str(result['required_mm']),
                       apparent_rate_mm_year=str(result['calculated_cr']), adopted_rate_mm_year=str(result['cr_used']),
                       remaining_life_years=str(result['remaining_life']), inspection_interval_years=str(result['interval']),
                       maximum_inspection_interval_years=str(result['interval']), maximum_interval_years=str(result['interval']),
                       thickness_margin_mm=str(float(inputs['current_mm'])-result['required_mm']),
                       due_date=result['next_inspection'], mawp_MPa=str(result['current_pressure_psi']*.006894757293) if result['current_pressure_psi'] is not None else None,
                       forecast_mawp_MPa=str(result['mawp_psi']*.006894757293) if result['remaining_life'] > 0 else None)
            if result['remaining_life'] == 0: row['issues'].append('BELOW_OR_AT_REQUIRED_THICKNESS')
            row['evaluation_status'] = 'EVALUATED'
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            row['issues'].append(str(exc))
            row['evaluation_status'] = 'MISSING_INPUTS'
        row['outputs'] = {key: row[key] for key in output_keys}
        row['outputs'].update(trace={'row7':row['row7'], 'forecast_mawp_MPa':{'net_thickness_mm':str(row['row7']['mawp_thickness_mm'])} if row['row7'] else {}}, issues={key:list(row['issues']) for key in output_keys})
        row['output_readiness'] = {key:dict(state='evaluated' if row[key] is not None else 'withheld',issues=list(row['issues'])) for key in output_keys}
        return row

    @staticmethod
    def _withheld_row7(row, output_keys):
        row['evaluation_status']='NEEDS_REVIEW'
        row['outputs']={key:None for key in output_keys}
        row['outputs'].update(trace={'row7':None},issues={key:list(row['issues']) for key in output_keys})
        row['output_readiness']={key:dict(state='withheld',issues=list(row['issues'])) for key in output_keys}
        return row

    @staticmethod
    def _exclude_other_sheet_inputs(override, sheet):
        try:
            references = json.loads(override.get('source_config_reference') or '{}')
        except (TypeError, ValueError):
            references = {}
        outside = {key for key, source in references.items()
                   if isinstance(source, str) and '!' in source and source.rsplit('!', 1)[0] != sheet} if isinstance(references, dict) else set()
        property_reference = override.get('material_reference') or ''
        if '!' in property_reference and property_reference.rsplit('!', 1)[0] != sheet:
            outside.update(('S_allow_psi', 'material_reference'))
        if override.get('review_note', '').startswith('Batch user review of workbook') and outside:
            outside.update(('adopted_rate_mm_year', 'inspection_code_reference', 'review_note'))
        if outside:
            override['reviewed'] = 'no'
            override.pop('source_config_reference', None)
            for key in outside:
                override.pop(key, None)

    def evaluate(self,comparison_id,expected_revision,options,preview_token=None):
        if not options.get('confirm_records'):raise ValueError('Confirm the proposed component records and their applicability before batch evaluation')
        with _LOCK,connection(self.path) as db:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            if int(expected_revision)!=self.flow.revision():raise ValueError('Project changed. Refresh the batch preview.')
            original=self.flow.comparison(comparison_id)
            if original['stale']:raise ValueError('Inspection inputs changed. Refresh the batch preview before confirming its assignments.')
            preview=self.preview(comparison_id,options.get('profile_sheet'),options)
            if preview_token and preview_token!=preview['preview_token']:raise ValueError('Component assignments changed. Refresh the batch preview.')
            config=preview['settings']
            for value,selection in [(options.get('previous_date'),original['baseline']),(options.get('current_date'),original['current_selection'])]:
                if value and {r['inspection_date'] for r in self.flow._selection(*selection)}!={value}:
                    self.service.resolve_campaign_date(*selection,value,'Local batch reviewer','Inspection event date supplied for batch evaluation',_expected_revision=self.flow.revision())
            comp=original
            if self.flow.comparison(comparison_id)['stale']:
                comp=self.flow.rebuild(comparison_id,self.flow.revision(),'Local batch reviewer','Refresh explicitly supplied campaign dates for batch')
                comparison_id=comp['id']
            profiles=[] if comp.get('selected_ut_only') else [p for p in self.profiles(comp['current_selection'][0]) if p['sheet']==config['profile_sheet']]
            if config.get('workspace_review') and comp is original:
                # Workspace rows derive confirmation from their own saved overrides.
                rows = preview['rows']
            else:
                assignments=self._assign(comp,profiles,config)
                rows=[self._calculate_row(item,config) for item in assignments]
            from evaluator.engineering.fitting_review import summarize_bends
            summarize_bends(rows)
            current_ids={r['observation_id'] for r in self.flow._selection(*comp['current_selection'])}
            if current_ids!={r['current_id'] for r in rows if r['current_id']}:raise ValueError('Batch coverage did not reconcile to current observations')
            result=dict(id=str(uuid.uuid4()),comparison_id=comparison_id,asset=comp['asset'],input_revision=self.flow.revision(),status='DRAFT / NOT VALIDATED',rule_version=VERSION,
                        profile_sheet=config['profile_sheet'],settings=config,rows=rows,source_snapshot=comp,profiles=profiles,
                        summary=dict(current=len(current_ids),life_evaluated=sum(r['remaining_life_years'] is not None for r in rows),interval_evaluated=sum(r['inspection_interval_years'] is not None for r in rows),mawp_evaluated=sum(r['mawp_MPa'] is not None for r in rows),date_evaluated=sum(r['due_date'] is not None for r in rows),issues=dict(Counter(i for r in rows for i in r['issues']))))
            with self.flow.change('Calculate component batch evaluation',inputs=False,expected=self.flow.revision(),actor='Local batch reviewer',reason='Component-specific source profiles and explicit grouped policy') as tx:
                tx.execute('INSERT OR REPLACE INTO wf_batch_settings VALUES(?,?)',(comparison_id,json.dumps(config)))
                tx.execute('INSERT INTO wf_batches VALUES(?,?,0)',(result['id'],json.dumps(result)))
            return result
