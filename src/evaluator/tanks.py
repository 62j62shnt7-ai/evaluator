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
        'CA_mm': 'Corrosion allowance (mm)', 'nominal_min_mm': 'Higher nominal plate minimum from project records (mm, optional)',
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

BOTTOM_FIELDS = {k: v for k, v in METHODS['api653_bottom'][1].items() if k != 'governing_min_mm'}
TOE_FIELDS = {'toe_mm': 'Thickness at outer weld toe (mm)', 'projection_mm': 'Projection beyond outer weld toe (mm)'}
METHODS.update({
    'api653_pits': ('API 653 · Scattered shell pit screening', {
        'shell_min_mm': 'Reviewed shell minimum excluding corrosion allowance (mm)',
    }),
    'api653_critical': ('API 653 · Bottom critical zone', {
        **BOTTOM_FIELDS, **TOE_FIELDS, 'lower_shell_min_mm': 'Lower shell course minimum (mm)',
    }),
    'api653_annular': ('API 653 · Annular ring', {
        **BOTTOM_FIELDS, **TOE_FIELDS, 'G': 'Highest product specific gravity',
        'table_min_mm': 'Reviewed minimum from the applicable annular table (mm)',
        'CA_mm': 'Specified annular corrosion allowance (mm)',
    }),
})


def screen_pits(raw, minimum):
    """Find maximum total pit extent in a sliding 200 mm vertical window."""
    lines = {}
    evidence = []
    rows = raw.strip().splitlines()
    if not rows or len(rows) > 200 or minimum < Decimal('2.5'):
        raise ValueError('Supply 1–200 pit observations and a reviewed shell minimum of at least 2.5 mm')
    for row in rows:
        parts = [part.strip() for part in row.split(',')]
        if len(parts) != 4 or not parts[0]:
            raise ValueError('Each pit row needs vertical line ID, start, end and remaining thickness')
        line, *numbers = parts
        try:
            start, end, remaining = map(Decimal, numbers)
        except DecimalException:
            raise ValueError('Pit dimensions and remaining thickness must be numeric') from None
        if not all(n.is_finite() for n in (start, end, remaining)) or not 0 <= start < end or remaining < 0:
            raise ValueError('Pit extents must be ordered and thickness nonnegative')
        lines.setdefault(line, []).append((start, end))
        evidence.append(dict(line=line, start_mm=str(start), end_mm=str(end), remaining_mm=str(remaining)))
    maximum = Decimal(0)
    width = Decimal(200)
    for intervals in lines.values():
        intervals.sort()
        if any(end > next_start for (_, end), (next_start, _) in zip(intervals, intervals[1:])):
            raise ValueError('Pit extents must be distinct on each vertical line; overlapping pits require separate review')
        boundaries = {edge + offset for span in intervals for edge in span for offset in (Decimal(0), -width)}
        maximum = max(maximum, *(sum(max(0, min(end, x + width) - max(start, x)) for start, end in intervals)
                                 for x in boundaries))
    limit = minimum / 2
    least = min(Decimal(pit['remaining_mm']) for pit in evidence)
    result = dict(pit_min_remaining_mm=least, pit_required_remaining_mm=limit, max_pit_extent_mm=maximum,
                  pit_screen='Meets both screening limits' if least >= limit and maximum <= 50 else 'Pit exclusion criteria not met')
    return result, evidence


