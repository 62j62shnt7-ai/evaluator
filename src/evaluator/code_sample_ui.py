"""Editable examples for the code library's draft arithmetic."""
import json
from decimal import Decimal, DecimalException

from evaluator.engineering.batch_rules import convert, pressure_at_thickness
from evaluator.engineering.reference_rules import (
    GAS_5L_FORMS, GAS_5L_SMYS_PSI, GAS_BASIC_CLASS_F, GAS_CLASS_REFERENCE,
    GAS_SMYS_REFERENCE, GAS_TEMPERATURE_REFERENCE, gas_temperature_factor,
    LIQUID_PIPE_SMYS, LIQUID_PIPE_SMYS_REFERENCE, LIQUID_WELD_FACTORS, LIQUID_WELD_REFERENCE,
)
from evaluator.engineering.references import dimensions, material_stresses
from evaluator.engineering.structural_reference import CLASSES, LOOKUP_FIELDS, NPS, structural_cell, structural_tables
from evaluator.engineering.draft import FORMULAS, REFERENCES, evaluate
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
    'CR_ST': ('API 510 · Vessel corrosion rate and remaining life', (
        ('t_previous_mm', 'Previous measured wall (mm)', '11.8'),
        ('t_current_mm', 'Current measured wall (mm)', '11.2'),
        ('elapsed_years', 'Years between UT readings', '2'),
        ('t_required_mm', 'Reviewed required wall (mm)', '5'))),
    'API650_ONE_FOOT_PRODUCT': ('API 650 · One-foot shell design', (
        ('D_m', 'Tank diameter (m)', '30'), ('H_m', 'Liquid height above course bottom (m)', '12'),
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
    'F_class', 'T_temp', 'E_joint',
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
API570_REFERENCE = 'API 570, 5th edition with Addendum 1, §§6.3.3, 7.1, 7.2 and 7.6; Table 1 (PDF p. 53)'
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
    'api570': ('API 570 · 5th edition', 'API570_PIPE'),
    'api650': ('API 650 · 14th edition', 'API650_ONE_FOOT_PRODUCT'),
}
VESSEL_FORMS = {'VIII_UG27_HOOP': 'Cylindrical shell', 'VIII_UG32_ELLIP': '2:1 ellipsoidal head',
                'VIII_UG32_TORI': 'Standard torispherical head'}


def code_rule(code, geometry):
    if code == 'viii' and geometry in VESSEL_FORMS:
        return geometry
    return CODES.get(code, ('', ''))[1]


def _code_picker(rule):
    selected = 'viii' if rule in VESSEL_FORMS else next(
        code for code, (_, candidate) in CODES.items() if candidate == rule)
    options = ''.join(f'<option value="{code}"{" selected" if code == selected else ""}>{label}</option>'
                      for code, (label, _) in CODES.items())
    geometry = ''
    if selected == 'viii':
        forms = ''.join(f'<option value="{key}"{" selected" if key == rule else ""}>{label}</option>'
                        for key, label in VESSEL_FORMS.items())
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

    if rule in (*PIPE_RULES, 'API570_PIPE'):
        data['dimensions'] = [
            dict(family=row['family'], nps=row['nps'], schedule=row['schedule'],
                 od=row['od_in'], wall=row['nominal_mm'],
                 reference=f"{row['reference']}, PDF p. {row['pdf_page']}")
            for row in dimensions() if not row['issues']
        ]
        select('pipe_family', 'Pipe dimension table')
        select('nps', 'Nominal pipe size (NPS)')
        select('schedule', 'Pipe schedule')
    stress_rule = PIPE_RULES[0] if rule == 'API570_PIPE' else rule
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
    data['factorDefaults'] = {key: value for key, _, value in PRESETS[rule][1] if key in EDITABLE_FACTORS}
    annex = _structural_controls(annex_tables, annex_error) if rule == 'API570_PIPE' else ''
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
    title = 'Next-inspection pressure candidate' if rules[0][1] in PIPE_RULES[1:] else 'Next-inspection MAWP candidate'
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


def _inspection_result(inputs):
    required = Decimal(inputs.get('t_required_mm') or '0')
    if not required.is_finite() or required <= 0:
        raise ValueError('Reviewed required wall must be positive and finite.')
    rate = _observed_rate(*(inputs.get(key, '') for key in ('t_previous_mm', 't_current_mm', 'elapsed_years')))
    life = evaluate('REMAINING_LIFE', dict(t_current_mm=inputs['t_current_mm'],
                    t_required_mm=required, approved_governing_CR_mm_per_year=rate))
    life_text = numeric(life['value']) + ' years' if life['value'] else ', '.join(life['issues'])
    return ('<div class="sample-result" role="status"><h3>Draft inspection history</h3><dl>'
            f'<dt>Observed corrosion rate</dt><dd>{E(numeric(rate))} mm/year</dd>'
            f'<dt>Remaining life using the observed rate</dt><dd>{E(life_text)}</dd></dl></div>')


def _pressure_result(rule, rules, inputs, wall):
    if rule == 'API650_ONE_FOOT_PRODUCT':
        return '<dt>MAWP</dt><dd>API 650 one-foot shell design returns thickness for the entered liquid height.</dd>'
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



def _api570_result(inputs, annex_tables):
    current = Decimal(inputs.get('measured_mm', ''))
    short_rate = _observed_rate(inputs.get('previous_mm', ''), current, inputs.get('elapsed_years', ''))
    long_rate = _observed_rate(inputs.get('initial_mm', ''), current, inputs.get('long_years', ''))
    if Decimal(inputs['long_years']) <= Decimal(inputs['elapsed_years']):
        raise ValueError('The initial reading must be older than the previous reading.')
    basis = inputs.get('rate_basis')
    if basis not in {'short', 'long', 'reviewed'}:
        raise ValueError('Choose a reviewed corrosion-rate basis.')
    rate = {'short': short_rate, 'long': long_rate}.get(basis)
    if basis == 'reviewed':
        rate = Decimal(inputs.get('reviewed_rate') or '0')
    if not rate.is_finite() or rate <= 0:
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
    ]
    notes = []
    if life <= 0:
        notes.append('Current wall is at or below the required wall. Remaining life and next-inspection results are withheld.')
    else:
        cap = min(life / 2, caps[service_class])
        if life < 4 and inputs.get('short_life_option') == 'yes':
            cap = min(life, Decimal(2), caps[service_class])
        years = Decimal(inputs.get('next_years') or cap)
        if not years.is_finite() or years <= 0 or years > cap:
            raise ValueError(f'Enter an interval above zero and at most {numeric(cap)} years, or leave it blank.')
        projected = current - rate * years
        entries.extend([
            ('Remaining life', life, 'years'), ('Maximum UT interval', cap, 'years'),
            ('Selected next inspection interval', years, 'years'), ('Projected wall', projected, 'mm'),
        ])
        for label, wall in [('Current MAWP candidate', current), ('Next-inspection MAWP candidate', projected)]:
            try:
                pressure, _ = pressure_at_thickness(wall - deduction, pipe_rule, inputs)
            except (ValueError, DecimalException) as exc:
                notes.append(f'{label} withheld: {exc}')
            else:
                entries.append((f'Wall used for {label.lower()}', wall - deduction, 'mm'))
                entries.append((label, convert(pressure, 'MPa', 'psi'), 'psi'))
    rows = ''.join(f'<dt>{label}</dt><dd>{E(numeric(value))} {unit}</dd>' for label, value, unit in entries)
    messages = ''.join(f'<p class="warn">{E(note)}</p>' for note in notes)
    return (f'<div class="sample-result" role="status"><h3>Draft API 570 piping assessment</h3>'
            f'<dl>{rows}</dl>{messages}<p>Structural thickness basis: {E(structural_basis)}</p>'
            f'<p>{E(API570_REFERENCE)}</p><p>{E(check["source_reference"])}</p></div>')


