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
from tests.source_config import SOURCE_ROOT, original_workbook

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture
def project(tmp_path):
    service=ProjectService(tmp_path)
    source=service.add_source(original_workbook('TL-B from SAG Gas MFD to GP.xlsx'))
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
    reference = SOURCE_ROOT / 'codes/RP_574_E5_EN_wA1.pdf'
    if not reference.is_file():
        pytest.skip('Original API RP 574 reference PDF is unavailable')
    digest = sha256(reference.read_bytes()).hexdigest()
    assert {row['source_sha256'] for row in data} == {digest}, reference.name


def test_row7_group_inputs_individual_override_and_saved_results(project):
    s,w,cid,_=project
    w.policy(cid,s.workflow.revision(),'row7')
    rows=w.state(cid)['workspace']['rows']
    ids=[r['current_id'] for r in rows if r['current_id'] and r['previous_id']][:2]
    w.apply(cid,s.workflow.revision(),ids,dict(material='A106 B',P_psi='800',structural_minimum_mm='2.8',adopted_rate_mm_year='.2'),dimension_key=['ferritic','8','80'])
    w.apply(cid,s.workflow.revision(),[ids[0]],dict(P_psi='900'))
    updated={r['id']:r for r in w.state(cid)['workspace']['rows']}
    assert updated[ids[0]]['row7'] is not None
    assert updated[ids[1]]['row7'] is not None
    assert updated[ids[0]]['input_trace']['inputs']['pd_psi']=='900'
    assert updated[ids[1]]['input_trace']['inputs']['pd_psi']=='800'
    assert updated[ids[0]]['nominal_thickness_mm']=='12.70'
    saved=w.evaluate(cid,s.workflow.revision())
    assert sum(bool(r['current_id']) for r in saved['rows'])==len(rows)
    assert next(r for r in saved['rows'] if r['id']==ids[0])['row7']==updated[ids[0]]['row7']


def test_fill_missing_preserves_inline_override(project):
    s,w,cid,_=project
    w.policy(cid,s.workflow.revision(),'row7')
    rows=w.state(cid)['workspace']['rows'];ids=[r['current_id'] for r in rows][:2]
    w.apply(cid,s.workflow.revision(),[ids[0]],dict(structural_minimum_mm='4.2'))
    before=s.workflow.revision()
    w.apply(cid,before,ids,dict(structural_minimum_mm='2.8',P_psi='999'),fill_missing=True)
    assert s.workflow.revision()==before+1
    updated={r['current_id']:r for r in w.state(cid)['workspace']['rows']}
    assert updated[ids[0]]['input_trace']['inputs']['structural_mm']=='4.2'
    assert updated[ids[1]]['input_trace']['inputs']['structural_mm'] is not None
    assert updated[ids[0]]['material'] in {'A106 B','A234 WPB'}


def test_partial_workspace_refresh_returns_only_requested_rows(project):
    s,w,cid,_=project
    all_rows=w.state(cid)['workspace']['rows']
    ids=[r['current_id'] for r in all_rows if r['current_id']][:2]
    partial=w.state(cid,row_ids=[ids[0]])
    assert [r['current_id'] for r in partial['workspace']['rows']]==[ids[0]]
    assert set(partial)=={'revision','workspace'}


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
    s=ProjectService(tmp_path);source=s.add_source(original_workbook(filename));s.inspect(source.sha256);w=Workspace(s)
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
    shutil.copyfile(original_workbook('Separator-204 Inspection Report.xlsx'),incoming)
    s=ProjectService(tmp_path/'project');source=s.add_source(incoming,'inspection.xlsx');s.inspect(source.sha256)
    opened=Workspace(s).auto_open(source.sha256,s.workflow.revision())
    assert opened['comparison_id']
    assert Workspace(s).state(opened['comparison_id'])['workspace']['counts']['locations']==37


@pytest.fixture
def dated_evaluation(tmp_path, request):
    from datetime import date
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = 'Evaluation Nov-26'
    sheet['F1'] = 'According to API-570 & ASME B31.3'
    sheet.append(['JOINT', 'BAND', 'MATERIAL', 'Pd (Psi)', 'OD\n(in)', 'S (Psi)',
                  'tstrc. (mm)\nAPI 574', 'tPd (mm)', 'tReq (mm)', 'Min. UT Reading (mm)'])
    sheet.merge_cells('J2:M2')
    sheet['L4'], sheet['M4'] = date(2018, 6, 20), date(2025, 7, 30)
    pipe_band, *fitting_bands = getattr(request, 'param', ('S', 'E', 'T', 'R'))
    sheet.append(['# 1', pipe_band, 'A106 B', 250, 8.625, 20000, 2.8, '=D5*E5', '=MAX(G5,H5)',
                  None, None, 6.5, 6.5])
    sheet['O3'], sheet['O5'] = 'Selected', 0.01
    for joint, band in enumerate(fitting_bands, start=2):
        sheet.append([f'# {joint}', band, 'SA-234-WPB', 250, 8.625, 20000, 2.8,
                      None, None, None, None, 6.5, 6.4])
    path = tmp_path / 'inspection.xlsx'
    book.save(path)

    service = ProjectService(tmp_path / 'project')
    source = service.add_source(path)
    service.inspect(source.sha256)
    workspace = Workspace(service)
    opened = workspace.auto_open(source.sha256, service.workflow.revision())
    return service, workspace, opened['comparison_id']


