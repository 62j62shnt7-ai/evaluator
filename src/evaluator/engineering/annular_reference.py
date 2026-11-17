"""Read the SI annular reference cells from the owner's local code PDFs."""
from decimal import Decimal
from functools import lru_cache
from hashlib import sha256
import os
from pathlib import Path

from evaluator.engineering.reference_rules import TANK_NOMINAL_REFERENCE

_SOURCES = {
    False: ('STD_653_E5_EN_wE1E2A1A2A3A4.pdf', 42,
            'cb936410a1fb40d04a27e996632837875b635675b8d39f6e6332c87ae7b64dbb',
            'API 653 Table 4.5a', (19, 25, 32, 38, None), (168, 186, 205, 223)),
    True: ('STD_650_E14_EN.pdf', 65,
           TANK_NOMINAL_REFERENCE['source_sha256'],
           'API 650 Table 5.1a', (19, 25, 32, 40, 45), (190, 210, 220, 250)),
}


def _code_path(filename):
    folder = os.environ.get('UT_EVALUATOR_CODES')
    if folder:
        return Path(folder).expanduser() / filename
    sources = os.environ.get('UT_EVALUATOR_SOURCES')
    if sources:
        return Path(sources).expanduser() / 'codes' / filename
    checkout = Path(__file__).resolve().parents[3] / 'sources' / 'codes' / filename
    return checkout if checkout.is_file() else Path.home() / 'Desktop' / 'Codes' / filename


@lru_cache(maxsize=2)
def _si_cells(pdf, page_number, name, columns):
    try:
        import pymupdf
    except ImportError:
        raise ValueError('Local PDF lookup requires the pdf-reference package option. Use the reviewed manual lookup until it is installed.') from None
    expected_header = [f'{"≤" if name.startswith("API 650") else "<"} {bound}' for bound in columns]
    with pymupdf.open(stream=pdf, filetype='pdf') as doc:
        page = doc[page_number - 1]
        if name.removeprefix('API 650 ').removeprefix('API 653 ') not in page.get_text():
            raise ValueError('The expected annular source table is missing')
        for table in page.find_tables().tables:
            data = table.extract()
            if table.col_count == 5 and len(data) >= 7 and data[1][1:] == expected_header:
                return tuple(tuple(Decimal(cell.strip()) for cell in row[1:]) for row in data[2:7])
    raise ValueError('Could not identify the SI annular table in the verified PDF')


def annular_minimum(gravity, shell_mm, stress_mpa):
    if not all(v.is_finite() and v > 0 for v in (gravity, shell_mm, stress_mpa)):
        raise ValueError('Specific gravity, first-course thickness and shell stress must be positive')
    dense_product = gravity >= 1
    filename, page, digest, name, rows, columns = _SOURCES[dense_product]
    row = next((i for i, bound in enumerate(rows) if bound is None or shell_mm <= bound), None)
    column = next((i for i, bound in enumerate(columns)
                   if stress_mpa < bound or (dense_product and stress_mpa == bound)), None)
    if row is None or column is None:
        raise ValueError('First-course thickness or stress is outside the supported annular table')
    try:
        pdf = _code_path(filename).read_bytes()
    except OSError:
        raise ValueError(f'Local code PDF unavailable: {filename}. Set UT_EVALUATOR_CODES or use a reviewed manual lookup.') from None
    if sha256(pdf).hexdigest() != digest:
        raise ValueError(f'Local code PDF differs from the verified copy: {filename}')
    value = _si_cells(pdf, page, name, columns)[row][column]
    return value, dict(reference=f'{name}, PDF p. {page}', source_sha256=digest, value=str(value),
                       row=row + 1, column=column + 1, shell_mm=str(shell_mm), stress_MPa=str(stress_mpa))
