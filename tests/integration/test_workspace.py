"""Real-source acceptance and regression checks for the redesigned workspace."""
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import json

from openpyxl import load_workbook
import pytest

from evaluator.app_services import ProjectService
from evaluator.engineering.references import dimension, dimensions
from evaluator.form_export import export_form
from evaluator.workspace import Workspace
from tests.source_config import SOURCE_ROOT

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture
def project(tmp_path):
    service=ProjectService(tmp_path)
    source=service.add_source(SOURCE_ROOT/'workbooks/TL-B from SAG Gas MFD to GP.xlsx')
    service.inspect(source.sha256)
    workspace=Workspace(service)
    opened=workspace.open_sheet(source.sha256,'UT 5-2025',service.workflow.revision(), '01-2021','05-2025')
    return service,workspace,opened['comparison_id'],source


def test_reference_dimensions_and_source_discrepancies():
    data=dimensions()
    assert len(data)==229
    assert len({(d['family'],d['nps'],d['schedule']) for d in data})==229
    assert dimension('ferritic','6','40')['nominal_mm']=='7.11'
    assert dimension('ferritic','6','80')['nominal_mm']=='10.97'
    assert dimension('ferritic','8','80')['od_in']=='8.625'
    assert dimension('ferritic','8','80')['nominal_mm']=='12.70'
    assert dimension('stainless','10','80S')['nominal_mm']=='12.70'
    assert dimension('ferritic','10','80')['nominal_mm']=='15.09'
    assert len([d for d in data if d['issues']])==2
    with pytest.raises(ValueError,match='source discrepancy'):dimension('stainless','1/8','80S')
    with pytest.raises(ValueError):dimension('ferritic','40','80')
    digest=sha256((SOURCE_ROOT/'codes/RP_574_E5_EN_wA1.pdf').read_bytes()).hexdigest()
    assert all(d['source_sha256']==digest for d in data)


def test_confirmation_is_per_row_and_actual_arithmetic(project):
    s,w,cid,_=project
    state=w.state(cid)['workspace']
    assert state['counts']['locations']==81
    assert state['profile_sheet']=='Evaluation 6-2025'
    target=next(r for r in state['rows'] if r['current_cell']=='K158')
    other=next(r for r in state['rows'] if r['current_id'] and r['id']!=target['id'])
    assert target['apparent_rate_mm_year'] is None
    w.apply(cid,s.workflow.revision(),[target['current_id']],{'reviewed':'yes'})
    rows=w.state(cid)['workspace']['rows']
    updated=next(r for r in rows if r['id']==target['id'])
    expected=Decimal('.2')*12/52
    assert abs(Decimal(updated['apparent_rate_mm_year'])-expected)<Decimal('1e-25')
    assert updated['remaining_life_years'] is not None
    assert next(r for r in rows if r['id']==other['id'])['apparent_rate_mm_year'] is None
    assert updated['profile']['code_edition']=='2020'
    assert 'CODE_EDITION_REFERENCE_UNAVAILABLE' in updated['issues']
    saved=w.evaluate(cid,s.workflow.revision(),state['profile_sheet'])
    assert next(r for r in saved['rows'] if r['id']==other['id'])['remaining_life_years'] is None


def test_batch_dimensions_templates_exceptions_and_undo(project):
    s,w,cid,_=project
    state=w.state(cid)['workspace'];ids=[r['current_id'] for r in state['rows'] if r['current_id']][:2]
    w.apply(cid,s.workflow.revision(),ids,{'segment':'Test segment'},dimension_key=['ferritic','6','40'])
    rows=w.state(cid)['workspace']['rows']
    for row in rows:
        if row['current_id'] in ids:
            assert row['nps']=='6';assert row['schedule']=='40';assert row['nominal_thickness_mm']=='7.11'
            assert 'API RP 574' in row['input_trace']['overrides']['dimension_reference']
            assert row['required_thickness_mm'] is None
        else:assert row['segment']!='Test segment'
    template=w.save_template(s.workflow.revision(),'Pipe configuration',{'material':'ASTM A106 Grade B','P_psi':'1000','reviewed':'yes'})
    assert 'reviewed' not in template['values']
    w.apply(cid,s.workflow.revision(),[ids[0]],{'P_psi':'900'},template_id=template['id'])
    assert s.batch.settings(cid)['row_overrides'][ids[0]]['P_psi']=='900'
    assert 'P_psi' not in s.batch.settings(cid)['row_overrides'][ids[1]]
    with pytest.raises(ValueError,match='changed'):w.apply(cid,0,ids,{'P_psi':'200'})
    s.workflow.undo(s.workflow.revision(),'test','undo batch override')
    assert 'P_psi' not in s.batch.settings(cid)['row_overrides'][ids[0]]
    assert Workspace(ProjectService(s.project_dir)).templates()[0]['name']=='Pipe configuration'


