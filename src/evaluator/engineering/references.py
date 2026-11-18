"""Traceable dimensions from the supplied API RP 574 Annex B tables."""
import json
import os
import re
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=1)
def dimensions():
    return json.loads((Path(__file__).parents[1]/'data'/'pipe_dimensions.json').read_text())


def dimension(family, nps, schedule):
    matches=[r for r in dimensions() if (r['family'],r['nps'],r['schedule'])==(family,nps,schedule)]
    if len(matches)!=1:raise ValueError('No unique API 574 size/schedule entry for this selection')
    row=matches[0]
    if row['issues']:raise ValueError('Reference row has a source discrepancy requiring review: '+', '.join(row['issues']))
    return row

# Limited, visually checked source rows. Exact tabulated temperatures only;
# no interpolation, extrapolation, other editions, or cross-code substitution.
@lru_cache(maxsize=1)
def material_stresses():
    return json.loads((Path(__file__).parents[1]/'data'/'material_stresses.json').read_text())


def material_token(material):
    token = re.sub(r'[^A-Z0-9]', '', str(material or '').upper()).removeprefix('ASTM')
    return token.replace('GRADE', '').replace('GR', '')


def material_stress(material, geometry, code, edition, temperature_F, product_form=None, *,
                    material_thickness_mm=None, material_condition_reference=None):
    from decimal import Decimal, InvalidOperation
    token = material_token(material)
    product='pipe' if geometry=='straight_pipe' else 'fitting' if geometry in {'elbow','tee','reducer','branch'} else None
    if code == 'ASME VIII-1':
        product = product_form if geometry in {'shell', 'cylindrical_shell', 'ellipsoidal_head_2to1', 'standard_torispherical_head', 'nozzle'} else None
    if product is None:
        return None
    try:temperature=Decimal(str(temperature_F))
    except InvalidOperation:return None
    matches=[r for r in material_stresses() if r['material_token']==token and r['product_form']==product and r['code_family']==code and r['code_edition']==str(edition) and Decimal(r['temperature_F'])==temperature]
    eligible = [row for row in matches if stress_conditions_match(
        row, material_thickness_mm, material_condition_reference)]
    return eligible[0] if len(eligible) == 1 else None


def b313_reference_factors(material, geometry, code, edition, temperature_f):
    """Use only factors supported by the matched library row and component form."""
    if code != 'ASME B31.3' or str(edition) != '2024':
        return {}
    stress = material_stress(material, geometry, code, edition, temperature_f)
    if not stress:
        return {}
    token = stress['material_token']
    if token not in {'A106B', 'A53TYPESB', 'A234WPB', 'A234WPC'}:
        return {}
    from decimal import Decimal
    temperature = Decimal(stress['temperature_F'])
    result = {}
    if temperature <= 800:
        result['W_reduction'] = ('1', 'B31.3-2024 Table 302.3.5-1, carbon steel')
    if temperature < 950:
        result['Y_coefficient'] = ('0.4', 'B31.3-2024 Table 304.1.1-1, ferritic steel')
    if geometry == 'straight_pipe' and token in {'A106B', 'A53TYPESB'}:
        result['E_quality'] = ('1', 'B31.3-2024 Table A-3, seamless pipe')
    return result


def lowest_material_stress(material, geometry, code, edition, product_form=None, **conditions):
    """Choose the lowest eligible library temperature for a blank design input."""
    from decimal import Decimal

    temperatures = {row['temperature_F'] for row in material_stresses()
                    if row['code_family'] == code and row['code_edition'] == str(edition)}
    for temperature in sorted(temperatures, key=Decimal):
        entry = material_stress(material, geometry, code, edition, temperature, product_form, **conditions)
        if entry:
            return entry
    return None


def stress_conditions_match(row, thickness, condition_reference):
    from decimal import Decimal, InvalidOperation
    if row.get('material_condition_record_required') and not str(condition_reference or '').strip():
        return False
    maximum = row.get('maximum_thickness_mm')
    minimum = row.get('minimum_thickness_exclusive_mm')
    if maximum is None and minimum is None:
        return True
    try:
        measured = Decimal(str(thickness))
        return (measured.is_finite() and measured > 0 and
                (maximum is None or measured <= Decimal(maximum)) and
                (minimum is None or measured > Decimal(minimum)))
    except InvalidOperation:
        return False


def code_pdf_path(filename):
    folder = os.environ.get('UT_EVALUATOR_CODES')
    if folder:
        return Path(folder).expanduser() / filename
    sources = os.environ.get('UT_EVALUATOR_SOURCES')
    if sources:
        return Path(sources).expanduser() / 'codes' / filename
    checkout = Path(__file__).resolve().parents[3] / 'sources' / 'codes' / filename
    return checkout if checkout.is_file() else Path.home() / 'Desktop' / 'Codes' / filename


@lru_cache(maxsize=1)
def supplementary_tables():
    path = Path(__file__).parents[1] / 'data' / 'tank_and_structural_references.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    if payload.get('schema_version') != 1:
        raise ValueError('Unsupported supplementary reference database version.')
    return payload
