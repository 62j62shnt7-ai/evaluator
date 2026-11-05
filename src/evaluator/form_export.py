"""Fill the supplied evaluation form by patching its OOXML package.

Unchanged ZIP members are copied byte for byte, including media and VBA. The
selected form receives values, never cached source results presented as new.
"""
from collections import defaultdict
from decimal import Decimal
from io import BytesIO
import json
import re
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, quoteattr
from zipfile import ZipFile

MAIN='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL='http://schemas.openxmlformats.org/package/2006/relationships'
DOCREL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def _cell(ref, value, original=''):
    style=re.search(r'\bs="[^"]*"',original)
    attrs=' r='+quoteattr(ref)+(' '+style[0] if style else '')
    if value is None:return '<c'+attrs+'/>'
    try:
        number=Decimal(str(value))
        if not number.is_finite():raise ValueError('Nonfinite export value')
        return '<c'+attrs+'><v>'+str(number)+'</v></c>'
    except Exception:
        return '<c'+attrs+' t="inlineStr"><is><t xml:space="preserve">'+escape(str(value))+'</t></is></c>'


def _column(ref):
    n=0
    for c in re.match('[A-Z]+',ref)[0]:n=n*26+ord(c)-64
    return n


def _patch(xml, values):
    def row_patch(match):
        opening,body,closing=match.groups();row=int(re.search(r'\br="(\d+)"',opening)[1])
        selected={k:v for k,v in values.items() if int(re.search(r'\d+',k)[0])==row}
        if not selected:return match[0]
        cells=list(re.finditer(r'<c\b[^>]*(?:/>|>.*?</c>)',body,re.S))
        fragments=[];last=0
        for c in cells:
            ref=re.search(r'\br="([A-Z]+\d+)"',c[0])[1]
            for missing in sorted([k for k in selected if _column(k)<_column(ref)],key=_column):
                fragments.append(_cell(missing,selected.pop(missing)))
            fragments.append(body[last:c.start()])
            fragments.append(_cell(ref,selected.pop(ref),c[0]) if ref in selected else c[0]);last=c.end()
        fragments.append(body[last:])
        # Cells must precede row extension markup, if any.
        tail=''.join(_cell(k,selected[k]) for k in sorted(selected,key=_column))
        combined=''.join(fragments)
        combined=combined.replace('<extLst',tail+'<extLst',1) if '<extLst' in combined else combined+tail
        return opening+combined+closing
    return re.sub(r'(<row\b[^>]*>)(.*?)(</row>)',row_patch,xml,flags=re.S)


