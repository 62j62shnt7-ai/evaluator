"""Compare measured UT evaluation with cached reference results; preserve source workbook."""
import csv
import json
import math
import re
import sys
from urllib.request import Request, urlopen
from types import SimpleNamespace
from collections import Counter, defaultdict
from pathlib import Path
from openpyxl import load_workbook
from evaluator.app_services import ProjectService
from evaluator.workspace import Workspace
from evaluator.importing.cells import merged_value

SOURCE=Path('/Users/don/Documents/evaluation sample.xlsx')
OUT=Path(__file__).resolve().parents[1]/'outputs/sample-comparison'
PROJECT=Path('/tmp/ut-row7-all-readings-test')

def token(value):
    return re.sub(r'[^A-Z0-9]', '', str(value or '').upper()).removeprefix('TEE')

def close(a,b):
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):
        return math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-8)
    return a==b

book=load_workbook(SOURCE,data_only=True);formula=load_workbook(SOURCE,data_only=False)
eval=book['Evaluation 11-2026'];ut=book['UT 11-2026']
LIVE='--live' in sys.argv
BASE='http://127.0.0.1:8765'
def live_state():
    return json.load(urlopen(BASE+'/api/workspace'))
def api(name,payload):
    state=live_state()
    data=dict(revision=state['revision'],comparison_id=state['workspace']['comparison']['id'],**payload)
    return json.load(urlopen(Request(BASE+'/api/workspace/'+name,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})))
if LIVE:
    state=live_state();cid=state['workspace']['comparison']['id'];PROJECT=Path.home()/'UT Inspection Evaluator'
    source=SimpleNamespace(sha256=state['sources'][0]['source_id'])
    for row in state['workspace']['rows']:
        if row['current_cell'] in {'F139','F140','E287','E288'} and not row['previous_id']:
            api('pair',{'id':row['current_id']})
    rows=live_state()['workspace']['rows']
else:
    s=ProjectService(PROJECT);source=s.add_source(SOURCE);s.inspect(source.sha256);w=Workspace(s)
    from evaluator.quick_workflow import import_single_dated_sheet
    import_single_dated_sheet(s,source.sha256,ut.title,s.workflow.revision())
    for campaign,cell in [('MIN 8-2023','K4'),('MIN 11-2024','L4'),('MIN 11-2026','M4')]:
        s.resolve_campaign_date(source.sha256,ut.title,campaign,eval[cell].value.date().isoformat(),'Sample comparison','Exact dates from Evaluation 11-2026!'+cell,_expected_revision=s.workflow.revision())
    opened=w.auto_open(source.sha256,s.workflow.revision());cid=opened['comparison_id'];w.policy(cid,s.workflow.revision(),'row7')
    comp=s.workflow.comparison(cid)
    previous=s.workflow._selection(*comp['baseline'])
    current=s.workflow._selection(*comp['current_selection'])
    for new in current:
        source_row=int(re.search(r'\d+',new['cell'])[0])
        if source_row not in {139,140,287,288}:continue
        candidates=[old for old in previous if int(re.search(r'\d+',old['cell'])[0])==source_row]
        if len(candidates)==1:
            s.workflow.pair(cid,candidates[0]['observation_id'],new['observation_id'],True,'Sample comparison',
                'Same physical source row and branch NPS in UT 11-2026 row '+str(source_row),s.workflow.revision())
    rows=w.state(cid)['workspace']['rows']
by_key=defaultdict(list)
for row in rows:
    if not row['current_id']:continue
    source_row=int(re.search(r'\d+',row['current_cell'])[0])
    key=(token(merged_value(ut,source_row,1)),token(merged_value(ut,source_row,2)))
    by_key[key].append(row)
