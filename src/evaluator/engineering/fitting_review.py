"""Continued-use check at a documented pressure for an identified B31.3 fitting."""
from decimal import Decimal

from evaluator.inspection_time import elapsed_days


CLAUSES = {
    'elbow': 'B31.3-2024 paras. 303, 302.2 and 304.2.2',
    'tee': 'B31.3-2024 paras. 303, 302.2 and 304.3',
    'reducer': 'B31.3-2024 paras. 303, 302.2 and 304.6',
}


def fitting_wall_progress(previous, current, previous_date, current_date, *, interval=None, adopted=None):
    """Calculate physical wall loss and projection independently of pressure capacity."""
    from .batch_rules import _number

    result = {'missing': []}
    if previous is None:
        result['missing'].append('Match an earlier UT reading at this fitting location.')
    else:
        try:
            loss = _number(previous, 'Previous wall', positive=True) - _number(current, 'Current wall', positive=True)
            result['wall_loss_mm'] = str(loss)
            years = Decimal(elapsed_days(previous_date, current_date, 365)) / 365
            if years <= 0:
                raise ValueError('Current date must follow previous date.')
            result['observed_rate_mm_year'] = str(loss / years)
            if loss < 0:
                result['missing'].append('Verify the UT match and readings because the measured wall increased.')
        except (ValueError, TypeError):
            result['missing'].append('Verify the UT readings and use comparable inspection dates in chronological order.')
    observed = Decimal(result.get('observed_rate_mm_year', '0'))
    rate = max(observed, _number(adopted, 'Adopted rate', nonnegative=True) if adopted not in (None, '') else Decimal(0))
    if rate <= 0:
        result['missing'].append('Enter a reviewed positive corrosion rate to project wall thickness.')
    if interval in (None, ''):
        result['missing'].append('Enter the next inspection interval to project wall thickness.')
    elif rate > 0 and current is not None:
        try:
            years = _number(interval, 'Inspection interval', positive=True)
            projected = _number(current, 'Current wall', positive=True) - rate * years
            result.update(projection_years=str(years), used_rate_mm_year=str(rate),
                          projected_wall_mm=str(max(Decimal(0), projected)))
            if projected <= 0:
                result['missing'].append('Projected metal loss reaches the measured wall within this interval.')
        except ValueError as exc:
            result['missing'].append(str(exc))
    return result


def assess_fitting(previous, current, previous_date, current_date, minimum, pressure, interval, adopted_rate):
    """Apply API 570 §7.5's wall deduction against a supplied engineering minimum."""
    previous, current, minimum, pressure, interval, adopted_rate = map(
        lambda value: Decimal(str(value)), (previous, current, minimum, pressure, interval, adopted_rate)
    )
    if any(not value.is_finite() or value <= 0 for value in (previous,current,minimum,pressure,interval)):
        raise ValueError('Positive UT, reviewed minimum wall, pressure and interval are required.')
    if not adopted_rate.is_finite() or adopted_rate < 0:
        raise ValueError('The adopted corrosion rate must be nonnegative.')
    years = Decimal(str(elapsed_days(previous_date, current_date, 365))) / Decimal(365)
    if years <= 0:
        raise ValueError('Current UT date must follow the previous UT date.')
    observed = (previous - current) / years
    rate = max(observed, adopted_rate)
    if rate <= 0:
        raise ValueError('Enter a positive reviewed rate when observed wall loss is zero or negative.')
    credited = current - 2 * rate * interval
    life = max(Decimal(0), (current - minimum) / rate)
    return dict(
        pressure_psi=str(pressure), minimum_mm=str(minimum), observed_rate=str(observed),
        used_rate=str(rate), credited_wall_mm=str(credited), remaining_life_years=str(life),
        projection_years=str(interval), current_meets_minimum=current > minimum,
        projected_meets_minimum=credited > minimum,
    )


def bend_minimum_from_inputs(profile, values):
    def field(key):
        return profile['fields'].get(key, {}).get('value')

    if not values.get('bend_design_reference', '').strip():
        raise ValueError('Enter the bend design basis reference to calculate the minimum wall.')
    return bend_minimum_mm(
        pressure_psi=values.get('fitting_pressure_psi'), position=values.get('bend_position'),
        radius_in=values.get('bend_radius_in'), allowance_mm=values.get('allowance_mm'),
        outside_diameter_in=field('D_outside_in'), stress_psi=field('S_allow_psi'),
        structural_minimum_mm=values.get('structural_minimum_mm', field('structural_minimum_mm')), quality=values.get('E_quality'),
        weld=values.get('W_reduction'), coefficient=values.get('Y_coefficient'),
    )


def bend_minimum_mm(*, pressure_psi, structural_minimum_mm, allowance_mm, outside_diameter_in,
                    radius_in, stress_psi, quality, weld, coefficient, position):
    """Calculate the local bend minimum at design pressure under eq. (3c)."""
    from .batch_rules import _number, convert

    diameter = convert(outside_diameter_in, 'in', 'mm')
    radius = convert(radius_in, 'in', 'mm')
    shape = _bend_shape(diameter, radius, position)
    p = _number(pressure_psi, 'design pressure', positive=True)
    s = _number(stress_psi, 'allowable stress', positive=True)
    e = _number(quality, 'E', positive=True)
    w = _number(weld, 'W', positive=True)
    y = _number(coefficient, 'Y', nonnegative=True)
    allowance = _number(allowance_mm, 'allowance', nonnegative=True)
    structural = _number(structural_minimum_mm, 'structural minimum', nonnegative=True)
    if e > 1 or w > 1 or p / (s * e) > Decimal('.385'):
        raise ValueError('Design pressure or joint factors exceed the supported bend formula range.')
    net = p * diameter / (2 * (s * e * w / shape + p * y))
    if not 0 < net < diameter / 6:
        raise ValueError('Calculated net wall must be positive and below D/6.')
    return max(structural, net + allowance)


