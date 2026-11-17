"""Editable examples for the code library's draft arithmetic."""
import json
from decimal import Decimal, DecimalException

from evaluator.engineering.batch_rules import convert, pressure_at_thickness
from evaluator.engineering.reference_rules import (
    GAS_5L_FORMS, GAS_5L_SMYS_PSI, GAS_BASIC_CLASS_F, GAS_CLASS_REFERENCE,
    GAS_SMYS_REFERENCE, GAS_TEMPERATURE_REFERENCE, gas_temperature_factor,
    LIQUID_PIPE_SMYS, LIQUID_PIPE_SMYS_REFERENCE, LIQUID_WELD_FACTORS, LIQUID_WELD_REFERENCE,
)
from evaluator.inspection_time import elapsed_days
from evaluator.engineering.references import dimensions, material_stresses
from evaluator.engineering.structural_reference import CLASSES, LOOKUP_FIELDS, NPS, structural_cell, structural_tables
from evaluator.engineering.draft import FORMULAS, REFERENCES, evaluate
from evaluator.tanks import calculate as calculate_tank
from evaluator.workflow_ui import E, field, hidden, numeric


PIPE = (
    ('P_MPa', 'Design pressure (MPa)', '5.5158'),
    ('D_outside_mm', 'Outside diameter (mm)', '219.075'),
)
PRESETS = {
    'B31_3_304_1_2': ('B31.3 · Straight process piping', PIPE + (
        ('S_B313_MPa', 'Allowable stress S (MPa)', '137.895'),
        ('E_quality', 'Quality factor E', '1'), ('W_reduction', 'Weld reduction factor W', '1'),
        ('Y_coefficient', 'Coefficient Y', '0.4'))),
    'B31_4_403_2_1': ('B31.4 · Liquid transmission', PIPE + (
        ('SMYS_MPa', 'Specified minimum yield strength (MPa)', '358.5274'),
        ('F_design', 'Design factor F', '0.72'), ('E_weld', 'Weld factor E', '1'))),
    'B31_8_841_1_1': ('B31.8 · Gas transmission', PIPE + (
        ('SMYS_MPa', 'Specified minimum yield strength (MPa)', '359.9063'),
        ('F_class', 'Class design factor F', '0.5'), ('E_weld', 'Weld factor E', '1'),
        ('T_temp', 'Temperature factor T', '1'))),
    'VIII_UG27_HOOP': ('VIII-1 · Cylindrical shell', (
        ('P_MPa', 'Design pressure (MPa)', '1.0342'), ('R_inside_mm', 'Inside radius (mm)', '609.6'),
        ('S_allow_MPa', 'Allowable stress S (MPa)', '138'), ('E_joint', 'Joint efficiency E', '0.85'))),
    'VIII_UG32_ELLIP': ('VIII-1 · 2:1 ellipsoidal head', (
        ('P_MPa', 'Design pressure (MPa)', '1.0342'), ('D_inside_mm', 'Inside diameter (mm)', '1219.2'),
        ('S_allow_MPa', 'Allowable stress S (MPa)', '138'), ('E_joint', 'Joint efficiency E', '0.85'))),
    'VIII_UG32_TORI': ('VIII-1 · Standard torispherical head', (
        ('P_MPa', 'Design pressure (MPa)', '1.0342'), ('L_inside_crown_mm', 'Inside crown radius (mm)', '1200'),
        ('S_allow_MPa', 'Allowable stress S (MPa)', '138'), ('E_joint', 'Joint efficiency E', '0.85'))),
    'CR_ST': ('API 510 · Vessel inspection and continued-use MAWP', (
        ('t_previous_mm', 'Previous measured wall (mm)', '11.8'),
        ('t_current_mm', 'Current measured wall (mm)', '11.2'),
        ('elapsed_years', 'Years between UT readings', '2'),
        ('t_required_mm', 'Reviewed governing required wall (mm)', '5'),
        ('original_psi', 'Original vessel MAWP (psi)', ''),
        ('next_years', 'Years to next internal or on-stream inspection', ''))),
    'API650_ONE_FOOT_PRODUCT': ('API 650 · One-foot shell design', (
        ('D_m', 'Tank diameter (m)', '30'), ('H_m', 'Product height above course bottom (m)', '12'),
        ('hydro_H_m', 'Hydrotest height above course bottom (m)', ''),
        ('G', 'Product specific gravity', '0.85'), ('Sd_MPa', 'Product design stress (MPa)', '160'),
        ('CA_mm', 'Corrosion allowance (mm)', '2'), ('St_MPa', 'Hydrotest stress (MPa)', '171'))),
}

PRESETS['API570_PIPE'] = ('API 570 · In-service straight process piping', PRESETS['B31_3_304_1_2'][1] + (
    ('initial_mm', 'Initial measured thickness (mm)', '12.4'),
    ('previous_mm', 'Previous measured thickness (mm)', '11.8'),
    ('measured_mm', 'Current measured thickness (mm)', '11.2'),
    ('long_years', 'Years from initial to current UT', '5'),
    ('elapsed_years', 'Years from previous to current UT', '2'),
    ('structural_mm', 'Reviewed structural minimum (mm)', '3'),
))


EDITABLE_FACTORS = {
    'E_quality', 'W_reduction', 'Y_coefficient', 'F_design', 'E_weld',
    'F_class', 'T_temp', 'E_joint', 'E_circumferential',
}


def _form_key(key):
    if key == 'D_outside_mm':
        return 'D_outside_in'
    return key.removesuffix('_MPa') + '_psi' if key.endswith('_MPa') else key


def _form_label(key, label):
    if key == 'D_outside_mm':
        return 'Outside diameter (in)'
    return label.replace('(MPa)', '(psi)')


