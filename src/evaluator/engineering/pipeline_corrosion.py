"""Draft modified B31G-2023 Level 1 arithmetic for a reviewed metal-loss case."""

from decimal import Decimal

from .batch_rules import _number, convert


def modified_level_one(*, outside_diameter_in, nominal_wall_mm, depth_mm, length_mm,
                       flow_stress_psi, safety_factor, applicability_reference):
    """Calculate defect pressure from explicit inputs and a documented scope decision."""
    if not isinstance(applicability_reference, str) or not applicability_reference.strip():
        raise ValueError('Supply the record confirming B31G applicability and defect interaction review.')
    diameter = convert(outside_diameter_in, 'in', 'mm')
    wall = _number(nominal_wall_mm, 'nominal wall', positive=True)
    depth = _number(depth_mm, 'effective depth', positive=True)
    length = _number(length_mm, 'axial length', positive=True)
    stress = _number(flow_stress_psi, 'flow stress', positive=True)
    factor = _number(safety_factor, 'safety factor', positive=True)
    if diameter <= 2 * wall or depth >= Decimal('.8') * wall or factor <= 1:
        raise ValueError('Require valid pipe geometry, depth below 80% of nominal wall and safety factor above one.')
    z = length ** 2 / (diameter * wall)
    bulging = ((1 + Decimal('.6275') * z - Decimal('.003375') * z ** 2).sqrt()
               if z <= 50 else Decimal('.032') * z + Decimal('3.3'))
    area_ratio = Decimal('.85') * depth / wall
    failure_stress = stress * (1 - area_ratio) / (1 - area_ratio / bulging)
    failure_pressure = 2 * wall * failure_stress / diameter
    return dict(rule='ASME B31G-2023 2.2(b)', status='DRAFT / NOT VALIDATED',
                applicability_reference=applicability_reference, z=str(z), bulging_factor=str(bulging),
                failure_stress_psi=str(failure_stress), estimated_failure_pressure_psi=str(failure_pressure),
                defect_screening_pressure_psi=str(failure_pressure / factor))

INPUT_LABELS = {
    'outside_diameter_in': 'Outside diameter (in)',
    'nominal_wall_mm': 'Nominal wall (mm)',
    'depth_mm': 'Effective defect depth (mm)',
    'length_mm': 'Axial defect length (mm)',
    'flow_stress_psi': 'Reviewed flow stress (psi)',
    'safety_factor': 'Reviewed safety factor',
    'applicability_reference': 'Applicability and interaction evidence',
}


def _linked_depth(workflow, comparison_id, form, inputs):
    observation = form.get('ut_observation_id', '').strip()
    if not observation:
        return None
    if not comparison_id:
        raise ValueError('Select the UT comparison that contains this observation.')
    comparison = workflow.comparison(comparison_id)
    if comparison['stale']:
        raise ValueError('Refresh the comparison before using its UT measurements.')
    reading = next((row for row in workflow._selection(*comparison['current_selection'])
                    if row['observation_id'] == observation), None)
    if (not reading or reading['raw_unit'] != 'mm' or reading.get('review_status') == 'excluded'
            or not reading.get('inspection_date')):
        raise ValueError('Select a dated, included current UT reading in mm from the chosen comparison.')
    if inputs['depth_mm']:
        raise ValueError('Clear manual defect depth when using a linked UT reading.')
    uncertainty = _number(form.get('ut_uncertainty_mm'), 'Depth uncertainty', nonnegative=True)
    wall = _number(reading.get('effective_value', reading['raw_value']), 'Measured UT wall', positive=True)
    nominal = _number(inputs['nominal_wall_mm'], 'Nominal wall', positive=True)
    if wall >= nominal:
        raise ValueError('Linked wall must be below the documented nominal wall.')
    depth = nominal - wall + uncertainty
    inputs['depth_mm'] = str(depth)
    return dict(observation_id=observation, source_id=reading['source_id'],
                sheet=reading['sheet_name'], cell=reading['cell'], date=reading['inspection_date'],
                measured_wall_mm=str(wall), uncertainty_mm=str(uncertainty),
                nominal_wall_mm=str(nominal), effective_depth_mm=str(depth),
                basis='Nominal wall minus measured remaining wall plus entered uncertainty')


def save(workflow, form):
    from decimal import DecimalException
    import json
    from uuid import uuid4

    is_limit = form.get('assessment_type') == 'documented_limits'
    identifier = 'code_basis' if is_limit else 'defect'
    metadata = {key: form.get(key, '').strip() for key in ('segment', identifier, 'reviewer', 'source_reference')}
    if not all(metadata.values()) or form.get('reviewed') != 'yes':
        raise ValueError('Enter the segment, assessment basis, reviewer and source, and confirm the reviewed inputs.')
    comparison_id = form.get('comparison_id') or None
    if comparison_id:
        workflow.comparison(comparison_id)
    inputs = {key: form.get(key, '').strip() for key in INPUT_LABELS}
    try:
        linkage = None if is_limit else _linked_depth(workflow, comparison_id, form, inputs)
        result = documented_limits(form) if is_limit else dict(modified_level_one(**inputs), inputs=inputs)
        if linkage:
            result['ut_trace'] = linkage
    except DecimalException as exc:
        raise ValueError('Inputs exceed the supported numeric range.') from exc
    revision = int(form['revision'])
    record = dict(result, **metadata, id=str(uuid4()),
                  comparison_id=comparison_id, input_revision=revision)
    with workflow.change('Save pipeline assessment', inputs=False, expected=revision,
                         actor=metadata['reviewer'], reason=metadata['source_reference']) as db:
        db.execute('INSERT INTO wf_pipeline_assessments VALUES (?, ?)', (record['id'], json.dumps(record)))
    return record


def history(workflow):
    import json
    from evaluator.storage.database import connection

    with connection(workflow.path) as db:
        return [json.loads(row[0]) for row in db.execute(
            'SELECT payload FROM wf_pipeline_assessments ORDER BY rowid DESC')]

LIMIT_LABELS = {
    'design_limit_psi': 'Design pressure limit',
    'test_limit_psi': 'Pressure-test-derived limit',
    'operating_limit_psi': 'Operating or historical pressure limit',
    'component_limit_psi': 'Component pressure limit',
    'other_limit_psi': 'Other applicable restriction',
}


def documented_limits(form):
    kind = form.get('limit_kind')
    if kind not in {'MAOP', 'MOP'}:
        raise ValueError('Choose the pressure basis, MAOP or MOP.')
    limits = {}
    for key, label in LIMIT_LABELS.items():
        disposition = form.get(key + '_disposition')
        evidence = form.get(key + '_reference', '').strip()
        raw = form.get(key, '').strip()
        if disposition not in {'documented', 'inapplicable'} or not evidence:
            raise ValueError(f'{label} requires a documented pressure or an applicability decision and reference.')
        if disposition == 'inapplicable' and raw:
            raise ValueError(f'Clear the pressure for {label} before marking it inapplicable.')
        limits[key] = dict(disposition=disposition, reference=evidence,
                           psi=str(_number(raw, label, positive=True)) if disposition == 'documented' else None)
    applicable = {key: Decimal(item['psi']) for key, item in limits.items() if item['psi'] is not None}
    if not applicable:
        raise ValueError('Enter at least one documented pressure limit.')
    governing = min(applicable.values())
    return dict(assessment_type='documented_limits', limit_kind=kind,
                governing_pressure_psi=str(governing),
                governing_limits=[key for key, value in applicable.items() if value == governing],
                status='DOCUMENTED LIMIT COMPARISON', inputs=limits)