@pytest.mark.parametrize('dated_evaluation', [
    ('S', 'E', 'T', 'R'),
    ('STRAIGHT PIPE', 'ELBOW 90', 'TEE-A', 'ECCENTRIC REDUCER'),
], indirect=True)
def test_auto_open_uses_dated_ut_columns_on_evaluation_tab(dated_evaluation):
    _, workspace, cid = dated_evaluation
    rows = workspace.state(cid)['workspace']['rows']
    assert {row['current_cell']: row['geometry'] for row in rows} == {
        'M5': 'straight_pipe', 'M6': 'elbow', 'M7': 'tee', 'M8': 'reducer',
    }
    row = next(row for row in rows if row['current_cell'] == 'M5')
    assert row['current_cell'] == 'M5'
    assert row['previous_id']
    assert row['match_identity']['size'] == '8.0'
    assert row['material'] == 'A106 B'
    assert row['profile']['fields']['structural_minimum_mm']['value'] == 2.8
    assert row['code_family'] == 'ASME B31.3'
    assert row['code_edition'] is None
    assert row['routing']['status'] == 'NEEDS_CODE_CONFIRMATION'


def test_sheet_code_basis_keeps_each_components_geometry_and_material(dated_evaluation):
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from evaluator.webapp import make_handler
    from evaluator.workspace_api import action

    service, workspace, cid = dated_evaluation
    rows = workspace.state(cid)['workspace']['rows']
    inputs = {row['current_id']: (row['geometry'], row['material']) for row in rows}
    values = dict(code_family='ASME B31.3', code_asset_type='process_piping',
                  code_evidence='Test line list', code_owner_confirmed='yes')
    payload = dict(comparison_id=cid, revision=service.workflow.revision(), scope='sheet',
                   ids=[rows[0]['current_id']], values=dict(values, geometry='straight_pipe'))
    with ThreadingHTTPServer(('127.0.0.1', 0), make_handler(service)) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = HTTPConnection('127.0.0.1', server.server_port)
        try:
            client.request('POST', '/api/workspace/apply_code_basis', json.dumps(payload),
                           {'Content-Type':'application/json'})
            response = client.getresponse()
            assert response.status == 200
            assert json.loads(response.read())['message'] == 'Code basis saved for 4 locations.'
        finally:
            client.close()
            server.shutdown()
            thread.join()
    updated = workspace.state(cid)['workspace']['rows']
    for row in updated:
        assert (row['geometry'], row['material']) == inputs[row['current_id']]
        assert row['code_family'] == 'ASME B31.3'
        assert row['code_edition'] == '2024'
        assert row['code_owner_confirmed']
    assert sum(row['routing']['status'] == 'ROUTE_SELECTED' for row in updated) == 1
    with pytest.raises(ValueError, match='Project changed'):
        action(service, 'apply_code_basis', payload)
    target = rows[0]['current_id']
    action(service, 'apply_code_basis', dict(payload, revision=service.workflow.revision(),
           scope='selected', values=dict(values, code_edition='2022')))
    checked = workspace.state(cid)['workspace']['rows']
    assert {row['current_id']: row['code_edition'] for row in checked} == {
        oid: '2022' if oid == target else '2024' for oid in inputs
    }


def test_sheet_material_prefill_keeps_pipe_and_fitting_scopes_separate(dated_evaluation):
    service, workspace, cid = dated_evaluation
    workspace.apply_sheet_materials(
        cid, service.workflow.revision(), {'pipe': 'API 5L X52', 'fittings': 'A420 WPL6'},
        replace_existing=True,
    )
    rows = workspace.state(cid)['workspace']['rows']
    assert {row['material'] for row in rows if row['geometry'] == 'straight_pipe'} == {'API 5L X52'}
    assert {row['material'] for row in rows if row['geometry'] in {'elbow', 'tee', 'reducer'}} == {'A420 WPL6'}
    assert not any(row['reviewed'] for row in rows)