def test_material_context_invalidates_properties_and_negative_rate_is_not_adopted(project):
    s,w,cid,_=project
    rows=w.state(cid)['workspace']['rows'];ids=[r['current_id'] for r in rows if r['current_id']]
    w.apply(cid,s.workflow.revision(),ids,{'reviewed':'yes'})
    rows=w.state(cid)['workspace']['rows']
    increased=[r for r in rows if 'THICKNESS_INCREASE_REVIEW' in r['issues']]
    assert increased
    assert all(r['adopted_rate_mm_year'] is None and r['remaining_life_years'] is None for r in increased)
    target=next(r for r in rows if r['current_cell']=='K158')
    w.apply(cid,s.workflow.revision(),[target['id']],{'material':'Different grade','code_edition':'2025'})
    changed=next(r for r in w.state(cid)['workspace']['rows'] if r['id']==target['id'])
    assert changed['profile']['fields']['SMYS_psi']['value'] is None
    assert changed['required_thickness_mm'] is None
    assert changed['pressure_thickness_mm'] is None
    assert changed['remaining_life_years'] is None


def test_form_preserves_original_package_and_has_no_stale_unmatched_outputs(project):
    s,w,cid,source=project
    st=w.state(cid)['workspace'];ids=[r['current_id'] for r in st['rows'] if r['current_id']]
    w.apply(cid,s.workflow.revision(),ids,{'reviewed':'yes'})
    result=w.evaluate(cid,s.workflow.revision(),st['profile_sheet'])
    raw,suffix=export_form(s,result)
    assert suffix=='.xlsx'
    assert sha256(source.stored_path.read_bytes()).hexdigest()==source.sha256
    with ZipFile(source.stored_path) as old,ZipFile(BytesIO(raw)) as new:
        for name in old.namelist():
            if name.startswith(('xl/media/','xl/drawings/')) or name.endswith('vbaProject.bin'):assert old.read(name)==new.read(name)
        assert old.read('xl/styles.xml')==new.read('xl/styles.xml')
    wb=load_workbook(BytesIO(raw),data_only=True)
    assert 'UT Calculation Ledger' in wb.sheetnames
    form=wb['Evaluation 6-2025']
    assert form['N5'].value=='2025-05'
    assert form['L5'].value=='2021-01'
    grouped={r['profile_id']:r for r in result['rows'] if r['profile_id']}
    for p in result['profiles']:
        row=grouped.get(p['id']);n=p['row']
        assert form[f'T{n}'].value==(float(row['remaining_life_years']) if row and row['remaining_life_years'] is not None else None)
        if not row:assert form[f'N{n}'].value is None
    assert form['A1'].value.startswith('DRAFT')
    wb.close()
    w.apply(cid,s.workflow.revision(),ids[:1],{'required_thickness_mm':'6'})
    with pytest.raises(ValueError,match='stale'):export_form(s,s.batch.results(cid)[0])


def test_exact_material_lookup_and_component_recalculation(project):
    from evaluator.engineering.references import material_stress
    assert material_stress('ASTM A106 Grade B','straight_pipe','ASME B31.3','2024','300')['S_allow_psi']=='20000'
    assert material_stress('A234 WPB','elbow','ASME B31.3','2024','500')['S_allow_psi']=='19000'
    assert material_stress('A106 B','straight_pipe','ASME B31.3','2020','300') is None
    assert material_stress('A106 B','straight_pipe','ASME B31.3','2024','350') is None
    assert material_stress('A106 B','elbow','ASME B31.3','2024','300') is None
    s,w,cid,_=project
    target=next(r for r in w.state(cid)['workspace']['rows'] if r['current_cell']=='K158')
    w.apply(cid,s.workflow.revision(),[target['id']],dict(material='ASTM A106 Grade B',geometry='straight_pipe',code_family='ASME B31.3',code_edition='2024',temperature_F='300',P_psi='1000',D_outside_in='8.625',E_quality='1',W_reduction='1',Y_coefficient='.4',structural_minimum_mm='3',reviewed='yes'))
    w.policy(cid,s.workflow.revision(),'recalculate')
    row=next(r for r in w.state(cid)['workspace']['rows'] if r['id']==target['id'])
    expected=Decimal(1000)*Decimal('8.625')/(2*(Decimal(20000)+1000*Decimal('.4')))*Decimal('25.4')
    assert abs(Decimal(row['required_thickness_mm'])-expected)<Decimal('1e-20')
    assert row['profile']['fields']['S_allow_psi']['value']=='20000'
    assert 'Table A-1C line 33' in row['input_trace']['overrides']['material_reference']
    w.apply(cid,s.workflow.revision(),[target['id']],dict(geometry='tee'))
    row=next(r for r in w.state(cid)['workspace']['rows'] if r['id']==target['id'])
    assert row['required_thickness_mm'] is None
    assert 'GEOMETRY_RULE_UNSUPPORTED' in row['issues']


