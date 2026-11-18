"""Prefill pipe inputs from the owning UT table, without inventing missing inputs."""
from bisect import bisect_left
import re
from evaluator.engineering.references import dimensions


class UTTableIndex:
    """Index headers for repeated lookups against one imported sheet snapshot."""

    def __init__(self, snapshot):
        self.cells = snapshot.get('cells', {})
        self.headers = sorted(
            int(address[1:]) for address, cell in self.cells.items()
            if re.fullmatch(r'A[1-9][0-9]*', address)
            and str(cell.get('value') or '').strip().upper().rstrip('#.') == 'JOINT'
            and str(self.cells.get('B' + address[1:], {}).get('value') or '').strip().upper() == 'BAND'
        )
        self.columns = {row: [] for row in self.headers}
        if self.columns:
            for address, cell in self.cells.items():
                match = re.fullmatch(r'([A-Z]+)([1-9][0-9]*)', address)
                if match and int(match[2]) in self.columns:
                    heading = re.sub(r'[^A-Z0-9]', '', str(cell.get('value') or '').upper())
                    self.columns[int(match[2])].append((match[1], heading))


def defaults(snapshot, cell, band, *, sources=None):
    table = snapshot if isinstance(snapshot, UTTableIndex) else UTTableIndex(snapshot)
    row = int(re.search(r'\d+', cell)[0])
    section = bisect_left(table.headers, row)
    if not section:
        return {}
    header = table.headers[section - 1]
    result={'segment':f'UT section {section}'}
    from .reading_identity import component
    geometry,material=component(band)
    if material:result.update(material=material,geometry=geometry)
    # Only use explicit, literal dimension columns in this table.
    for column, heading in table.columns[header]:
        datum = table.cells.get(f'{column}{row}', {})
        if datum.get('formula') or datum.get('value') in (None,''):continue
        val=str(datum['value']).strip()
        if sources is not None:
            for key, headings in {
                'nps': {'DIAM','NOMD','NPS'}, 'D_outside_in': {'DIAM','NOMD','NPS','ODIN'},
                'nominal_thickness_mm': {'NOMT','TNOM','NOMINALTHICKNESS'},
                'schedule': {'SCH','SCHEDULE'},
                'material': {'MAT','MATERIAL','MATERIALGRADE'},
            }.items():
                if heading in headings:
                    sources[key] = f'{column}{row}'
        if heading in {'DIAM','NOMD','NPS'}:
            nps=val.replace('"','').replace("'",'').strip()
            matches=[d for d in dimensions() if d['family']=='ferritic' and d['nps']==nps]
            if matches:result.update(nps=nps,D_outside_in=matches[0]['od_in'])
        elif heading == 'ODIN':
            matches = {d['nps'] for d in dimensions() if d['family']=='ferritic' and d['od_in']==val}
            if len(matches)==1:result.update(nps=matches.pop(),D_outside_in=val)
        elif heading in {'NOMT','TNOM','NOMINALTHICKNESS'}:
            try:
                if float(val)>0:result['nominal_thickness_mm']=val
            except ValueError:pass
        elif heading in {'SCH','SCHEDULE'}:result['schedule']=val
        elif heading in {'MAT','MATERIAL','MATERIALGRADE'} and val.upper() not in {'NA', 'N/A', '-', 'UNKNOWN'}:
            result['material'] = val
        elif heading in {'MAT','MATERIAL','MATERIALGRADE'} and sources is not None:
            sources.pop('material', None)
    return result
