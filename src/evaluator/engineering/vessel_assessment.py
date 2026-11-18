"""Compare next-inspection component capacities at a common vessel datum."""

import json
from decimal import Decimal, DecimalException
from uuid import uuid4

from evaluator.storage.database import connection
from .batch_rules import _number


def assess(form):
    from datetime import date

    date.fromisoformat(form['inspection_date'])
    gravity = _number(form['specific_gravity'], 'Specific gravity', nonnegative=True)
    datum = _number(form['datum_ft'], 'Pressure datum elevation')
    components = []
    seen = set()
    for index in range(1, 9):
        values = {field: form.get(f'{field}_{index}', '').strip() for field in
                  ('component', 'pressure_psi', 'elevation_ft', 'reference')}
        if not any(values.values()):
            continue
        if not all(values.values()) or values['component'].casefold() in seen:
            raise ValueError('Each component needs a unique ID, pressure, elevation and dated calculation reference.')
        seen.add(values['component'].casefold())
        pressure = _number(values['pressure_psi'], 'Next-inspection component pressure', positive=True)
        elevation = _number(values['elevation_ft'], 'Component elevation')
        liquid_level = _number(form['liquid_level_ft'], 'Maximum liquid elevation')
        head = Decimal('0.4335275') * gravity * (max(liquid_level - elevation, 0) - max(liquid_level - datum, 0))
        capacity = pressure - head
        if capacity <= 0:
            raise ValueError(f"{values['component']} cannot support positive pressure at the chosen datum.")
        components.append(dict(values, static_head_psi=str(head), datum_pressure_psi=str(capacity)))
    if not components:
        raise ValueError('Enter at least one governing-scope component.')
    governing = min(Decimal(item['datum_pressure_psi']) for item in components)
    return dict(components=components, mawp_psi=str(governing),
                governing_components=[item['component'] for item in components
                                      if Decimal(item['datum_pressure_psi']) == governing],
                inspection_date=form['inspection_date'], datum_ft=str(datum),
                specific_gravity=str(gravity), liquid_level_ft=str(liquid_level),
                head_coefficient_psi_per_ft='0.4335275', status='DRAFT / NOT VALIDATED')


def save(workflow, form):
    metadata = {key: form.get(key, '').strip() for key in ('vessel', 'code_basis', 'head_reference', 'reviewer')}
    if not all(metadata.values()) or form.get('reviewed') != 'yes':
        raise ValueError('Enter the vessel basis, head record and reviewer, then confirm component coverage.')
    try:
        result = assess(form)
    except DecimalException as exc:
        raise ValueError('Vessel inputs exceed the supported numeric range.') from exc
    revision = int(form['revision'])
    record = dict(result, **metadata, id=str(uuid4()), input_revision=revision)
    with workflow.change('Save vessel pressure assessment', inputs=False, expected=revision,
                         actor=metadata['reviewer'], reason=metadata['head_reference']) as db:
        db.execute('INSERT INTO wf_vessel_assessments VALUES (?, ?)', (record['id'], json.dumps(record)))
    return record


def history(workflow):
    with connection(workflow.path) as db:
        return [json.loads(row[0]) for row in db.execute(
            'SELECT payload FROM wf_vessel_assessments ORDER BY rowid DESC')]
