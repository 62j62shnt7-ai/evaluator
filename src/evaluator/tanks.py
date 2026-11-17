"""Revisioned SI tank calculations using user-sourced component inputs."""
from decimal import Decimal, DecimalException
import json
from uuid import uuid4

from evaluator.engineering.draft import evaluate
from evaluator.storage.database import connection

STATUS = 'DRAFT / NOT VALIDATED'
METHODS = {
    'api650': ('API 650 (2025) · One-foot shell design', {
        'D_m': 'Tank diameter (m)', 'H_m': 'Product height above course bottom (m)',
        'hydro_H_m': 'Hydrotest height above course bottom (m)', 'G': 'Product specific gravity',
        'Sd_MPa': 'Product allowable stress (MPa)', 'St_MPa': 'Hydrotest allowable stress (MPa)',
        'CA_mm': 'Corrosion allowance (mm)', 'nominal_min_mm': 'Applicable nominal plate minimum (mm)',
    }),
    'api653_shell': ('API 653 (through July 2025) · Shell thickness and liquid height', {
        'D_m': 'Tank diameter (m)', 'H_m': 'Liquid height above evaluation datum (m)',
        'G': 'Highest product specific gravity', 'course': 'Shell course number (bottom = 1)',
        'Y_MPa': 'Specified minimum yield strength (MPa)', 'T_MPa': 'Specified minimum tensile strength (MPa)',
        'E': 'Applicable joint efficiency', 'measured_mm': 'Reviewed controlling thickness / local average t1 (mm)',
        't2_mm': 'Local area only: least thickness excluding pits, t2 (mm)',
        'CA_mm': 'Future corrosion allowance (mm)', 'design_H_m': 'Original maximum design height above same datum (m)',
    }),
    'api653_bottom': ('API 653 (through July 2025) · Bottom thickness projection', {
        'RTbc_mm': 'Minimum remaining thickness from bottom-side corrosion (mm)',
        'RTip_mm': 'Minimum remaining thickness from product-side corrosion (mm)',
        'interval_years': 'Proposed interval (years)', 'StPr': 'Product-side corrosion rate (mm/year)',
        'UPr': 'Underside corrosion rate (mm/year)',
        'governing_min_mm': 'Reviewed governing zone minimum (mm)',
    }),
}


