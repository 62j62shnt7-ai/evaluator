"""Synthetic workbook acceptance for the pipe workspace and vessel batch service."""
from openpyxl import Workbook
import pytest

from evaluator.app_services import ProjectService
from evaluator.workspace import Workspace


def write_fixture(path, readings, size='8"'):
    book = Workbook()
    sheet = book.active
    sheet.title = 'UT 11-2026'
    sheet['A1'] = 'SYNTHETIC UT REPORT — ASSUMED DATA'
    sheet['A6'] = 'section #1'
    sheet.append(['JOINT#', 'BAND', 'DIAM.', 'MIN 11-2024', 'MIN 11-2026', 'MAX', 'NOM.T', 'SCH'])
    for index, (previous, current) in enumerate(readings, 1):
        sheet.append([index, 1, size, previous, current, None, 12.7, '80' if size else None])
    book.save(path)
    book.close()


def open_fixture(tmp_path, name, readings, size='8"'):
    path = tmp_path / name
    write_fixture(path, readings, size)
    service = ProjectService(tmp_path / 'project')
    source = service.add_source(path)
    service.inspect(source.sha256)
    workspace = Workspace(service)
    opened = workspace.open_sheet(source.sha256, 'UT 11-2026', service.workflow.revision())
    return service, workspace, opened['comparison_id']


def test_synthetic_pipe_report_through_workspace(tmp_path):
    service, workspace, cid = open_fixture(tmp_path, 'Pipe.xlsx', [(11.8, 11.2)])
    row = workspace.state(cid)['workspace']['rows'][0]
    workspace.apply(cid, service.workflow.revision(), [row['current_id']], dict(
        geometry='straight_pipe', material='A106 B', temperature_F='300',
        P_psi='800', structural_minimum_mm='2.8', code_asset_type='process_piping',
        code_family='ASME B31.3', code_edition='2024', code_evidence='Assumed synthetic line list',
        code_owner_confirmed='yes', reviewed='yes'), dimension_key=['ferritic','8','80'])
    saved = workspace.evaluate(cid, service.workflow.revision())
    row = next(r for r in saved['rows'] if r['current_id'])
    out = row['row7']
    assert out is not None, row['issues']
    assert (row['previous_cell'], row['current_cell']) == ('D8', 'E8')
    assert row['profile']['fields']['nominal_thickness_mm']['value'] == '12.70'
    assert out['s_psi'] == 20000
    assert out['calculated_cr'] == pytest.approx(.3)
    assert out['pressure_mm'] == pytest.approx(4.3125)
    assert out['remaining_life'] == pytest.approx(22.9583333333)
    projected_wall = 11.2 - 2 * .3 * 10
    # Use the tabulated inch OD converted exactly, as the workspace does.
    expected_pressure = 2 * 20000 * projected_wall / (8.625 * 25.4 - .8 * projected_wall)
    assert out['mawp_psi'] == pytest.approx(expected_pressure)
    assert saved['status'] == 'DRAFT / NOT VALIDATED'


def test_synthetic_vessel_shell_and_head_through_batch(tmp_path):
    service, workspace, cid = open_fixture(tmp_path, 'Vessel.xlsx', [(12.4, 12), (11.4, 11)], size='48"')
    rows = workspace.state(cid)['workspace']['rows']
    for row, geometry in zip(rows, ['cylindrical_shell', 'ellipsoidal_head_2to1'], strict=True):
        workspace.apply(cid, service.workflow.revision(), [row['current_id']], dict(
            geometry=geometry, material='SA-516 Grade 70', product_form='plate', temperature_F='302', P_psi='150',
            D_inside_in='48', E_joint='.85', structural_minimum_mm='3',
            code_asset_type='pressure_vessel', code_family='ASME VIII-1', code_edition='2025',
            code_evidence='Assumed drawing and material record', code_owner_confirmed='yes', reviewed='yes'))
    from evaluator.workspace_api import action
    saved = action(service, 'evaluate', dict(comparison_id=cid,
                   revision=service.workflow.revision(), basis='recalculate'))
    rows = {row['rule']: row for row in saved['rows'] if row['current_id']}
    assert set(rows) == {'VIII_SHELL', 'VIII_UG32_ELLIP'}, rows
    stress = 138 * .85
    pressure = 150 * .006894757293
    for rule, expected in {'VIII_SHELL': pressure * 609.6 / (stress - .6 * pressure),
                           'VIII_UG32_ELLIP': pressure * 1219.2 / (2 * stress - .2 * pressure)}.items():
        row = rows[rule]
        assert float(row['apparent_rate_mm_year']) == pytest.approx(.2)
        assert float(row['pressure_thickness_mm']) == pytest.approx(expected)
        current_wall = float(row['current_thickness_mm'])
        expected_life = (current_wall - max(expected, 3)) / .2
        assert float(row['remaining_life_years']) == pytest.approx(expected_life)
        wall = current_wall - .2 * expected_life
        assert float(row['input_trace']['design_inputs']['S_allow_MPa']) == pytest.approx(138)
        assert 'Table 1A line 43' in row['profile']['fields']['S_allow_psi']['basis']
        if rule == 'VIII_SHELL':
            psi = min(wall * stress / (609.6 + .6 * wall),
                      2 * wall * stress / (609.6 - .4 * wall))
        else:
            psi = 2 * wall * stress / (1219.2 + .2 * wall)
        assert float(row['mawp_MPa']) == pytest.approx(psi)
    assert workspace.state(cid)['workspace']['settings']['basis'] == 'recalculate'


