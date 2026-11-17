from decimal import Decimal
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from threading import Thread
from urllib.parse import urlencode
from zipfile import ZipFile

import pytest

from evaluator.app_services import ProjectService
from evaluator.tanks import calculate, history
from evaluator.webapp import make_handler


DESIGN = dict(D_m=30, H_m=12, hydro_H_m=12, G='.85', Sd_MPa=160, St_MPa=171,
              CA_mm=2, nominal_min_mm=12)
SHELL = dict(D_m=30, H_m=12, design_H_m=12, G='.85', course=1, Y_MPa=250,
             T_MPa=400, E=1, measured_mm=12, CA_mm=2, t2_mm=10)


def test_tank_plan_checkpoints_and_governing_limits():
    design = calculate('api650', DESIGN)['outputs']
    assert Decimal(design['product_mm']) == Decimal('11.13696875')
    assert float(design['hydrotest_mm']) == pytest.approx(10.057894736842105)
    assert Decimal(design['governing_candidate_mm']) == 12
    for scope, minimum in [('whole', 8.51931818181818), ('local', 8.737762237762238)]:
        shell = calculate('api653_shell', SHELL, scope)['outputs']
        assert Decimal(shell['allowable_stress_MPa']) == Decimal('171.6')
        assert float(shell['minimum_mm']) == pytest.approx(minimum)
        assert Decimal(shell['liquid_height_candidate_m']) == 12
    local = calculate('api653_shell', dict(SHELL, t2_mm=5), 'local')['outputs']
    assert Decimal(local['local_least_margin_mm']) < 0
    assert float(local['liquid_height_candidate_m']) < 12
    assert float(local['profile_length_mm']) == pytest.approx(34 * (30 * 5) ** .5)
    thin = calculate('api653_shell', dict(SHELL, H_m=1, measured_mm=3), 'whole')['outputs']
    assert Decimal(thin['minimum_mm']) == Decimal('2.5')
    assert thin['liquid_height_candidate_m'] is None
    upper = calculate('api653_shell', dict(SHELL, course=3, T_MPa=700), 'whole')['outputs']
    assert Decimal(upper['allowable_stress_MPa']) == 220
    bottom = calculate('api653_bottom', dict(RTbc_mm=6, RTip_mm=7, interval_years=4,
        StPr='.2', UPr='.15', governing_min_mm='2.54'))['outputs']
    assert Decimal(bottom['projected_remaining_mm']) == Decimal('4.6')


@pytest.mark.parametrize('changes', [{'E': 0}, {'E': '1.01'}, {'course': '1.5'}, {'design_H_m': 11}, {'G': 'NaN'}])
def test_shell_rejects_invalid_domains(changes):
    with pytest.raises(ValueError):
        calculate('api653_shell', dict(SHELL, **changes), 'whole')


def test_tank_workspace_saves_exports_and_undoes(tmp_path):
    service = ProjectService(tmp_path)
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(service))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = HTTPConnection('127.0.0.1', server.server_port, timeout=5)

    def request(method, path, form=None):
        client.request(method, path, urlencode(form) if form else None,
                       {'Content-Type': 'application/x-www-form-urlencoded'})
        response = client.getresponse()
        return response.status, response.read()

    try:
        for path in ('/', '/tanks', '/codes'):
            status, document = request('GET', path)
            assert status == 200
            assert b'class="integrity-desk"' in document
            assert b'/assets/integrity-desk.css' in document
        assert b'aria-current="page">Tank assessments' in request('GET', '/tanks')[1]
        assert b'aria-current="page">Code reference library' in request('GET', '/codes')[1]
        revision = service.workflow.revision()
        form = dict(DESIGN, method='api650', revision=revision, tank='T-1', component='Course 1',
                    reviewer='Test reviewer', reason='Reviewed drawing and stress records', applicability='yes')
        status, document = request('POST', '/tanks', dict(form, applicability='no'))
        assert status == 400
        assert b'role="alert"' in document
        assert b'class="card tank-method" open' in document
        assert request('POST', '/tanks', form)[0] == 303
        assert request('POST', '/tanks', form)[0] == 400
        shell = dict(form, **SHELL, method='api653_shell', scope='local')
        shell['revision'] = service.workflow.revision()
        assert request('POST', '/tanks', shell)[0] == 303
        status, page = request('GET', '/tanks')
        assert status == 200
        assert b'DRAFT / NOT VALIDATED' in page and b'Liquid height candidate' in page
        assert len(history(service.workflow)) == 2
        with ZipFile(service.workflow.export_revision()) as archive:
            snapshot = json.loads(archive.read('project_snapshot.json'))
        assert len(snapshot['tank_assessments']) == 2
        service.workflow.undo(service.workflow.revision(), 'Test reviewer', 'Undo shell assessment')
        assert [row['method'] for row in history(service.workflow)] == ['api650']
    finally:
        client.close()
        server.shutdown()
        server.server_close()
        thread.join()


