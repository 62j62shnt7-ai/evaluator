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


def test_ut_sheet_selection_prefills_source_dimensions_and_separate_materials(tmp_path):
    from openpyxl import load_workbook
    from evaluator.workspace_api import action

    path = tmp_path / 'Mixed UT.xlsx'
    write_fixture(path, [(11.8, 11.2)] * 4)
    book = load_workbook(path)
    sheet = book.active
    sheet['I7'] = 'Material'
    sheet['I8'] = 'API 5L X52'
    for row, band in enumerate(('S', 'E45', 'T8X4', 'R8X6'), 8):
        sheet[f'B{row}'] = band
    book.create_sheet('Cover')
    book.save(path)
    book.close()

    service = ProjectService(tmp_path / 'project')
    source = service.add_source(path)
    service.inspect(source.sha256)
    opened = action(service, 'import', dict(
        source_id=source.sha256, sheet='UT 11-2026', revision=service.workflow.revision(),
    ))
    workspace = Workspace(service)
    cid = opened['comparison_id']
    rows = workspace.state(cid)['workspace']['rows']
    assert service.workflow.comparison(cid)['selected_ut_only']
    assert service.batch.profiles(source.sha256) == []
    assert all(row['material'] is None for row in rows)
    assert {row['geometry'] for row in rows} == {'straight_pipe', 'elbow', 'tee', 'reducer'}
    assert all((row['previous_inspection_date'], row['inspection_date']) == ('2024-11', '2026-11') for row in rows)
    workspace.apply_code_basis(cid, service.workflow.revision(), 'sheet', [], dict(
        code_asset_type='process_piping', code_family='ASME B31.3',
        code_evidence='Synthetic test design basis', code_owner_confirmed='yes',
    ))
    workspace.apply_sheet_materials(
        cid, service.workflow.revision(), {'pipe': 'A106 B', 'fittings': 'A234 WPB'},
    )
    rows = workspace.state(cid)['workspace']['rows']
    assert {row['material'] for row in rows if row['geometry'] == 'straight_pipe'} == {'A106 B'}
    assert {row['material'] for row in rows if row['geometry'] != 'straight_pipe'} == {'A234 WPB'}
    for row in rows:
        assert (row['nps'], row['schedule']) == ('8', '80')
        assert row['profile']['fields']['D_outside_in']['value'] == '8.625'
        assert row['ut_dimensions']['schedule']['cell'].startswith('UT 11-2026!H')


def test_selected_ut_scope_preserves_manual_inputs_and_ignores_other_tab_values(tmp_path):
    service, workspace, cid = open_fixture(tmp_path, 'Pipe.xlsx', [(11.8, 11.2)])
    oid = workspace.state(cid)['workspace']['rows'][0]['current_id']
    workspace.apply(cid, service.workflow.revision(), [oid], dict(
        material='ASTM A106 Grade B', P_psi='800', structural_minimum_mm='2.8',
        source_config_reference='{"structural_minimum_mm":"Evaluation!G7"}',
    ))
    workspace.restrict_to_ut(cid, service.workflow.revision())
    row = workspace.state(cid)['workspace']['rows'][0]
    assert row['material'] == 'ASTM A106 Grade B'
    assert row['profile']['fields']['P_psi']['value'] == '800'
    assert 'structural_minimum_mm' not in row['input_trace']['overrides']


def test_selected_ut_calculates_without_extra_review_checkbox(tmp_path):
    service, workspace, cid = open_fixture(tmp_path, 'Pipe.xlsx', [(11.8, 11.2)])
    workspace.restrict_to_ut(cid, service.workflow.revision())
    row = workspace.state(cid)['workspace']['rows'][0]
    assert float(row['apparent_rate_mm_year']) == pytest.approx(.3)
    workspace.apply_code_basis(cid, service.workflow.revision(), 'sheet', [], dict(
        code_asset_type='production_flowline', code_family='ASME B31.3',
        code_evidence='Synthetic line list', code_owner_confirmed='yes',
    ))
    workspace.apply(cid, service.workflow.revision(), [row['current_id']], dict(
        material='ASTM A106 Grade B', P_psi='800', structural_minimum_mm='2.8',
    ))
    saved = workspace.evaluate(cid, service.workflow.revision(), basis='assigned')['rows'][0]
    assert saved['mawp_MPa'] is not None
    assert saved['remaining_life_years'] is not None
    assert 'INSPECTION_POLICY_REQUIRED' not in saved['issues']
    assert float(saved['inspection_interval_years']) == 5
    assert saved['forecast_mawp_MPa'] is not None
    assert 'pending confirmation of applicability' in saved['input_trace']['interval_policy']['reference']
    workspace.apply(cid, service.workflow.revision(), [row['current_id']], {'api570_ut_class': '1'})
    saved = workspace.evaluate(cid, service.workflow.revision(), basis='assigned')['rows'][0]
    assert saved['forecast_mawp_MPa'] is not None


