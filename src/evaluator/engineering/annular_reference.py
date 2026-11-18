"""Look up verified SI annular reference cells in the packaged dataset."""
from decimal import Decimal
from evaluator.engineering.references import supplementary_tables


def annular_minimum(gravity, shell_mm, stress_mpa):
    if not all(v.is_finite() and v > 0 for v in (gravity, shell_mm, stress_mpa)):
        raise ValueError('Specific gravity, first-course thickness and shell stress must be positive')
    dense_product = gravity >= 1
    table = supplementary_tables()['annular'][str(int(dense_product))]
    rows, columns = table['rows'], table['columns']
    row = next((i for i, bound in enumerate(rows) if bound is None or shell_mm <= bound), None)
    column = next((i for i, bound in enumerate(columns)
                   if stress_mpa < bound or (dense_product and stress_mpa == bound)), None)
    if row is None or column is None:
        raise ValueError('First-course thickness or stress is outside the supported annular table')
    value = Decimal(table['cells'][row][column])
    return value, dict(reference=f"{table['name']}, PDF p. {table['page']}",
                       source_file=table['source_file'], source_sha256=table['source_sha256'],
                       value=str(value), row=row + 1, column=column + 1,
                       shell_mm=str(shell_mm), stress_MPa=str(stress_mpa))