def calculate(method, inputs, scope=''):
    if method not in METHODS:
        raise ValueError('Select a tank calculation method')
    fields = METHODS[method][1]
    values = {}
    for key, label in fields.items():
        if key in {'nominal_min_mm', 'governing_min_mm', 'table_min_mm'} and inputs.get(key) in (None, ''):
            continue
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
        from evaluator.engineering.reference_rules import tank_nominal_minimum
        position = inputs.get('course_position', '')
        nominal = tank_nominal_minimum(v['D_m'], position)
        result = dict(product_mm=product['value'], hydrotest_mm=hydro['value'],
                      code_nominal_min_mm=nominal,
                      governing_candidate_mm=max(Decimal(product['value']), Decimal(hydro['value']),
                                                 nominal, v.get('nominal_min_mm', Decimal(0))))
        reference = 'API 650 14th edition (2025), 5.6.1 and 5.6.3'
        note = 'Shell-course thickness for the stated load cases. Other design loads and details require their own checks.'
    elif method == 'api653_shell':
        if scope not in {'whole', 'local'}:
            raise ValueError('Select whole course or local area')
        if not 0 < v['D_m'] <= 61 or not v['G'] or not v['Y_MPa'] or not v['T_MPa'] or not 0 < v['E'] <= 1:
            raise ValueError('Diameter must be above zero and at most 61 m. Supply positive gravity, strengths and joint efficiency up to 1.')
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
    elif method == 'api653_pits':
        if inputs.get('scattered') != 'yes':
            raise ValueError('Confirm these are widely scattered shell pits and all relevant vertical lines were surveyed')
        result, pits = screen_pits(inputs.get('pit_rows', ''), v['shell_min_mm'])
        reference = 'API 653 5th edition through July 2025, 4.3.2.2'
        note = 'Screening applies to the surveyed shell pits and the entered thickness basis.'
    else:
        if v['interval_years'] <= 0:
            raise ValueError('Supply a positive reviewed operating interval')
        mrt = min(v['RTbc_mm'], v['RTip_mm']) - v['interval_years'] * (v['StPr'] + v['UPr'])
        result = dict(projected_remaining_mm=mrt)
        if method == 'api653_critical':
            if v['lower_shell_min_mm'] < Decimal('2.5'):
                raise ValueError('Enter the lower shell course minimum from 4.3.3.1')
            minimum = max(Decimal('2.5'), min(Decimal(3), v['lower_shell_min_mm'] / 2))
            reference = 'API 653 5th edition through July 2025, 4.4.5.1, 4.4.5.4 and 4.4.5.7'
            note = 'Uses minimum readings for general critical-zone assessment without stress analysis. Isolated corrosion exceptions require a tank engineer.'
        elif method == 'api653_annular':
            if inputs.get('nonseismic') != 'yes':
                raise ValueError('Seismic annular rings require evaluation to the as-built standard')
            if v['G'] <= 0 or not inputs.get('table_evidence', '').strip():
                raise ValueError('Supply positive gravity and evidence for the shell stress and plate basis')
            table = 'API 653 Table 4.5a' if v['G'] < 1 else 'API 650 Table 5.1a'
            lookup = None
            if inputs.get('annular_mode') == 'local_pdf':
                from evaluator.engineering.annular_reference import annular_minimum
                try:
                    shell_mm = Decimal(str(inputs.get('shell_course_mm', '')))
                    stress_mpa = Decimal(str(inputs.get('shell_stress_MPa', '')))
                except DecimalException:
                    raise ValueError('Enter the reviewed first-course thickness and stress') from None
                minimum, lookup = annular_minimum(v['G'], shell_mm, stress_mpa)
            else:
                if inputs.get('annular_table') != table:
                    raise ValueError(f'Use {table} for the entered product specific gravity')
                minimum = v.get('table_min_mm', Decimal(0))
                if minimum <= 0:
                    raise ValueError('Supply the reviewed table minimum')
            current_required = minimum + v['CA_mm']
            result.update(annular_current_required_mm=current_required,
                          annular_current_margin_mm=min(v['RTbc_mm'], v['RTip_mm']) - current_required)
            reference = 'API 653 5th edition through July 2025, 4.4.6 and 4.4.5.7; ' + table
            note = 'Uses the reviewed table lookup and allowance. Confirm uniform foundation support and applicable shell stress.'
        else:
            from evaluator.engineering.reference_rules import BOTTOM_DESIGN_MIN_MM, BOTTOM_DESIGN_REFERENCE
            bottom_design = inputs.get('bottom_design', '')
            tabulated = BOTTOM_DESIGN_MIN_MM.get(bottom_design)
            minimum = max(v.get('governing_min_mm', Decimal(0)), Decimal(tabulated or 0))
            if minimum <= 0:
                raise ValueError('Select the verified bottom design or supply a reviewed governing minimum')
            reference = 'API 653 5th edition through July 2025, 4.4.5.1'
            if tabulated:
                reference += '; ' + BOTTOM_DESIGN_REFERENCE
            note = 'Projection for the selected general bottom zone.'
        result.update(governing_bottom_min_mm=minimum, margin_to_reviewed_minimum_mm=mrt - minimum)
        if method in {'api653_critical', 'api653_annular'}:
            result.update(toe_thickness_margin_mm=v['toe_mm'] - Decimal('2.5'),
                          toe_projection_margin_mm=v['projection_mm'] - Decimal(10))
    record = dict(status=STATUS, reference=reference, note=note, method=method, scope=scope,
                  inputs={k: str(x) for k, x in v.items()},
                  outputs={k: str(x) if x is not None else None for k, x in result.items()})
    if method == 'api650':
        from evaluator.engineering.reference_rules import TANK_NOMINAL_REFERENCE
        record['inputs']['course_position'] = position
        record['reference_values'] = {'code_nominal_min_mm': dict(TANK_NOMINAL_REFERENCE, value=str(nominal))}
    if method == 'api653_bottom' and tabulated:
        record['inputs']['bottom_design'] = bottom_design
        record['reference_values'] = {'bottom_design_min_mm': dict(reference=BOTTOM_DESIGN_REFERENCE, value=tabulated)}
    if method == 'api653_pits':
        record['pit_observations'] = pits
        record['inputs']['scattered'] = True
    if method == 'api653_annular':
        record['inputs'].update(table=table, table_evidence=inputs['table_evidence'].strip(), nonseismic=True)
        if lookup:
            record['reference_values'] = {'annular_table_min_mm': lookup}
    return record


def save(workflow, form):
    metadata = {key: form.get(key, '').strip() for key in ('tank', 'component', 'reviewer', 'reason', 'revision')}
    if not all(metadata.values()) or form.get('applicability') != 'yes':
        raise ValueError('Tank, component, reviewer, source evidence and applicability confirmation are required')
    revision = int(metadata.pop('revision'))
    try:
        from evaluator.tank_ut import import_values
        mapped, provenance = import_values(workflow.service, form)
        record = calculate(mapped.get('method'), mapped, mapped.get('scope', ''))
        if provenance is not None:
            record['ut_provenance'] = provenance
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
