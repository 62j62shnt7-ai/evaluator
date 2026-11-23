from collections import Counter
"""Single-sheet intake and batch workspace over the existing audited services."""
from collections import Counter
from copy import deepcopy
from decimal import Decimal
from functools import lru_cache
import hashlib
import json
import re
import uuid

from evaluator.batch import PROFILE_FIELDS, PROFILE_TEXT, NUMERIC_OVERRIDES, TEXT_OVERRIDES, _value
from evaluator.engineering.references import dimensions, dimension, material_stresses, material_stress, material_token
from evaluator.quick_workflow import import_single_dated_sheet, match_single_sheet, single_sheet_campaigns, local_actor
from evaluator.storage.database import connection
from evaluator.workflow import _LOCK

CONFIG_FIELDS=PROFILE_FIELDS|PROFILE_TEXT|NUMERIC_OVERRIDES|{'rule','dimension_reference','material_reference','source_config_reference'}

FITTING_QUALIFICATION_FIELDS = (
    'qualification_tag', 'qualification_points', 'qualification_reference',
    'qualification_temperature_F', 'fitting_pressure_psi', 'fitting_minimum_mm',
    'fitting_reference',
)


def _workbook_pipe_review(row):
    from evaluator.batch import _num

    profile = row['profile'] or {}
    fields = profile.get('fields', {})

    def source(key):
        field = fields.get(key, {})
        record = field.get('source_record') or field
        return record if record.get('kind') == 'literal' else {}

    def reference(record):
        return f"{profile['sheet']}!{record['cell']}" if record.get('cell') else ''

    stress = source('S_allow_psi')
    rate = source('adopted_rate_mm_year')
    material = source('material')
    if row['routing']['status'] != 'ROUTE_SELECTED':
        reason = 'Confirm the sheet code basis first.'
    elif material_token(material.get('value')) != material_token(row['material']):
        reason = 'Check the material against the workbook.'
    elif _num(stress.get('value'), True) is None or not reference(stress):
        reason = 'Enter reviewed allowable stress for this location.'
    elif _num(rate.get('value')) is None or not reference(rate):
        reason = 'Enter a reviewed adopted corrosion rate for this location.'
    else:
        reason = ''
    if reason and row['routing']['status'] == 'ROUTE_SELECTED' and not row.get('previous_id'):
        reason += ' Match an earlier UT reading or enter an approved adopted corrosion rate.'
    return dict(eligible=not reason, reason=reason, stress=stress.get('value'), rate=rate.get('value'),
                stress_source=reference(stress), rate_source=reference(rate))


def _historical_pipe_review(row, candidate, ut, ut_cells):
    """Propose code-compatible source cells for explicit workbook review."""
    from evaluator.batch import _num

    fields = candidate['fields']
    if (not row['previous_id'] or not ut.get('D_outside_in')
            or _num(ut['D_outside_in']) != _num(_value(candidate, 'D_outside_in'))):
        return
    inputs = {}
    references = {}
    for key in ('material', 'P_psi', 'D_outside_in', 'structural_minimum_mm',
                'S_allow_psi', 'adopted_rate_mm_year'):
        field = fields.get(key, {})
        value = field.get('value')
        if value in (None, '') or not field.get('cell'):
            return None
        if field['kind'] != 'literal' and not (key == 'adopted_rate_mm_year' and field['kind'] == 'formula'):
            return None
        inputs[key] = value
        references[key] = f"{candidate['sheet']}!{field['cell']}"
    if row.get('material') and material_token(row['material']) != material_token(inputs['material']):
        return None
    if ut.get('nominal_thickness_mm'):
        inputs['nominal_thickness_mm'] = ut['nominal_thickness_mm']
        references['nominal_thickness_mm'] = f"{row['current_sheet']}!{ut_cells['nominal_thickness_mm']}"
    factors = candidate.get('workbook_pressure_factors', {})
    for key, value in factors.get('values', {}).items():
        inputs[key] = value
        references[key] = f"{candidate['sheet']}!{factors['cell']}"
    policy = candidate.get('interval_policy')
    policy_cell = fields.get('selected_interval_years', {}).get('cell')
    if policy and policy_cell:
        policy_cell = policy.get('source_cell') or policy_cell
        inputs.update(interval_fraction=policy['fraction'], interval_cap_years=policy['cap_years'])
        for key in ('interval_fraction', 'interval_cap_years'):
            references[key] = f"{candidate['sheet']}!{policy_cell}"
    return dict(eligible=True, reason='', stress=inputs['S_allow_psi'], rate=inputs['adopted_rate_mm_year'],
                stress_source=references['S_allow_psi'], rate_source=references['adopted_rate_mm_year'],
                linked_inputs=inputs, references=references,
                inspection_code_reference=(
                    f"API 570 identified in {candidate['sheet']}!{candidate['code_basis_cell']}"
                    if candidate.get('code_basis_cell') and re.search(r'\bAPI[\s-]+570\b',
                                                                       candidate.get('code_basis') or '', re.I)
                    else None),
                cached_rate=fields['adopted_rate_mm_year']['kind'] == 'formula')


@lru_cache(maxsize=4)
def _oil_records_with_pressure_factors(path, source_id, modified_ns):
    """Read the new source fields for comparisons imported by older versions."""
    from evaluator.engineering.records import import_records
    if hashlib.sha256(path.read_bytes()).hexdigest() != source_id:
        raise ValueError('Source integrity check failed')
    return {record['id']: record for record in import_records(path)}


def _oil_workbook_code(profile, correction):
    if (correction and profile.get('sheet') == 'Evaluation 11-2024'
            and profile.get('code_basis_cell') == 'F1' and profile['code_family'] == 'ASME B31.5'):
        return 'ASME B31.3'
    return profile['code_family']


