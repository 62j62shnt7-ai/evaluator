"""Prefill pipe inputs from the owning UT table, without inventing missing inputs."""
import re
from evaluator.engineering.references import dimensions


def defaults(snapshot, cell, band):
    cells=snapshot.get('cells',{})
    def value(address):return cells.get(address,{}).get('value')
    row=int(re.search(r'\d+',cell)[0])
    headers=[n for n in range(1,row) if str(value(f'A{n}') or '').strip().upper().rstrip('#.')=='JOINT' and str(value(f'B{n}') or '').strip().upper()=='BAND']
    if not headers:return {}
    header=headers[-1]
    result={'segment':f'UT section {len(headers)}'}
    from .reading_identity import component
    geometry,material=component(band)
    if material:result.update(material=material,geometry=geometry)
    # Only use explicit, literal dimension columns in this table.
    for address,label in cells.items():
        if not re.fullmatch(r'[A-Z]+'+str(header),address):continue
        heading=re.sub(r'[^A-Z0-9]','',str(label.get('value') or '').upper())
        column=re.match(r'[A-Z]+',address)[0];datum=cells.get(f'{column}{row}',{})
        if datum.get('formula') or datum.get('value') in (None,''):continue
        val=str(datum['value']).strip()
        if heading in {'DIAM','NOMD','NPS'}:
            nps=val.replace('"','').replace("'",'').strip()
            matches=[d for d in dimensions() if d['family']=='ferritic' and d['nps']==nps]
            if matches:result.update(nps=nps,D_outside_in=matches[0]['od_in'])
        elif heading in {'NOMT','TNOM','NOMINALTHICKNESS'}:
            try:
                if float(val)>0:result['nominal_thickness_mm']=val
            except ValueError:pass
        elif heading in {'SCH','SCHEDULE'}:result['schedule']=val
    return result
