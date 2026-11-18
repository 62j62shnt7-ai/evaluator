"""Read explanations exclusively from saved batch inputs and outputs."""
import re
from urllib.parse import urlencode

from evaluator.desk_ui import shell
from evaluator.workflow_ui import E

_LABELS = {
    'VIII_UG27_HOOP': 'Vessel shell hoop', 'VIII_UG27_LONG': 'Vessel shell longitudinal',
    'VIII_UG32_ELLIP': '2:1 ellipsoidal head', 'VIII_UG32_TORI': 'Standard torispherical head',
}

_SYMBOL_FIELDS = {
    'P': 'P_MPa', 'R': 'R_inside_mm', 'L': 'L_inside_crown_mm', 'E': 'E_joint',
    'W': 'W_reduction', 'Y': 'Y_coefficient', 'SMYS': 'SMYS_MPa', 'T': 'T_temp',
}


def _substitute(check):
    rule = check['rule']
    fields = dict(_SYMBOL_FIELDS)
    fields['D'] = 'D_inside_mm' if rule.startswith('VIII_') else 'D_outside_mm'
    fields['S'] = 'S_B313_MPa' if rule == 'B31_3_304_1_2' else 'S_allow_MPa'
    if rule.startswith('B31_'):
        fields['E'] = 'E_quality' if rule == 'B31_3_304_1_2' else 'E_weld'
        fields['F'] = 'F_class' if rule == 'B31_8_841_1_1' else 'F_design'
    values = check.get('inputs', {})
    return re.sub(r'\b[A-Z]+\b', lambda m: str(values.get(fields.get(m[0]), m[0])), check['formula'])


def _table(headers, values):
    return ('<div class="scroll"><table><thead><tr>' +
            ''.join(f'<th>{E(header)}</th>' for header in headers) + '</tr></thead><tbody>' +
            ''.join('<tr>' + ''.join(f'<td>{E(value)}</td>' for value in row) + '</tr>' for row in values) +
            '</tbody></table></div>')


