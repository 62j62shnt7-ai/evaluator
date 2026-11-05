"""Repeat the new workflow against all supplied originals in an isolated project."""
from collections import Counter
from decimal import Decimal
from datetime import date
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
from zipfile import ZipFile
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from evaluator.app_services import ProjectService
from evaluator.workspace import Workspace
from evaluator.form_export import export_form
from evaluator.engineering.references import dimensions,material_stresses


def run(destination):
    destination=Path(destination).resolve()
    if (destination/'project.sqlite').exists():raise ValueError('Choose a fresh validation folder')
    service=ProjectService(destination);workspace=Workspace(service);checks=[]
    originals={str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in (ROOT/'sources').rglob('*') if p.is_file() and p.suffix.lower() in {'.pdf','.xlsx','.xlsm'}}
    for path in sorted((ROOT/'sources/workbooks').glob('*.xls*')):
        source=service.add_source(path);service.inspect(source.sha256)
        opened=workspace.auto_open(source.sha256,service.workflow.revision());cid=opened['comparison_id']
        assert cid,opened
        state=workspace.state(cid)['workspace'];ids=[r['current_id'] for r in state['rows'] if r['current_id']]
        assert ids
        workspace.apply(cid,service.workflow.revision(),ids,{'reviewed':'yes'},sheet=state['profile_sheet'])
        result=workspace.evaluate(cid,service.workflow.revision(),state['profile_sheet'])
        counts=Counter()
        readings={r['observation_id']:r for r in service.readings()}
        for row in result['rows']:
            if row['apparent_rate_mm_year'] is not None:
                year_days=Decimal(str(row['input_trace']['year_days']))
                old=readings[row['previous_id']]['inspection_date'];new=readings[row['current_id']]['inspection_date']
                loss=Decimal(row['previous_thickness_mm'])-Decimal(row['current_thickness_mm'])
                if len(old)==7 or len(new)==7:
                    months=(int(new[:4])-int(old[:4]))*12+int(new[5:7])-int(old[5:7])
                    expected=loss*12/Decimal(months)
                else:expected=loss*year_days/Decimal((date.fromisoformat(new)-date.fromisoformat(old)).days)
                assert abs(Decimal(row['apparent_rate_mm_year'])-expected)<Decimal('1e-20');counts['rates']+=1
                if expected<0:assert row['remaining_life_years'] is None;counts['increases_withheld']+=1
            if row['remaining_life_years'] is not None:
                minimum=Decimal(row['required_thickness_mm'] or row['pressure_thickness_mm'])
                rate=Decimal(row['adopted_rate_mm_year']);assert rate>0
                expected=(Decimal(row['current_thickness_mm'])-minimum)/rate
                assert abs(Decimal(row['remaining_life_years'])-expected)<Decimal('1e-20');counts['life']+=1
            if row['profile'] and row['profile']['geometry'] in {'elbow','tee','reducer','nozzle'}:assert row['mawp_MPa'] is None;counts['unsupported_geometry_pressure_withheld']+=1
        raw,suffix=export_form(service,result)
        output=destination/(path.stem+'-completed'+suffix);output.write_bytes(raw)
        book=load_workbook(BytesIO(raw),data_only=True,keep_vba=suffix=='.xlsm');assert 'UT Calculation Ledger' in book.sheetnames;book.close()
        unchanged=0
        with ZipFile(source.stored_path) as before,ZipFile(BytesIO(raw)) as after:
            for name in before.namelist():
                if name.startswith(('xl/media/','xl/drawings/')) or name in {'xl/styles.xml','xl/vbaProject.bin'}:
                    assert before.read(name)==after.read(name);unchanged+=1
            assert 'xl/calcChain.xml' not in after.namelist()
        report=service.workflow.export_revision(cid)
        with ZipFile(report) as archive:
            manifest=json.loads(archive.read('manifest.json'))
            for name,digest in manifest['files'].items():assert sha256(archive.read(name)).hexdigest()==digest
        checks.append(dict(workbook=path.name,comparison=cid,source_sheet=state['comparison']['current_selection'][1],campaigns=[state['comparison']['baseline'][2],state['comparison']['current_selection'][2]],current_locations=len(ids),geometries=dict(Counter(r['profile']['geometry'] if r['profile'] else 'unmapped' for r in result['rows'])),arithmetic_checks=dict(counts),original_media_style_vba_parts_preserved=unchanged,form=str(output),form_sha256=sha256(raw).hexdigest(),summary=result['summary']))
        print(path.name,len(ids),'locations;',dict(counts),flush=True)
    for relative,digest in originals.items():assert sha256((ROOT/relative).read_bytes()).hexdigest()==digest
    evidence=dict(status='SOFTWARE ACCEPTANCE PASSED; engineering applicability remains draft',originals_unchanged=originals,dimensions=dict(entries=len(dimensions()),source_discrepancies_withheld=[r for r in dimensions() if r['issues']]),material_stress_entries=len(material_stresses()),workbooks=checks)
    (destination/'verification.json').write_text(json.dumps(evidence,indent=2))
    return evidence

if __name__=='__main__':run(sys.argv[1])
