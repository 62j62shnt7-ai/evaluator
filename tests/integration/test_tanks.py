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
        assert b'/tanks' in request('GET', '/')[1]
        revision = service.workflow.revision()
        form = dict(DESIGN, method='api650', revision=revision, tank='T-1', component='Course 1',
                    reviewer='Test reviewer', reason='Reviewed drawing and stress records', applicability='yes')
        assert request('POST', '/tanks', dict(form, applicability='no'))[0] == 400
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
