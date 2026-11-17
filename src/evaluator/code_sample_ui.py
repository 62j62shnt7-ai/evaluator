"""Editable examples for the code library's draft arithmetic."""
from decimal import Decimal, DecimalException

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
    return markup + '</dl></div>'


def panel(sample='', submitted=None):
    rule = sample if sample in PRESETS else next(iter(PRESETS))
    options = ''.join(f'<option value="{key}"{" selected" if key == rule else ""}>{E(label)}</option>'
                      for key, (label, _) in PRESETS.items())
    controls = []
    for key, label, default in PRESETS[rule][1]:
        value = default if submitted is None else submitted.get(key, '')
        controls.append(field(key, label, value, kind='number'))
    controls.append(field('measured_mm', 'Measured thickness (mm), optional',
                          (submitted or {}).get('measured_mm', '12'), kind='number', required=False))
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
        '<p>Load an example and edit any value. These draft calculations do not save to your project. '
        'The thickness comparison covers the equations shown. Review other applicable limits separately.</p>'
        '<form class="sample-picker" action="/codes#sample-calculator" method="get">'
        f'<label>Example preset<select name="sample">{options}</select></label>'
        '<button>Load preset</button></form>'
        f'<form action="/codes#sample-calculator" method="post">{hidden("sample", rule)}'
        f'<p><code>{E(FORMULAS[rule])}</code><br>{E(REFERENCES[rule])}</p>'
        '<div class="fields">' + ''.join(controls) + '</div>'
        '<button class="primary">Calculate sample</button></form>' + output + '</section>'
    )
