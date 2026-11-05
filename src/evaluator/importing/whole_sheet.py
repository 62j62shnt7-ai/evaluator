"""Lossless-source-backed worksheet evidence; no workbook is ever resaved.

JSON is an index for review, not a replacement for the canonical ZIP package.
Raw XML and relationships preserve unsupported content without claiming to
interpret image readings, drawing semantics, styles or formula calculations.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import posixpath
import re
from zipfile import ZipFile
import xml.etree.ElementTree as ET

M='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS={'m':M}


def _rels_part(part):
    return posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels')


def _target(part, target):
    return posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(posixpath.dirname(part),target))


def snapshot(path: Path, sheet_name: str) -> dict:
    """Index every serialized cell and transitive sheet package relationship."""
    path=Path(path)
    with ZipFile(path) as z:
        names=set(z.namelist())
        workbook=ET.fromstring(z.read('xl/workbook.xml'))
        relationships=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        rels={e.get('Id'):e.get('Target') for e in relationships}
        sheet=next((s for s in workbook.findall('m:sheets/m:sheet',NS) if s.get('name')==sheet_name),None)
        if sheet is None: raise KeyError(f'unknown exact sheet name: {sheet_name!r}')
        part=_target('xl/workbook.xml',rels[sheet.get('{'+R+'}id')])
        raw=z.read(part); root=ET.fromstring(raw)
        strings=[]
        if 'xl/sharedStrings.xml' in names:
            strings=[''.join(t.text or '' for t in n.iter('{'+M+'}t')) for n in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        cells={}
        serialized_cells=[]
        row_number=0
        for row in root.findall('m:sheetData/m:row',NS):
            row_number=int(row.get('r',row_number+1))
            column=0
            for c in row.findall('m:c',NS):
                address=c.get('r')
                if address:
                    letters=re.match(r'[A-Za-z]+',address).group().upper()
                    column=0
                    for letter in letters: column=column*26+ord(letter)-64
                else:
                    column+=1; number=column; letters=''
                    while number:
                        number,remainder=divmod(number-1,26); letters=chr(65+remainder)+letters
                    address=f'{letters}{row_number}'
                serialized_cells.append((address,c))
        for address,c in serialized_cells:
            v=c.find('m:v',NS); f=c.find('m:f',NS); inline=c.find('m:is',NS)
            cached=v.text if v is not None else None
            value=cached
            if c.get('t')=='s' and cached is not None: value=strings[int(cached)]
            elif inline is not None: value=''.join(t.text or '' for t in inline.iter('{'+M+'}t'))
            cells[address]={'value':value,'type':c.get('t','n'),'style':c.get('s'),
                'formula':f.text or '' if f is not None else None,'formula_attributes':dict(f.attrib) if f is not None else {},
                'cached_value':cached,'xml':ET.tostring(c,encoding='unicode')}
        dependencies=[]; related=[]; visited=set(); pending=[part]
        while pending:
            current=pending.pop()
            if current in visited: continue
            visited.add(current)
            relpart=_rels_part(current)
            if relpart not in names: continue
            related.append({'part':relpart,'kind':'relationships','xml':z.read(relpart).decode('utf-8')})
            for rel in ET.fromstring(z.read(relpart)):
                external=rel.get('TargetMode')=='External'
                target=rel.get('Target','') if external else _target(current,rel.get('Target',''))
                dependencies.append({'from_part':current,'id':rel.get('Id'),'type':rel.get('Type'),'target':target,'external':external,'present':not external and target in names})
                if external or target not in names or target in visited: continue
                data=z.read(target)
                info={'part':target,'kind':rel.get('Type','').rsplit('/',1)[-1],'size_bytes':len(data),'sha256':sha256(data).hexdigest()}
                if target.endswith(('.xml','.vml')):
                    info['xml']=data.decode('utf-8')
                    obj=ET.fromstring(data)
                    info['texts']=[n.text for n in obj.iter() if n.tag.rsplit('}',1)[-1] in {'t','text'} and n.text]
                    info['anchors']=[ET.tostring(n,encoding='unicode') for n in obj.iter() if n.tag.rsplit('}',1)[-1] in {'twoCellAnchor','oneCellAnchor','absoluteAnchor','Anchor'}]
                related.append(info); pending.append(target)
        headers=[]
        for address,cell in cells.items():
            text=str(cell['value'] or '').strip().upper()
            section_name=None
            if text in {'CMLS','NOZZLES','PIPELINE','PIPING'} or re.fullmatch(r'SECTION\s+\d+.*',text):
                section_name=text
            elif re.fullmatch(r'.*\(CMLS?\)',text):
                section_name='CMLS'
            elif re.fullmatch(r'.*\(NOZZLES?\)',text):
                section_name='NOZZLES'
            if section_name:
                headers.append((int(re.search(r'\d+',address).group()),section_name))
        # Some older reports label a section only through JOINT/CML/LOCATION
        # column headings, without a standalone CMLS caption.
        for address,cell in cells.items():
            if not re.fullmatch(r'A\d+',address) or str(cell['value'] or '').strip().upper()!='JOINT': continue
            row=int(re.search(r'\d+',address).group())
            b=str(cells.get('B'+str(row),{}).get('value') or '').strip().upper()
            c=str(cells.get('C'+str(row),{}).get('value') or '').strip().upper()
            if 'CML' in b: headers.append((row,'CMLS'))
            elif b=='BAND' and c=='SIZE': headers.append((row,'NOZZLES'))
        ordered=[]
        for header in sorted(set(headers)):
            if not ordered or ordered[-1][1]!=header[1]: ordered.append(header)
        headers=ordered
        sections=[]
        for i,(start,name) in enumerate(headers):
            end=headers[i+1][0]-1 if i+1<len(headers) else max((int(re.search(r'\d+',a).group()) for a in cells),default=start)
            sections.append({'name':name,'start_row':start,'end_row':end,'cells':[a for a in cells if start<=int(re.search(r'\d+',a).group())<=end]})
        dimension=root.find('m:dimension',NS)
        return {'schema_version':2,'source_sha256':sha256(path.read_bytes()).hexdigest(),'sheet_name':sheet_name,
            'worksheet_part':part,'worksheet_xml':raw.decode('utf-8'),'dimensions':dimension.get('ref','') if dimension is not None else '',
            'merged_regions':[m.get('ref') for m in root.findall('m:mergeCells/m:mergeCell',NS)],
            'rows':[dict(r.attrib) for r in root.findall('m:sheetData/m:row',NS)],
            'columns':[dict(c.attrib) for c in root.findall('m:cols/m:col',NS)],'cells':cells,'sections':sections,
            'dependencies':dependencies,'related_parts':related,
            'shared_parts':[n for n in ('xl/styles.xml','xl/sharedStrings.xml','xl/workbook.xml','xl/_rels/workbook.xml.rels','[Content_Types].xml') if n in names],
            'fidelity':'Canonical source package is preserved unchanged; JSON indexes serialized evidence. Drawing/image readings are not OCR-normalized.'}
