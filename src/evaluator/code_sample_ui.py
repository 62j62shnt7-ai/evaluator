"""Editable examples for the code library's draft arithmetic."""
import json
from decimal import Decimal, DecimalException

from evaluator.engineering.batch_rules import convert, pressure_at_thickness
from evaluator.engineering.reference_rules import (
    GAS_5L_FORMS, GAS_5L_SMYS_PSI, GAS_BASIC_CLASS_F, GAS_CLASS_REFERENCE,
    GAS_SMYS_REFERENCE, GAS_TEMPERATURE_REFERENCE, gas_temperature_factor,
)
from evaluator.engineering.references import dimensions, material_stresses
from evaluator.engineering.draft import FORMULAS, REFERENCES, evaluate
from evaluator.workflow_ui import E, field, hidden, numeric


PIPE = (
    ('P_MPa', 'Design pressure (MPa)', '5.5158'),
    ('D_outside_mm', 'Outside diameter (mm)', '219.075'),
)
PRESETS = {
    'B31_3_304_1_2': ('B31.3 · A106 B, NPS 8 Sch 80', PIPE + (
        ('S_B313_MPa', 'Allowable stress S (MPa)', '137.895'),
        ('E_quality', 'Quality factor E', '1'), ('W_reduction', 'Weld reduction factor W', '1'),
        ('Y_coefficient', 'Coefficient Y', '0.4'))),
    'B31_4_403_2_1': ('B31.4 · Liquid transmission', PIPE + (
        ('SMYS_MPa', 'Specified minimum yield strength (MPa)', '358.5274'),
        ('F_design', 'Design factor F', '0.72'), ('E_weld', 'Weld factor E', '1'))),
    'B31_8_841_1_1': ('B31.8 · X52 seamless, Class 3', PIPE + (
        ('SMYS_MPa', 'Specified minimum yield strength (MPa)', '359.9063'),
        ('F_class', 'Class design factor F', '0.5'), ('E_weld', 'Weld factor E', '1'),
        ('T_temp', 'Temperature factor T', '1'))),
    'VIII_UG27_HOOP': ('VIII-1 · SA-516 Grade 70 cylindrical shell', (
        ('P_MPa', 'Design pressure (MPa)', '1.0342'), ('R_inside_mm', 'Inside radius (mm)', '609.6'),
        ('S_allow_MPa', 'Allowable stress S (MPa)', '138'), ('E_joint', 'Joint efficiency E', '0.85'))),
    'VIII_UG32_ELLIP': ('VIII-1 · SA-516 Grade 70 2:1 ellipsoidal head', (
        ('P_MPa', 'Design pressure (MPa)', '1.0342'), ('D_inside_mm', 'Inside diameter (mm)', '1219.2'),
        ('S_allow_MPa', 'Allowable stress S (MPa)', '138'), ('E_joint', 'Joint efficiency E', '0.85'))),
    'API650_ONE_FOOT_PRODUCT': ('API 650 · One-foot shell design', (
        ('D_m', 'Tank diameter (m)', '30'), ('H_m', 'Liquid height above course bottom (m)', '12'),
        ('G', 'Product specific gravity', '0.85'), ('Sd_MPa', 'Product design stress (MPa)', '160'),
        ('CA_mm', 'Corrosion allowance (mm)', '2'), ('St_MPa', 'Hydrotest stress (MPa)', '171'))),
}


PIPE_RULES = ('B31_3_304_1_2', 'B31_4_403_2_1', 'B31_8_841_1_1')
STRESS_CONTEXTS = {
    PIPE_RULES[0]: ('ASME B31.3', '2024', 'pipe', 'S_B313_MPa'),
    'VIII_UG27_HOOP': ('ASME VIII-1', '2025', 'plate', 'S_allow_MPa'),
    'VIII_UG32_ELLIP': ('ASME VIII-1', '2025', 'plate', 'S_allow_MPa'),
}


CODES = {
    'b313': ('ASME B31.3 · 2024', 'B31_3_304_1_2'),
    'b314': ('ASME B31.4 · 2025', 'B31_4_403_2_1'),
    'b318': ('ASME B31.8 · 2025', 'B31_8_841_1_1'),
    'viii': ('ASME VIII-1 · 2025', 'VIII_UG27_HOOP'),
    'api650': ('API 650 · 14th edition', 'API650_ONE_FOOT_PRODUCT'),
}
VESSEL_FORMS = {'VIII_UG27_HOOP': 'Cylindrical shell', 'VIII_UG32_ELLIP': '2:1 ellipsoidal head'}


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