def export_form(service, result):
    if result.get('stale'):raise ValueError('Re-evaluate before exporting a stale result')
    cid=result['comparison_id'];comp=service.workflow.comparison(cid)
    source=next(s for s in service.repository.sources() if s.sha256==comp['current_selection'][0])
    sheet=result['profile_sheet']
    if not sheet:raise ValueError('No supplied evaluation form is available for this workbook')
    profiles={p['id']:p for p in result['profiles']}
    if not profiles:raise ValueError('No recognized evaluation-form mapping is available')
    grouped=defaultdict(list)
    for row in result['rows']:
        if row['current_id'] and row['profile_id'] in profiles:grouped[row['profile_id']].append(row)
    values={};mapping=[]
    family=next(iter(profiles.values()))['family']
    layouts={
        'Evaluation 6-2025':dict(current='N',previous='L',required='I',rate='S',life='T',interval='U',future='V',pressure='W',status='X',date='Y',history=['J','K','L','M','N']),
        'Evalation 4-2026':dict(current='O',previous='N',required='I',rate='T',life='U',interval='V',future='W',pressure='X',status='Y',date='Z',history=['J','K','L','M','N','O']),
        'Reassess 1500 Psi May-2025':dict(current='O',previous='N',required='I',rate='U',life='V',interval='W',future='X',pressure='Y',status='Z',date=None,history=['J','K','L','M','N','O']),
        'Eval 8-2023 - ASME B31.8':dict(current='M',previous='L',required='H',rate='R',life='S',interval='T',future='U',pressure='V',status='W',date=None,history=['I','J','K','L','M']),
        'Eval 8-2023 - ASME B31.3':dict(current='O',previous='N',required='J',rate='S',life='T',interval='U',future='V',pressure='W',status='X',date='Y',history=['K','L','M','N','O']),
    }
    for pid,p in profiles.items():
        n=p['row'];items=grouped[pid];row=items[0] if len(items)==1 else None
        if family=='separator':
            nozzle=p['section']=='NOZZLES'
            layout=dict(current='M',previous='L',required='S' if nozzle else 'N',rate='V' if nozzle else 'R',life='X' if nozzle else 'T',interval='Y' if nozzle else 'U',future='Z' if nozzle else 'V',pressure='AA' if nozzle else 'W',status='AC' if nozzle else 'Y',date='AB' if nozzle else 'X',history=['K','L','M'])
            clear_columns=list('NOPQR') if not nozzle else ['N','O','P','Q','R','S','T','U','V','W','X','Y','Z','AA','AB','AC']
        else:
            if sheet not in layouts:raise ValueError('Unsupported form mapping')
            layout=layouts[sheet];clear_columns=['O','P','Q','R','S','T','U','V','W','X','Y','Z']
        for col in clear_columns+layout['history']:values[f'{col}{n}']=None
        # Clear all outputs first; unavailable rows cannot inherit source results.
        for col in layout.values():
            if isinstance(col,str):values[f'{col}{n}']=None
        mapping.append(dict(profile_id=pid,template_row=n,current_ids=[r['current_id'] for r in items],state='mapped' if row else 'ambiguous' if items else 'unmatched'))
        values[f"{layout['status']}{n}"]='DRAFT / '+('REVIEW: '+', '.join(row['issues']) if row else 'unresolved mapping')
        if not row:continue
        for key,col in [('current_thickness_mm','current'),('previous_thickness_mm','previous'),('adopted_rate_mm_year','rate'),('remaining_life_years','life'),('inspection_interval_years','interval')]:values[f'{layout[col]}{n}']=row[key]
        values[f"{layout['required']}{n}"]=row['required_thickness_mm'] or (row['pressure_thickness_mm'] if row['evaluation_status']!='NEEDS_REVIEW' else None)
        if row['forecast_mawp_MPa'] is not None:values[f"{layout['pressure']}{n}"]=str(Decimal(row['forecast_mawp_MPa'])/Decimal('0.006894757293'))
        forecast=row.get('outputs',{}).get('trace',{}).get('forecast_mawp_MPa',{})
        if forecast.get('net_thickness_mm') is not None:values[f"{layout['future']}{n}"]=forecast['net_thickness_mm']
        if layout['date']:values[f"{layout['date']}{n}"]=row['due_date']
        profile=row['profile']
        stress='SMYS_psi' if profile.get('code_family') in {'ASME B31.4','ASME B31.8'} else 'S_allow_psi'
        cols={'material':'C','P_psi':'D',stress:'F','D_outside_in':'H' if family=='separator' else 'E','nominal_thickness_mm':'J' if family=='separator' else 'G'}
        if family=='separator':cols.update(D_inside_in='I',temperature_F='E',E_joint='G')
        elif sheet in {'Evaluation 6-2025','Evalation 4-2026','Reassess 1500 Psi May-2025'}:cols['schedule']='H'
        for key,col in cols.items():
            values[f'{col}{n}']=profile.get('fields',{}).get(key,{}).get('value')
    def campaign_date(key,selection):
        candidates={r.get(key) for r in result['rows'] if r.get(key)}
        return candidates.pop() if len(candidates)==1 else 'Previous dates vary by location' if key=='previous_inspection_date' and comp.get('baseline_per_location') else selection[2]+' (dates unresolved or mixed)'
    current_date=campaign_date('inspection_date',comp['current_selection']);previous_date=campaign_date('previous_inspection_date',comp['baseline'])
    values['A1']='DRAFT — generated evaluation; see UT Calculation Ledger for scope and exceptions'
    if family=='separator':
        values['A49']='DRAFT: source recommendation replaced. Review the UT Calculation Ledger and all unresolved locations before engineering disposition.'
        values['M4']=current_date;values['M26']=current_date;values['L4']=previous_date;values['L26']=previous_date
    else:
        header={'Evaluation 6-2025':5,'Evalation 4-2026':5,'Reassess 1500 Psi May-2025':5,'Eval 8-2023 - ASME B31.8':6,'Eval 8-2023 - ASME B31.3':7}[sheet]
        values[f"{layouts[sheet]['current']}{header}"]=current_date
        values[f"{layouts[sheet]['previous']}{header}"]=previous_date
    # Create a supporting ledger inside the same workbook using inline strings.
    columns=['location','inspection_date','previous_inspection_date','segment','component','current_sheet','current_cell','previous_cell','previous_thickness_mm','current_thickness_mm','required_thickness_mm','pressure_thickness_mm','apparent_rate_mm_year','adopted_rate_mm_year','remaining_life_years','inspection_interval_years','due_date','mawp_MPa','forecast_mawp_MPa','issues','input_trace']
    matrix=[['DRAFT / NOT VALIDATED', 'Selected generated form: '+sheet,'Source SHA256: '+source.sha256],['Other worksheets retain original source content. Pressure-only minima are not governing acceptance limits.'],['CR=(previous-current)/elapsed years; life=(current-required)/positive adopted CR. See input_trace for method and provenance.'],columns]
    matrix += [[json.dumps(r.get(k),ensure_ascii=False) if isinstance(r.get(k),(dict,list)) else r.get(k) for k in columns] for r in result['rows']]
    matrix += [['FORM MAPPING',json.dumps(m)] for m in mapping]
    def letters(n):
        s=''
        while n:n,r=divmod(n-1,26);s=chr(65+r)+s
        return s
    ledger='<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="'+MAIN+'"><sheetData>'+''.join('<row r="'+str(i)+'">'+''.join(_cell(letters(j)+str(i),v) for j,v in enumerate(row,1))+'</row>' for i,row in enumerate(matrix,1))+'</sheetData></worksheet>'
    out=BytesIO()
    with ZipFile(source.stored_path) as archive,ZipFile(out,'w') as target:
        workbook=archive.read('xl/workbook.xml').decode();rels=archive.read('xl/_rels/workbook.xml.rels').decode()
        root=ET.fromstring(workbook);relroot=ET.fromstring(rels)
        sheets=root.find('{'+MAIN+'}sheets');found=next(s for s in sheets if s.get('name')==sheet)
        rid=found.get('{'+DOCREL+'}id');part=next(r.get('Target') for r in relroot if r.get('Id')==rid)
        part=part.lstrip('/') if part.startswith('/') else 'xl/'+part
        ids={r.get('Id') for r in relroot};newid='rIdUTLedger'
        while newid in ids:newid+='x'
        ledger_name='UT Calculation Ledger';suffix=1;names={s.get('name') for s in sheets}
        while ledger_name in names:suffix+=1;ledger_name=f'UT Calculation Ledger {suffix}'
        ledger_part='xl/worksheets/ut-ledger.xml'
        while ledger_part in archive.namelist():ledger_part=ledger_part.replace('.xml','x.xml')
        workbook=workbook.replace('</sheets>','<sheet name='+quoteattr(ledger_name)+' sheetId="'+str(max(int(s.get('sheetId')) for s in sheets)+1)+'" xmlns:r="'+DOCREL+'" r:id="'+newid+'"/></sheets>')
        rels=rels.replace('</Relationships>','<Relationship Id="'+newid+'" Type="'+DOCREL+'/worksheet" Target="'+ledger_part[3:]+'"/></Relationships>')
        rels=re.sub(r'<Relationship\b[^>]*Type="[^"]*/calcChain"[^>]*/>','',rels)
        types=re.sub(r'<Override\b[^>]*PartName="/xl/calcChain.xml"[^>]*/>','',archive.read('[Content_Types].xml').decode()).replace('</Types>','<Override PartName="/'+ledger_part+'" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        original_sheet=archive.read(part).decode()
        for cell in re.finditer(r'<c\b[^>]*(?:/>|>.*?</c>)',original_sheet,re.S):
            if re.search(r'<f[ >]',cell[0]):
                ref=re.search(r'\br="([A-Z]+\d+)"',cell[0])[1]
                values.setdefault(ref,None)
        values['E1' if family=='separator' else 'I1']='DRAFT: '+result['asset']+'; generated '+sheet+'. Per-location code editions and review items are in UT Calculation Ledger.'
        replacements={'xl/workbook.xml':workbook,'xl/_rels/workbook.xml.rels':rels,'[Content_Types].xml':types,part:_patch(archive.read(part).decode(),values)}
        for info in archive.infolist():
            if info.filename!='xl/calcChain.xml':target.writestr(info,replacements.get(info.filename,archive.read(info.filename)))
        target.writestr(ledger_part,ledger)
    return out.getvalue(),source.stored_path.suffix
