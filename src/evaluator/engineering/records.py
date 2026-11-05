"""Read-only proposals from recognized engineering tables; never Excel evaluation.

Keys normalize labels for review only. Formula caches are supplied results, not
measurements or independently verified code calculations.
"""
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
import json
import re

from openpyxl import load_workbook
from openpyxl.formula.translate import Translator
from evaluator.importing.cells import merged_value


def _token(value):
    return re.sub(r'[^A-Z0-9]', '', str(value if value is not None else '').upper())


def identity(section, component, point, family):
    section = re.sub(r'\[.*?\]', '', str(section or ''))
    match = re.match(r'\s*SECTION\s*(\d+)', section, re.I)
    if match:
        section = 'SECTION' + match[1]
    component = _token(component)
    point = _token(point)
    if family == 'separator':
        component = re.sub(r'^CAP', 'HEAD', component)
        component = re.sub(r'CML$', '', component)
        point = re.sub(r'^CML', '', point)
    return (_token(section), component, point)


def _scalar(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def _field(ws, cache, col, row, unit):
    cell = f'{col}{row}' if col else None
    raw = _scalar(ws[cell].value) if cell else None
    cached = _scalar(cache[cell].value) if cell else None
    kind = 'missing' if raw in (None, '') else 'formula' if isinstance(raw, str) and raw.startswith('=') else 'literal'
    return dict(cell=cell, raw=raw, cached=cached, kind=kind, unit=unit,
                value=cached if kind == 'formula' else raw)


def _policy(raw, life_col, row):
    if not isinstance(raw, str):
        return None
    formula = re.sub(r'[\s$()]', '', raw.upper())
    life = f'{life_col}{row}'
    # Recognize only explicit half-life capped MIN patterns, in either order.
    match = re.fullmatch(r'=MIN' + re.escape(life) + r'/2,([0-9.]+)', formula)
    if not match:
        match = re.fullmatch(r'=MIN([0-9.]+),' + re.escape(life) + r'/2', formula)
    return dict(fraction=.5, cap_years=float(match[1])) if match else None


def _forecast_policy(raw, row):
    """Recognize the source's simple current - factor * rate * horizon pattern."""
    if not isinstance(raw, str):
        return None
    formula = re.sub(r'[\s$()]', '', raw.upper())
    match = re.fullmatch(r'=([A-Z]+\d+)-([0-9.]+)\*([A-Z]+\d+)\*([A-Z]+\d+|[0-9.]+)', formula)
    if not match:
        return None
    current, factor, rate, horizon = match.groups()
    if not current.endswith(str(row)) or not rate.endswith(str(row)):
        return None
    dynamic = horizon.endswith(str(row)) and bool(re.match(r'^[A-Z]+', horizon))
    return dict(current_cell=current, rate_cell=rate, horizon_cell=horizon if dynamic else None,
                horizon_basis='selected_interval' if dynamic else 'fixed_years',
                forecast_years=None if dynamic else float(horizon), factor=float(factor),
                raw=raw)


def _neighbor_interval_policy(ws, interval_col, life_col, row):
    """Use a nearby copied interval formula as a default for a literal override row."""
    for distance in range(1, 5):
        for neighbor in (row-distance, row+distance):
            if neighbor < 1:
                continue
            source = ws[f'{interval_col}{neighbor}'].value
            if not isinstance(source, str) or not source.startswith('='):
                continue
            try:
                translated = Translator(source, origin=f'{interval_col}{neighbor}').translate_formula(f'{interval_col}{row}')
            except (TypeError, ValueError):
                continue
            policy = _policy(translated, life_col, row)
            if policy:
                return dict(policy, source_cell=f'{interval_col}{neighbor}', source_formula=source)
    return None


def _record(ws, cache, digest, family, section, row, columns, datecell, caption, interval, life):
    component, point = merged_value(ws, row, 1), merged_value(ws, row, 2)
    key = identity(section, component, point, family)
    if family == 'separator':
        geometry = 'nozzle' if section == 'NOZZLES' else 'head_unspecified' if key[1].startswith('HEAD') else 'shell' if key[1].startswith('PLATE') else 'unknown'
        code = 'ASME VIII-1'
    else:
        geometry = {'S': 'straight_pipe', 'E': 'elbow', 'T': 'tee', 'R': 'reducer'}.get(key[2], 'straight_pipe' if key[2].isdigit() else 'unknown')
        code = 'ASME B31.3' if 'B31.3' in caption else 'ASME B31.8'
    edition = re.search(r'B31\.[38]\s*-\s*(\d{4})', caption)
    fields = {name: _field(ws, cache, col, row, unit) for name, (col, unit) in columns.items()}
    dt = ws[datecell].value
    stable = json.dumps([digest, ws.title, row, code], separators=(',', ':'))
    interval_raw = ws[f'{interval}{row}'].value
    policy = _policy(interval_raw, life, row)
    policy_basis = 'row_formula' if policy else None
    if (policy is None and ws.title == 'Evalation 4-2026' and row == 15
            and fields.get('selected_interval_years', {}).get('kind') == 'literal'):
        policy = _neighbor_interval_policy(ws, interval, life, row)
        if policy:
            policy_basis = 'neighbor_formula'
    rule_candidates = []
    if geometry in ('shell', 'straight_pipe'):
        rule_candidates = [dict(code_family=code, geometry=geometry, approved=False, basis=caption)]
    pressure = fields.get('pressure_thickness_mm', {})
    forecast = fields.get('forecast_thickness_mm', {})
    forecast_policy = _forecast_policy(forecast.get('raw'), row)
    scheduled = fields.get('scheduled_date', {})
    factor = None
    if code == 'ASME B31.8' and pressure.get('raw') and re.fullmatch(r'=\(?D' + str(row) + r'\*E' + str(row) + r'\)?/\(2\*F' + str(row) + r'\*0\.8\)\*25\.4', str(pressure['raw'])):
        factor = dict(value=.8, cell=pressure['cell'], raw=pressure['raw'], approved=False)
    return dict(id=sha256(stable.encode()).hexdigest(), source_id=digest,
                sheet=ws.title, row=row, family=family, section=section,
                component=_scalar(component), point=_scalar(point), key=list(key),
                geometry=geometry, code_family=code, code_edition=edition[1] if edition else None,
                code_basis=caption, inspection_date=dt.date().isoformat() if isinstance(dt, datetime) else dt.isoformat() if isinstance(dt, date) else None,
                fields=fields, interval_policy=policy, interval_policy_basis=policy_basis,
                policy_candidates=dict(interval_policy=policy, basis=policy_basis),
                forecast_policy=forecast_policy,
                schedule_candidate={key: scheduled.get(key) for key in ('cell', 'raw', 'cached', 'kind')},
                year_days=365,
                rule_candidates=rule_candidates, factor_candidates={'design_factor': factor} if factor else {})


def import_records(path: Path) -> list[dict]:
    """Import recognized source scenarios, retaining every original cell and cache."""
    path = Path(path)
    digest = sha256(path.read_bytes()).hexdigest()
    wb = load_workbook(path, data_only=False, keep_links=False)
    cached = None
    records = []
    try:
        cached = load_workbook(path, data_only=True, keep_links=False)
        for ws in wb:
            caption = '\n'.join(str(c.value) for row in ws.iter_rows(min_row=1, max_row=1) for c in row if c.value is not None)
            if ws.title == 'Evaluation 2026' and 'ASME-VIII' in caption:
                for section, start, end, required, rate, interval, life, dt in [('CMLS',5,23,'N','R','U','T','M4'),('NOZZLES',27,45,'S','V','Y','X','M26')]:
                    due = 'X' if section == 'CMLS' else 'AB'
                    future = 'V' if section == 'CMLS' else 'Z'
                    future_mawp = 'W' if section == 'CMLS' else 'AA'
                    columns = dict(material=('C',None), P_psi=('D','psi'), temperature_F=('E','F'), S_allow_psi=('F','psi'), E_joint=('G',None), D_outside_in=('H','in'), D_inside_in=('I','in'), nominal_thickness_mm=('J','mm'), current_mm=('M','mm'), required_thickness_mm=(required,'mm'), pressure_thickness_mm=(None,'mm'), adopted_rate_mm_year=(rate,'mm/year'), structural_minimum_mm=(None,'mm'), selected_interval_years=(interval,'year'), scheduled_date=(due,'date'), forecast_thickness_mm=(future,'mm'), forecast_pressure_psi=(future_mawp,'psi'))
                    for row in range(start,end+1):
                        if merged_value(ws,row,1) is not None and merged_value(ws,row,2) is not None:
                            records.append(_record(ws,cached[ws.title],digest,'separator',section,row,columns,dt,caption,interval,life))
            layouts = {
                'Evaluation 6-2025': ('I','N','S','U','T','N5',None,None,'Y','V','W'),
                'Evalation 4-2026': ('I','O','T','V','U','O5',None,None,'Z','W','X'),
                'Reassess 1500 Psi May-2025': ('I','O','U','W','V','O5',None,None,None,'X','Y'),
                'Eval 8-2023 - ASME B31.8': ('H','M','R','T','S','M6',None,None,None,'U','V'),
                'Eval 8-2023 - ASME B31.3': ('I','O','S','U','T','O7','J','H','Y','V','W'),
            }
            if ws.title not in layouts or not re.search(r'ASME\s+B31\.[38]', caption):
                continue
            pressure,current,rate,interval,life,dt,required,structural,due,forecast,forecast_mawp = layouts[ws.title]
            columns = dict(schedule=('H',None) if ws.title in {'Evaluation 6-2025','Evalation 4-2026','Reassess 1500 Psi May-2025'} else (None,None), material=('C',None), P_psi=('D','psi'), D_outside_in=('E','in'), nominal_thickness_mm=('G','mm'), pressure_thickness_mm=(pressure,'mm'), required_thickness_mm=(required,'mm'), structural_minimum_mm=(structural,'mm'), current_mm=(current,'mm'), adopted_rate_mm_year=(rate,'mm/year'), E_joint=(None,None), D_inside_in=(None,'in'), selected_interval_years=(interval,'year'), scheduled_date=(due,'date'), forecast_thickness_mm=(forecast,'mm'), forecast_pressure_psi=(forecast_mawp,'psi'))
            columns['S_allow_psi' if 'B31.3' in caption else 'SMYS_psi'] = ('F','psi')
            section = ''
            for row in range(3,ws.max_row+1):
                label = ws.cell(row,1).value
                match = re.match(r'SECTION\s+(\d+)',str(label or ''),re.I)
                if match:
                    section = 'SECTION ' + match[1]
                    continue
                if not section or not isinstance(ws.cell(row,4).value,(int,float)) or not ws.cell(row,3).value:
                    continue
                if merged_value(ws,row,1) is None or merged_value(ws,row,2) is None:
                    continue
                records.append(_record(ws,cached[ws.title],digest,'pipeline',section,row,columns,dt,caption,interval,life))
        from collections import defaultdict
        properties=defaultdict(list)
        for record in records:
            fields=record['fields'];material=fields.get('material',{}).get('value')
            temperature=fields.get('temperature_F',{}).get('value')
            for key in ('S_allow_psi','SMYS_psi'):
                field=fields.get(key,{})
                if field.get('value') is not None:properties[(record['sheet'],material,temperature,key)].append((record,field))
        for key,items in properties.items():
            if len({str(f['value']) for _,f in items})>1:
                evidence=[dict(value=f['value'],cell=f['cell']) for _,f in items]
                for record,_ in items:record.setdefault('property_conflicts',{})[key[3]]=evidence
        return records
    finally:
        wb.close()
        if cached is not None:
            cached.close()
