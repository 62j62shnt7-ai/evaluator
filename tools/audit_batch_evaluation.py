"""Read-only inventory of candidate engineering profiles vs actual UT observations.

Labels are normalized solely to find review candidates. A candidate is NOT a
confirmed physical mapping or an engineering applicability decision.
"""
from collections import Counter,defaultdict
from datetime import date,datetime
from hashlib import sha256
from pathlib import Path
import json,re
from openpyxl import load_workbook
from evaluator.importing.cells import merged_value,is_measurement
from evaluator.importing.separator import extract as extract_separator
from evaluator.importing.tlb import extract as extract_tlb

ROOT=Path(__file__).resolve().parents[1]

def scalar(v):
    if isinstance(v,(date,datetime)):return v.isoformat()
    return v

def token(v):
    return re.sub(r'[^A-Z0-9]','',str(v or '').upper())

def sep_component(v):
    value=token(v)
    value=re.sub(r'^CAP','HEAD',value)
    value=re.sub(r'CML$','',value)
    return value

def point_key(section,joint,band,separator=False):
    return (token(section),sep_component(joint) if separator else token(joint),re.sub(r'^CML','',token(band)) if separator else token(band))

def profile_rows(wb,filename,sheet_name,kind):
    ws=wb[sheet_name];rows=[];section=''
    if kind=='separator':
        specs=[('CMLS',5,23,{'component':'A','point':'B','material':'C','pressure_psi':'D','temperature_F':'E','stress_psi':'F','joint_efficiency':'G','outside_diameter_in':'H','inside_diameter_in':'I','nominal_thickness_mm':'J','current_mm':'M','required_thickness_mm':'N','adopted_rate_mm_year':'R','remaining_life_years':'T','interval_years':'U','mawp_psi':'W'}),
               ('NOZZLES',27,45,{'component':'A','point':'B','material':'C','pressure_psi':'D','temperature_F':'E','stress_psi':'F','joint_efficiency':'G','outside_diameter_in':'H','inside_diameter_in':'I','nominal_thickness_mm':'J','current_mm':'M','required_thickness_mm':'S','adopted_rate_mm_year':'V','remaining_life_years':'X','interval_years':'Y','mawp_psi':'AA'})]
        for section,start,end,fields in specs:
            for r in range(start,end+1):
                joint=merged_value(ws,r,1);band=merged_value(ws,r,2)
                if not joint or not band:continue
                values={name:dict(cell=col+str(r),value=scalar(ws[col+str(r)].value)) for name,col in fields.items()}
                rows.append(dict(sheet=sheet_name,row=r,key=point_key(section,joint,band,True),component=scalar(joint),point=scalar(band),fields=values))
    else:
        fields={'material':'C','pressure_psi':'D','outside_diameter_in':'E','strength_psi':'F','nominal_thickness_mm':'G','pressure_thickness_mm':'I',
                'current_mm':'N' if sheet_name=='Evaluation 6-2025' else 'O','adopted_rate_mm_year':'S' if sheet_name=='Evaluation 6-2025' else 'T',
                'remaining_life_years':'T' if sheet_name=='Evaluation 6-2025' else 'U','interval_years':'U' if sheet_name=='Evaluation 6-2025' else 'V','mawp_psi':'W' if sheet_name=='Evaluation 6-2025' else 'X'}
        for r in range(6,ws.max_row+1):
            a=ws.cell(r,1).value
            m=re.match(r'SECTION\s+(\d+)',str(a or ''),re.I)
            if m:section='SECTION '+m[1];continue
            if not is_measurement(ws['D'+str(r)]) or not ws['C'+str(r)].value:continue
            joint=merged_value(ws,r,1);band=merged_value(ws,r,2)
            if joint is None or band is None or not section:continue
            values={name:dict(cell=col+str(r),value=scalar(ws[col+str(r)].value)) for name,col in fields.items()}
            rows.append(dict(sheet=sheet_name,row=r,key=point_key(section,joint,band),component=scalar(joint),point=scalar(band),fields=values))
    return rows