def _api570_controls(submitted):
    values = submitted or {}
    def select(name, label, options):
        selected = values.get(name, '')
        options = ''.join(f'<option value="{key}"{" selected" if key == selected else ""}>{text}</option>'
                          for key, text in options)
        return f'<label>{label}<select name="{name}" required><option value="">Choose…</option>{options}</select></label>'

    return (
        select('service_class', 'API 570 piping service class', [(str(i), f'Class {i}') for i in (1, 2, 3)])
        + select('rate_basis', 'Governing corrosion-rate basis',
                 [('short', 'Short-term UT'), ('long', 'Long-term UT'), ('reviewed', 'Reviewed manual rate')])
        + field('reviewed_rate', 'Reviewed manual rate (mm/year)', values.get('reviewed_rate', ''), 'number', False)
        + field('next_years', 'Next inspection interval (years), blank uses maximum', values.get('next_years', ''), 'number', False)
        + '<label><input type="checkbox" name="short_life_option" value="yes"'
        + (' checked' if values.get('short_life_option') == 'yes' else '')
        + '> Use reviewed short-life interval provision when remaining life is under four years</label>'
    )


def _result(rule, inputs, annex_tables=()):
    if rule == 'CR_ST':
        return _inspection_result(inputs)
    if rule == 'API570_PIPE':
        return _api570_result(inputs, annex_tables)
    measured = inputs.get('measured_mm', '')
    wall = Decimal(measured) if measured else None
    if wall is not None and (not wall.is_finite() or wall <= 0):
        raise ValueError('Measured thickness must be a positive finite number.')

    rules = {
        'VIII_UG27_HOOP': (('Hoop', rule), ('Longitudinal', 'VIII_UG27_LONG')),
        'API650_ONE_FOOT_PRODUCT': (('Product', rule), ('Hydrotest', 'API650_ONE_FOOT_HYDRO')),
    }.get(rule, (('Pressure', rule),))
    results = [(label, evaluate(key, inputs)) for label, key in rules]
    for _, result in results:
        if result['value'] is None:
            raise ValueError(' '.join(result['issues']))
    governing = max(Decimal(result['value']) for _, result in results)
    markup = '<div class="sample-result" role="status"><h3>Draft calculated thickness</h3><dl>'
    for label, result in results:
        markup += (f'<dt>{label} thickness</dt><dd><strong>{E(numeric(result["value"]))} mm</strong>'
                   f'<br><code>{E(result["formula"])}</code><br>{E(result["source_reference"])}</dd>')
    if wall is not None:
        markup += f'<dt>Measured wall minus largest calculation above</dt><dd>{E(numeric(wall - governing))} mm</dd>'
    return markup + _pressure_result(rule, rules, inputs, wall) + '</dl></div>'


