"""Independent draft outputs from explicit inputs; no inference of fitness or policy.

Interval is the exact Decimal year bound before date conversion. Due dates add
floor(interval * year_days) whole days to the supplied inspection date. MAWP is
inverse algebra for one explicitly selected candidate rule, not a complete
component pressure rating. Caller must establish geometry and applicability.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, DecimalException, ROUND_FLOOR, localcontext
from collections.abc import Mapping

from .draft import REQUIRED, REFERENCES, evaluate

STATUS = 'DRAFT / NOT VALIDATED'
VERSION = 'batch-draft-0.3.1'
OUTPUTS = ('thickness_margin_mm', 'remaining_life_years', 'inspection_interval_years',
           'maximum_inspection_interval_years', 'due_date', 'mawp_MPa', 'forecast_mawp_MPa')
PRESSURE_RULES = frozenset(k for k in REQUIRED if k.startswith(('VIII_', 'B31_')))


def _number(value, name, *, positive=False, nonnegative=False):
    try:
        if value is None or isinstance(value, bool):
            raise ValueError(name + ' is required as a finite number')
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError(name + ' must be finite')
        if positive and result <= 0:
            raise ValueError(name + ' must be positive')
        if nonnegative and result < 0:
            raise ValueError(name + ' must be nonnegative')
        return result
    except DecimalException as exc:
        raise ValueError(name + ' must be a finite number') from exc


def convert(value, from_unit, to_unit):
    """Convert explicit compatible units with Decimal; reject invalid inputs."""
    amount = _number(value, 'value')
    families = {'psi':'pressure', 'MPa':'pressure', 'in':'length', 'mm':'length', 'F':'temperature', 'C':'temperature'}
    if from_unit not in families or to_unit not in families or families[from_unit] != families[to_unit]:
        raise ValueError('Unsupported unit conversion')
    if from_unit == to_unit:
        return amount
    if from_unit == 'psi': return amount * Decimal('0.006894757293')
    if from_unit == 'MPa': return amount / Decimal('0.006894757293')
    if from_unit == 'in': return amount * Decimal('25.4')
    if from_unit == 'mm': return amount / Decimal('25.4')
    if from_unit == 'F': return (amount - 32) * 5 / 9
    return amount * 9 / 5 + 32


def _pressure(net, rule, inputs):
    if rule not in PRESSURE_RULES:
        raise ValueError('Explicit supported pressure rule is required; unsupported geometry needs separate analysis')
    if not isinstance(inputs, Mapping):
        raise ValueError('design_inputs must supply geometry, strength and factors')
    v = {k: _number(inputs.get(k), k, nonnegative=True)
         for k in REQUIRED[rule] if k != 'P_MPa'}
    d = Decimal
    if rule == 'VIII_UG27_HOOP':
        numerator, denominator = net*v['S_allow_MPa']*v['E_joint'], v['R_inside_mm']+d('.6')*net
    elif rule == 'VIII_UG27_LONG':
        numerator, denominator = 2*net*v['S_allow_MPa']*v['E_joint'], v['R_inside_mm']-d('.4')*net
    elif rule == 'VIII_UG32_ELLIP':
        numerator, denominator = 2*net*v['S_allow_MPa']*v['E_joint'], v['D_inside_mm']+d('.2')*net
    elif rule == 'VIII_UG32_TORI':
        numerator, denominator = net*v['S_allow_MPa']*v['E_joint'], d('.885')*v['L_inside_crown_mm']+d('.1')*net
    elif rule == 'B31_3_304_1_2':
        numerator, denominator = 2*net*v['S_B313_MPa']*v['E_quality']*v['W_reduction'], v['D_outside_mm']-2*net*v['Y_coefficient']
    elif rule == 'B31_4_403_2_1':
        numerator, denominator = 2*net*v['F_design']*v['E_weld']*v['SMYS_MPa'], v['D_outside_mm']
    else:
        numerator, denominator = 2*net*v['SMYS_MPa']*v['F_class']*v['E_weld']*v['T_temp'], v['D_outside_mm']
    if denominator <= 0:
        raise ValueError('Inverse pressure denominator must be positive')
    pressure = numerator / denominator
    checked = evaluate(rule, dict(v, P_MPa=pressure))
    if checked['value'] is None:
        raise ValueError('Pressure roundtrip unavailable')
    if abs(Decimal(checked['value'])-net) > max(abs(net), d(1))*d('1e-24'):
        raise ValueError('Pressure roundtrip outside numerical tolerance')
    return pressure, {'rule':rule, 'source_reference':REFERENCES[rule], 'basis':'inverse of '+checked['formula'],
                      'net_thickness_mm':str(net), 'inputs':checked['inputs'],
                      'limitations':'Candidate arithmetic only; applicability, geometry and other loads require verification'}


def outputs(current_mm, required_mm=None, adopted_rate=None, inspection_date=None,
            year_days='365.2425', interval_fraction=None, interval_cap_years=None,
            rule=None, design_inputs=None, allowance_mm=None, forecast_years=None,
            forecast_factor=None, selected_interval_years=None, scheduled_due_date=None,
            next_inspection_years=None, manual_interval_override=False,
            manual_selected_interval=False):
    """Return each independently ready value (str/null) with keyed issues/trace.

    required_mm must be an explicitly established governing minimum; a pressure
    thickness alone cannot establish it. adopted_rate is caller-selected, never
    inferred from history. Zero allowance is permitted only as explicit input.
    """
    result = {key:None for key in OUTPUTS}
    result.update(status=STATUS, version=VERSION, issues={k:[] for k in OUTPUTS},
                  trace={k:{'status':STATUS, 'version':VERSION} for k in OUTPUTS})

    def run(key, calculation):
        try:
            with localcontext() as context:
                context.prec = 40
                value, trace = calculation()
            result[key] = str(value)
            result['trace'][key].update(trace)
        except (ValueError, TypeError, DecimalException, OverflowError) as exc:
            result['issues'][key].append(str(exc) or 'Invalid numerical input')

    def current(): return _number(current_mm, 'current_mm', positive=True)
    def margin(): return current() - _number(required_mm, 'required_mm', nonnegative=True)
    def life():
        difference = margin()
        if difference <= 0:
            raise ValueError('BELOW_OR_AT_REQUIRED_THICKNESS')
        return difference / _number(adopted_rate, 'adopted_rate', positive=True)
    def interval():
        return min(life()*_number(interval_fraction, 'interval_fraction', positive=True),
                   _number(interval_cap_years, 'interval_cap_years', positive=True))
    def selected_interval():
        if selected_interval_years in ('', None):
            return interval()
        return _number(selected_interval_years, 'selected_interval_years', positive=True)
    def due():
        if scheduled_due_date not in ('', None) and not manual_interval_override:
            due_date = date.fromisoformat(str(scheduled_due_date)[:10])
            return due_date.isoformat(), {'source_scheduled_date':due_date.isoformat(),
                                          'basis':'provided schedule record'}
        years = selected_interval()
        basis = _number(year_days, 'year_days', positive=True)
        if isinstance(inspection_date, datetime):
            inspected = inspection_date.date()
        elif isinstance(inspection_date, date):
            inspected = inspection_date
        else:
            if not inspection_date: raise ValueError('inspection_date is required')
            inspected = date.fromisoformat(str(inspection_date))
        days = int((years*basis).to_integral_value(rounding=ROUND_FLOOR))
        return (inspected+timedelta(days=days)).isoformat(), {'year_days':str(basis), 'interval_years':str(years), 'rounding':'floor whole days', 'days':str(days), 'inspection_date':inspected.isoformat()}
    def pressure(years, factor, horizon_basis):
        allowance = Decimal(0) if allowance_mm in ('', None) else _number(allowance_mm, 'allowance_mm', nonnegative=True)
        net = current()-allowance
        years = _number(years, 'forecast_years', nonnegative=True)
        factor = _number(factor, 'forecast_factor', positive=True)
        rate = _number(adopted_rate, 'adopted_rate', positive=True)
        net -= rate*years*factor
        trace = {'allowance_mm':str(allowance), 'current_mm':str(current()),
                 'forecast_years':str(years), 'forecast_factor':str(factor),
                 'adopted_rate':str(rate), 'horizon_basis':horizon_basis}
        if net <= 0: raise ValueError('Available net thickness must be positive')
        value, details = _pressure(net, rule, design_inputs)
        return value, dict(trace, **details)

    def remaining_life_mawp():
        years = life()
        return pressure(years, '1', 'remaining_life_endpoint')

    def next_inspection_mawp():
        years = forecast_years if forecast_years not in ('', None) else next_inspection_years
        if years == 'remaining_life':
            years = life()
        if years in ('', None):
            years = selected_interval() if manual_selected_interval else life()
        factor = forecast_factor if forecast_factor not in ('', None) else '2' if manual_selected_interval else '1'
        return pressure(years, factor, 'manual_forecast_horizon' if forecast_years not in ('', None)
                        else 'manual_interval_override' if manual_selected_interval
                        else 'remaining_life_endpoint')

    run('thickness_margin_mm', lambda:(margin(), {'formula':'current_mm - required_mm', 'current_mm':str(current_mm), 'required_mm':str(required_mm)}))
    run('remaining_life_years', lambda:(life(), {'formula':'(current_mm - required_mm) / adopted_rate', 'current_mm':str(current_mm), 'required_mm':str(required_mm), 'adopted_rate':str(adopted_rate)}))
    run('maximum_inspection_interval_years', lambda:(interval(), {'formula':'min(remaining_life_years * interval_fraction, interval_cap_years)', 'interval_fraction':str(interval_fraction), 'interval_cap_years':str(interval_cap_years)}))
    run('inspection_interval_years', lambda:(selected_interval(), {'selected_interval_years':str(selected_interval_years) if selected_interval_years not in ('', None) else None,
          'maximum_interval_years':str(interval()) if selected_interval_years not in ('', None) else None,
          'basis':'selected source/policy interval' if selected_interval_years not in ('', None) else 'calculated maximum interval'}))
    if selected_interval_years not in ('', None):
        try:
            if selected_interval() > interval():
                result['issues']['inspection_interval_years'].append('SELECTED_INTERVAL_EXCEEDS_CALCULATED_MAXIMUM')
        except (ValueError, TypeError, DecimalException):
            pass
    run('due_date', due)
    run('mawp_MPa', remaining_life_mawp)
    run('forecast_mawp_MPa', next_inspection_mawp)
    return result
