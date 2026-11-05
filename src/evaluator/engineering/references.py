"""Traceable dimensions from the supplied API RP 574 Annex B tables."""
import json
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


def material_stress(material, geometry, code, edition, temperature_F):
    import re
    from decimal import Decimal, InvalidOperation
    token=re.sub(r'[^A-Z0-9]','',str(material).upper()).removeprefix('ASTM')
    token=token.replace('GRADE','').replace('GR','')
    product='pipe' if geometry=='straight_pipe' else 'fitting' if geometry in {'elbow','tee','reducer','branch'} else None
    try:temperature=Decimal(str(temperature_F))
    except InvalidOperation:return None
    matches=[r for r in material_stresses() if r['material_token']==token and r['product_form']==product and r['code_family']==code and r['code_edition']==str(edition) and Decimal(r['temperature_F'])==temperature]
    return matches[0] if len(matches)==1 else None