def test_vessel_lookup_requires_verified_context():
    from evaluator.engineering.references import material_stress
    args = ('SA-516 Grade 70', 'ellipsoidal_head_2to1', 'ASME VIII-1', '2025', '302')
    assert material_stress(*args, product_form='plate')['S_allow_MPa'] == '138'
    assert material_stress(*args) is None
    assert material_stress(*args, product_form='forging') is None
    assert material_stress(*args[:-1], '300', product_form='plate') is None
    assert material_stress(*args[:3], '2023', '302', product_form='plate') is None


def test_one_workspace_action_calculates_mixed_components_and_retains_unready_rows(tmp_path):
    from evaluator.workspace_api import action

    service, workspace, cid = open_fixture(tmp_path, 'Mixed.xlsx', [(11.8, 11.2), (12.4, 12), (11, 10)])
    pipe, shell, unready = workspace.state(cid)['workspace']['rows']
    workspace.apply(cid, service.workflow.revision(), [pipe['current_id']], dict(
        geometry='straight_pipe', material='A106 B', temperature_F='300', P_psi='800',
        structural_minimum_mm='2.8', code_asset_type='process_piping', code_family='ASME B31.3',
        code_edition='2024', code_evidence='Synthetic line list', code_owner_confirmed='yes',
        reviewed='yes'), dimension_key=['ferritic', '8', '80'])
    workspace.apply(cid, service.workflow.revision(), [shell['current_id']], dict(
        geometry='cylindrical_shell', material='SA-516 Grade 70', product_form='plate',
        temperature_F='302', P_psi='150', D_inside_in='48', E_joint='.85', structural_minimum_mm='3',
        code_asset_type='pressure_vessel', code_family='ASME VIII-1', code_edition='2025',
        code_evidence='Synthetic drawing', code_owner_confirmed='yes', reviewed='yes'))
    result = action(service, 'evaluate', dict(comparison_id=cid, revision=service.workflow.revision(), basis='assigned'))
    rows = {row['current_id']: row for row in result['rows'] if row['current_id']}
    assert rows[pipe['current_id']]['rule'] == 'ROW7'
    assert rows[pipe['current_id']]['row7']['pressure_mm'] == pytest.approx(4.3125)
    assert rows[shell['current_id']]['rule'] == 'VIII_SHELL'
    assert rows[shell['current_id']]['pressure_thickness_mm'] is not None
    assert rows[unready['current_id']]['pressure_thickness_mm'] is None
    assert rows[unready['current_id']]['issues']

    from evaluator.calculation_trace_ui import page
    explanation = page(result, rows[shell['current_id']])
    assert 'class="integrity-desk"' in explanation
    assert 'view=results' in explanation
    assert 'Vessel shell hoop · governs' in explanation
    assert 'Vessel shell longitudinal' in explanation
    assert 'Table 1A line 43' in explanation
    assert 'End-of-life net wall' in explanation
    pipe_explanation = page(result, rows[pipe['current_id']])
    assert '4.3125 mm' in pipe_explanation
    assert 'Projected wall' in pipe_explanation