def _bend_shape(diameter, radius, position):
    if diameter <= 0 or radius <= diameter / 2:
        raise ValueError('Bend centerline radius must exceed half the outside diameter.')
    ratio = 4 * radius / diameter
    if position == 'intrados':
        return (ratio - 1) / (ratio - 2)
    if position == 'extrados':
        return (ratio + 1) / (ratio + 2)
    if position not in BEND_COVERAGE | {'sidewall', 'tangent'}:
        raise ValueError('Identify the UT position as intrados, extrados, sidewall or tangent.')
    return Decimal(1)


def bend_pressure_psi(*, wall_mm, allowance_mm, outside_diameter_in, radius_in,
                      stress_psi, quality, weld, coefficient, position):
    """Invert B31.3-2024 eq. (3c) at one reviewed bend measurement position."""
    from .batch_rules import _number, convert

    diameter = convert(outside_diameter_in, 'in', 'mm')
    radius = convert(radius_in, 'in', 'mm')
    shape = _bend_shape(diameter, radius, position)
    wall = _number(wall_mm, 'credited_wall_mm', positive=True)
    net = wall - _number(allowance_mm, 'allowance_mm', nonnegative=True)
    if not 0 < net < diameter / 6:
        raise ValueError('Net wall must be positive and below D/6 for this pressure method.')
    stress = _number(stress_psi, 'stress_psi', positive=True)
    e = _number(quality, 'E', positive=True)
    w = _number(weld, 'W', positive=True)
    y = _number(coefficient, 'Y', nonnegative=True)
    if e > 1 or w > 1:
        raise ValueError('E and W must be at most 1.')
    denominator = diameter - 2 * net * y
    if denominator <= 0:
        raise ValueError('Pressure equation denominator must be positive.')
    pressure = 2 * stress * e * w * net / (shape * denominator)
    if pressure / (stress * e) > Decimal('.385'):
        raise ValueError('P/SE exceeds the supported formula range.')
    return pressure

BEND_COVERAGE = frozenset({'intrados', 'extrados', 'sidewall_left', 'sidewall_right',
                           'tangent_start', 'tangent_end'})


def summarize_bends(rows):
    """Attach the same reviewed bend summary to each member of the saved batch."""
    groups = {}
    for row in rows:
        tag = row.get('input_trace', {}).get('overrides', {}).get('bend_tag', '').strip()
        if row.get('current_id') and tag:
            groups.setdefault(tag, []).append(row)
    for tag, members in groups.items():
        positions = set()
        inputs = []
        issues = []
        for row in members:
            check = row.get('fitting_check') or {}
            if not check.get('bend_pressure_psi'):
                issues.append(f"{row['location']}: local bend pressure unavailable.")
                continue
            positions.add(check['bend_position'])
            inputs.append(dict(location=row['location'], observation_id=row['current_id'],
                               position=check['bend_position'], pressure_psi=check['bend_pressure_psi'],
                               inspection_date=row['inspection_date'], interval_years=check['projection_years'],
                               design_reference=check['bend_design_reference']))
        missing = sorted(BEND_COVERAGE - positions)
        if missing:
            issues.append('Missing bend coverage: ' + ', '.join(missing))
        if len({(item['inspection_date'], Decimal(item['interval_years']), item['design_reference'])
                for item in inputs}) > 1:
            issues.append('Use the same assessment date, projection interval and design basis for the bend.')
        pressure = min((Decimal(item['pressure_psi']) for item in inputs), default=None) if not issues else None
        summary = dict(tag=tag, pressure_psi=None if pressure is None else str(pressure),
                       governing=[item for item in inputs if pressure is not None and Decimal(item['pressure_psi']) == pressure],
                       inputs=inputs, issues=issues)
        for row in members:
            row['bend_summary'] = summary


def qualified_pressure_psi(wall_mm, points):
    """Apply the conservative step limit from an approved pressure/wall schedule."""
    candidates = []
    previous_wall = previous_pressure = Decimal(0)
    wall = Decimal(wall_mm)
    for line in points.splitlines():
        if not line.strip():
            continue
        try:
            required, pressure = (Decimal(item.strip()) for item in line.split(','))
        except (ValueError, ArithmeticError) as exc:
            raise ValueError('Enter one minimum wall (mm), pressure (psi) pair per line.') from exc
        if (not required.is_finite() or not pressure.is_finite() or
                required <= previous_wall or pressure <= previous_pressure):
            raise ValueError('Qualification wall and pressure limits must be positive and strictly ascending.')
        if wall >= required:
            candidates.append((required, pressure))
        previous_wall, previous_pressure = required, pressure
    if not candidates:
        raise ValueError('Projected wall does not support any documented pressure in the qualification.')
    required, pressure = candidates[-1]
    return dict(pressure_psi=str(pressure), qualification_required_wall_mm=str(required))
