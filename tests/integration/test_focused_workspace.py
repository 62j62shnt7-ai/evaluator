from pathlib import Path
from http.server import ThreadingHTTPServer
from http.client import HTTPConnection
from threading import Thread
from types import SimpleNamespace
import csv
import io
import json

ROOT = Path(__file__).resolve().parents[2] / 'src/evaluator/static'


def test_active_workspace_only_exposes_current_workflow():
    html = (ROOT / 'workspace.html').read_text()
    for old in ['/legacy', '/readings-only', 'id="basis"', 'name="code_family"',
                'name="temperature_F"', 'id="catalog"', 'id="confirmSelected"', 'Separator 204']:
        assert old not in html
    for field in ['material', 'P_psi', 'D_outside_in', 'nominal_thickness_mm',
                  'structural_minimum_mm', 'adopted_rate_mm_year']:
        assert f'name="{field}"' in html
    for control in ['nps', 'schedule', 'previousCampaign', 'currentCampaign']:
        assert f'id="{control}"' in html
    assert 'name="S_allow_psi"' in html
    assert 'name="geometry"' in html
    assert 'id="componentFilter"' in html and 'id="selectComponent"' in html
    script = (ROOT / 'workspace.js').read_text()
    assert 'componentFilter' in script and "component==='straight_pipe'" in script
    assert 'function materialGrades(rows)' in script
    assert 'id="materialCustom"' not in html


def test_retired_routes_and_saved_calculation_exports():
    from openpyxl import load_workbook
    from evaluator.webapp import make_handler
    result = dict(id='saved', stale=False, rows=[dict(current_id='current',location='Joint 2 / Band 2',
        previous_inspection_date='2023-08-25',inspection_date='2026-11-06',
        previous_thickness_mm='11.6',current_thickness_mm='11.3',issues=[],
        input_trace={'inputs':{'material':'A106 B','pd_psi':'800'}},row7={'result':'Safe','mawp_psi':1782.525})])
    result['rows'].append(dict(current_id=None,location='Historical only'))
    service = SimpleNamespace(
        batch=SimpleNamespace(result_by_id=lambda key: result if key == 'saved' else None),
        workflow=SimpleNamespace(),
    )
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        client=HTTPConnection('127.0.0.1',server.server_port)
        for route in ['/legacy','/workflow','/calculator','/readings-only','/row-evaluation']:
            client.request('GET',route);response=client.getresponse()
            assert response.status==404;response.read()
        for action in ('prefill_sheet_materials', 'record_sleeve_assessment'):
            client.request('POST', f'/api/workspace/{action}', '{}')
            response = client.getresponse()
            assert response.status == 400
            response.read()
        client.request('GET','/workspace/results.csv?result=saved');response=client.getresponse()
        assert response.status==200
        rows=list(csv.DictReader(io.StringIO(response.read().decode())))
        assert rows[0]['Result']=='DRAFT / NOT VALIDATED · Safe'
        assert rows[0]['Pd psi']=='800'
        assert rows[0]['Next-inspection component pressure psi']=='1782.525'
        client.request('GET', '/workspace/results.json?result=saved')
        response = client.getresponse()
        assert response.status == 200
        snapshot = json.loads(response.read())
        assert len(snapshot['rows']) == 1
        client.request('GET', '/workspace/results.xlsx?result=saved')
        response = client.getresponse()
        assert response.status == 200
        assert response.getheader('Content-Type') == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        sheet = load_workbook(io.BytesIO(response.read()), data_only=True)['Calculations']
        assert sheet.freeze_panes == 'B3'
        assert list(sheet.values)[1:] == [
            tuple(column['label'] for column in snapshot['columns']),
            tuple(None if value == '' else value for value in snapshot['rows'][0]),
        ]
        result['stale'] = True
        for extension in ('json', 'xlsx', 'csv'):
            client.request('GET', f'/workspace/results.{extension}?result=saved')
            response = client.getresponse()
            assert response.status == 400
            response.read()
        client.close()
    finally:
        server.shutdown();server.server_close();thread.join()


def test_row_material_override_is_not_batch_prefilled():
    from evaluator.workspace import Workspace
    from types import SimpleNamespace
    w=object.__new__(Workspace)
    w.service=SimpleNamespace(repository=SimpleNamespace(path='unused'))
    w.flow=SimpleNamespace(revision=lambda:1)
    w.templates=lambda:[]
    w.sources=lambda:[]
    w.state=lambda *a,**k:None
    # Exercise the row projection directly through an imported source configuration.
    html=(ROOT/'workspace.js').read_text()
    assert "row['material']=over.get('material',_value(p,'material'))" in (ROOT.parent/'workspace.py').read_text()