def test_workbook_pipe_review_reports_missing_historical_ut():
    from evaluator.workspace import _workbook_pipe_review

    row = {
        'profile': None,
        'material': None,
        'previous_id': None,
        'routing': {'status': 'ROUTE_SELECTED'},
    }
    review = _workbook_pipe_review(row)
    assert not review['eligible']
    assert 'earlier UT' in review['reason']
    assert 'approved adopted corrosion rate' in review['reason']


def test_workbook_pipe_review_accepts_library_spelling_but_rejects_other_grades():
    from evaluator.workspace import _workbook_pipe_review

    def literal(value, cell):
        return {'value': value, 'cell': cell, 'kind': 'literal'}

    row = dict(material='ASTM A106 Grade B', previous_id='previous', routing={'status': 'ROUTE_SELECTED'},
               profile=dict(sheet='Evaluation', fields={
                   'material': literal('A106 B', 'C5'),
                   'S_allow_psi': literal(20000, 'F5'),
                   'adopted_rate_mm_year': literal(.21, 'O5'),
               }))
    assert _workbook_pipe_review(row)['eligible']
    row['material'] = 'API 5L X52'
    assert not _workbook_pipe_review(row)['eligible']


def test_batch_workbook_pipe_review_saves_source_values_and_calculates(dated_evaluation):
    from evaluator.workspace_api import action

    service, workspace, cid = dated_evaluation
    values = dict(code_family='ASME B31.3', code_asset_type='process_piping',
                  code_evidence='Test line list', code_owner_confirmed='yes')
    workspace.apply_code_basis(cid, service.workflow.revision(), 'sheet', [], values)
    rows = workspace.state(cid)['workspace']['rows']
    pipe = next(row for row in rows if row['geometry'] == 'straight_pipe')
    assert pipe['workbook_review']['eligible']
    payload = dict(comparison_id=cid, revision=service.workflow.revision(), ids=[pipe['current_id']])
    with pytest.raises(ValueError, match='Confirm the workbook'):
        action(service, 'review_workbook_pipes', payload)
    action(service, 'review_workbook_pipes', dict(payload, confirmed=True))
    workspace.apply(cid, service.workflow.revision(), [pipe['current_id']], dict(
        E_quality='1', W_reduction='1', Y_coefficient='.4',
        interval_fraction='.5', interval_cap_years='10', reviewed='yes',
    ))
    batch = workspace.evaluate(cid, service.workflow.revision(), basis='assigned')
    result = next(row for row in batch['rows'] if row['current_id'] == pipe['current_id'])
    assert result['rule'] == 'B31_3_304_1_2'
    assert result['pressure_thickness_mm'] is not None
    assert result['adopted_rate_mm_year'] == '0.01'
    assert result['input_trace']['overrides']['material_reference'] == 'Evaluation Nov-26!F5'
    assert 'Evaluation Nov-26!O5' in result['input_trace']['overrides']['review_note']
    assert batch['summary']['mawp_evaluated'] == 1


def test_fittings_calculate_from_reviewed_inputs_without_rating_check(dated_evaluation):
    service, workspace, cid = dated_evaluation
    workspace.apply_code_basis(cid, service.workflow.revision(), 'sheet', [], dict(
        code_family='ASME B31.3', code_asset_type='process_piping',
        code_evidence='Test line list', code_owner_confirmed='yes',
    ))
    rows = {row['geometry']: row for row in workspace.state(cid)['workspace']['rows']}
    for geometry in ('elbow', 'tee', 'reducer'):
        values = dict(reviewed='yes', temperature_F='100', selected_interval_years='2',
                      required_thickness_mm='5', fitting_life_reference='Synthetic governing required wall')
        if geometry == 'elbow':
            values.update(D_outside_in='8.625', S_allow_psi='20000', bend_radius_in='15',
                          bend_position='intrados', allowance_mm='0', E_quality='1', W_reduction='1',
                          Y_coefficient='.4', bend_design_reference='Synthetic reviewed bend drawing')
        else:
            values.update(qualification_tag=geometry, qualification_points='4, 100\n6, 200',
                          qualification_reference='Synthetic approved schedule and UT map',
                          qualification_temperature_F='100')
        workspace.apply(cid, service.workflow.revision(), [rows[geometry]['current_id']], values)
    result = workspace.evaluate(cid, service.workflow.revision(), basis='assigned')
    rows = {row['profile']['geometry']: row for row in result['rows'] if row.get('profile')}
    assert Decimal(rows['elbow']['fitting_progress']['bend_pressure_psi']) > 0
    for geometry in ('tee', 'reducer'):
        assert rows[geometry]['fitting_progress']['qualified_current_pressure_psi'] == '200'
        assert Decimal(rows[geometry]['fitting_progress']['projected_wall_mm']) < Decimal('6.4')
    assert all('fitting_check' not in rows[geometry] for geometry in ('elbow', 'tee', 'reducer'))
    for geometry in ('elbow', 'tee', 'reducer'):
        row = rows[geometry]
        assert Decimal(row['remaining_life_years']) > 0
        assert row['fitting_progress']['next_interval_years'] == '2'
        assert not row['fitting_progress']['planning_projection_only']
        assert Decimal(row['fitting_progress']['credited_wall_mm']) >= Decimal('5')
        assert row['outputs']['trace']['remaining_life_years']['minimum_reference'] == 'Synthetic governing required wall'