def page(batch, row):
    trace = row.get('input_trace', {})
    profile = row.get('profile') or {}
    href = '/?' + urlencode({'comparison': batch['comparison_id'], 'view': 'results'})
    body = [f'<p><a href="{E(href)}">Back to calculation results</a></p><h1>How was this calculated?</h1>',
            f'<h2>{E(row["location"])}</h2><p>DRAFT / NOT VALIDATED · Saved input revision {E(batch.get("input_revision"))}</p>',
            f'<p>Assigned code: {E(profile.get("code_family"))} {E(profile.get("code_edition"))} · Method: {E(row.get("rule"))}</p>']
    if batch.get('stale'):
        body.append('<p class="warn">Historical result. Recalculate against current inputs before using current results.</p>')
    body.append('<section><h2>Workbook readings</h2>')
    body.append(_table(('Reading','Thickness (mm)','Inspection date','Worksheet','Cell'), [
        ('Previous',row.get('previous_thickness_mm'),row.get('previous_inspection_date'),row.get('previous_sheet'),row.get('previous_cell')),
        ('Current',row.get('current_thickness_mm'),row.get('inspection_date'),row.get('current_sheet'),row.get('current_cell')),
    ]))
    body.append('</section><section><h2>Equipment and reference inputs</h2>')
    rows = []
    for key, value in profile.get('fields', {}).items():
        if value.get('value') in (None, ''):
            continue
        origin = value.get('source_record') or value
        source = ' · '.join(str(item) for item in (
            value.get('basis'), profile.get('sheet') if origin.get('cell') else None, origin.get('cell')) if item)
        rows.append((key, value['value'], value.get('unit'), value.get('kind'), source))
    body.append(_table(('Field','Value','Unit','Origin','Reference'), rows))
    normalized = trace.get('normalized_design', {})
    inputs = trace.get('design_inputs', {})
    if inputs:
        rows = []
        for key, value in inputs.items():
            evidence = normalized.get(key, {})
            source = evidence.get('reference') or evidence.get('basis') or (evidence.get('source') or {}).get('basis')
            rows.append((key, value, source or 'See saved equipment inputs or component overrides'))
        body.append(_table(('Formula input','Normalized value','Source'), rows))
    body.append('</section><section><h2>Pressure thickness checks</h2>')
    checks = trace.get('pressure_checks', [])
    for check in checks:
        value = check.get('value')
        label = _LABELS.get(check['rule'], check['rule'])
        governs = value is not None and value == row.get('pressure_thickness_mm')
        body.append(f'<h3>{E(label)}{" · governs" if governs else ""}</h3>')
        body.append(f'<p><small>{E(check["source_reference"])}</small><br><code>{E(check["formula"])}</code></p>')
        if value is not None:
            body.append(f'<p><code>{E(_substitute(check))} = {E(value)} mm</code></p>')
        else:
            body.append('<p>Withheld. ' + E('; '.join(check.get('issues', []))) + '</p>')
    pipe = row.get('row7')
    if pipe:
        i = trace['inputs']
        body.append('<p>Simplified pipe method with E = 1, W = 1 and Y = 0.4.</p>')
        body.append(f'<p><code>{E(i["pd_psi"])} × {E(i["od_in"])} × 25.4 ÷ '
                    f'(2 × {E(pipe["s_psi"])} + 0.8 × {E(i["pd_psi"])}) = {E(pipe["pressure_mm"])} mm</code></p>')
    if not checks and not pipe:
        body.append('<p>This record has no saved individual pressure equation checks.</p>')
    body.append('</section><section><h2>From wall loss to the saved result</h2>')
    if row.get('apparent_rate_mm_year') is not None:
        body.append(f'<p>Observed rate: ({E(row["previous_thickness_mm"])} − {E(row["current_thickness_mm"])}) mm '
                    f'over the saved inspection interval = {E(row["apparent_rate_mm_year"])} mm/year.</p>')
    if row.get('remaining_life_years') is not None and row.get('required_thickness_mm') is not None:
        body.append(f'<p>Remaining life: ({E(row["current_thickness_mm"])} − {E(row["required_thickness_mm"])}) mm '
                    f'÷ {E(row["adopted_rate_mm_year"])} mm/year = {E(row["remaining_life_years"])} years'
                    + (' (minimum zero in the simplified pipe workflow).</p>' if pipe else '.</p>'))
    structural = trace.get('overrides', {}).get('structural_minimum_mm')
    if structural not in (None, '') and row.get('pressure_thickness_mm') is not None and row.get('required_thickness_mm') is not None:
        body.append(f'<p>Required thickness: max({E(row["pressure_thickness_mm"])} mm pressure thickness, '
                    f'{E(structural)} mm structural minimum) = {E(row["required_thickness_mm"])} mm.</p>')
    from evaluator.engineering.batch_rules import pressure_psi
    output_trace = row.get('outputs', {}).get('trace', {})
    inspection_code = row.get('input_trace', {}).get('inspection_code_reference')
    if inspection_code:
        body.append(f'<p>Inspection code evidence: {E(inspection_code)}.</p>')
    life = output_trace.get('remaining_life_years', {})
    if row.get('remaining_life_years') is not None and life.get('required_mm') is not None:
        source = life.get('source_reference')
        body.append(f'<p>Remaining life uses {E(life["current_mm"])} mm measured wall and '
                    f'{E(life["required_mm"])} mm required wall. '
                    f'{E(life.get("basis") or (str(life.get("adopted_rate")) + " mm/year rate"))}. '
                    f'Result: {E(row["remaining_life_years"])} years. {E(source or "")}</p>')
    pressure_key = 'forecast_mawp_MPa' if row.get('forecast_mawp_MPa') is not None else 'mawp_MPa'
    inverse = output_trace.get(pressure_key, {})
    horizon = inverse.get('horizon_basis')
    assessment = {'remaining_life_endpoint': 'End-of-life', 'current_measurement': 'Current'}.get(horizon, 'Forecast')
    if row.get(pressure_key) is not None and inverse.get('forecast_years') is not None:
        body.append(f'<p>{E(assessment)} net wall: {E(inverse["current_mm"])} − {E(inverse["allowance_mm"])} − '
                    f'{E(inverse["adopted_rate"])} × {E(inverse["forecast_years"])} × '
                    f'{E(inverse["forecast_factor"])} = {E(inverse["net_thickness_mm"])} mm.</p>')
        if inverse.get('inspection_reference'):
            body.append(f'<p>Projected physical wall: {E(inverse["projected_physical_wall_mm"])} mm. '
                        f'Wall credited before mechanical allowances: {E(inverse["credited_wall_mm"])} mm. '
                        f'{E(inverse["inspection_reference"])}.</p>')
        directions = (inverse, inverse.get('longitudinal_check', {}))
        for direction in directions:
            if direction.get('pressure_MPa') is not None:
                label = _LABELS.get(direction['rule'], direction['rule'])
                value = direction['pressure_MPa']
                suffix = ' · governs' if value == row[pressure_key] else ''
                body.append(f'<p>{E(label)} inverse pressure: {E(pressure_psi(value))} psi{suffix}.</p>')
    elif pipe and row.get('forecast_mawp_MPa') is not None:
        body.append(f'<p>Projected wall: {E(row["current_thickness_mm"])} − 2 × {E(pipe["cr_used"])} × '
                    f'{E(pipe["interval"])} = {E(pipe["mawp_thickness_mm"])} mm. '
                    f'The simplified inverse equation gives {E(pipe["mawp_psi"])} psi.</p>')
    output_labels = [('Pressure thickness (mm)','pressure_thickness_mm'),('Required thickness (mm)','required_thickness_mm'),
                     ('Adopted rate (mm/year)','adopted_rate_mm_year'),('Remaining life (years)','remaining_life_years'),
                     ('Inspection interval (years)','inspection_interval_years'),('Forecast pressure (psi)','forecast_mawp_psi')]
    saved = dict(row, forecast_mawp_psi=pressure_psi(row.get('forecast_mawp_MPa')))
    body.append(_table(('Saved output','Value'), [(label, saved[key] if saved.get(key) is not None else 'Withheld')
                                                for label, key in output_labels]))
    if row.get('issues'):
        body.append('<h3>Review items</h3><ul>' + ''.join(f'<li>{E(issue)}</li>' for issue in row['issues']) + '</ul>')
    return shell('How was this calculated?', ''.join(body) + '</section>', workspace_url=href)