def run():
    evidence={'purpose':'Batch implementation gap audit. Every label match is a review candidate, not confirmed continuity/applicability.','files':[]}
    specs=[('Separator-204 Inspection Report.xlsx','separator','UT 10-2026',['Evaluation 2026']),('Separator-204 Inspection Report.xlsm','separator','UT 10-2026',['Evaluation 2026']),('TL-B from SAG Gas MFD to GP.xlsx','pipeline','UT 5-2025',['Evaluation 6-2025','Evalation 4-2026'])]
    for filename,kind,inspection,sheets in specs:
        path=ROOT/'sources/workbooks'/filename;digest=sha256(path.read_bytes()).hexdigest()
        formula=load_workbook(path,data_only=False,keep_links=False);cached=load_workbook(path,data_only=True,keep_links=False)
        try:
            extracted=(extract_separator if kind=='separator' else extract_tlb)(path,inspection)
            observations=[o for o in extracted.observations if o.campaign_label==('current' if kind=='separator' else '05-2025')]
            by_reading=defaultdict(list)
            for o in observations:by_reading[point_key(o.location_candidates[0],o.location_candidates[1],o.location_candidates[2],kind=='separator')].append(o)
            file=dict(file=filename,sha256=digest,inspection=inspection,current_observations=len(observations),profiles=[],notes=[])
            for sheet_name in sheets:
                current_inspection=inspection
                if kind=='pipeline' and sheet_name=='Evalation 4-2026':
                    current_inspection='UT 4- 2026'
                    observations=[o for o in extract_tlb(path,current_inspection).observations if o.campaign_label=='4-2026']
                    by_reading=defaultdict(list)
                    for o in observations:by_reading[point_key(*o.location_candidates[:3])].append(o)
                rows=profile_rows(formula,filename,sheet_name,kind);by_profile=defaultdict(list)
                for row in rows:
                    by_profile[row['key']].append(row)
                    for field in row['fields'].values():field['cached']=scalar(cached[sheet_name][field['cell']].value)
                count=Counter();examples=[];mapping_issues=[]
                for key,rr in by_reading.items():
                    pp=by_profile.get(key,[])
                    if not pp:
                        count['no_profile_candidate']+=len(rr)
                        mapping_issues.append(dict(issue='NO_PROFILE_CANDIDATE',key=key,reading_cells=[r.source.cell for r in rr],profile_rows=[]))
                        continue
                    if len(rr)!=1 or len(pp)!=1:
                        count['ambiguous_reading_or_profile']+=len(rr)
                        mapping_issues.append(dict(issue='AMBIGUOUS',key=key,reading_cells=[r.source.cell for r in rr],profile_rows=[r['row'] for r in pp]))
                        continue
                    count['unique_label_candidates']+=1
                    current=pp[0]['fields']['current_mm'];raw=rr[0].raw_value
                    if isinstance(current['value'],str) and current['value'].startswith('='):count['profile_current_is_calculated']+=1
                    if current['cached'] is not None:
                        try:equal=float(raw)==float(current['cached'])
                        except (ValueError,TypeError):equal=False
                        count['same_current_value' if equal else 'different_current_value']+=1
                        if not equal and len(examples)<5: examples.append(dict(key=key,reading_cell=rr[0].source.cell,reading_value=raw,profile_cell=current['cell'],profile_value=current['value'],profile_cached=current['cached']))
                    else:count['profile_current_cache_missing']+=1
                field_counts={name:dict(literal=sum(r['fields'][name]['value'] not in ('',None) and not str(r['fields'][name]['value']).startswith('=') for r in rows),formula=sum(str(r['fields'][name]['value']).startswith('=') for r in rows),cached_numeric=sum(isinstance(r['fields'][name]['cached'],(int,float)) for r in rows)) for name in rows[0]['fields']} if rows else {}
                dates=[dict(cell=c.coordinate,value=scalar(c.value)) for row in formula[sheet_name].iter_rows() for c in row if isinstance(c.value,(date,datetime))]
                file['profiles'].append(dict(sheet=sheet_name,inspection_sheet=current_inspection,current_observations=sum(len(v) for v in by_reading.values()),profile_rows=len(rows),label_candidate_counts=dict(count),field_counts=field_counts,dates=dates,band_labels=dict(Counter(str(r['point']) for r in rows)),mapping_issues=mapping_issues,conflict_examples=examples,example_rows=rows[:2]))
            if kind=='separator':
                file['notes']=['CAP/HEAD and punctuation normalization are proposed aliases only.','Nozzle duplicate S labels remain ambiguous.','Current October report has 2026-01-20/2026-10-20 candidates; evaluation sheet date is 2026-10-22.','Older January CML numbering differs from October; do not apply October profiles automatically.']
            else:
                file['notes']=['Evaluation 6-2025 uses B31.8-2020 caption; supplied code reference is 2025.','F column is strength in this B31.8 context, not automatically a VIII/B31.3 allowable stress.','B31.8 tPd cells are pressure-thickness candidates, not a proven governing required thickness including structural minima/other loads.', 'April-2026 O current column is formula-derived, not measured UT.','UT May sheet has 2026-03-31 report header / May-2025 campaign conflict; June evaluation supplies another candidate event date.']
            evidence['files'].append(file)
            print(filename,[(p['sheet'],p['profile_rows'],p['label_candidate_counts']) for p in file['profiles']],flush=True)
        finally:formula.close();cached.close()
        assert sha256(path.read_bytes()).hexdigest()==digest
    dest=ROOT/'evidence/batch_evaluation/workbook_readiness.json';dest.write_text(json.dumps(evidence,indent=2,ensure_ascii=False)+'\n')
    return evidence

if __name__=='__main__':run()