PIPE_RULES = ('B31_3_304_1_2', 'B31_4_403_2_1', 'B31_8_841_1_1')
API570_REFERENCE = 'API 570, 5th edition with Addendum 1, §§6.3.3, 7.1, 7.2, 7.5 and 7.6; Table 1 (PDF p. 53); Annex C (PDF p. 87)'
STRESS_CONTEXTS = {
    PIPE_RULES[0]: ('ASME B31.3', '2024', 'pipe', 'S_B313_MPa'),
    'VIII_UG27_HOOP': ('ASME VIII-1', '2025', 'plate', 'S_allow_MPa'),
    'VIII_UG32_ELLIP': ('ASME VIII-1', '2025', 'plate', 'S_allow_MPa'),
    'VIII_UG32_TORI': ('ASME VIII-1', '2025', 'plate', 'S_allow_MPa'),
}


CODES = {
    'b313': ('ASME B31.3 · 2024', 'B31_3_304_1_2'),
    'b314': ('ASME B31.4 · 2025', 'B31_4_403_2_1'),
    'b318': ('ASME B31.8 · 2025', 'B31_8_841_1_1'),
    'viii': ('ASME VIII-1 · 2025', 'VIII_UG27_HOOP'),
    'api510': ('API 510 · 11th edition', 'CR_ST'),
    'api570': ('API 570 · 5th edition', 'API570_DATED'),
    'api650': ('API 650 · 14th edition', 'API650_ONE_FOOT_PRODUCT'),
}
VESSEL_FORMS = {'VIII_UG27_HOOP': 'Cylindrical shell', 'VIII_UG32_ELLIP': '2:1 ellipsoidal head',
                'VIII_UG32_TORI': 'Standard torispherical head'}


API510_FORMS = {'CR_ST' if i == 0 else f'API510_{rule}': rule
                for i, rule in enumerate(VESSEL_FORMS)}
_api510_fields = PRESETS['CR_ST'][1]
for sample, geometry in API510_FORMS.items():
    geometry_fields = PRESETS[geometry][1][1:]
    if geometry == 'VIII_UG27_HOOP':
        geometry_fields = geometry_fields[:-1] + (
            ('E_joint', 'Longitudinal joint efficiency (hoop check)', '0.85'),
            ('E_circumferential', 'Circumferential joint efficiency (longitudinal check)', '0.85'),
        )
    PRESETS[sample] = ('API 510 · ' + VESSEL_FORMS[geometry], _api510_fields + geometry_fields)



def code_rule(code, geometry):
    if code == 'row7':
        code = 'api570'
    if code == 'viii' and geometry in VESSEL_FORMS:
        return geometry
    if code == 'api510' and geometry in API510_FORMS:
        return geometry
    return CODES.get(code, ('', ''))[1]


def _code_picker(rule):
    if rule == 'API570_PIPE':
        rule = 'API570_DATED'
    selected = 'api510' if rule in API510_FORMS else 'viii' if rule in VESSEL_FORMS else next(
        code for code, (_, candidate) in CODES.items() if candidate == rule)
    options = ''.join(f'<option value="{code}"{" selected" if code == selected else ""}>{label}</option>'
                      for code, (label, _) in CODES.items())
    geometry = ''
    if selected in {'viii', 'api510'}:
        geometries = (VESSEL_FORMS if selected == 'viii' else
                      {key: VESSEL_FORMS[value] for key, value in API510_FORMS.items()})
        forms = ''.join(f'<option value="{key}"{" selected" if key == rule else ""}>{label}</option>'
                        for key, label in geometries.items())
        geometry = f'<label>Vessel geometry<select name="geometry">{forms}</select></label>'
    return ('<form class="sample-picker" action="/codes#sample-calculator" method="get">'
            f'<label>Calculation code<select name="code">{options}</select></label>{geometry}'
            '<button id="apply-calculation-code">Apply code</button></form>'
            '<script defer src="/assets/code-sample.js"></script>')