def test_pit_screen_uses_all_sliding_windows_and_both_limits():
    basis = dict(shell_min_mm=8, scattered='yes')
    good = calculate('api653_pits', dict(basis, pit_rows='A,190,215,4\nA,250,275,5\nB,250,280,4'))
    assert good['outputs']['max_pit_extent_mm'] == '50'
    assert good['outputs']['pit_screen'] == 'Meets both screening limits'
    for readings in ['A,190,215,3.9', 'A,190,216,4\nA,250,275,5']:
        bad = calculate('api653_pits', dict(basis, pit_rows=readings))
        assert bad['outputs']['pit_screen'] == 'Pit exclusion criteria not met'
    with pytest.raises(ValueError, match='overlapping'):
        calculate('api653_pits', dict(basis, pit_rows='A,1,6,5\nA,5,7,5'))


def test_critical_zone_and_annular_boundaries():
    base = dict(RTbc_mm=6, RTip_mm=7, interval_years=4, StPr='.2', UPr='.15',
                toe_mm='2.5', projection_mm=10)
    critical = calculate('api653_critical', dict(base, lower_shell_min_mm=4))['outputs']
    assert Decimal(critical['governing_bottom_min_mm']) == Decimal('2.5')
    assert Decimal(critical['margin_to_reviewed_minimum_mm']) == Decimal('2.1')
    assert Decimal(critical['toe_projection_margin_mm']) == 0
    assert Decimal(calculate('api653_critical', dict(base, lower_shell_min_mm=10))['outputs']['governing_bottom_min_mm']) == 3
    annular = dict(base, G='.9', table_min_mm='4.32', CA_mm='.5',
                   annular_table='API 653 Table 4.5a', nonseismic='yes', table_evidence='Reviewed lookup')
    result = calculate('api653_annular', annular)
    assert Decimal(result['outputs']['margin_to_reviewed_minimum_mm']) == Decimal('.28')
    assert Decimal(result['outputs']['annular_current_margin_mm']) == Decimal('1.18')
    assert result['inputs']['table_evidence'] == 'Reviewed lookup'
    with pytest.raises(ValueError, match='Table 5.1a'):
        calculate('api653_annular', dict(annular, G=1))
    assert 'Table 5.1a' in calculate('api653_annular', dict(annular, G=1, annular_table='API 650 Table 5.1a'))['reference']
    with pytest.raises(ValueError, match='as-built'):
        calculate('api653_annular', dict(annular, nonseismic='no'))


def test_imported_ut_mapping_into_tank_history(tmp_path):
    from openpyxl import Workbook
    from evaluator.tanks import save

    path = tmp_path / 'tank.xlsx'
    book = Workbook()
    sheet = book.active
    sheet.title = 'Tank UT'
    for value in (10, 12, 12, 12, 14):
        sheet.append([value])
    sheet['B1'] = 8
    sheet['B2'] = '=B1'
    book.save(path)

    service = ProjectService(tmp_path / 'project')
    original = service.add_source(path)
    form = dict(SHELL, method='api653_shell', scope='local', tank='TK-1', component='Course 1',
                reviewer='Reviewer', reason='UT survey and profile checked', applicability='yes',
                revision=str(service.workflow.revision()), ut_source=original.sha256, ut_sheet=sheet.title,
                ut_primary='A1,A2,A3,A4,A5', ut_secondary='B1', ut_mm='yes',
                ut_profile_reviewed='yes', ut_date='2026-11-17')
    with pytest.raises(ValueError, match='literal'):
        save(service.workflow, dict(form, ut_secondary='B2'))
    assert history(service.workflow) == []
    record = save(service.workflow, form)
    assert Decimal(record['inputs']['measured_mm']) == 12
    assert Decimal(record['inputs']['t2_mm']) == 8
    assert record['ut_provenance']['groups']['t2_mm']['cells'] == {'B1': '8'}
    assert record['ut_provenance']['source_sha256'] == original.sha256
    assert history(service.workflow)[0] == record
    assert path.read_bytes() == original.stored_path.read_bytes()
