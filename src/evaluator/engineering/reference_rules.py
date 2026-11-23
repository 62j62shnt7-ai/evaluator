"""Edition-scoped reference rules verified against the supplied editions."""
from decimal import Decimal

import json
from pathlib import Path
import re

_DATA = json.loads((Path(__file__).parents[1] / 'data' / 'code_reference_values.json').read_text(encoding='utf-8'))
if _DATA.get('schema_version') != 1:
    raise ValueError('Unsupported code reference database version.')


def _reference(key):
    return {field: _DATA[key][field] for field in ('reference', 'source_sha256')}


GAS_TEMPERATURE_REFERENCE = _reference('gas_temperature')
TANK_NOMINAL_REFERENCE = _reference('tank_nominal')
API570_UT_CAP_YEARS = {'1': '5', '2': '10', '3': '10'}
API570_UT_POLICY_REFERENCE = 'API 570 fifth edition + Addendum 1, §6.3.3 and Table 1'


def gas_temperature_factor(temperature_f):
    """Interpolate within the B31.8 steel-pipe temperature table in °F."""
    temperature = Decimal(str(temperature_f))
    if not temperature.is_finite() or temperature > 450:
        raise ValueError('B31.8 temperature is outside the supported table range')
    if temperature <= 250:
        return Decimal(1)
    points = tuple((Decimal(t), Decimal(f)) for t, f in
                   _DATA['gas_temperature']['points'])
    for (lo, a), (hi, b) in zip(points, points[1:]):
        if temperature <= hi:
            return a + (b - a) * (temperature - lo) / (hi - lo)


def tank_nominal_minimum(diameter_m, position):
    """API 650 SI erection minimum with the lowest-course exception."""
    if not diameter_m.is_finite() or diameter_m <= 0:
        raise ValueError('Tank diameter must be positive')
    table = _DATA['tank_nominal']
    low, middle, high = map(Decimal, table['thresholds_m'])
    least, lower, upper, highest = map(Decimal, table['minimums_mm'])
    if Decimal(table['least_diameter_exception_m']) < diameter_m < low:
        if position not in {'lowest', 'upper'}:
            raise ValueError('Identify the lowest or upper shell course for this tank diameter')
        return lower if position == 'lowest' else least
    if diameter_m < low:
        return least
    if diameter_m < middle:
        return lower
    return upper if diameter_m <= high else highest

GAS_SMYS_REFERENCE = _reference('gas_smys')
GAS_5L_SMYS_PSI = _DATA['gas_smys']['values']
GAS_5L_FORMS = frozenset(_DATA['gas_smys']['standard_forms']) | {'CW'}
GAS_5L_GRADE_FORMS = {
    grade: _DATA['gas_smys']['grade_forms'].get(grade, _DATA['gas_smys']['standard_forms'])
    for grade in GAS_5L_SMYS_PSI
}


def gas_pipe_smys(material, product_form):
    match = re.fullmatch(r'API(?:SPEC)?5L(?:GRADE)?(A25|A|B|X[0-9]+)',
                         re.sub(r'[^A-Z0-9]', '', str(material).upper()))
    if match and product_form in GAS_5L_GRADE_FORMS.get(match[1], ()):
        return GAS_5L_SMYS_PSI[match[1]]
    return None


GAS_BASIC_CLASS_F = _DATA['gas_class']['values']
GAS_CLASS_REFERENCE = _reference('gas_class')
BOTTOM_DESIGN_MIN_MM = _DATA['tank_bottom']['values']
BOTTOM_DESIGN_REFERENCE = _DATA['tank_bottom']['reference']
LIQUID_WELD_REFERENCE = _reference('liquid_weld')
LIQUID_WELD_FACTORS = _DATA['liquid_weld']['values']
LIQUID_PIPE_SMYS = _DATA['liquid_smys']['values']
LIQUID_PIPE_SMYS_REFERENCE = _DATA['liquid_smys']['reference']