def test_fitting_checks_require_documented_limits_and_keep_mawp_blank(dated_evaluation):
    from evaluator.workspace_api import action

    service, workspace, cid = dated_evaluation
    basis = dict(code_family='ASME B31.3', code_asset_type='process_piping',
                 code_evidence='Test line list', code_owner_confirmed='yes')
    workspace.apply_code_basis(cid, service.workflow.revision(), 'sheet', [], basis)
    rows = workspace.state(cid)['workspace']['rows']
    fittings = [row for row in rows if row['geometry'] != 'straight_pipe']
    assert all(row['routing']['status'] == 'FITTING_REVIEW_REQUIRED' for row in fittings)
    assert all(row['issues'] == ['Optional fitting rating check has not been run.'] for row in fittings)
    assert all(row['fitting_workbook_review']['inputs']['fitting_pressure_psi']['value'] == 250
               for row in fittings)
    assert all(Decimal(row['fitting_progress']['wall_loss_mm']) == Decimal('.1') for row in fittings)
    review = dict(fitting_pressure_psi=250, fitting_minimum_mm=5,
                  fitting_interval_years=2, adopted_rate_mm_year=0.4,
                  fitting_reference='Synthetic assessment')
    entries = {row['current_id']: review for row in fittings}
    action(service, 'review_fittings', dict(comparison_id=cid, revision=service.workflow.revision(),
           confirmed=True, entries=entries))
    batch = workspace.evaluate(cid, service.workflow.revision(), basis='assigned')
    results = [row for row in batch['rows'] if row['current_id'] in entries]
    assert len(results) == 3
    for row in results:
        assert row['mawp_MPa'] is None
        assert row['fitting_check']['current_meets_minimum'] is True
        assert row['fitting_check']['projected_meets_minimum'] is False
        assert Decimal(row['fitting_check']['credited_wall_mm']) == Decimal('4.8')


def test_fitting_qualification_prefills_exact_ut_location_without_review(dated_evaluation):
    service, workspace, cid = dated_evaluation
    revision = service.workflow.revision
    basis = dict(code_family='ASME B31.3', code_asset_type='process_piping',
                 code_evidence='Test line list', code_owner_confirmed='yes')
    workspace.apply_code_basis(cid, revision(), 'sheet', [], basis)
    rows = workspace.state(cid)['workspace']['rows']
    tee = next(row for row in rows if row['geometry'] == 'tee')
    oid = tee['current_id']
    service.batch.apply_overrides(cid, revision(), [], [oid], {'temperature_F': '300'})
    entry = dict(fitting_pressure_psi='800', fitting_minimum_mm='3', fitting_interval_years='2',
                 adopted_rate_mm_year='0.1', fitting_reference='Assessment Q1',
                 qualification_tag='TEE-17', qualification_reference='Qualification Q1',
                 qualification_temperature_F='300', qualification_points='1,500\n3,800')
    with pytest.raises(ValueError, match='enter a fitting tag'):
        workspace.review_fittings(cid, revision(), {oid: dict(entry, qualification_tag='')})
    workspace.review_fittings(cid, revision(), {oid: entry})
    source, sheet, campaign = service.workflow.comparison(cid)['current_selection']
    repeat = workspace.open_sheet(source, sheet, revision(), current=campaign)['comparison_id']
    rows = workspace.state(repeat)['workspace']['rows']
    prefilled = [row for row in rows if row.get('qualification_prefill')]
    assert [row['current_id'] for row in prefilled] == [oid]
    draft = prefilled[0]
    assert draft['qualification_prefill']['qualification_tag'] == 'TEE-17'
    assert draft['qualification_prefill']['qualification_reference'] == 'Qualification Q1'
    assert 'fitting_interval_years' not in draft['qualification_prefill']
    assert 'adopted_rate_mm_year' not in draft['qualification_prefill']
    assert not draft['reviewed']
    assert not draft.get('fitting_check')


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