def _reference_controls(rule, submitted, annex_tables=(), annex_error=''):
    values = submitted or {}
    data = {'selection': {key: values.get(key, '') for key in (
        'pipe_family', 'nps', 'schedule', 'material', 'temperature', 'product_form', 'basic_class', 'liquid_weld',
    )}}
    controls = []

    def select(name, label):
        controls.append(f'<label>{label}<select name="{name}"><option value="">Manual entry</option></select></label>')

    if rule in (*PIPE_RULES, 'API570_PIPE', 'API570_DATED'):
        data['dimensions'] = [
            dict(family=row['family'], nps=row['nps'], schedule=row['schedule'],
                 od=row['od_in'], wall=row['nominal_mm'],
                 reference=f"{row['reference']}, PDF p. {row['pdf_page']}")
            for row in dimensions() if not row['issues']
        ]
        select('pipe_family', 'Pipe dimension table')
        select('nps', 'Nominal pipe size (NPS)')
        if rule != 'API570_DATED':
            select('schedule', 'Pipe schedule')
    stress_rule = PIPE_RULES[0] if rule in {'API570_PIPE', 'API570_DATED'} else API510_FORMS.get(rule, rule)
    if stress_rule in STRESS_CONTEXTS:
        code, edition, product, target = STRESS_CONTEXTS[stress_rule]
        select('material', f'Material · {code} {edition} · {product}')
        select('temperature', 'Exact design temperature from table')
        data['stressTarget'] = _form_key(target)
        data['stresses'] = [
            dict(material=row['material'], temperature=row['temperature_F'],
                 label=f"{row['temperature_C']} °C ({row['temperature_F']} °F)" if row.get('temperature_C')
                 else f"{row['temperature_F']} °F", reference=row['reference'],
                 stress=row.get('S_allow_psi') or str(convert(row['S_allow_MPa'], 'MPa', 'psi')))
            for row in material_stresses()
            if (row['code_family'], row['code_edition'], row['product_form']) == (code, edition, product)
        ]
    if rule == PIPE_RULES[1]:
        select('liquid_weld', 'Pipe specification, grade and weld type · B31.4')
        select('material', 'Pipe grade for SMYS · confirm against material records')
        data['liquidStrength'] = {
            grade: dict(value=str(psi), reference=f'{LIQUID_PIPE_SMYS_REFERENCE}, line {line}')
            for grade, (psi, line) in LIQUID_PIPE_SMYS.items()
        }
        data['liquidWeld'] = dict(values=LIQUID_WELD_FACTORS, reference=LIQUID_WELD_REFERENCE['reference'])
    if rule == PIPE_RULES[2]:
        select('material', 'API 5L grade · ASME B31.8 2025')
        select('product_form', 'Steel pipe product form')
        select('temperature', 'Design temperature from table')
        select('basic_class', 'Location class · basic design factor')
        data['gas'] = dict(
            grades={f'API 5L {grade}': str(psi)
                    for grade, psi in GAS_5L_SMYS_PSI.items()},
            forms=sorted(GAS_5L_FORMS),
            temperatures={str(t): str(gas_temperature_factor(t)) for t in (250, 300, 350, 400, 450)},
            classes=GAS_BASIC_CLASS_F,
            smys_reference=GAS_SMYS_REFERENCE['reference'],
            temperature_reference=GAS_TEMPERATURE_REFERENCE['reference'],
            class_reference=GAS_CLASS_REFERENCE['reference'],
        )
    if not controls:
        return ''
    data['factorDefaults'] = {key: value for key, _, value in PRESETS.get(rule, ('', ()))[1] if key in EDITABLE_FACTORS}
    annex = _structural_controls(annex_tables, annex_error) if rule in {'API570_PIPE', 'API570_DATED'} else ''
    if annex_tables:
        data['structural'] = dict(tables=annex_tables, sizes=NPS, classes=CLASSES)
        data['selection'].update({key: values.get(key, '') for key in LOOKUP_FIELDS})
    payload = json.dumps(data).replace('<', '\\u003c')
    return ('<fieldset><legend>Reference lookups</legend><div class="fields">'
            + ''.join(controls) + '</div><p class="sample-sources" aria-live="polite"></p></fieldset>' + annex +
            f'<script type="application/json" id="sample-reference-data">{payload}</script>')



def _structural_controls(tables, error):
    markup = ('<fieldset><legend>API RP 574 Annex D structural thickness</legend>'
              '<p>Use the examples for straight spans only when Annex D material, temperature, span, '
              'support and loading assumptions apply. Use a reviewed manual value for other cases.</p>')
    if not tables:
        return f'{markup}<p class="warn">{E(error)}</p></fieldset>'
    labels = ('Annex D material', 'Annex D table temperature', 'Structural lookup NPS', 'Piping pressure class')
    fields = ''.join(f'<label>{label}<select name="{key}"><option value="">Manual entry</option></select></label>'
                     for key, label in zip(LOOKUP_FIELDS, labels))
    return (f'{markup}<div class="fields">{fields}</div>'
            '<p class="structural-source" aria-live="polite"></p></fieldset>')


def _observed_rate(previous, current, elapsed):
    readings = [Decimal(value) for value in (previous, current, elapsed)]
    if any(not value.is_finite() or value <= 0 for value in readings):
        raise ValueError('Both readings and the elapsed years must be positive finite numbers.')
    return Decimal(evaluate('CR_ST', dict(zip(
        ('t_previous_mm', 't_current_mm', 'elapsed_years'), readings)))['value'])


def _forecast(rules, inputs, wall, deduction):
    previous, elapsed, interval = (inputs.get(key) for key in ('previous_mm', 'elapsed_years', 'next_years'))
    if not any((previous, elapsed, interval)):
        return ''
    title = 'Next-inspection pressure candidate' if rules[0][1] in (*PIPE_RULES[1:], *VESSEL_FORMS) else 'Next-inspection MAWP candidate'
    try:
        if not all((previous, elapsed, interval)):
            raise ValueError('Enter previous UT, years between readings and years until the next inspection.')
        years = Decimal(interval)
        if not years.is_finite() or years <= 0:
            raise ValueError('Years until next inspection must be positive and finite.')
        rate = _observed_rate(previous, wall, elapsed)
        if rate < 0:
            raise ValueError(f'Observed rate is {numeric(rate)} mm/year. Resolve the increase in measured wall before forecasting.')
        if rate == 0:
            raise ValueError('Observed rate is 0 mm/year. A reviewed future rate is needed to forecast from unchanged readings.')
        projected = wall - rate * years
        net = projected - deduction
        pressure, label = min((pressure_at_thickness(net, key, inputs)[0], label) for label, key in rules)
    except (ValueError, DecimalException) as exc:
        return f'<dt>{title} withheld</dt><dd>{E(str(exc) or "Invalid forecast inputs.")}</dd>'
    return (f'<dt>Observed corrosion rate</dt><dd>{E(numeric(rate))} mm/year</dd>'
            f'<dt>Projected wall at next inspection</dt><dd>{E(numeric(projected))} mm '
            f'({E(numeric(net))} mm after deduction)</dd>'
            f'<dt>{title}</dt><dd><strong>{E(numeric(convert(pressure, "MPa", "psi")))} psi</strong> · {label} check</dd>')


def _positive(value, label):
    amount = Decimal(value or '0')
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f'{label} must be positive and finite.')
    return amount


def _optional_nonnegative(inputs, key):
    amount = Decimal(inputs.get(key) or '0')
    if not amount.is_finite() or amount < 0:
        raise ValueError(f'{key.replace("_", " ")} must be finite and nonnegative.')
    return amount