def _reference_controls(rule, submitted):
    values = submitted or {}
    data = {'selection': {key: values.get(key, '') for key in (
        'pipe_family', 'nps', 'schedule', 'material', 'temperature', 'product_form', 'basic_class',
    )}}
    controls = []

    def select(name, label):
        controls.append(f'<label>{label}<select name="{name}"><option value="">Manual entry</option></select></label>')

    if rule in PIPE_RULES:
        data['dimensions'] = [
            dict(family=row['family'], nps=row['nps'], schedule=row['schedule'],
                 od=str(convert(row['od_in'], 'in', 'mm')), wall=row['nominal_mm'],
                 reference=f"{row['reference']}, PDF p. {row['pdf_page']}")
            for row in dimensions() if not row['issues']
        ]
        select('pipe_family', 'Pipe dimension table')
        select('nps', 'Nominal pipe size (NPS)')
        select('schedule', 'Pipe schedule')
    if rule in STRESS_CONTEXTS:
        code, edition, product, target = STRESS_CONTEXTS[rule]
        select('material', f'Material · {code} {edition} · {product}')
        select('temperature', 'Exact design temperature from table')
        data['stressTarget'] = target
        data['stresses'] = [
            dict(material=row['material'], temperature=row['temperature_F'],
                 label=f"{row['temperature_C']} °C ({row['temperature_F']} °F)" if row.get('temperature_C')
                 else f"{row['temperature_F']} °F", reference=row['reference'],
                 stress=row.get('S_allow_MPa') or str(convert(row['S_allow_psi'], 'psi', 'MPa')))
            for row in material_stresses()
            if (row['code_family'], row['code_edition'], row['product_form']) == (code, edition, product)
        ]
    if rule == PIPE_RULES[2]:
        select('material', 'API 5L grade · ASME B31.8 2025')
        select('product_form', 'Steel pipe product form')
        select('temperature', 'Design temperature from table')
        select('basic_class', 'Location class · basic design factor')
        data['gas'] = dict(
            grades={f'API 5L {grade}': str(convert(psi, 'psi', 'MPa'))
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
    payload = json.dumps(data).replace('<', '\u003c')
    return ('<fieldset><legend>Reference lookups</legend><div class="fields">'
            + ''.join(controls) + '</div><p class="sample-sources" aria-live="polite"></p></fieldset>'
            f'<script type="application/json" id="sample-reference-data">{payload}</script>')


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
        f'<dt>{title} at entered wall</dt><dd><strong>{E(numeric(pressure))} MPa '
        f'({E(numeric(convert(pressure, "MPa", "psi")))} psi)</strong><br>'
        f'Net wall {E(numeric(net))} mm · {label} check · {E(REFERENCES[key])}</dd>'
    )


def _result(rule, inputs):
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
    controls = []
    for key, label, default in PRESETS[rule][1]:
        value = default if submitted is None else submitted.get(key, '')
        controls.append(field(key, label, value, kind='number'))
    controls.append(field('measured_mm', 'Measured thickness (mm), optional',
                          (submitted or {}).get('measured_mm', '12'), kind='number', required=False))
    if rule in PIPE_RULES:
        controls.append(field('nominal_mm', 'Nominal wall (mm), reference only',
                              (submitted or {}).get('nominal_mm', ''), kind='number', required=False))
    if rule != 'API650_ONE_FOOT_PRODUCT':
        controls.append(field('wall_deduction_mm', 'Wall deduction for pressure check (mm)',
                              (submitted or {}).get('wall_deduction_mm', '0'), kind='number', required=False))
    output = ''
    if submitted is not None:
        try:
            if sample not in PRESETS:
                raise ValueError('Choose a supported calculation preset.')
            output = _result(rule, submitted)
        except DecimalException:
            output = '<p class="warn" role="alert">Enter valid decimal inputs within the supported numeric range.</p>'
        except ValueError as exc:
            output = f'<p class="warn" role="alert">{E(exc)}</p>'
    return (
        '<section id="sample-calculator"><h2>Sample calculator</h2>'
        '<p>Choose a code, then edit the example values or use the reference dropdowns. Samples do not save to your project. '
        'The thickness comparison covers the equations shown. Review other applicable limits separately.</p>'
        + _code_picker(rule)
        + f'<h3>{E(PRESETS[rule][0].split(" · ", 1)[1])}</h3>'
        + f'<form id="sample-inputs" action="/codes#sample-calculator" method="post">{hidden("sample", rule)}'
        f'<p><code>{E(FORMULAS[rule])}</code><br>{E(REFERENCES[rule])}</p>'
        + _reference_controls(rule, submitted)
        + '<div class="fields">' + ''.join(controls) + '</div>'
        '<button class="primary">Calculate sample</button></form>' + output + '</section>'
    )