def test_inline_correction_is_one_undo_and_keeps_configuration(project):
    s,w,cid,_=project
    row=next(r for r in w.state(cid)['workspace']['rows'] if r['current_cell']=='K158')
    w.apply(cid,s.workflow.revision(),[row['id']],{'segment':'Retained segment','reviewed':'yes'})
    rev=s.workflow.revision()
    assert w.correct(cid,rev,row['id'],'6.7')==cid
    assert s.workflow.revision()==rev+1
    corrected=next(r for r in w.state(cid)['workspace']['rows'] if r['id']==row['id'])
    assert corrected['current_thickness_mm']=='6.7'
    assert corrected['segment']=='Retained segment'
    assert not corrected['reviewed']
    raw=next(r for r in s.readings() if r['observation_id']==row['id'])
    assert raw['raw_value']=='6.8'
    s.workflow.undo(s.workflow.revision(),'test','reverse inline edit')
    restored=next(r for r in w.state(cid)['workspace']['rows'] if r['id']==row['id'])
    assert restored['current_thickness_mm']=='6.8'
    assert restored['reviewed']


def test_workspace_http_api_is_revisioned_and_origin_checked(project):
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from evaluator.webapp import make_handler
    s,w,cid,_=project
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(s));thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    client=HTTPConnection('127.0.0.1',server.server_port)
    try:
        client.request('GET','/');response=client.getresponse();page=response.read()
        assert response.status==200 and b'Apply to selected' in page and b'Results & export' in page
        client.request('GET','/api/workspace?comparison='+cid);response=client.getresponse();data=json.loads(response.read())
        assert response.status==200 and data['workspace']['counts']['locations']==81
        oid=next(r['id'] for r in data['workspace']['rows'] if r['current_id'])
        payload=json.dumps(dict(comparison_id=cid,revision=data['revision'],ids=[oid],values={'segment':'HTTP batch'}))
        client.request('POST','/api/workspace/apply',payload,{'Content-Type':'application/json','Origin':'https://untrusted.invalid'});response=client.getresponse();assert response.status==400;response.read()
        client.request('POST','/api/workspace/apply',payload,{'Content-Type':'application/json'});response=client.getresponse();assert response.status==200;response.read()
        client.request('POST','/api/workspace/apply',payload,{'Content-Type':'application/json'});response=client.getresponse();assert response.status==400;assert 'changed' in json.loads(response.read())['error']
    finally:client.close();server.shutdown();server.server_close();thread.join()


def test_scenarios_keep_separate_assignments_and_confirmation(project):
    s,w,cid,_=project
    first=w.state(cid)['workspace'];target=next(r for r in first['rows'] if r['current_cell']=='K158')
    w.apply(cid,s.workflow.revision(),[target['id']],{'segment':'Scenario A','reviewed':'yes'},sheet='Evaluation 6-2025')
    second=w.state(cid,'Evalation 4-2026')['workspace']
    other=next(r for r in second['rows'] if r['id']==target['id'])
    assert other['segment']!='Scenario A' and not other['reviewed']
    w.apply(cid,s.workflow.revision(),[target['id']],{'segment':'Scenario B'},sheet='Evalation 4-2026')
    restored=next(r for r in w.state(cid,'Evaluation 6-2025')['workspace']['rows'] if r['id']==target['id'])
    assert restored['segment']=='Scenario A' and restored['reviewed']
    w.policy(cid,s.workflow.revision(),'provided','Evaluation 6-2025')
    assert s.batch.settings(cid)['profile_sheet']=='Evaluation 6-2025'