def _display_value(label, value, unit):
    return f'{value:.0f}' if unit == 'psi' and 'MAWP' in label else numeric(value)


def _result_rows(entries):
    return ''.join(f'<dt>{E(label)}</dt><dd>{E(_display_value(label, value, unit))} {E(unit)}</dd>'
                   for label, value, unit in entries)


def _inspection_result(geometry, inputs):
    current = _positive(inputs.get('t_current_mm'), 'Current wall')
    required = _positive(inputs.get('t_required_mm'), 'Reviewed required wall')
    original = _positive(inputs.get('original_psi'), 'Original vessel MAWP')
    years = _positive(inputs.get('next_years'), 'Planned inspection interval')
    observed = _observed_rate(inputs.get('t_previous_mm'), current, inputs.get('elapsed_years'))
    rate = _positive(inputs.get('reviewed_rate') or str(observed), 'Governing corrosion rate')
    head = _optional_nonnegative(inputs, 'static_head_psi')
    loss = rate * years
    net = current - 2 * loss
    life = (current - required) / rate
    entries = [('Observed short-term corrosion rate', observed, 'mm/yr'),
               ('Governing corrosion rate', rate, 'mm/yr')]
    note = ''
    if life <= 0:
        note = 'Current wall is at or below the reviewed required wall.'
    else:
        cap = min(life / 2, Decimal(10))
        if life < 4 and inputs.get('short_life_option') == 'yes':
            cap = min(life, Decimal(2))
        entries.extend([('Remaining life', life, 'yr'), ('Maximum non-RBI interval', cap, 'yr')])
        if years > cap:
            raise ValueError(f'The planned interval exceeds the {numeric(cap)} yr non-RBI limit.')
        entries.extend([('Estimated loss to next inspection', loss, 'mm'),
                        ('Projected wall at next inspection', current - loss, 'mm'),
                        ('API 510 wall used for MAWP', net, 'mm')])
        if net <= 0:
            note = 'The doubled corrosion deduction leaves no positive wall for MAWP.'
        else:
            pressure = pressure_at_thickness(net, geometry, inputs)[0]
            if geometry == 'VIII_UG27_HOOP':
                longitudinal = dict(inputs, E_joint=inputs.get('E_circumferential'))
                pressure = min(pressure, pressure_at_thickness(net, 'VIII_UG27_LONG', longitudinal)[0])
            at_top = convert(pressure, 'MPa', 'psi') - head
            if at_top <= 0:
                note = 'The component pressure candidate does not exceed the entered static head.'
            else:
                entries.extend([('Component pressure candidate at vessel top', at_top, 'psi'),
                                ('Original vessel MAWP cap', original, 'psi'),
                                ('Continued-use MAWP candidate', min(at_top, original), 'psi')])
    warning = f'<p class="warn">{E(note)} Continued-use MAWP withheld.</p>' if note else ''
    if not note and net < required:
        warning = '<p class="warn">The MAWP calculation wall is below the reviewed required wall. Review governing load limits.</p>'
    return ('<div class="sample-result" role="status"><h3>Draft API 510 vessel assessment</h3>'
            f'<dl>{_result_rows(entries)}</dl>{warning}'
            '<p>API 510 11th edition §§6.5.1.1, 7.2.1 and 7.3.1–7.3.4 (PDF pp. 44, 51–52). '
            'The selected component uses measured wall minus twice the estimated loss. '
            'The vessel rating also depends on the remaining components and applicable load checks.</p>'
            f'<p>Construction method: {E(REFERENCES[geometry])}.</p></div>')


def _pressure_result(rule, rules, inputs, wall):
    if wall is None:
        return '<dt>MAWP candidate</dt><dd>Enter measured thickness to calculate a pressure candidate.</dd>'
    try:
        deduction = Decimal(inputs.get('wall_deduction_mm') or '0')
        if not deduction.is_finite() or deduction < 0:
            raise ValueError('The wall deduction must be finite and nonnegative.')
        net = wall - deduction
        checks = [(pressure_at_thickness(net, key, inputs)[0], label, key) for label, key in rules]
        pressure, label, key = min(checks)
    except (ValueError, DecimalException) as exc:
        return f'<dt>MAWP candidate withheld</dt><dd>{E(str(exc) or "Invalid pressure inputs.")}</dd>'
    title = 'Pressure candidate (pipeline)' if rule in PIPE_RULES[1:] else 'MAWP candidate'
    return (
        f'<dt>{title} at entered wall</dt><dd><strong>{E(numeric(convert(pressure, "MPa", "psi")))} psi</strong><br>'
        f'Net wall {E(numeric(net))} mm · {label} check · {E(REFERENCES[key])}</dd>'
        + _forecast(rules, inputs, wall, deduction)
    )



