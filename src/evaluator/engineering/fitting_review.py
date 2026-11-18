"""Continued-use check at a documented pressure for an identified B31.3 fitting."""
from decimal import Decimal

from evaluator.inspection_time import elapsed_days


CLAUSES = {
    'elbow': 'B31.3-2024 paras. 303, 302.2 and 304.2.2',
    'tee': 'B31.3-2024 paras. 303, 302.2 and 304.3',
    'reducer': 'B31.3-2024 paras. 303, 302.2 and 304.6',
}


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
