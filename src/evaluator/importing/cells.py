"""Read-only merged-cell evidence resolution; never guesses across empty rows."""
from decimal import Decimal, InvalidOperation


def merged_value(sheet, row, column):
    cell=sheet.cell(row,column)
    if cell.value is not None: return cell.value
    for region in sheet.merged_cells.ranges:
        if region.min_row<=row<=region.max_row and region.min_col<=column<=region.max_col:
            return sheet.cell(region.min_row,region.min_col).value
    return None


def is_measurement(cell):
    value=cell.value
    if value is None or isinstance(value,bool) or cell.data_type=='f': return False
    if isinstance(value,str) and not value.strip(): return False
    try: return Decimal(str(value)).is_finite()
    except (InvalidOperation,ValueError): return False