def _api570_calculation(inputs, annex_tables):
    current = _positive(inputs.get('measured_mm'), 'Current wall')
    baseline = inputs.get('initial_mm'), inputs.get('long_years')
    previous = inputs.get('previous_mm'), inputs.get('elapsed_years')
    short_rate = _observed_rate(previous[0], current, previous[1]) if all(previous) else None
    long_rate = _observed_rate(baseline[0], current, baseline[1]) if all(baseline) else None
    if (any(previous) and short_rate is None) or (any(baseline) and long_rate is None):
        raise ValueError('Supply both the thickness and elapsed years for each UT baseline entered.')
    if short_rate is not None and long_rate is not None and Decimal(baseline[1]) <= Decimal(previous[1]):
        raise ValueError('The initial reading must be older than the previous reading.')
    basis = inputs.get('rate_basis')
    if basis not in {'short', 'long', 'reviewed'}:
        raise ValueError('Choose a reviewed corrosion-rate basis.')
    rate = {'short': short_rate, 'long': long_rate}.get(basis)
    if basis == 'reviewed':
        rate = Decimal(inputs.get('reviewed_rate') or '0')
    if rate is None or not rate.is_finite() or rate <= 0:
        raise ValueError('Select a positive observed rate or enter a positive reviewed rate.')
    pipe_rule = PIPE_RULES[0]
    check = evaluate(pipe_rule, inputs)
    if check['value'] is None:
        raise ValueError(' '.join(check['issues']))
    pressure_wall = Decimal(check['value'])
    structural = Decimal(inputs.get('structural_mm', ''))
    deduction = Decimal(inputs.get('wall_deduction_mm') or '0')
    if not structural.is_finite() or structural <= 0 or not deduction.is_finite() or deduction < 0:
        raise ValueError('Enter a positive structural minimum and a nonnegative wall deduction.')
    match = structural_cell(annex_tables, inputs)
    structural_basis = (match[1] if match and Decimal(match[0]) == structural
                        else 'Manual reviewed structural minimum')
    required = max(pressure_wall, structural)
    life = (current - required) / rate
    service_class = inputs.get('service_class')
    caps = {'1': Decimal(5), '2': Decimal(10), '3': Decimal(10)}
    if service_class not in caps:
        raise ValueError('Choose API 570 service Class 1, 2 or 3 for this non-RBI interval method.')
    entries = [
        ('Short-term corrosion rate', short_rate, 'mm/year'), ('Long-term corrosion rate', long_rate, 'mm/year'),
        ('Selected corrosion rate', rate, 'mm/year'), ('Pressure thickness', pressure_wall, 'mm'),
        ('Structural minimum', structural, 'mm'), ('Governing required thickness', required, 'mm'),
        ('Current measured wall', current, 'mm'), ('Margin to required thickness', current - required, 'mm'),
    ]
    notes = []
    if life <= 0:
        basis = ('pressure thickness' if pressure_wall > structural else
                 'structural minimum' if structural > pressure_wall else 'pressure and structural minima')
        comparison = 'equals' if current == required else 'is below'
        notes.append(f'Current measured wall ({numeric(current)} mm) {comparison} the required wall '
                     f'({numeric(required)} mm, governed by {basis}). Remaining life and next-inspection '
                     'results are withheld.')
    else:
        cap = min(life / 2, caps[service_class])
        if life < 4 and inputs.get('short_life_option') == 'yes':
            cap = min(life, Decimal(2), caps[service_class])
        years = Decimal(inputs.get('next_years') or cap)
        if not years.is_finite() or years <= 0 or years > cap:
            raise ValueError(f'Enter an interval above zero and at most {numeric(cap)} years, or leave it blank.')
        estimated_loss = rate * years
        projected = current - estimated_loss
        mawp_wall = current - 2 * estimated_loss
        entries.extend([
            ('Remaining life', life, 'years'), ('Maximum UT interval', cap, 'years'),
            ('Selected next inspection interval', years, 'years'),
            ('Estimated corrosion loss by next inspection', estimated_loss, 'mm'),
            ('Projected wall', projected, 'mm'),
            ('API 570 MAWP corrosion deduction (2 × estimated loss)', 2 * estimated_loss, 'mm'),
        ])
        for label, wall in [('Current MAWP candidate', current), ('Next-inspection MAWP candidate', mawp_wall)]:
            try:
                pressure, _ = pressure_at_thickness(wall - deduction, pipe_rule, inputs)
            except (ValueError, DecimalException) as exc:
                notes.append(f'{label} withheld: {exc}')
            else:
                entries.append((f'Wall used for {label.lower()}', wall - deduction, 'mm'))
                entries.append((label, convert(pressure, 'MPa', 'psi'), 'psi'))
    return entries, notes, structural_basis, check['source_reference']


def _api570_result(inputs, annex_tables):
    entries, notes, structural_basis, pressure_basis = _api570_calculation(inputs, annex_tables)
    rows = _result_rows((label, value, unit) for label, value, unit in entries if value is not None)
    messages = ''.join(f'<p class="warn">{E(note)}</p>' for note in notes)
    return (f'<div class="sample-result" role="status"><h3>Draft API 570 piping assessment</h3>'
            f'<dl>{rows}</dl>{messages}<p>Structural thickness basis: {E(structural_basis)}</p>'
            '<p>The current MAWP candidate uses the measured wall. The continued-use MAWP candidate uses '
            'measured wall minus twice the estimated loss to the next inspection (§7.5). '
            'Any entered wall deduction is also applied to both pressure checks.</p>'
            f'<p>{E(API570_REFERENCE)}</p><p>{E(pressure_basis)}</p></div>')


def _api570_controls(submitted):
    values = submitted or {}
    return (
        _select_control('service_class', 'API 570 piping service class',
                        {str(i): f'Class {i}' for i in (1, 2, 3)}, values)
        + _select_control('rate_basis', 'Governing corrosion-rate basis',
                          {'short': 'Short-term UT', 'long': 'Long-term UT', 'reviewed': 'Reviewed manual rate'}, values)
        + field('reviewed_rate', 'Reviewed manual rate (mm/year)', values.get('reviewed_rate', ''), 'number', False)
        + field('next_years', 'Next inspection interval (years), blank uses maximum', values.get('next_years', ''), 'number', False)
        + _short_life_control(values)
    )


def _short_life_control(values):
    checked = ' checked' if values.get('short_life_option') == 'yes' else ''
    return ('<label><input type="checkbox" name="short_life_option" value="yes"'
            f'{checked}> Use reviewed short-life provision when remaining life is under four years</label>')