def panel(sample='', submitted=None):
    rule = sample if sample in PRESETS else next(iter(PRESETS))
    values = submitted or {}
    fields = PRESETS[rule][1]
    controls = [
        field(_form_key(key), _form_label(key, label),
              values.get(_form_key(key), default if key in EDITABLE_FACTORS else ''), kind='number')
        for key, label, default in fields
    ]
    if rule not in {'CR_ST', 'API570_PIPE'}:
        controls.append(field('measured_mm', 'Current measured thickness (mm)',
                              (submitted or {}).get('measured_mm', ''), kind='number', required=False))
    if rule in (*PIPE_RULES, 'API570_PIPE'):
        controls.append(field('nominal_mm', 'Nominal wall (mm), reference only',
                              (submitted or {}).get('nominal_mm', ''), kind='number', required=False))
    if rule not in {'API650_ONE_FOOT_PRODUCT', 'CR_ST'}:
        controls.append(field('wall_deduction_mm', 'Wall deduction for pressure check (mm)',
                              (submitted or {}).get('wall_deduction_mm', ''), kind='number', required=False))
    if rule == 'API570_PIPE':
        controls.append(_api570_controls(submitted))
    forecast_fields = ''
    if rule not in {'API650_ONE_FOOT_PRODUCT', 'CR_ST', 'API570_PIPE'}:
        forecast_fields = ('<fieldset><legend>Next inspection (optional)</legend><div class="fields">'
                           + ''.join(field(key, label, (submitted or {}).get(key, ''), kind='number', required=False)
                                     for key, label in (
                                         ('previous_mm', 'Previous measured thickness (mm)'),
                                         ('elapsed_years', 'Years between UT readings'),
                                         ('next_years', 'Years from current UT to next inspection'),
                                     )) + '</div></fieldset>')
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
         else f'<p><code>{E(FORMULAS[rule])}</code><br>{E(REFERENCES[rule])}</p>')
        + ('<p>Prefilled coefficients and factors are editable sample assumptions. Confirm them for your case.</p>'
           if any(key in EDITABLE_FACTORS for key, _, _ in fields) else '')
        + _reference_controls(rule, submitted, annex_tables, annex_error)
        + '<div class="fields">' + ''.join(controls) + '</div>' + forecast_fields
        + '<button class="primary">Calculate sample</button></form>' + output + '</section>'
    )