def _nearby_pipe_evidence(row, key, profiles, ut, ut_cells, correction):
    """Offer a differing joint label for review when the earlier UT agrees."""
    from evaluator.batch import _num

    joint, band = key
    previous = _num(row.get('previous_thickness_mm'), True)
    previous_date = row.get('previous_inspection_date') or ''
    if previous is None or not previous_date or not joint.isdigit() or not band.isdigit():
        return None
    for label in (str(int(joint) - 1), str(int(joint) + 1)):
        for profile in profiles.get((label, band), []):
            field = profile.get('historical_ut') or profile['fields'].get('current_mm', {})
            date = profile.get('historical_ut_date') or profile.get('inspection_date') or ''
            if (not field.get('cell') or not date.startswith(previous_date)
                    or _num(field.get('value'), True) != previous
                    or _oil_workbook_code(profile, correction) != row['code_family']):
                continue
            proposal = _historical_pipe_review(row, profile, ut, ut_cells)
            if proposal:
                yield dict(proposal, profile_id=profile['id'], joint=label, band=band,
                           ut_source=f"{profile['sheet']}!{field['cell']}", historical_date=date)


class Workspace:
    def __init__(self, service):
        self.service=service
        self.flow=service.workflow

    def sources(self):
        return [dict(s,sheets=[x['name'] for x in (self.service.inventory_for(s['source_id']) or {}).get('sheets',[])]) for s in self.service.sources()]

    def open_sheet(self, source_id, sheet, revision, previous='', current='', *, ut_only=False, straight_pipe_fitting_screen=False):
        with _LOCK, connection(self.service.repository.path) as db:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            if int(revision) != self.flow.revision():
                raise ValueError('The project changed. Refresh before opening the sheet.')
            inventory = self.service.inventory_for(source_id)
            if not inventory or sheet not in {entry['name'] for entry in inventory['sheets']}:
                raise ValueError('Choose a worksheet from the selected workbook.')
            if self.service.imported_sheet(source_id, sheet) is None:
                campaigns = import_single_dated_sheet(self.service, source_id, sheet, revision)
            else:
                from evaluator.quick_workflow import single_sheet_campaigns
                campaigns = single_sheet_campaigns(self.service, source_id, sheet)
            dated=[c for c in campaigns if c['date_rank']]
            if len(dated)<2:
                return dict(comparison_id=None,campaigns=campaigns,message='Whole sheet preserved. Two dated measured campaigns were not found; choose another sheet or use detailed date-resolution tools.')
            current=current or dated[-1]['campaign']
            chosen = next((campaign for campaign in dated if campaign['campaign'] == current), None)
            if chosen is None:
                raise ValueError('Choose a dated current inspection from the selected worksheet.')
            if ut_only and not previous:
                for saved in self.flow.comparisons():
                    if (not saved['stale'] and saved.get('selected_ut_only') and saved.get('baseline_per_location')
                            and saved['current_selection'] == [source_id, sheet, current]
                            and bool(saved.get('straight_pipe_fitting_screen')) == straight_pipe_fitting_screen):
                        return dict(comparison_id=saved['id'], campaigns=campaigns, reused=True,
                                    message='Opened the saved comparison.')
            if not previous or previous.startswith('auto:'):
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
            if ut_only:
                comp['selected_ut_only'] = True
                comp['straight_pipe_fitting_screen'] = straight_pipe_fitting_screen is True
                db.execute('UPDATE wf_comparisons SET payload=? WHERE id=?', (json.dumps(comp), comp['id']))
            else:
                self.service.batch.prepare(comp['id'],self.flow.revision())
            return dict(comparison_id=comp['id'],campaigns=campaigns,message='Latest measured campaign selected with previous measurements chosen per location. Review assignments and physical continuity before evaluating.')

    def restrict_to_ut(self, cid, revision):
        comp = self.flow.comparison(cid)
        if not comp.get('selected_ut_only'):
            with self.flow.change('Restrict comparison to the selected UT sheet', inputs=False, expected=revision,
                                  actor=local_actor(), reason='Use the selected UT worksheet and manually entered engineering inputs') as db:
                comp['selected_ut_only'] = True
                db.execute('UPDATE wf_comparisons SET payload=? WHERE id=?', (json.dumps(comp), cid))
                self.service.batch._stale(db, cid)

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

    def fitting_qualification_prefills(self, comparison):
        """Find reviewed qualifications for the same workbook, sheet and UT identity."""
        matches = {}
        with connection(self.service.repository.path) as db:
            records = db.execute(
                'SELECT c.payload, s.payload FROM wf_comparisons c '
                'JOIN wf_batch_settings s ON c.id=s.comparison_id ORDER BY c.rowid DESC'
            )
            for raw_comparison, raw_settings in records:
                prior = json.loads(raw_comparison)
                if (prior['id'] == comparison['id']
                        or prior['current_selection'][:2] != comparison['current_selection'][:2]):
                    continue
                overrides = json.loads(raw_settings).get('row_overrides', {})
                for entry in overrides.values():
                    tag = entry.get('qualification_tag')
                    location = entry.get('qualification_location_key')
                    if tag and location and entry.get('qualification_reviewed') == 'yes':
                        key = (entry.get('fitting_geometry'), location)
                        matches.setdefault(key, {}).setdefault(tag, entry)
        return {key: next(iter(entries.values())) for key, entries in matches.items()
                if len(entries) == 1 and next(iter(entries.values())).get('qualification_points')}

    def state(self, cid=None, sheet=None, row_ids=None):
        partial=row_ids is not None
        requested=set(row_ids or ())
        comparisons=self.flow.comparisons()
        cid=cid or (comparisons[0]['id'] if comparisons else None)
        base={'revision':self.flow.revision()}
        if not partial:
            from evaluator.engineering.code_context import CODES_BY_ASSET, DEFAULT_EDITIONS
            from evaluator.engineering.reference_rules import GAS_5L_SMYS_PSI, LIQUID_PIPE_SMYS
            base['codes_by_asset'] = {asset: sorted(codes) for asset, codes in CODES_BY_ASSET.items()}
            base['default_code_editions'] = DEFAULT_EDITIONS
            base['gas_pipe_grades'] = list(GAS_5L_SMYS_PSI)
            base['liquid_pipe_grades'] = list(LIQUID_PIPE_SMYS)
            base.update(sources=self.sources(),comparisons=[dict(id=c['id'],asset=c['asset'],sheet=c['current_selection'][1]) for c in comparisons],templates=self.templates(),dimensions=dimensions(),material_stresses=material_stresses(),reference_gaps=['Offline stress lookup uses reviewed exact entries by code, edition, grade, form and temperature. Some rows also require thickness and material-condition evidence.'])
            from evaluator.project_cleanup import latest_backup
            base['cleanup_backup_available']=latest_backup(self.service) is not None
        if not cid:return dict(base,workspace=None)
        comp=self.flow.comparison(cid)
        preview=self.service.batch.preview(cid,sheet,dict(basis=self.service.batch.settings(cid).get('basis','assigned'),confirm_records=False,confirm_history=False,confirm_rules=False,workspace_review=True))
        config=preview['settings']
        profiles=preview['profiles']
        rows=preview['rows']
        rows=[row for row in rows if row['current_id']]
        if partial:rows=[row for row in rows if row['current_id'] in requested]
        settings=config.get('row_overrides',{})
        for row in rows:
            p=row['profile'] or {};over=settings.get(row['current_id'],{})
            if comp.get('selected_ut_only'):
                over = dict(over)
                self.service.batch._exclude_other_sheet_inputs(over, row['current_sheet'])
            row['reviewed']=over.get('reviewed')=='yes'
            row['segment']=over.get('segment') or p.get('segment') or p.get('section') or row['location'].split(' / ')[0]
            row['component']=p.get('component') or ' / '.join(row['location'].split(' / ')[1:3])
            row['material']=over.get('material',_value(p,'material'));row['schedule']=_value(p,'schedule');row['nps']=_value(p,'nps')
            row['S_allow_psi']=_value(p,'S_allow_psi')
            row['nominal_thickness_mm']=_value(p,'nominal_thickness_mm')
            row['geometry']=p.get('geometry',row['detected_geometry']);row['code_family']=over.get('code_family') or p.get('code_family');row['code_edition']=over.get('code_edition',p.get('code_edition'))
            if row['detected_geometry'] == 'sleeve_tee':
                row['geometry'] = 'sleeve_tee'
            row['code_evidence']=over.get('code_evidence',p.get('code_evidence',p.get('code_basis','')))
            row['code_owner_confirmed']=over.get('code_owner_confirmed')=='yes' or bool(p.get('code_owner_confirmed'))
            row['code_asset_type']=over.get('code_asset_type',p.get('code_asset_type',''))
            row['routing']=row.get('routing') or {'status':'NEEDS_CODE_CONFIRMATION','issues':['Owner-confirmed code basis is required.']}
            if not comp.get('selected_ut_only') and row['code_family']=='ASME B31.3' and row['geometry']=='straight_pipe':
                row['workbook_review'] = _workbook_pipe_review(row)
            od=_value(p,'D_outside_in')
            if not row['nps'] and od:
                matches={d['nps'] for d in dimensions() if abs(Decimal(d['od_in'])-Decimal(str(od)))<Decimal('.001')}
                if len(matches)==1:row['nps']=matches.pop();row['size_basis']='API 574 OD correspondence; schedule requires source evidence or confirmation'
            row['status']='DRAFT / NOT VALIDATED · BELOW MINIMUM REVIEW' if 'BELOW_OR_AT_REQUIRED_THICKNESS' in row['issues'] else 'NEEDS REVIEW' if row['issues'] else 'DRAFT / NOT VALIDATED · '+str((row.get('row7') or {}).get('result','Calculated'))
            row['attention']=bool(row['issues']) or not row['reviewed']
        readings={r['observation_id']:r for r in self.flow._selection(*comp['current_selection'])}
        fitting_keys = {oid: self.flow._key(reading) for oid, reading in readings.items()
                        if reading.get('review_status') != 'excluded'}
        key_counts = Counter(fitting_keys.values())
        qualifications = {} if comp.get('selected_ut_only') else self.fitting_qualification_prefills(comp)
        for row in rows:
            oid = row['current_id']
            key = fitting_keys.get(oid)
            if row['geometry'] not in {'tee', 'reducer'} or not key or key_counts[key] != 1:
                continue
            row['qualification_location_key'] = json.dumps(key)
            if 'qualification_tag' in settings.get(oid, {}):
                continue
            entry = qualifications.get((row['geometry'], row['qualification_location_key']))
            if entry:
                row['qualification_prefill'] = {field: entry[field] for field in FITTING_QUALIFICATION_FIELDS}
        previous=self.flow._selection(*comp['baseline'])
        previous_choices=[dict(id=r['observation_id'],identity=self.flow.match_identity(r),cell=r['cell'],date=r['inspection_date'],value=r.get('effective_value',r['raw_value'])) for r in previous if r.get('review_status')!='excluded']
        previous_by_section={}
        for choice in previous_choices:previous_by_section.setdefault(choice['identity']['section'],[]).append(choice)
        from evaluator.importing.ut_defaults import UTTableIndex, defaults as ut_defaults
        from evaluator.engineering.records import identity as profile_identity

        ut_sheet = UTTableIndex(self.service.imported_sheet(*comp['current_selection'][:2]) or {})
        fitting_profiles = {}
        pipe_profiles = {}
        source_id = comp['current_selection'][0]
        records = [] if comp.get('selected_ut_only') else self.service.batch.profiles(source_id)
        if any(record['sheet'] in {'Eval-8-2023', 'Evaluation 11-2024'}
               and 'forecast_pressure_psi' not in record['fields'] for record in records):
            source = next(entry for entry in self.service.repository.sources() if entry.sha256 == source_id)
            path = source.stored_path
            upgraded = _oil_records_with_pressure_factors(path, source_id, path.stat().st_mtime_ns)
            records = [upgraded.get(record['id'], record) for record in records]
        for profile in records:
            if profile['geometry'] in {'elbow', 'tee', 'reducer'}:
                fitting_profiles.setdefault(tuple(profile['key'][1:]), []).append(profile)
            elif profile['geometry'] == 'straight_pipe' and not profile['key'][0]:
                pipe_profiles.setdefault(tuple(profile['key'][1:]), []).append(profile)
        identities = {oid: self.flow.match_identity(reading) for oid, reading in readings.items()}
        point_keys = {oid: profile_identity('', identity['joint'], identity['band'], 'pipeline')[1:]
                      for oid, identity in identities.items()}
        point_counts = Counter(point_keys.values())
        for row in rows:
            oid = row['current_id']
            identity = identities[oid]
            key = point_keys[oid]
            source_cells = {}
            ut = ut_defaults(ut_sheet, row['current_cell'], identity['band'], sources=source_cells)
            row['ut_dimensions'] = {
                key: {'value': ut[key], 'cell': f"{row['current_sheet']}!{cell}"}
                for key, cell in source_cells.items()
                if key in ut and key in {'nps', 'schedule', 'D_outside_in', 'nominal_thickness_mm'}
            }
            for field in ('nps', 'schedule', 'nominal_thickness_mm'):
                if field in ut and field not in settings.get(oid, {}):
                    row[field] = ut[field]
            if not comp.get('selected_ut_only') and 'material' in source_cells and 'material' not in settings.get(oid, {}):
                row['ut_material'] = {'value': ut['material'], 'cell': f"{row['current_sheet']}!{source_cells['material']}"}
                row['material'] = ut['material']
            correction = settings.get(oid, {}).get('workbook_code_correction_reference')
            review = row.get('workbook_review')
            if review and not review['eligible'] and row['routing']['status'] == 'ROUTE_SELECTED':
                history = pipe_profiles.get(key, [])
                conflicts = [f"{p['code_family']} · {p['sheet']}!{p['code_basis_cell']}"
                             for p in history if _oil_workbook_code(p, correction) != row['code_family'] and p.get('code_basis_cell')]
                candidates = [p for p in history if _oil_workbook_code(p, correction) == row['code_family']
                              and p.get('inspection_date') and row.get('inspection_date')
                              and p['inspection_date'][:10] <= row['inspection_date']]
                latest = max((p['inspection_date'] for p in candidates), default=None)
                candidates = [p for p in candidates if p['inspection_date'] == latest]
                if point_counts[key] == 1 and len(candidates) == 1:
                    linked = _historical_pipe_review(row, candidates[0], ut, source_cells)
                    if linked:
                        row['workbook_review'] = review = linked
                        if _oil_workbook_code(candidates[0], correction) != candidates[0]['code_family']:
                            review['code_correction'] = correction
                if not review['eligible'] and not candidates:
                    review['reason'] = (
                        'No matching historical evaluation under the confirmed construction code. '
                        'Enter reviewed pipe design inputs.'
                    )
                    if not row['previous_id']:
                        review['reason'] += ' Match an earlier UT reading or enter an approved adopted corrosion rate.'
                    else:
                        review['alternate_records'] = list(_nearby_pipe_evidence(
                            row, key, pipe_profiles, ut, source_cells, correction,
                        ))
                if not review['eligible'] and len(candidates) == 1:
                    workbook_grade = _value(candidates[0], 'material')
                    if workbook_grade and row['material'] and material_token(workbook_grade) != material_token(row['material']):
                        review['detected_material'] = workbook_grade
                        review['reason'] = (f"Selected material {row['material']} differs from workbook material "
                                            f"{workbook_grade} at {candidates[0]['sheet']}!"
                                            f"{candidates[0]['fields']['material']['cell']}.")
                if conflicts:
                    review['code_conflicts'] = conflicts
            if row['geometry'] in {'elbow', 'tee', 'reducer'}:
                candidates = fitting_profiles.get(key, [])
                # Prefer an assigned profile, then a unique older workbook record per sheet.
                counts = Counter(profile['sheet'] for profile in candidates)
                candidates = [profile for profile in candidates if counts[profile['sheet']] == 1]
                candidates.sort(key=lambda profile: profile.get('inspection_date') or '', reverse=True)
                assigned = row['profile']
                if assigned:
                    candidates = [assigned] + [p for p in candidates if p['id'] != assigned['id']]
                fields = {key: dict(value=ut[key], cell=cell, sheet=row['current_sheet'])
                          for key, cell in source_cells.items()
                          if key in ut and (key != 'material' or not comp.get('selected_ut_only'))}
                for key, field in {
                    'fitting_pressure_psi': 'P_psi', 'fitting_minimum_mm': 'required_thickness_mm',
                    'fitting_interval_years': 'selected_interval_years', 'adopted_rate_mm_year': 'adopted_rate_mm_year',
                    'material': 'material', 'D_outside_in': 'D_outside_in',
                    'nominal_thickness_mm': 'nominal_thickness_mm', 'S_allow_psi': 'S_allow_psi',
                    'structural_minimum_mm': 'structural_minimum_mm', 'pressure_thickness_mm': 'pressure_thickness_mm',
                }.items():
                    for profile in candidates:
                        value = profile['fields'].get(field, {})
                        if key not in fields and value.get('value') not in (None, ''):
                            fields[key] = dict(value, sheet=profile['sheet'])
                            break
                codes = [dict(code=_oil_workbook_code(p, correction), sheet=p['sheet'], cell=p.get('code_basis_cell'),
                              original_code=p['code_family'] if _oil_workbook_code(p, correction) != p['code_family'] else None,
                              date=p.get('inspection_date'), date_cell=p.get('inspection_date_cell'))
                         for p in candidates if p.get('code_family')]
                date_evidence = {}
                for prefix, date_key in [('current', 'inspection_date'), ('previous', 'previous_inspection_date')]:
                    month = (row[date_key] or '')[:7]
                    if not month:
                        continue
                    reports = next((p['report_dates'] for p in candidates if p.get('report_dates')), {})
                    matching = [(sheet, item) for sheet, item in reports.items() if item['date'][:7] == month]
                    if len({item['date'] for _, item in matching}) == 1:
                        sheet, item = next(((sheet, item) for sheet, item in matching
                                            if sheet == row[prefix+'_sheet']), matching[0])
                        date_evidence[prefix] = dict(item, sheet=sheet)
                row['fitting_workbook_review'] = dict(
                    geometry=row['geometry'], inputs=fields, codes=codes, dates=date_evidence,
                    conflict=len({record['code'] for record in codes}) > 1,
                )
            row['match_identity']=identity
            row['previous_section']=identity['section']
            row['match_flags']=[]
            if not identity['size']:row['match_flags'].append('Size missing; verify physical location')
            if row['geometry']=='unknown':row['match_flags'].append('Component type unclear; choose pipe or fitting')
            if not row['previous_id']:row['match_flags'].append('No unique previous reading; review identity or choose a previous reading')
            elif row['previous_id']:
                prior=next((r for r in previous if r['observation_id']==row['previous_id']),None)
                if prior and self.flow._key(prior)!=self.flow._key(readings[row['current_id']]):row['match_flags'].append('Manually selected previous reading has different identity fields; review the assignment')
            if row['match_flags'] or row['routing'].get('status')!='ROUTE_SELECTED':row['attention']=True
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
        return dict(base,workspace=dict(comparison=comp,profile_sheet=preview['profile_sheet'],profile_sheets=preview['sheets'],campaigns=campaigns,rows=rows,previous_choices_by_section=previous_by_section,catalog=list(catalog.values()),assignment_choices=[dict(id=p['id'],label=f"{p['section']} / {p['component']} / {p['point']} · {_value(p,'D_outside_in')} in OD · row {p['row']}") for p in profiles],settings=config,counts=dict(locations=sum(bool(r['current_id']) for r in rows),review=sum(r['attention'] for r in rows),below=sum('BELOW_OR_AT_REQUIRED_THICKNESS' in r['issues'] for r in rows),life=sum(r['remaining_life_years'] is not None for r in rows)),results=self.service.batch.latest_result(cid, preview['profile_sheet'])))

    def apply(self, cid, revision, ids, values=None, template_id=None, dimension_key=None, sheet=None, clear=False, fill_missing=False):
        values=dict(values or {})
        if 'sleeve_assessment_record' in values:
            raise ValueError('Use Sleeve-T review to save the approved assembly assessment.')
        with _LOCK,connection(self.service.repository.path) as db:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            if int(revision)!=self.flow.revision():raise ValueError('Project changed; refresh before applying changes')
            if template_id:
                template=next((t for t in self.templates() if t['id']==template_id),None)
                if template is None:raise ValueError('Configuration template not found')
                values=dict(template['values'],**values)
            if values.get('qualification_points') and not clear:
                if len(ids) != 1:
                    raise ValueError('Apply the qualification to one fitting location at a time.')
                rows = self.state(cid, sheet, row_ids=ids)['workspace']['rows']
                if len(rows) != 1:
                    raise ValueError('Choose an existing fitting location.')
                row = rows[0]
                if (row['geometry'] not in {'tee', 'reducer'} or not row.get('qualification_location_key')
                        or values.get('reviewed') != 'yes'):
                    raise ValueError('Confirm the qualification for a unique tee or reducer UT location.')
                from evaluator.engineering.fitting_review import qualified_pressure_psi
                qualified_pressure_psi('Infinity', values['qualification_points'])
                values['qualification_location_key'] = row['qualification_location_key']
            if dimension_key:
                d=dimension(*dimension_key)
                values.update(nps=d['nps'],schedule=d['schedule'],D_outside_in=d['od_in'],nominal_thickness_mm=d['nominal_mm'],dimension_reference=f"{d['reference']}; PDF page {d['pdf_page']}; SHA256 {d['source_sha256']}")
            stress=material_stress(values.get('material'),values.get('geometry'),values.get('code_family'),values.get('code_edition'),values.get('temperature_F'),values.get('product_form'),
                                 material_thickness_mm=values.get('material_thickness_mm'),
                                 material_condition_reference=values.get('material_condition_reference'))
            if stress and 'S_allow_psi' not in values:
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
                if set(values)&{'material','temperature_F','code_family','code_edition','code_evidence','code_asset_type'}:
                    values.setdefault('review_note','Changed material/code/temperature; confirm property applicability')
                if fill_missing:
                    current={r['current_id']:r for r in self.state(cid,sheet)['workspace']['rows']}
                    if not ids or not set(ids)<=set(current):raise ValueError('Choose existing current locations')
                    aliases=dict(P_psi='pd_psi',D_outside_in='od_in',nominal_thickness_mm='nominal_mm',structural_minimum_mm='structural_mm',adopted_rate_mm_year='selected_cr',material='material',S_allow_psi='s_allow_psi')
                    per_row={}
                    for oid in ids:
                        row=current[oid];inputs=row.get('input_trace',{}).get('inputs',{})
                        missing={k:v for k,v in values.items() if (inputs.get(aliases[k]) if k in aliases else (row.get('geometry') if k=='geometry' else row.get(k, row.get('input_trace', {}).get('overrides', {}).get(k, _value(row['profile'] or {}, k))))) in (None,'','unknown') or (k=='S_allow_psi' and row.get('input_trace',{}).get('inputs',{}).get('s_allow_psi')!=v)}
                        if dimension_key:
                            missing.update({key: values[key] for key in
                                            ('nps', 'schedule', 'D_outside_in', 'nominal_thickness_mm', 'dimension_reference')})
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

    def prior_code_bases(self, cid):
        current = self.flow.comparison(cid)
        if current.get('selected_ut_only'):
            return []
        scope = tuple(current['current_selection'][:2])
        fields = ('code_asset_type', 'code_family', 'code_edition', 'code_evidence')
        suggestions = []
        seen = set()
        for other in self.flow.comparisons():
            if other['id'] == cid or tuple(other['current_selection'][:2]) != scope:
                continue
            preview = self.service.batch.preview(other['id'], options={'workspace_review': True})
            rows = [row for row in preview['rows'] if row.get('current_id')]
            profiles = [row.get('profile') or {} for row in rows]
            if not profiles or not all(profile.get('code_owner_confirmed') for profile in profiles):
                continue
            bases = {tuple(profile.get(field) for field in fields) for profile in profiles}
            if len(bases) != 1:
                continue
            basis = next(iter(bases))
            if all(basis) and basis not in seen:
                suggestions.append(dict(zip(fields, basis), comparison_id=other['id']))
                seen.add(basis)
        return suggestions

    def apply_code_basis(self, cid, revision, scope, ids, values):
        from evaluator.engineering.code_context import CODES_BY_ASSET, DEFAULT_EDITIONS
        from evaluator.engineering.reference_rules import GAS_BASIC_CLASS_F, GAS_5L_FORMS

        shared = {}
        if values.get('code_family') == 'ASME B31.8':
            for key in ('product_form', 'gas_basic_class', 'temperature_F', 'E_weld'):
                if values.get(key) not in (None, ''):
                    shared[key] = values[key]
            if shared.get('gas_basic_class') and shared['gas_basic_class'] not in GAS_BASIC_CLASS_F:
                raise ValueError('Choose a supported B31.8 location class.')
            if shared.get('product_form') and shared['product_form'] not in GAS_5L_FORMS:
                raise ValueError('Choose a supported pipe manufacturing type.')

        basis = {key: str(values.get(key) or '').strip() for key in (
            'code_asset_type', 'code_family', 'code_edition', 'code_evidence', 'code_owner_confirmed',
        )}
        if basis['code_family'] not in CODES_BY_ASSET.get(basis['code_asset_type'], ()):
            raise ValueError('Choose a construction code that matches the asset and service boundary.')
        if basis['code_edition'] and not re.fullmatch(r'[0-9]{4}', basis['code_edition']):
            raise ValueError('Enter a four-digit edition year or leave it blank.')
        if not basis['code_evidence']:
            raise ValueError('Enter the source document for this code basis.')
        basis['code_edition'] = basis['code_edition'] or DEFAULT_EDITIONS.get(basis['code_family'], '')
        if basis['code_owner_confirmed'] != 'yes':
            raise ValueError('Confirm the code basis for all locations in the selected scope.')
        if int(revision) != self.flow.revision():
            raise ValueError('Project changed; refresh before applying changes')
        rows = self.state(cid)['workspace']['rows']
        if scope == 'sheet':
            ids = [row['current_id'] for row in rows]
        elif scope != 'selected':
            raise ValueError('Choose the current sheet or selected locations.')
        entries = {}
        existing = self.service.batch.settings(cid).get('row_overrides', {})
        for row in rows:
            oid = row['current_id']
            if oid not in ids:
                continue
            dimensions = {key: item for key, item in row['ut_dimensions'].items()
                          if key not in existing.get(oid, {})}
            values = dict(basis, **{key: item['value'] for key, item in dimensions.items()})
            if row['geometry'] == 'straight_pipe':
                values.update(shared)
            if row.get('ut_material') and not existing.get(oid, {}).get('material'):
                values['material'] = row['ut_material']['value']
                values['source_config_reference'] = json.dumps({'material': row['ut_material']['cell']})
            if dimensions and 'dimension_reference' not in existing.get(oid, {}):
                values['dimension_reference'] = '; '.join(
                    f"{key} from {item['cell']}" for key, item in dimensions.items()
                )
            entries[oid] = values
        if not ids or set(ids) != entries.keys():
            raise ValueError('Choose existing locations.')
        self.service.batch.apply_overrides(cid, revision, [], [], {}, per_row_values=entries, assign_code=True)
        return dict(message=f"Code basis saved for {len(ids)} locations.")

    def apply_sheet_materials(self, cid, revision, materials, *, replace_existing=False):
        grades = {key: str(materials.get(key) or '').strip() for key in ('pipe', 'fittings')}
        if not any(grades.values()):
            raise ValueError('Enter a material for straight pipes, fittings, or both.')
        fittings = {'elbow', 'tee', 'reducer', 'branch', 'fitting'}
        changes = {}
        for row in self.state(cid)['workspace']['rows']:
            geometry = row['geometry']
            group = 'pipe' if geometry == 'straight_pipe' else 'fittings' if geometry in fittings else None
            material = grades.get(group)
            if material and (replace_existing or not row['material']) and material != row['material']:
                changes[row['current_id']] = {'material': material, 'reviewed': 'no'}
        if changes:
            self.service.batch.apply_overrides(cid, revision, [], [], {}, per_row_values=changes)
        elif int(revision) != self.flow.revision():
            raise ValueError('Project changed; refresh before applying materials.')
        return dict(message=f'Material prefilled for {len(changes)} locations.')

    def policy(self,cid,revision,basis,sheet=None):
        if basis not in {'provided','recalculate','row7','assigned'}:raise ValueError('Unsupported calculation basis')
        with self.flow.change('Change workspace calculation basis',inputs=False,expected=revision,actor=local_actor(),reason='Explicit source or recalculation method') as db:
            config=self.service.batch.preview(cid,sheet)['settings'];config['basis']=basis
            db.execute('INSERT OR REPLACE INTO wf_batch_settings VALUES(?,?)',(cid,json.dumps(config)))
            self.service.batch._stale(db,cid)

    def review_workbook_pipes(self, cid, revision, ids, alternate_records=None):
        if self.flow.comparison(cid).get('selected_ut_only'):
            raise ValueError('This comparison uses manually entered engineering inputs.')
        if int(revision) != self.flow.revision():
            raise ValueError('Project changed; reopen batch review to confirm current inputs.')
        rows = self.state(cid)['workspace']['rows']
        proposals = {row['current_id']: row['workbook_review'] for row in rows
                     if row.get('workbook_review', {}).get('eligible')}
        alternate_records = alternate_records or {}
        if not isinstance(alternate_records, dict) or not alternate_records.keys() <= set(ids):
            raise ValueError('Choose an alternate record for a selected location.')
        for row in rows:
            oid = row['current_id']
            if oid not in alternate_records:
                continue
            candidate = next((item for item in row.get('workbook_review', {}).get('alternate_records', [])
                              if item['profile_id'] == alternate_records[oid]), None)
            if candidate is None:
                raise ValueError('The alternate record is unavailable. Reopen location review.')
            proposals[oid] = candidate
        if not ids or not set(ids) <= proposals.keys():
            raise ValueError('Choose straight pipes with a saved route and usable workbook inputs.')
        changes = {}
        existing = self.service.batch.settings(cid).get('row_overrides', {})
        for oid in ids:
            proposal = proposals[oid]
            changes[oid] = dict(reviewed='yes', S_allow_psi=proposal['stress'],
                                material_reference=proposal['stress_source'],
                                adopted_rate_mm_year=proposal['rate'],
                                review_note=f"Batch user review of workbook stress ({proposal['stress_source']}) and adopted corrosion rate ({proposal['rate_source']}).")
            if proposal.get('inspection_code_reference'):
                changes[oid]['inspection_code_reference'] = proposal['inspection_code_reference']
            if proposal.get('linked_inputs'):
                prefills = {'E_quality', 'W_reduction', 'Y_coefficient', 'interval_fraction', 'interval_cap_years'}
                changes[oid].update({key: value for key, value in proposal['linked_inputs'].items()
                                     if key not in prefills or key not in existing.get(oid, {})})
                references = {key: reference for key, reference in proposal['references'].items()
                              if key not in prefills or key not in existing.get(oid, {})}
                try:
                    prior_sources = json.loads(existing.get(oid, {}).get('source_config_reference', '{}'))
                except (TypeError, ValueError):
                    prior_sources = {}
                if isinstance(prior_sources, dict):
                    references = {**prior_sources, **references}
                changes[oid]['source_config_reference'] = json.dumps(references, sort_keys=True)
                if proposal.get('code_conflicts'):
                    changes[oid]['review_note'] += ' Conflicting older code evidence: ' + '; '.join(proposal['code_conflicts'])
                if proposal.get('code_correction'):
                    changes[oid]['review_note'] += ' ' + proposal['code_correction']
                if oid in alternate_records:
                    changes[oid]['review_note'] += (
                        f" Reviewer confirmed differing historical joint {proposal['joint']} / "
                        f"{proposal['band']} using {proposal['ut_source']}."
                    )
        self.service.batch.apply_overrides(cid, revision, [], [], {}, per_row_values=changes)
        return dict(message=f'Workbook inputs confirmed for {len(changes)} straight-pipe locations.')

    def record_sleeve_assessment(self, cid, revision, oid, values):
        from decimal import InvalidOperation

        row = next((r for r in self.state(cid, row_ids=[oid])['workspace']['rows']
                    if r['current_id'] == oid and r['geometry'] == 'sleeve_tee'), None)
        if row is None:
            raise ValueError('Choose a Sleeve-T location.')
        fields = ('drawing', 'inspection_map', 'assessment_reference', 'assessor',
                  'pressure_psi', 'temperature_F', 'minimum_wall_mm')
        record = {key: str(values.get(key) or '').strip() for key in fields}
        if not all(record.values()):
            raise ValueError('Complete the approved assessment and its supporting references.')
        try:
            pressure, temperature, wall = (Decimal(record[key]) for key in fields[-3:])
        except InvalidOperation as exc:
            raise ValueError('Enter valid pressure, temperature and minimum wall values.') from exc
        if not all(value.is_finite() for value in (pressure, temperature, wall)) or pressure <= 0 or wall <= 0:
            raise ValueError('Enter a finite temperature and positive pressure and minimum wall.')
        self.service.batch.apply_overrides(cid, revision, [], [], {}, per_row_values={
            oid: {'sleeve_assessment_record': json.dumps(record)}
        })
        return dict(comparison_id=cid, refresh_ids=[oid], message='Approved Sleeve-T assessment recorded.')

    def review_fittings(self, cid, revision, entries):
        from evaluator.batch import _num

        if int(revision) != self.flow.revision():
            raise ValueError('Project changed; reopen fitting review.')
        rows = {row['current_id']: row for row in self.state(cid)['workspace']['rows']
                if row['routing']['status'] in {'FITTING_REVIEW_REQUIRED','FITTING_CHECK_AVAILABLE'}}
        if not isinstance(entries, dict) or not entries or not entries.keys() <= rows.keys():
            raise ValueError('Select fittings on the confirmed B31.3-2024 sheet.')
        changes = {}
        for oid, entry in entries.items():
            row = rows[oid]
            if not isinstance(entry, dict):
                raise ValueError('Each fitting needs its own assessment inputs.')
            values = {key: _num(entry.get(key), True) for key in
                      ('fitting_pressure_psi','fitting_minimum_mm','fitting_interval_years')}
            reference = str(entry.get('fitting_reference') or '').strip()
            rate = _num(entry.get('adopted_rate_mm_year'))
            derived_minimum = row['geometry'] == 'elbow' and values['fitting_minimum_mm'] is None and not entry.get('fitting_minimum_mm')
            if derived_minimum:
                from evaluator.engineering.fitting_review import bend_minimum_from_inputs

                values['fitting_minimum_mm'] = bend_minimum_from_inputs(row['profile'], {**row['input_trace']['overrides'], **entry})
            if not row['previous_id'] or None in values.values() or not reference or rate is None:
                raise ValueError(f"{row['location']}: provide paired UT, documented pressure, minimum wall, reference, interval and adopted rate.")
            if row['geometry'] == 'elbow' and entry.get('bend_position'):
                position = entry['bend_position']
                from evaluator.engineering.fitting_review import BEND_COVERAGE
                if position not in BEND_COVERAGE | {'sidewall', 'tangent'}:
                    raise ValueError('Choose the measured position on the bend.')
                values['bend_position'] = position
                if entry.get('bend_tag', '').strip():
                    values['bend_tag'] = entry['bend_tag'].strip()
                values['bend_design_reference'] = str(entry.get('bend_design_reference', '')).strip()
                values.update({key: str(entry[key]) for key in
                               ('bend_radius_in', 'allowance_mm', 'E_quality', 'W_reduction', 'Y_coefficient')
                               if entry.get(key) not in (None, '')})
            if row['geometry'] in {'tee', 'reducer'}:
                for field in FITTING_QUALIFICATION_FIELDS[:4]:
                    values[field] = str(entry.get(field, '')).strip()
                if values['qualification_points']:
                    from evaluator.engineering.fitting_review import qualified_pressure_psi
                    if not values['qualification_tag'] or not row.get('qualification_location_key'):
                        raise ValueError(f"{row['location']}: enter a fitting tag and resolve the exact UT location.")
                    if (not values['qualification_reference']
                            or _num(values['qualification_temperature_F']) is None):
                        raise ValueError(f"{row['location']}: enter the qualification reference and temperature.")
                    if _num(values['qualification_temperature_F']) != _num(_value(row['profile'], 'temperature_F')):
                        raise ValueError(f"{row['location']}: qualification temperature must match the design temperature.")
                    qualified_pressure_psi('Infinity', values['qualification_points'])
                values['qualification_location_key'] = row.get('qualification_location_key', '')
                values['qualification_reviewed'] = 'yes'
            changes[oid] = dict(values, reviewed='yes', fitting_reference=reference,
                                fitting_minimum_basis='bend' if derived_minimum else 'documented',
                                fitting_geometry=row['geometry'], adopted_rate_mm_year=rate)
        self.service.batch.apply_overrides(cid, revision, [], [], {}, per_row_values=changes)
        return dict(message=f'Documented fitting inputs saved for {len(changes)} locations.')

    def evaluate(self,cid,revision,sheet=None,basis=None):
        # Saved review flags apply per row, keeping unconfirmed rows withheld.
        basis = basis or self.service.batch.settings(cid).get('basis', 'assigned')
        if basis not in {'row7', 'recalculate', 'provided', 'assigned'}:
            raise ValueError('Unsupported calculation basis')
        comp = self.flow.comparison(cid)
        if comp['stale']:
            changed = set()
            for side, selection in (('previous', comp['baseline']), ('current', comp['current_selection'])):
                saved = {}
                for pair in comp['rows']:
                    records = pair.get(side + '_candidates', [])
                    if pair.get(side):
                        records = [*records, pair[side]]
                    saved.update((record['observation_id'], record) for record in records)
                latest = {record['observation_id']: record for record in self.flow._selection(*selection)}
                if saved.keys() != latest.keys() or any(
                    self.flow._key(saved[oid]) != self.flow._key(record) for oid, record in latest.items()
                ):
                    raise ValueError('Reading locations changed. Review the matches before calculating.')
                changed.update(oid for oid, record in latest.items() if record != saved[oid])
            with self.flow.change('Refresh workspace comparison', inputs=False, expected=revision,
                                  actor=local_actor(), reason='Update readings while preserving location matches') as db:
                self._refresh(db, comp, changed)
            revision = self.flow.revision()
        return self.service.batch.evaluate(cid,revision,dict(profile_sheet=sheet,confirm_records=True,confirm_history=False,confirm_rules=False,basis=basis,workspace_review=True))

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
                    entry['reviewed']='no'
                    for key in ('S_allow_psi','SMYS_psi','material_reference'):
                        entry.pop(key,None)
                    db.execute('INSERT OR REPLACE INTO wf_batch_settings VALUES(?,?)',(cid,json.dumps(config)))
            self.flow._identity_revision=None
            comp['rows']=self.flow._match_records(self.flow._selection(*comp['baseline']),self.flow._selection(*comp['current_selection']),True)
            db.execute('UPDATE wf_comparisons SET payload=?,stale=0 WHERE id=?',(json.dumps(comp),cid))
            self.flow._stale_comparison_results(db,cid)
        return cid