def test_campaign_date_correction_and_increasing_rate_override_are_explicit(project):
    s,w,cid,_=project
    rows=w.state(cid)['workspace']['rows'];ids=[r['id'] for r in rows if r['current_id']]
    w.apply(cid,s.workflow.revision(),ids,{'reviewed':'yes'})
    increased=next(r for r in w.state(cid)['workspace']['rows'] if 'THICKNESS_INCREASE_REVIEW' in r['issues'] and r['profile'])
    with pytest.raises(ValueError,match='review basis'):w.apply(cid,s.workflow.revision(),[increased['id']],{'allow_increase':'yes','adopted_rate_mm_year':'.2'})
    w.apply(cid,s.workflow.revision(),[increased['id']],{'allow_increase':'yes','adopted_rate_mm_year':'.2','review_note':'Software test: checked positive adopted rate'})
    adjusted=next(r for r in w.state(cid)['workspace']['rows'] if r['id']==increased['id'])
    assert adjusted['apparent_rate_mm_year'].startswith('-')
    assert adjusted['adopted_rate_mm_year']=='0.2' or adjusted['adopted_rate_mm_year']=='.2'
    revision=s.workflow.revision()
    w.dates(cid,revision,'2021-01-22','2025-05-15')
    assert s.workflow.revision()==revision+1
    assert all(not r['reviewed'] for r in w.state(cid)['workspace']['rows'])
    s.workflow.undo(s.workflow.revision(),'test','restore header month precision')
    assert next(r for r in w.state(cid)['workspace']['rows'] if r['id']==increased['id'])['reviewed']


@pytest.mark.parametrize('filename',['Separator-204 Inspection Report.xlsx','Separator-204 Inspection Report.xlsm'])
def test_separator_auto_import_and_preserved_form(tmp_path,filename):
    s=ProjectService(tmp_path);source=s.add_source(SOURCE_ROOT/'workbooks'/filename);s.inspect(source.sha256);w=Workspace(s)
    opened=w.auto_open(source.sha256,s.workflow.revision());cid=opened['comparison_id']
    state=w.state(cid)['workspace']
    assert state['comparison']['current_selection'][1]=='UT Jan 2026'
    assert state['counts']['locations']==37
    ids=[r['id'] for r in state['rows'] if r['current_id']]
    w.apply(cid,s.workflow.revision(),ids,{'reviewed':'yes'})
    result=w.evaluate(cid,s.workflow.revision(),state['profile_sheet'])
    raw,suffix=export_form(s,result)
    assert suffix==Path(filename).suffix
    with ZipFile(source.stored_path) as original,ZipFile(BytesIO(raw)) as completed:
        assert 'xl/calcChain.xml' not in completed.namelist()
        assert original.read('xl/styles.xml')==completed.read('xl/styles.xml')
        for name in original.namelist():
            if name.startswith(('xl/drawings/','xl/media/')) or name.endswith('vbaProject.bin'):assert original.read(name)==completed.read(name)
    book=load_workbook(BytesIO(raw),data_only=True,keep_vba=suffix=='.xlsm')
    assert book['Evaluation 2026']['A49'].value.startswith('DRAFT:')
    assert 'UT Calculation Ledger' in book.sheetnames
    book.close()


def test_automatic_history_uses_latest_available_prior_measurement_per_location(project):
    s,w,_,source=project
    opened=w.open_sheet(source.sha256,'UT 5-2025',s.workflow.revision())
    state=w.state(opened['comparison_id'])['workspace'];comp=state['comparison']
    assert comp.get('baseline_per_location')
    assert comp['baseline'][2].startswith('auto:')
    actual={r['observation_id']:r for r in s.readings()}
    dates=set()
    for pair in comp['rows']:
        if pair['kind']!='lifecycle_mismatch':continue
        previous,current=pair['previous'],pair['current']
        earlier=[r for r in actual.values() if r['source_id']==source.sha256 and r['sheet_name']=='UT 5-2025' and s.workflow._key(r)==s.workflow._key(current) and r['inspection_date'] and r['inspection_date']<current['inspection_date']]
        assert previous['inspection_date']==max(r['inspection_date'] for r in earlier)
        dates.add(previous['inspection_date'])
    assert len(dates)>=2
    assert len(s.workflow._selection(*comp['baseline']))==56
    with pytest.raises(ValueError,match='vary'):w.dates(comp['id'],s.workflow.revision(),previous='2021-01-22')


def test_uploaded_workbook_family_is_detected_from_structure_not_staging_name(tmp_path):
    import shutil
    incoming=tmp_path/'upload-random.xlsx'
    shutil.copyfile(SOURCE_ROOT/'workbooks/Separator-204 Inspection Report.xlsx',incoming)
    s=ProjectService(tmp_path/'project');source=s.add_source(incoming,'inspection.xlsx');s.inspect(source.sha256)
    opened=Workspace(s).auto_open(source.sha256,s.workflow.revision())
    assert opened['comparison_id']
    assert Workspace(s).state(opened['comparison_id'])['workspace']['counts']['locations']==37