def calculate(method, inputs, scope=''):
    if method not in METHODS:
        raise ValueError('Select a tank calculation method')
    fields = METHODS[method][1]
    values = {}
    for key, label in fields.items():
        if key == 't2_mm' and scope != 'local':
            continue
        try:
            value = Decimal(str(inputs.get(key, '')))
        except DecimalException:
            raise ValueError(f'{label} requires a number') from None
        if not value.is_finite() or value < 0:
            raise ValueError(f'{label} must be finite and nonnegative')
        values[key] = value
    v = values
    if method == 'api650':
        product = evaluate('API650_ONE_FOOT_PRODUCT', v)
        hydro = evaluate('API650_ONE_FOOT_HYDRO', dict(v, H_m=v['hydro_H_m']))
        if v['nominal_min_mm'] <= 0:
            raise ValueError('Supply the applicable nominal plate minimum')
        result = dict(product_mm=product['value'], hydrotest_mm=hydro['value'],
                      governing_candidate_mm=max(Decimal(product['value']), Decimal(hydro['value']), v['nominal_min_mm']))
        reference = 'API 650 14th edition (2025), 5.6.1 and 5.6.3'
        note = 'Shell-course thickness for the stated load cases. Other design loads and details require their own checks.'
    elif method == 'api653_shell':
        if scope not in {'whole', 'local'}:
            raise ValueError('Select whole course or local area')
        if not v['D_m'] or not v['G'] or not v['Y_MPa'] or not v['T_MPa'] or not 0 < v['E'] <= 1:
            raise ValueError('Positive diameter, specific gravity, strengths and joint efficiency are required; E cannot exceed 1')
        if v['course'] < 1 or v['course'] != v['course'].to_integral_value():
            raise ValueError('Shell course must be a positive whole number')
        offset = Decimal('0.3') if scope == 'whole' else Decimal(0)
        if not offset < v['H_m'] <= v['design_H_m']:
            raise ValueError('Evaluation height must exceed the method offset and stay within the original design height')
        y_factor, t_factor = ('0.80', '0.429') if v['course'] <= 2 else ('0.88', '0.472')
        stress = min(Decimal(y_factor) * v['Y_MPa'], Decimal(t_factor) * min(v['T_MPa'], Decimal(550)))
        coefficient = Decimal('4.9') * v['D_m'] * v['G'] / (stress * v['E'])
        floor = Decimal('2.5')
        minimum = max(floor, coefficient * (v['H_m'] - offset))
        net = v['measured_mm'] - v['CA_mm']
        available = net
        result = dict(allowable_stress_MPa=stress, minimum_mm=minimum, net_mm=net)
        if scope == 'local':
            if not 0 < v['t2_mm'] <= v['measured_mm']:
                raise ValueError('Local least thickness must be positive and cannot exceed the reviewed average')
            fraction = Decimal('0.60')
            net_t2 = v['t2_mm'] - v['CA_mm']
            available = min(net, net_t2 / fraction)
            result.update(profile_length_mm=min(Decimal(1000), Decimal(34) * (v['D_m'] * v['t2_mm']).sqrt()),
                          local_average_margin_mm=net - minimum,
                          local_least_margin_mm=net_t2 - fraction * minimum)
        result['liquid_height_candidate_m'] = (
            min(v['design_H_m'], available / coefficient + offset) if available >= floor else None
        )
        reference = 'API 653 5th edition through July 2025, 4.3.1.5, 4.3.2.1 and 4.3.3.1'
        note = 'Height uses the stated evaluation datum. Local profiles, pit acceptance, reconstructed tanks and additional loads require separate checks.'
    else:
        if v['governing_min_mm'] <= 0 or v['interval_years'] <= 0:
            raise ValueError('Supply a positive interval and reviewed governing zone minimum')
        mrt = min(v['RTbc_mm'], v['RTip_mm']) - v['interval_years'] * (v['StPr'] + v['UPr'])
        result = dict(projected_remaining_mm=mrt, margin_to_reviewed_minimum_mm=mrt - v['governing_min_mm'])
        reference = 'API 653 5th edition through July 2025, 4.4.5.1'
        note = 'Projection for the selected bottom zone. Confirm the applicable bottom, critical zone and annular requirements separately.'
    return dict(status=STATUS, reference=reference, note=note, method=method, scope=scope,
                inputs={k: str(x) for k, x in v.items()},
                outputs={k: str(x) if x is not None else None for k, x in result.items()})


def save(workflow, form):
    metadata = {key: form.get(key, '').strip() for key in ('tank', 'component', 'reviewer', 'reason', 'revision')}
    if not all(metadata.values()) or form.get('applicability') != 'yes':
        raise ValueError('Tank, component, reviewer, source evidence and applicability confirmation are required')
    revision = int(metadata.pop('revision'))
    try:
        record = calculate(form.get('method'), form, form.get('scope', ''))
    except DecimalException:
        raise ValueError('Tank inputs exceed the supported numeric range') from None
    record.update(metadata, id=str(uuid4()), input_revision=revision)
    with workflow.change('Calculate tank assessment', inputs=False, expected=revision,
                         actor=metadata['reviewer'], reason=metadata['reason']) as db:
        db.execute('INSERT INTO wf_tank_assessments VALUES(?,?)', (record['id'], json.dumps(record)))
    return record


def history(workflow):
    with connection(workflow.path) as db:
        return [json.loads(row[0]) for row in db.execute('SELECT payload FROM wf_tank_assessments ORDER BY rowid DESC')]