def _select_control(name, label, options, values, *, required=True):
    selected = values.get(name, '')
    choices = ''.join(f'<option value="{E(key)}"{" selected" if key == selected else ""}>{E(text)}</option>'
                      for key, text in options.items())
    required_attr = ' required' if required else ''
    return f'<label>{E(label)}<select name="{E(name)}"{required_attr}><option value="">Choose…</option>{choices}</select></label>'


GAS_TEST_FACTORS = {'furnace': Decimal('0.60'), 'mill': Decimal('0.85'), 'retest': Decimal('0.85')}


def _gas_pressure_result(inputs, pressure_wall):
    basis = inputs.get('gas_test_basis')
    if basis not in GAS_TEST_FACTORS:
        raise ValueError('Select the applicable mill test or qualified retest basis.')
    test_pressure = _positive(inputs.get('gas_test_psi'), 'Documented test pressure')
    cap = test_pressure * GAS_TEST_FACTORS[basis]
    design = convert(inputs['P_MPa'], 'MPa', 'psi')
    rows = [('Pressure design thickness', pressure_wall, 'mm'),
            ('§841.1.3 test pressure ceiling', cap, 'psi')]
    nominal = inputs.get('nominal_mm')
    if nominal:
        formula_pressure = pressure_at_thickness(_positive(nominal, 'Nominal wall'), PIPE_RULES[2], inputs)[0]
        formula_psi = convert(formula_pressure, 'MPa', 'psi')
        limit = min(formula_psi, cap)
        rows.extend([('§841.1.1 pressure at nominal wall', formula_psi, 'psi'),
                     ('Governing design pressure candidate', limit, 'psi')])
    else:
        limit = cap
    warning = '<p class="warn">Entered design pressure exceeds the governing available pressure limit.</p>' if design > limit else ''
    return ('<div class="sample-result" role="status"><h3>Draft B31.8 design pressure check</h3>'
            f'<dl>{_result_rows(rows)}</dl>{warning}'
            '<p>ASME B31.8-2025 §§841.1.1 and 841.1.3 (PDF pp. 66, 68). '
            'Supply nominal wall to compare the pipe formula with the test ceiling. '
            'The retest basis requires eligibility review under §841.1.3(b).</p></div>')


def _pipe_nominal_result(rule, inputs, pressure_wall):
    if inputs.get('design_allowance_mm') in (None, ''):
        return '<dt>Nominal wall check</dt><dd>Enter the design allowance total, including zero if applicable.</dd>'
    allowance = _optional_nonnegative(inputs, 'design_allowance_mm')
    required = pressure_wall + allowance
    nominal = inputs.get('nominal_mm')
    available = _positive(nominal, 'Nominal wall') if nominal else None
    reference = 'B31.4 §403.2.1'
    required_nominal = required
    if rule == PIPE_RULES[0]:
        if inputs.get('mill_tolerance_pct') in (None, ''):
            return '<dt>Nominal wall check</dt><dd>Enter the applicable mill minus tolerance, including zero if applicable.</dd>'
        tolerance = _optional_nonnegative(inputs, 'mill_tolerance_pct') / 100
        if tolerance >= 1:
            raise ValueError('Mill minus tolerance must be less than 100%.')
        required_nominal /= 1 - tolerance
        if available is not None:
            available *= 1 - tolerance
        reference = 'B31.3 §304.1.1'
    rows = [('Required design wall including allowances', required, 'mm'),
            ('Minimum nominal wall for design check', required_nominal, 'mm')]
    if available is not None:
        rows.extend([('Available wall for design check', available, 'mm'),
                     ('Wall margin', available - required, 'mm')])
    return _result_rows(rows) + f'<dt>Nominal wall basis</dt><dd>{E(reference)}</dd>'


def _tank_shell_result(inputs):
    record = calculate_tank('api650', inputs)
    outputs = record['outputs']
    labels = {'product_mm': 'Product design wall', 'hydrotest_mm': 'Hydrotest wall',
              'code_nominal_min_mm': 'Code nominal plate minimum',
              'governing_candidate_mm': 'Governing shell thickness candidate'}
    rows = _result_rows((label, outputs[key], 'mm') for key, label in labels.items())
    return ('<div class="sample-result" role="status"><h3>Draft API 650 shell design</h3>'
            f'<dl>{rows}</dl><p>{E(record["reference"])}</p><p>{E(record["note"])}</p></div>')


def _result(rule, inputs, annex_tables=()):
    if rule in API510_FORMS:
        return _inspection_result(API510_FORMS[rule], inputs)
    if rule == 'API570_PIPE':
        return _api570_result(inputs, annex_tables)
    if rule == 'API650_ONE_FOOT_PRODUCT':
        return _tank_shell_result(inputs)
    measured = inputs.get('measured_mm', '')
    wall = Decimal(measured) if measured else None
    if wall is not None and (not wall.is_finite() or wall <= 0):
        raise ValueError('Measured thickness must be a positive finite number.')

    rules = {
        'VIII_UG27_HOOP': (('Hoop', rule), ('Longitudinal', 'VIII_UG27_LONG')),
    }.get(rule, (('Pressure', rule),))
    results = [(label, evaluate(key, inputs)) for label, key in rules]
    for _, result in results:
        if result['value'] is None:
            raise ValueError(' '.join(result['issues']))
    governing = max(Decimal(result['value']) for _, result in results)
    if rule == PIPE_RULES[2]:
        return _gas_pressure_result(inputs, governing)
    markup = '<div class="sample-result" role="status"><h3>Draft calculated thickness</h3><dl>'
    for label, result in results:
        markup += (f'<dt>{label} thickness</dt><dd><strong>{E(numeric(result["value"]))} mm</strong>'
                   f'<br><code>{E(result["formula"])}</code><br>{E(result["source_reference"])}</dd>')
    if wall is not None:
        markup += f'<dt>Measured wall minus largest calculation above</dt><dd>{E(numeric(wall - governing))} mm</dd>'
    if rule in PIPE_RULES[:2]:
        markup += _pipe_nominal_result(rule, inputs, governing)
    return markup + _pressure_result(rule, rules, inputs, wall) + '</dl></div>'


