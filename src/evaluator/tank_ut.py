"""Explicit workbook cell mapping for tank UT inputs."""
from datetime import date
from decimal import Decimal, DecimalException
from hashlib import sha256
from io import BytesIO
import re

from openpyxl import load_workbook

MAPPINGS = {
    'api653_shell': ('measured_mm', 't2_mm'),
    'api653_bottom': ('RTbc_mm', 'RTip_mm'),
    'api653_critical': ('RTbc_mm', 'RTip_mm'),
    'api653_annular': ('RTbc_mm', 'RTip_mm'),
}


def import_values(service, form):
    source_id = form.get('ut_source', '')
    if not source_id:
        if any(form.get(k) for k in ('ut_sheet', 'ut_date', 'ut_primary', 'ut_secondary')):
            raise ValueError('Select an imported workbook for the UT cell mapping')
        return dict(form), None
    method = form.get('method')
    if method not in MAPPINGS:
        raise ValueError('This tank method does not take workbook UT inputs')
    if form.get('ut_mm') != 'yes':
        raise ValueError('Confirm the selected workbook readings are in millimetres')
    event_date = date.fromisoformat(form.get('ut_date', '')).isoformat()
    sheet = form.get('ut_sheet', '')
    source = next((s for s in service.repository.sources() if s.sha256 == source_id), None)
    if source is None:
        raise ValueError('Selected UT workbook is unavailable')
    payload = source.stored_path.read_bytes()
    if sha256(payload).hexdigest() != source_id:
        raise ValueError('Source workbook integrity check failed')
    local = method == 'api653_shell' and form.get('scope') == 'local'
    if local and form.get('ut_profile_reviewed') != 'yes':
        raise ValueError('Confirm the local profile and least-thickness area mapping')
    keys = MAPPINGS[method][:1] if method == 'api653_shell' and not local else MAPPINGS[method]
    groups = {}
    result = dict(form)
    book = load_workbook(BytesIO(payload), read_only=True, data_only=False, keep_links=False)
    try:
        if sheet not in book.sheetnames:
            raise ValueError('Enter the exact UT worksheet name')
        ws = book[sheet]
        for index, key in enumerate(keys):
            cells = form.get(('ut_primary', 'ut_secondary')[index], '').upper().split(',')
            cells = [cell.strip() for cell in cells]
            if len(cells) > 100 or len(set(cells)) != len(cells) or any(
                not re.fullmatch(r'[A-Z]{1,3}[1-9][0-9]{0,6}', cell) for cell in cells
            ):
                raise ValueError('Enter up to 100 distinct cell addresses per UT input')
            readings = []
            for cell in cells:
                entry = ws[cell]
                if entry.data_type != 'n' or entry.value is None:
                    raise ValueError(f'{sheet}!{cell} must contain a literal numeric UT reading')
                try:
                    value = Decimal(str(entry.value))
                except DecimalException:
                    raise ValueError(f'{sheet}!{cell} is not a valid UT reading') from None
                if not value.is_finite() or value <= 0:
                    raise ValueError(f'{sheet}!{cell} must contain positive thickness')
                readings.append(value)
            if local and index == 0:
                if len(readings) < 5:
                    raise ValueError('Local profile t1 requires at least five equally spaced UT readings')
                value = sum(readings, Decimal(0)) / len(readings)
            else:
                value = min(readings)
            groups[key] = dict(cells=dict(zip(cells, map(str, readings))), aggregation='mean' if local and index == 0 else 'minimum')
            result[key] = str(value)
    finally:
        book.close()
    return result, dict(source_sha256=source_id, sheet=sheet, inspection_date=event_date,
                        units='mm', groups=groups)