records=[];groups=defaultdict(list);mapped_ids=set()
for n in range(5,107):
    key=(token(merged_value(eval,n,1)),token(merged_value(eval,n,2)))
    candidates=by_key.get(key,[])
    # Reducers and tee branches share labels; source NPS distinguishes their dimensions.
    if len(candidates)>1:
        od=float(eval.cell(n,5).value)
        from evaluator.engineering.references import dimensions
        nps={d['nps'] for d in dimensions() if abs(float(d['od_in'])-od)<.001}
        candidates=[r for r in candidates if token(merged_value(ut,int(re.search(r'\d+',r['current_cell'])[0]),3)) in {token(x) for x in nps}]
    record=dict(evaluation_row=n,joint=str(merged_value(eval,n,1)),band=str(merged_value(eval,n,2)),status='',notes=[],current_id=None)
    if formula[eval.title].cell(n,13).data_type=='f':record['notes'].append('Evaluation current thickness is a formula projection')
    if len(candidates)!=1:
        record['status']='No measured current UT match' if not candidates else 'Ambiguous UT match'
    else:
        r=candidates[0];record['current_id']=r['current_id'];mapped_ids.add(r['current_id']);record['ut_cell']=r['current_cell']
        vals=dict(material=eval.cell(n,3).value,P_psi=str(eval.cell(n,4).value),D_outside_in=str(eval.cell(n,5).value),nominal_thickness_mm=str(eval.cell(n,7).value),structural_minimum_mm=str(eval.cell(n,8).value),adopted_rate_mm_year=str(eval.cell(n,15).value))
        from evaluator.engineering.references import dimensions
        dimension_matches=[d for d in dimensions() if d['family']=='ferritic' and not d['issues'] and abs(float(d['od_in'])-float(vals['D_outside_in']))<.001 and abs(float(d['nominal_mm'])-float(vals['nominal_thickness_mm']))<.001]
        vals.update(nps=dimension_matches[0]['nps'] if dimension_matches else 'Custom',schedule=dimension_matches[0]['schedule'] if dimension_matches else 'Custom')
        groups[json.dumps(vals,sort_keys=True)].append(r['current_id'])
        previous=eval.cell(n,11).value if eval.cell(n,11).value is not None else eval.cell(n,12).value
        if r['current_thickness_mm'] is not None and not close(float(r['current_thickness_mm']),eval.cell(n,13).value):record['notes'].append('Measured current UT differs from evaluation current thickness')
        if r['previous_thickness_mm'] is not None and not close(float(r['previous_thickness_mm']),previous):record['notes'].append('Measured previous UT differs from evaluation previous thickness')
    records.append(record)
for signature,ids in groups.items():
    if LIVE:api('apply',{'ids':ids,'values':json.loads(signature)})
    else:w.apply(cid,s.workflow.revision(),ids,json.loads(signature))
saved=api('evaluate',{}) if LIVE else w.evaluate(cid,s.workflow.revision());actual={r['current_id']:r for r in saved['rows'] if r['current_id']}
fields={'s_psi':'F','pressure_mm':'I','required_mm':'J','calculated_cr':'N','remaining_life':'P','interval':'Q','mawp_thickness_mm':'R','mawp_psi':'S','result':'T','next_inspection':'V'}
details=[]
for record in records:
    r=actual.get(record['current_id']);result=(r or {}).get('row7')
    if not result:
        if not record['status']:record['status']='Withheld: missing or ambiguous history';record['notes']+=(r or {}).get('issues',[])
        continue
    differences=[]
    for field,col in fields.items():
        expected=eval[f'{col}{record["evaluation_row"]}'].value;value=result[field]
        if field=='next_inspection':expected=expected.date().isoformat() if hasattr(expected,'date') else expected
        if field=='result':expected='Safe' if expected=='Safe' else 'Not safe'
        match=close(value,expected)
        details.append(dict(evaluation_row=record['evaluation_row'],ut_cell=record['ut_cell'],field=field,app=value,workbook=expected,match=match))
        if not match:differences.append(field)
    record['status']='Match' if not differences and not record['notes'] else 'Difference'
    record['differences']=differences;record['app']=result
    if 'result' in differences:record['notes'].append('MAWP at Pd boundary; workbook status may reflect cached floating-point comparison')
counts=Counter(r['status'] for r in records)
summary=dict(source=str(SOURCE),comparison_id=cid,project=str(PROJECT),evaluation_rows=len(records),current_ut_readings=len(actual),mapped_current_readings=len(mapped_ids),calculated_current_readings=sum(bool(r.get('row7')) for r in actual.values()),counts=dict(counts),unmapped_current_readings=[dict(location=r['location'],cell=r['current_cell']) for oid,r in actual.items() if oid not in mapped_ids],records=records)
if LIVE:OUT=OUT.parent/'full-flow-comparison'
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'comparison.json').write_text(json.dumps(summary,indent=2,default=str))
for name,data in [('field-comparison',details),('row-summary',[dict(evaluation_row=r['evaluation_row'],joint=r['joint'],band=r['band'],ut_cell=r.get('ut_cell',''),status=r['status'],differences=', '.join(r.get('differences',[])),notes='; '.join(r['notes'])) for r in records])]:
    with (OUT/(name+'.csv')).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
print(json.dumps({k:v for k,v in summary.items() if k!='records'},indent=2))
for r in records:
    if r['status']=='Difference':print(r['evaluation_row'],r['differences'],r['notes'])
