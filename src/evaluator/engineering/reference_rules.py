"""Edition-scoped reference rules verified against the supplied editions."""
from decimal import Decimal

GAS_TEMPERATURE_REFERENCE = {
    'reference': 'ASME B31.8-2025 Table 841.1.8-1, PDF p. 70 (printed p. 44)',
    'source_sha256': '9d2323f391cfe83b77e154e5d41f043f40587eac2b086cdc4e7a7fa98c7ff2cd',
}
TANK_NOMINAL_REFERENCE = {
    'reference': 'API 650 14th edition (2025), 5.6.1.1 and Note 4, PDF pp. 65–66',
    'source_sha256': 'd8e996516be095fd6f786d2752cedb11aa10b39cf5cc5f9a47b3c90ff936b3a7',
}


def gas_temperature_factor(temperature_f):
    """Interpolate within the B31.8 steel-pipe temperature table in °F."""
    temperature = Decimal(str(temperature_f))
    if not temperature.is_finite() or temperature > 450:
        raise ValueError('B31.8 temperature is outside the supported table range')
    if temperature <= 250:
        return Decimal(1)
    points = tuple((Decimal(t), Decimal(f)) for t, f in
                   [(250, '1'), (300, '.967'), (350, '.933'), (400, '.900'), (450, '.867')])
    for (lo, a), (hi, b) in zip(points, points[1:]):
        if temperature <= hi:
            return a + (b - a) * (temperature - lo) / (hi - lo)


def tank_nominal_minimum(diameter_m, position):
    """API 650 SI erection minimum with the lowest-course exception."""
    if not diameter_m.is_finite() or diameter_m <= 0:
        raise ValueError('Tank diameter must be positive')
    if Decimal('3.2') < diameter_m < 15:
        if position not in {'lowest', 'upper'}:
            raise ValueError('Identify the lowest or upper shell course for this tank diameter')
        return Decimal(6 if position == 'lowest' else 5)
    if diameter_m < 15:
        return Decimal(5)
    if diameter_m < 36:
        return Decimal(6)
    return Decimal(8 if diameter_m <= 60 else 10)

GAS_SMYS_REFERENCE = {
    'reference': 'ASME B31.8-2025 Table D-1, API Spec 5L, PDF p. 176 (printed p. 150)',
    'source_sha256': GAS_TEMPERATURE_REFERENCE['source_sha256'],
}
GAS_5L_SMYS_PSI = {'B': 35500, 'X42': 42100, 'X52': 52200, 'X60': 60200, 'X65': 65300, 'X70': 70300}
GAS_5L_FORMS = frozenset({'LFW', 'HFW', 'SMLS', 'SAWL', 'SAWH', 'COWL', 'COWH'})


def gas_pipe_smys(material, product_form):
    import re

    match = re.fullmatch(r'API(?:SPEC)?5L(?:GRADE)?(B|X[0-9]+)',
                         re.sub(r'[^A-Z0-9]', '', str(material).upper()))
    if match and product_form in GAS_5L_FORMS:
        return GAS_5L_SMYS_PSI.get(match[1])
    return None

GAS_BASIC_CLASS_F = {'1 Division 1': '0.80', '1 Division 2': '0.72', '2': '0.60', '3': '0.50', '4': '0.40'}
GAS_CLASS_REFERENCE = {
    'reference': 'ASME B31.8-2025 Table 841.1.6-1, basic design factor, PDF p. 69',
    'source_sha256': GAS_TEMPERATURE_REFERENCE['source_sha256'],
}
BOTTOM_DESIGN_MIN_MM = {'no_leak_containment': '2.54', 'leak_detection_containment': '1.27',
                        'qualified_reinforced_lining': '1.27'}
BOTTOM_DESIGN_REFERENCE = 'API 653 5th edition through July 2025, Table 4.4a, PDF p. 40'

LIQUID_WELD_REFERENCE = {
    'reference': 'ASME B31.4-2025 Table 403.2.1-1, PDF p. 37 (printed p. 17)',
    'source_sha256': '198eeef109b7d2c39e74a9285ddd72cadbf086ba9e49fe93f85f2f9ae4c280f2',
}
LIQUID_WELD_FACTORS = {
    'API 5L seamless · A25 through X80Q/M': '1.00',
    'ASTM A53 seamless · all grades': '1.00',
    'ASTM A106 seamless · all grades': '1.00',
    'ASTM A333 seamless · Grade 6': '1.00',
    'ASTM A524 seamless · all grades': '1.00',
    'ASTM A53 furnace butt/continuous weld · Type F Grade A': '0.60',
    'API 5L furnace butt/continuous weld · A25': '0.60',
    'API 5L ERW or electric flash welded · A25 through X80Q/M': '1.00',
    'ASTM A53 ERW or electric flash welded · all grades': '1.00',
    'ASTM A135 ERW or electric flash welded · all grades': '1.00',
    'ASTM A333 ERW or electric flash welded · Grade 6': '1.00',
    'ASTM A134 electric fusion welded · all grades': '0.80',
    'ASTM A139 electric fusion welded · all grades': '0.80',
    'ASTM A381 submerged arc welded · Y35 through Y65': '1.00',
}

# Material strength, distinct from the B31.4 weld factor.
LIQUID_PIPE_SMYS = {
    'ASTM A53 Type S Grade B': ('35000', 32),
    'ASTM A106 Grade B': ('35000', 33),
    'ASTM A333 Grade 6': ('35000', 34),
}
LIQUID_PIPE_SMYS_REFERENCE = 'ASME B31.3-2024 Table A-1C, minimum yield strength column (material property), PDF pp. 322–323'