def test_later_context_edit_cannot_reuse_a_previously_looked_up_stress(project):
    s,w,cid,_=project
    target=next(r for r in w.state(cid)['workspace']['rows'] if r['current_cell']=='K158')
    config=dict(material='ASTM A106 Grade B',geometry='straight_pipe',code_family='ASME B31.3',code_edition='2024',temperature_F='300',P_psi='1000',D_outside_in='8.625',E_quality='1',W_reduction='1',Y_coefficient='.4',structural_minimum_mm='3',reviewed='yes')
    w.apply(cid,s.workflow.revision(),[target['id']],config)
    w.policy(cid,s.workflow.revision(),'recalculate')
    assert next(r for r in w.state(cid)['workspace']['rows'] if r['id']==target['id'])['required_thickness_mm'] is not None
    w.apply(cid,s.workflow.revision(),[target['id']],{'temperature_F':'900'})
    updated=next(r for r in w.state(cid)['workspace']['rows'] if r['id']==target['id'])
    assert updated['profile']['fields']['S_allow_psi']['value'] is None
    assert updated['required_thickness_mm'] is None
    assert updated['remaining_life_years'] is None
    assert not updated['input_trace']['overrides'].get('material_reference')


def test_export_clears_invalidated_property_instead_of_retaining_source_value(project):
    s,w,cid,_=project
    target=next(r for r in w.state(cid)['workspace']['rows'] if r['current_cell']=='K158')
    w.apply(cid,s.workflow.revision(),[target['id']],{'material':'Different grade','code_edition':'2025','reviewed':'yes'})
    result=w.evaluate(cid,s.workflow.revision(),'Evaluation 6-2025')
    row=next(r for r in result['rows'] if r['id']==target['id']);assert row['profile']['fields']['SMYS_psi']['value'] is None
    raw,_=export_form(s,result);book=load_workbook(BytesIO(raw),data_only=True)
    assert book['Evaluation 6-2025']['C15'].value=='Different grade'
    assert book['Evaluation 6-2025']['F15'].value is None
    book.close()


def test_export_updates_schedule_with_its_looked_up_dimensions(project):
    s,w,cid,_=project
    target=next(r for r in w.state(cid)['workspace']['rows'] if r['current_cell']=='K158')
    w.apply(cid,s.workflow.revision(),[target['id']],{'reviewed':'yes'},dimension_key=['ferritic','6','40'])
    raw,_=export_form(s,w.evaluate(cid,s.workflow.revision(),'Evaluation 6-2025'))
    book=load_workbook(BytesIO(raw),data_only=True);form=book['Evaluation 6-2025']
    assert form['E15'].value==6.625
    assert form['G15'].value==7.11
    assert str(form['H15'].value)=='40'
    book.close()


def test_explicit_rule_must_match_the_declared_code_family(project):
    s,w,cid,_=project
    target=next(r for r in w.state(cid)['workspace']['rows'] if r['current_cell']=='K158')
    w.apply(cid,s.workflow.revision(),[target['id']],dict(material='ASTM A106 Grade B',geometry='straight_pipe',code_family='ASME B31.3',code_edition='2024',temperature_F='300',P_psi='1000',D_outside_in='8.625',SMYS_psi='52000',F_class='.8',E_weld='1',T_temp='1',rule='B31_8_841_1_1',structural_minimum_mm='3',reviewed='yes'))
    w.policy(cid,s.workflow.revision(),'recalculate')
    row=next(r for r in w.state(cid)['workspace']['rows'] if r['id']==target['id'])
    assert row['required_thickness_mm'] is None
    assert row['mawp_MPa'] is None
    assert 'RULE_CODE_MISMATCH' in row['issues']


def test_geometry_change_invalidates_product_form_specific_stress(project):
    s,w,cid,_=project
    target=next(r for r in w.state(cid)['workspace']['rows'] if r['current_cell']=='K158')
    w.apply(cid,s.workflow.revision(),[target['id']],dict(material='ASTM A234 WPB',geometry='elbow',code_family='ASME B31.3',code_edition='2024',temperature_F='500',P_psi='1000',D_outside_in='8.625',E_quality='1',W_reduction='1',Y_coefficient='.4',structural_minimum_mm='3',reviewed='yes'))
    assert next(r for r in w.state(cid)['workspace']['rows'] if r['id']==target['id'])['profile']['fields']['S_allow_psi']['value']=='19000'
    w.apply(cid,s.workflow.revision(),[target['id']],{'geometry':'straight_pipe'})
    row=next(r for r in w.state(cid)['workspace']['rows'] if r['id']==target['id'])
    assert row['profile']['fields']['S_allow_psi']['value'] is None
    assert not row['input_trace']['overrides'].get('material_reference')
