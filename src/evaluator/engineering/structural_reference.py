"""Packaged structural thickness examples from verified API RP 574 Annex D."""
from evaluator.engineering.references import supplementary_tables


FILENAME = 'RP_574_E5_EN_wA1.pdf'
CLASSES = ('150', '300', '600', '900', '1500', '2500')
NPS = ('0.5', '0.75', '1', '1.5', '2', '3', '4', '6',
       '8', '10', '12', '14', '16', '18', '20', '24')
LOOKUP_FIELDS = ('structural_material', 'structural_temperature', 'structural_nps', 'structural_class')


def structural_tables():
    source = supplementary_tables()['structural']
    return tuple(dict(table, source_file=source['source_file'], source_sha256=source['source_sha256'])
                 for table in source['tables'])


def structural_cell(tables, inputs):
    material, temperature, nps, pressure_class = (inputs.get(key, '') for key in LOOKUP_FIELDS)
    for table in tables:
        if (table['material'], table['temperature']) == (material, temperature):
            value = table['cells'].get(nps, {}).get(pressure_class)
            if value is not None:
                return value, f"{table['reference']} · {material} · {temperature} °F · NPS {nps} · Class {pressure_class}"
    return None