def test_sheet_code_switch_recalculates_with_new_route_and_defaults(tmp_path):
    service, workspace, cid = open_fixture(tmp_path, 'Pipe.xlsx', [(11.8, 11.2)])
    workspace.restrict_to_ut(cid, service.workflow.revision())
    oid = workspace.state(cid)['workspace']['rows'][0]['current_id']

    def assign(code, service_type, **inputs):
        workspace.apply_code_basis(cid, service.workflow.revision(), 'sheet', [], dict(
            code_asset_type=service_type, code_family=code, code_evidence='Synthetic line list',
            code_owner_confirmed='yes', **inputs,
        ))

    assign('ASME B31.3', 'process_piping')
    workspace.apply(cid, service.workflow.revision(), [oid], dict(
        material='API 5L X52', P_psi='800', structural_minimum_mm='2.8',
        rule='B31_3_304_1_2', interval_fraction='0.5', interval_cap_years='2',
        selected_interval_years='1', adopted_rate_mm_year='0.05',
        E_quality='0.9',
    ))
    workspace.policy(cid, service.workflow.revision(), 'row7')
    assign('ASME B31.8', 'gas_transmission', product_form='SMLS', gas_basic_class='2',
           temperature_F='100', E_weld='1')
    row = workspace.evaluate(cid, service.workflow.revision())['rows'][0]
    assert row['rule'] == 'B31_8_841_1_1'
    assert row['pressure_thickness_mm'] is not None
    assert row['mawp_MPa'] is not None
    assert row['selected_interval_years'] is None
    assert 'INSPECTION_POLICY_REQUIRED' in row['issues']
    assert 'MANUAL_INTERVAL_OVERRIDE_INVALID' not in row['issues']
    assert row['input_trace']['normalized_design']['SMYS_MPa']['value_psi'] == 52200
    assert row['input_trace']['normalized_design']['T_temp']['value'] == '1'
    assert row['input_trace']['overrides']['structural_minimum_mm'] == '2.8'

    assign('ASME B31.3', 'process_piping')
    row = workspace.evaluate(cid, service.workflow.revision())['rows'][0]
    assert row['rule'] == 'B31_3_304_1_2'
    assert 'INSPECTION_POLICY_REQUIRED' not in row['issues']
    assert row['input_trace']['interval_policy']['cap_years'] == '5'
    assert row['input_trace']['overrides']['E_weld'] is None


def test_api570_interval_and_observed_rate_for_b313_pipe(tmp_path):
    service, workspace, cid = open_fixture(tmp_path, 'Pipe.xlsx', [(11.8, 11.2)])
    workspace.apply_code_basis(cid, service.workflow.revision(), 'sheet', [], dict(
        code_asset_type='process_piping', code_family='ASME B31.3',
        code_evidence='Synthetic line list', code_owner_confirmed='yes',
    ))
    oid = workspace.state(cid)['workspace']['rows'][0]['current_id']
    workspace.apply(cid, service.workflow.revision(), [oid], dict(
        material='ASTM A106 Grade B', P_psi='800', structural_minimum_mm='2.8',
        adopted_rate_mm_year='0.1', reviewed='yes',
    ))
    row = workspace.state(cid)['workspace']['rows'][0]
    assert 'INSPECTION_POLICY_REQUIRED' in row['issues']
    assert float(row['adopted_rate_mm_year']) == pytest.approx(.3)
    assert not row['input_trace']['source_rate_selected']
    workspace.apply(cid, service.workflow.revision(), [oid], {'api570_ut_class': '1'})
    row = workspace.state(cid)['workspace']['rows'][0]
    assert 'INSPECTION_POLICY_REQUIRED' not in row['issues']
    assert float(row['inspection_interval_years']) == 5
    assert '§6.3.3 and Table 1' in row['input_trace']['interval_policy']['reference']
    assert row['forecast_mawp_MPa'] is not None