def panel(sample='', submitted=None):
    if sample in {'', 'ROW7', 'API570_DATED'}:
        return _api570_panel(submitted)
    rule = sample if sample in PRESETS else next(iter(PRESETS))
    values = submitted or {}
    fields = PRESETS[rule][1]
    controls = [
        field(_form_key(key), _form_label(key, label),
              values.get(_form_key(key), default if key in EDITABLE_FACTORS else ''), kind='number',
              required=rule != 'API570_PIPE' or key not in {'initial_mm', 'long_years', 'previous_mm', 'elapsed_years'})
        for key, label, default in fields
    ]
    if rule in (*PIPE_RULES[:2], *VESSEL_FORMS):
        controls.append(field('measured_mm', 'Current measured thickness (mm)',
                              (submitted or {}).get('measured_mm', ''), kind='number', required=False))
    if rule in PIPE_RULES:
        controls.append(field('nominal_mm', 'Selected nominal wall (mm)',
                              (submitted or {}).get('nominal_mm', ''), kind='number', required=False))
    if rule in PIPE_RULES[:2]:
        controls.append(field('design_allowance_mm', 'Total design allowances (mm)',
                              values.get('design_allowance_mm', ''), 'number', False))
    if rule == PIPE_RULES[0]:
        controls.append(field('mill_tolerance_pct', 'Mill minus tolerance (%)',
                              values.get('mill_tolerance_pct', ''), 'number', False))
    if rule == PIPE_RULES[2]:
        controls.extend([
            _select_control('gas_test_basis', 'Documented test basis', {
                'mill': 'Mill test · other pipe', 'furnace': 'Mill test · furnace butt-welded',
                'retest': 'Qualified retest · other pipe',
            }, values),
            field('gas_test_psi', 'Documented test pressure (psi)', values.get('gas_test_psi', ''), 'number'),
        ])
    if rule == 'API650_ONE_FOOT_PRODUCT':
        controls.append(_select_control('course_position', 'Shell course position (required for diameter > 3.2 m and < 15 m)',
                                       {'lowest': 'Lowest course', 'upper': 'Upper course'}, values, required=False))
    if rule in (*PIPE_RULES[:2], *VESSEL_FORMS, 'API570_PIPE'):
        controls.append(field('wall_deduction_mm', 'Wall deduction for pressure check (mm)',
                              (submitted or {}).get('wall_deduction_mm', ''), kind='number', required=False))
    if rule == 'API570_PIPE':
        controls.append(_api570_controls(submitted))
    if rule in API510_FORMS:
        controls.extend([
            field('reviewed_rate', 'Reviewed governing rate override (mm/yr)', values.get('reviewed_rate', ''), 'number', False),
            field('static_head_psi', 'Static head from vessel top to component (psi, blank = 0)',
                  values.get('static_head_psi', ''), 'number', False),
            _short_life_control(values),
        ])
    forecast_fields = ''
    if rule in (*PIPE_RULES[:2], *VESSEL_FORMS):
        forecast_fields = ('<details><summary>Optional wall projection using the construction equation</summary><div class="fields">'
                           + ''.join(field(key, label, (submitted or {}).get(key, ''), kind='number', required=False)
                                     for key, label in (
                                         ('previous_mm', 'Previous measured thickness (mm)'),
                                         ('elapsed_years', 'Years between UT readings'),
                                         ('next_years', 'Years from current UT to next inspection'),
                                     )) + '</div></details>')
    annex_tables, annex_error = (), ''
    if rule == 'API570_PIPE':
        try:
            annex_tables = structural_tables()
        except ValueError as exc:
            annex_error = str(exc)
    output = ''
    if submitted is not None:
        try:
            if sample not in PRESETS:
                raise ValueError('Choose a supported calculation preset.')
            inputs = dict(submitted)
            for key, label, _ in fields:
                form_key = _form_key(key)
                if form_key != key:
                    raw = submitted.get(form_key, '')
                    if not raw:
                        raise ValueError(f'Enter {_form_label(key, label)}.')
                    units = ('in', 'mm') if key == 'D_outside_mm' else ('psi', 'MPa')
                    inputs[key] = convert(raw, *units)
            output = _result(rule, inputs, annex_tables)
        except DecimalException:
            output = '<p class="warn" role="alert">Enter valid decimal inputs within the supported numeric range.</p>'
        except ValueError as exc:
            output = f'<p class="warn" role="alert">{E(exc)}</p>'
    return (
        '<section id="sample-calculator"><h2>Sample calculator</h2>'
        '<p>Choose a code, fill in your inputs, and use the reference dropdowns for available table values. Samples do not save to your project. '
        'The thickness comparison covers the equations shown. Review other applicable limits separately.</p>'
        + _code_picker(rule)
        + f'<h3>{E(PRESETS[rule][0].split(" · ", 1)[1])}</h3>'
        + f'<form id="sample-inputs" action="/codes#sample-calculator" method="post">{hidden("sample", rule)}'
        + (f'<p>Non-RBI Class 1–3 straight process piping. Use comparable UT readings from the same CML. '
         f'Pressure calculations use {E(REFERENCES[PIPE_RULES[0]])}.</p>' if rule == 'API570_PIPE'
         else '<p>Non-RBI internal/on-stream inspection. Use corroded-condition geometry and a reviewed required wall. '
              'The previous and current readings supply the short-term rate unless you enter a reviewed governing rate.</p>'
         if rule in API510_FORMS else f'<p><code>{E(FORMULAS[rule])}</code><br>{E(REFERENCES[rule])}</p>')
        + ('<p>For continued-use vessel MAWP, use the API 510 calculator. This construction sample uses the '
           'entered geometry and checks internal pressure only.</p>' if rule in VESSEL_FORMS else '')
        + ('<p>Prefilled coefficients and factors are editable sample assumptions. Confirm them for your case.</p>'
           if any(key in EDITABLE_FACTORS for key, _, _ in fields) else '')
        + _reference_controls(rule, submitted, annex_tables, annex_error)
        + '<div class="fields">' + ''.join(controls) + '</div>' + forecast_fields
        + '<button class="primary">Calculate sample</button></form>' + output + '</section>'
    )



