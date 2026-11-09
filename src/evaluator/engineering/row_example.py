"""User-specified evaluation sequence, seeded from Evaluation 11-2026 row 7."""
from datetime import date, timedelta
import math
import re
from evaluator.inspection_time import elapsed_days

FIXED_STRESS_PSI = {'A106 B': 20000, 'A234 WPB': 20000, 'API 5L X52': 22000}
EXAMPLE = dict(material='A106 B', pd_psi='800', od_in='8.625', nominal_mm='12.7',
               structural_mm='2.8', previous_mm='11.6', current_mm='11.3',
               previous_date='2023-08-25', current_date='2026-11-06', selected_cr='0.2')


def calculate(inputs):
    def number(key, positive=True):
        value = float(inputs[key])
        if not math.isfinite(value) or value < 0 or (positive and value == 0):
            raise ValueError(f'{key} must be finite and ' + ('positive' if positive else 'nonnegative'))
        return value
    token = re.sub('[^A-Z0-9]', '', str(inputs['material']).upper()).removeprefix('ASTM').replace('GRADE', '').replace('GR', '')
    stress = float(inputs.get('s_allow_psi') or {'A106B': 20000, 'A234WPB': 20000, 'API5LX52': 22000}.get(token, 0))
    if not math.isfinite(stress) or stress <= 0:
        raise ValueError('Allowable S must be a positive finite value')
    if stress is None:
        raise ValueError('Choose a material with a configured fixed S value')
    pd, od = number('pd_psi'), number('od_in')
    number('nominal_mm')
    structural = number('structural_mm', False)
    previous, current = number('previous_mm'), number('current_mm')
    days = float(elapsed_days(inputs['previous_date'], inputs['current_date'], 365))
    # Month precision is retained for due dates instead of inventing a day.
    month_only = len(inputs['current_date']) == 7
    current_date = date.fromisoformat(inputs['current_date'] + '-01' if month_only else inputs['current_date'])
    if days <= 0:
        raise ValueError('Current UT date must be after previous UT date')
    cr = (previous - current) / (days / 365)
    rate = cr if cr > 0 else number('selected_cr')
    pressure = pd * od * 25.4 / (2 * stress + .8 * pd)
    required = max(structural, pressure)
    life = max(0, (current - required) / rate)
    interval = min(10, life / 2)
    thickness = current - 2 * rate * interval
    denominator = od * 25.4 - .8 * thickness
    if denominator <= 0:
        raise ValueError('MAWP denominator must be positive')
    mawp = 2 * stress * thickness / denominator
    return dict(s_psi=stress, pressure_mm=pressure, required_mm=required,
                elapsed_days=days, elapsed_years=days / 365, calculated_cr=cr,
                cr_used=rate, cr_basis='Calculated CR' if cr > 0 else 'Selected manual CR',
                remaining_life=life, interval=interval, mawp_thickness_mm=thickness,
                mawp_psi=mawp, result='Safe' if current > required and mawp > pd and not math.isclose(mawp, pd, rel_tol=1e-12, abs_tol=1e-9) else 'Not safe',
                next_inspection=(current_date + timedelta(days=math.floor(interval * 365))).isoformat() if not month_only else
                f'{(current_date.year * 12 + current_date.month - 1 + math.floor(interval * 12)) // 12:04d}-{(current_date.year * 12 + current_date.month - 1 + math.floor(interval * 12)) % 12 + 1:02d}')