def test_material_only_edit_prefills_library_stress_from_saved_code(tmp_path):
    service, workspace, cid = open_fixture(tmp_path, 'Pipe.xlsx', [(11.8, 11.2)])
    workspace.apply_code_basis(cid, service.workflow.revision(), 'sheet', [], dict(
        code_asset_type='process_piping', code_family='ASME B31.3',
        code_evidence='Synthetic line list', code_owner_confirmed='yes',
    ))
    oid = workspace.state(cid)['workspace']['rows'][0]['current_id']
    workspace.apply(cid, service.workflow.revision(), [oid], {'material': 'ASTM A106 Grade B'})
    row = workspace.state(cid)['workspace']['rows'][0]
    assert row['S_allow_psi'] == '20000'
    assert row['profile']['fields']['temperature_F']['value'] == '100'
    assert row['profile']['fields']['S_allow_psi']['kind'] == 'reference_derived'
    workspace.apply(cid, service.workflow.revision(), [oid], dict(
        P_psi='800', structural_minimum_mm='2.8', reviewed='yes',
    ))
    row = workspace.state(cid)['workspace']['rows'][0]
    assert row['mawp_MPa'] is not None
    workspace.apply(cid, service.workflow.revision(), [oid], {'temperature_F': '101'})
    assert workspace.state(cid)['workspace']['rows'][0]['S_allow_psi'] is None


def test_synthetic_pipe_report_through_workspace(tmp_path):
    service, workspace, cid = open_fixture(tmp_path, 'Pipe.xlsx', [(11.8, 11.2)])
    row = workspace.state(cid)['workspace']['rows'][0]
    workspace.apply(cid, service.workflow.revision(), [row['current_id']], dict(
        geometry='straight_pipe', material='A106 B', temperature_F='300',
        P_psi='800', structural_minimum_mm='2.8', code_asset_type='process_piping',
        code_family='ASME B31.3', code_edition='2024', code_evidence='Assumed synthetic line list',
        code_owner_confirmed='yes', reviewed='yes', pipe_method='example'), dimension_key=['ferritic','8','80'])
    saved = workspace.evaluate(cid, service.workflow.revision(), basis='recalculate')
    row = next(r for r in saved['rows'] if r['current_id'])
    out = row['row7']
    assert out is not None, row['issues']
    assert 'INSPECTION_POLICY_REQUIRED' not in row['issues']
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
        E_quality='1', W_reduction='1', Y_coefficient='.4',
        interval_fraction='.5', interval_cap_years='10', selected_interval_years='2',
        reviewed='yes'), dimension_key=['ferritic', '8', '80'])
    workspace.apply(cid, service.workflow.revision(), [shell['current_id']], dict(
        geometry='cylindrical_shell', material='SA-516 Grade 70', product_form='plate',
        temperature_F='302', P_psi='150', D_inside_in='48', E_joint='.85', structural_minimum_mm='3',
        code_asset_type='pressure_vessel', code_family='ASME VIII-1', code_edition='2025',
        code_evidence='Synthetic drawing', code_owner_confirmed='yes', reviewed='yes'))
    result = action(service, 'evaluate', dict(comparison_id=cid, revision=service.workflow.revision(), basis='assigned'))
    rows = {row['current_id']: row for row in result['rows'] if row['current_id']}
    assert rows[pipe['current_id']]['rule'] == 'B31_3_304_1_2'
    assert float(rows[pipe['current_id']]['pressure_thickness_mm']) == pytest.approx(4.3125)
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
    assert rows[pipe['current_id']]['forecast_mawp_MPa'] is not None
    assert 'Forecast net wall' in pipe_explanation