API570_UT = (('older', 'Initial'), ('previous', 'Previous'), ('current', 'Current'))
API570_FACTORS = PRESETS[PIPE_RULES[0]][1][3:]


def _dated_pipe_inputs(values):
    inspection_fields = {'service_class': 'API 570 piping service class', 'rate_basis': 'governing corrosion-rate basis'}
    missing = [label for key, label in inspection_fields.items() if not values.get(key)]
    if missing:
        raise ValueError(f'Choose {" and ".join(missing)} in API 570 inspection basis.')
    inputs = dict(values, measured_mm=values.get('current_mm'))
    readings = []
    for key, label in API570_UT:
        day, wall = values.get(f'{key}_date'), values.get(f'{key}_mm')
        if bool(day) != bool(wall) or (key == 'current' and not day):
            raise ValueError(f'Enter both the UT date and reading for {label.lower()}.')
        if day:
            readings.append((day, _positive(wall, f'{label} UT reading')))
    for (start, _), (end, _) in zip(readings, readings[1:]):
        if elapsed_days(start, end, 365) <= 0:
            raise ValueError('UT dates must increase from left to right.')
    current_date = readings[-1][0]
    if len(readings) >= 2:
        previous, wall = readings[-2]
        inputs.update(previous_mm=str(wall), elapsed_years=str(Decimal(elapsed_days(previous, current_date, 365)) / 365))
    if len(readings) >= 3:
        initial, wall = readings[0]
        inputs.update(initial_mm=str(wall), long_years=str(Decimal(elapsed_days(initial, current_date, 365)) / 365))
    for key, form_key, original, target, label in (
        ('P_MPa', 'P_psi', 'psi', 'MPa', 'Design pressure'),
        ('D_outside_mm', 'D_outside_in', 'in', 'mm', 'Outside diameter'),
        ('S_B313_MPa', 'S_B313_psi', 'psi', 'MPa', 'Allowable stress'),
    ):
        inputs[key] = convert(_positive(values.get(form_key), label), original, target)
    return inputs



def _api570_panel(submitted):
    values = submitted or {}
    try:
        tables, error = structural_tables(), ''
    except ValueError as exc:
        tables, error = (), str(exc)
    output = ''
    if submitted is not None:
        try:
            output = _api570_result(_dated_pipe_inputs(values), tables)
        except (DecimalException, ValueError, TypeError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else 'Complete the required numeric inputs.'
            output = f'<p class="warn" role="alert">{E(reason)}</p>'

    def number(key, label, *, default='', required=True):
        return field(key, label, values.get(key, default), 'number', required)

    design = ''.join(number(key, label) for key, label in (
        ('P_psi', 'Design pressure (psi)'), ('D_outside_in', 'Outside diameter (in)'),
        ('S_B313_psi', 'Allowable stress S (psi)'), ('structural_mm', 'Structural minimum (mm)'),
    ))
    readings = []
    for key, label in API570_UT:
        required = key == 'current'
        readings.append(field(f'{key}_date', f'{label} UT date', values.get(f'{key}_date', ''),
                              'date', required))
        readings.append(number(f'{key}_mm', f'{label} minimum UT (mm)', required=required))
    factors = ''.join(number(key, label, default=default) for key, label, default in API570_FACTORS)
    factors += number('wall_deduction_mm', 'Other wall deduction for pressure (mm)', required=False)
    return (
        '<section id="sample-calculator"><h2>Calculator</h2>' + _code_picker('API570_DATED')
        + '<h3>API 570 · Straight process piping</h3>'
        '<p>Non-RBI inspection for B31.3 piping. Use the previous and current readings for short-term corrosion. '
        'Add the initial reading for a long-term rate. Elapsed years use actual days divided by 365.</p>'
        '<form id="sample-inputs" action="/codes?code=api570#calculation-feedback" method="post" novalidate>'
        + hidden('sample', 'API570_DATED')
        + '<fieldset><legend>Pipe design</legend><div class="fields">' + design + '</div>'
        + '<details><summary>Look up OD, allowable stress or structural minimum</summary>'
        + _reference_controls('API570_DATED', submitted, tables, error) + '</details></fieldset>'
        + '<fieldset><legend>Ultrasonic thickness readings</legend><div class="fields">'
        + ''.join(readings[2:]) + '</div><details' + (' open' if values.get('older_date') or values.get('older_mm') else '')
        + '><summary>Initial reading for long-term rate</summary><div class="fields">'
        + ''.join(readings[:2]) + '</div></details></fieldset>'
        + '<fieldset><legend>API 570 inspection basis</legend><div class="fields">'
        + _api570_controls(submitted) + '</div></fieldset>'
        + '<details><summary>B31.3 factors and other wall deduction</summary>'
        + '<p>Confirm the prefilled E, W and Y values for your piping.</p><div class="fields">' + factors
        + '</div></details><button class="primary">Calculate</button></form>'
        + '<div id="calculation-feedback">' + output + '</div></section>'
    )
