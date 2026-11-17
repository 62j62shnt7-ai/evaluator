"""Structural thickness examples from the owner's verified API RP 574 Annex D PDF."""
from functools import lru_cache
from hashlib import sha256
import re

from evaluator.engineering.references import code_pdf_path


FILENAME = 'RP_574_E5_EN_wA1.pdf'
DIGEST = '42d99b85a7864a77953e4a897c4d0f5d5c09f97658a2ffafc38a557a819114cf'
TABLES = (
    ('D.2b', 148, 'Carbon steel', '400'),
    ('D.2d', 149, 'Carbon steel', '750'),
    ('D.3b', 150, 'Austenitic stainless steel', '400'),
    ('D.3d', 151, 'Austenitic stainless steel', '1000'),
    ('D.4b', 152, '1¼Cr–½Mo', '750'),
    ('D.4d', 153, '1¼Cr–½Mo', '1100'),
)
CLASSES = ('150', '300', '600', '900', '1500', '2500')
NPS = ('0.5', '0.75', '1', '1.5', '2', '3', '4', '6',
       '8', '10', '12', '14', '16', '18', '20', '24')
LOOKUP_FIELDS = ('structural_material', 'structural_temperature', 'structural_nps', 'structural_class')


def structural_tables():
    path = code_pdf_path(FILENAME)
    try:
        stat = path.stat()
        return _read_tables(path, stat.st_size, stat.st_mtime_ns)
    except OSError:
        raise ValueError('Local API RP 574 PDF unavailable. Use a reviewed manual structural minimum.') from None


@lru_cache(maxsize=2)
def _read_tables(path, size, modified):
    try:
        import pymupdf
    except ImportError:
        raise ValueError('Annex D lookup requires the pdf-reference package option.') from None
    pdf = path.read_bytes()
    if sha256(pdf).hexdigest() != DIGEST:
        raise ValueError('Local API RP 574 PDF differs from the verified Annex D source.')
    tables = []
    with pymupdf.open(stream=pdf, filetype='pdf') as document:
        for name, page_number, material, temperature in TABLES:
            page = document[page_number - 1]
            classes = CLASSES[1:] if name == 'D.4d' else CLASSES
            tables_found = page.find_tables().tables
            if f'Table {name}' not in page.get_text() or len(tables_found) != 2:
                raise ValueError(f'Could not identify the metric Annex D Table {name}.')
            cells = tables_found[1].extract()
            rows = cells[2:]
            if (tuple(cells[1][1:]) != classes or tuple(row[0] for row in rows) != NPS
                    or any(len(row) != len(classes) + 1
                           or any(cell != '—' and not re.fullmatch(r'[0-9]+\.[0-9]{2}', cell or '')
                                  for cell in row[1:]) for row in rows)):
                raise ValueError(f'Unexpected row, column or cell in Annex D Table {name}.')
            tables.append(dict(material=material, temperature=temperature,
                               reference=f'API RP 574 Annex D Table {name}, PDF p. {page_number}',
                               cells={nps: {pressure_class: value
                                            for pressure_class, value in zip(classes, values)
                                            if value != '—'}
                                      for nps, *values in rows}))
    return tuple(tables)


def structural_cell(tables, inputs):
    material, temperature, nps, pressure_class = (inputs.get(key, '') for key in LOOKUP_FIELDS)
    for table in tables:
        if (table['material'], table['temperature']) == (material, temperature):
            value = table['cells'].get(nps, {}).get(pressure_class)
            if value is not None:
                return value, f"{table['reference']} · {material} · {temperature} °F · NPS {nps} · Class {pressure_class}"
    return None
