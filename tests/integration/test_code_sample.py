from decimal import Decimal

from evaluator.code_sample_ui import PRESETS, panel
from evaluator.engineering.batch_rules import convert
from evaluator.engineering.references import material_stress


def sample_form(rule):
    form = {key: value for key, _, value in PRESETS[rule][1] if not key.endswith('_MPa')}
    form.pop('D_outside_mm')
    form.update(P_psi='800', S_B313_psi='20000', D_outside_in='8.625')
    return form


def test_pipe_next_inspection_pressure_uses_projected_net_wall():
    rule = 'B31_3_304_1_2'
    form = sample_form(rule)
    form.update(measured_mm='11.2', previous_mm='11.8', elapsed_years='2',
                next_years='4', wall_deduction_mm='0.5')
    result = panel(rule, form)
    net = Decimal('9.5')
    pressure = 2 * net * Decimal(form['S_B313_psi']) / (convert(form['D_outside_in'], 'in', 'mm') - Decimal('0.8') * net)
    assert '0.3 mm/year' in result
    assert '10 mm (9.5 mm after deduction)' in result
    assert f'{pressure:.4f} psi' in result
    assert 'Next-inspection MAWP candidate withheld' in panel(rule, dict(form, previous_mm='11'))
    assert 'Next-inspection MAWP candidate withheld' in panel(rule, dict(form, next_years='40'))


def test_new_material_rows_and_code_specific_weld_dropdown():
    for grade in ('ASTM A53 Type S Grade B', 'ASTM A333 Grade 6'):
        row = material_stress(grade, 'straight_pipe', 'ASME B31.3', '2024', '400')
        assert row['S_allow_psi'] == '19900'
        assert material_stress(grade, 'straight_pipe', 'ASME B31.4', '2025', '400') is None
    result = panel('B31_4_403_2_1')
    assert 'name="liquid_weld"' in result
    assert 'ASTM A139 electric fusion welded' in result
    assert 'Table 403.2.1-1' in result


def test_api570_has_its_own_rates_class_interval_and_pressure_forecast():
    from evaluator.code_sample_ui import code_rule

    rule = code_rule('api570', '')
    assert rule != code_rule('api510', '')
    form = sample_form(rule)
    form.update(service_class='1', rate_basis='short', next_years='4', wall_deduction_mm='0.5')
    result = panel(rule, form)
    assert 'Short-term corrosion rate</dt><dd>0.3 mm/year' in result
    assert 'Long-term corrosion rate</dt><dd>0.24 mm/year' in result
    assert 'Maximum UT interval</dt><dd>5 years' in result
    assert 'Projected wall</dt><dd>10 mm' in result
    assert 'Estimated corrosion loss by next inspection</dt><dd>1.2 mm' in result
    assert 'API 570 MAWP corrosion deduction (2 × estimated loss)</dt><dd>2.4 mm' in result
    assert 'Wall used for next-inspection mawp candidate</dt><dd>8.3 mm' in result
    assert 'Current MAWP candidate</dt><dd>2033.1093 psi' in result
    assert 'Next-inspection MAWP candidate</dt><dd>1562.831 psi' in result
    assert 'at most 5 years' in panel(rule, dict(form, next_years='6'))

    short = dict(form, structural_mm='10.3', next_years='')
    assert 'Maximum UT interval</dt><dd>1.5 years' in panel(rule, short)
    assert 'Maximum UT interval</dt><dd>2 years' in panel(rule, dict(short, short_life_option='yes'))


def test_sample_forms_start_with_blank_manual_inputs_and_keep_submitted_values():
    import re

    for rule in PRESETS:
        markup = panel(rule)
        inputs = dict(re.findall(r'<input type="number" name="([^"]+)" value="([^"]*)"', markup))
        expected = {
            key: value for key, _, value in PRESETS[rule][1]
            if key in {'E_quality', 'W_reduction', 'Y_coefficient', 'F_design', 'E_weld', 'F_class', 'T_temp', 'E_joint', 'E_circumferential'}
        }
        assert inputs and {key: value for key, value in inputs.items() if value} == expected, rule
        assert not any(key.endswith('_MPa') for key in inputs), rule
        if 'D_outside_in' in inputs:
            assert 'Outside diameter (in)' in markup and inputs['D_outside_in'] == ''
        for key, label, _ in PRESETS[rule][1]:
            if key.endswith('_MPa'):
                assert label.replace('(MPa)', '(psi)') in markup
                assert inputs[key.replace('_MPa', '_psi')] == ''

    api570 = panel('API570_PIPE')
    assert '<select name="service_class" required><option value="">' in api570
    assert '<select name="rate_basis" required><option value="">' in api570
    assert ' selected>Class 2' not in api570
    refilled = panel('API570_PIPE', {'measured_mm': '11.2', 'service_class': '2'})
    assert 'name="measured_mm" value="11.2"' in refilled
    assert 'value="2" selected>Class 2' in refilled


def test_api570_annex_d_local_tables_and_result_provenance():
    import pytest

    from evaluator.engineering.references import code_pdf_path
    from evaluator.engineering.structural_reference import FILENAME, structural_cell, structural_tables

    pytest.importorskip('pymupdf')
    if not code_pdf_path(FILENAME).is_file():
        pytest.skip('Original API RP 574 PDF unavailable')
    tables = structural_tables()
    assert [sum(map(len, table['cells'].values())) for table in tables] == [96] * 5 + [53]
    assert [table['cells']['24']['2500'] for table in tables] == [
        '37.72', '42.93', '32.26', '30.86', '42.55', '48.39',
    ]

    rule = 'API570_PIPE'
    form = sample_form(rule)
    form.update(service_class='1', rate_basis='short', next_years='4',
                structural_material='Carbon steel', structural_temperature='400',
                structural_nps='8', structural_class='600', structural_mm='5.46')
    markup = panel(rule, form)
    assert 'Structural minimum</dt><dd>5.46 mm' in markup
    assert 'Governing required thickness</dt><dd>5.46 mm' in markup
    assert 'Structural thickness basis: API RP 574 Annex D Table D.2b, PDF p. 148' in markup
    assert 'Structural thickness basis: Manual reviewed structural minimum' in panel(
        rule, dict(form, structural_mm='6'))
    assert structural_cell(tables, dict(form, structural_temperature='401')) is None
    assert structural_cell(tables, dict(form, structural_material='1¼Cr–½Mo',
                                       structural_temperature='1100', structural_nps='2')) is None


def test_api570_without_annex_d_keeps_manual_calculation_available(monkeypatch, tmp_path):
    monkeypatch.setenv('UT_EVALUATOR_CODES', str(tmp_path))
    rule = 'API570_PIPE'
    form = sample_form(rule)
    form.update(service_class='1', rate_basis='short')
    markup = panel(rule, form)
    assert 'Local API RP 574 PDF unavailable' in markup
    assert 'name="structural_mm" value="3"' in markup
    assert 'Structural thickness basis: Manual reviewed structural minimum' in markup

    (tmp_path / 'RP_574_E5_EN_wA1.pdf').write_bytes(b'wrong PDF')
    import pytest
    pytest.importorskip('pymupdf')
    assert 'Local API RP 574 PDF differs' in panel(rule)


def test_api510_vessel_double_loss_original_cap_and_inspection_limit():
    from evaluator.code_sample_ui import code_rule

    rule = code_rule('api510', '')
    form = dict(t_previous_mm='11.8', t_current_mm='11.2', elapsed_years='2',
                t_required_mm='5', next_years='4', original_psi='200',
                R_inside_mm='609.6', S_allow_psi='20000', E_joint='1',
                E_circumferential='1', static_head_psi='10')
    result = panel(rule, form)
    assert 'Projected wall at next inspection</dt><dd>10 mm' in result
    assert 'API 510 wall used for MAWP</dt><dd>8.8 mm' in result
    assert 'Continued-use MAWP candidate</dt><dd>200 psi' in result
    t = Decimal('8.8')
    pressure = t * 20000 / (Decimal('609.6') + Decimal('.6') * t) - 10
    assert f'Continued-use MAWP candidate</dt><dd>{pressure:.4f} psi' in panel(
        rule, dict(form, original_psi='500'))
    assert 'non-RBI limit' in panel(rule, dict(form, next_years='11'))
    assert 'Continued-use MAWP withheld' in panel(rule, dict(form, t_required_mm='11.2'))
    thin_weld = panel(rule, dict(form, E_circumferential='.2'))
    longitudinal = 2 * t * 4000 / (Decimal('609.6') - Decimal('.4') * t) - 10
    assert f'Continued-use MAWP candidate</dt><dd>{longitudinal:.4f} psi' in thin_weld
    for geometry in ('API510_VIII_UG32_ELLIP', 'API510_VIII_UG32_TORI'):
        selected = code_rule('api510', geometry)
        result = panel(selected, dict(form, D_inside_mm='1219.2', L_inside_crown_mm='1200'))
        assert 'Continued-use MAWP candidate</dt><dd>' in result
        assert 'Circumferential joint efficiency' not in result
    assert 'name="P_psi"' not in panel(rule)


def test_pipeline_design_allowances_and_test_pressure_limits():
    b313 = sample_form('B31_3_304_1_2')
    b313.update(nominal_mm='6', design_allowance_mm='1', mill_tolerance_pct='12.5')
    result = panel('B31_3_304_1_2', b313)
    assert 'Available wall for design check</dt><dd>5.25 mm' in result
    assert 'Wall margin</dt><dd>-' in result
    b314 = dict(P_psi='800', D_outside_in='8.625', SMYS_psi='52000',
                F_design='.72', E_weld='1', design_allowance_mm='1', nominal_mm='6')
    result = panel('B31_4_403_2_1', b314)
    assert 'Minimum nominal wall for design check</dt><dd>3.3405 mm' in result
    assert 'Available wall for design check</dt><dd>6 mm' in result

    b318 = dict(P_psi='800', D_outside_in='8.625', SMYS_psi='52200', F_class='.5',
                E_weld='1', T_temp='1', nominal_mm='6', gas_test_psi='1000')
    for basis, cap in [('furnace', 600), ('mill', 850), ('retest', 850)]:
        result = panel('B31_8_841_1_1', dict(b318, gas_test_basis=basis))
        assert f'Governing design pressure candidate</dt><dd>{cap} psi' in result
        assert ('exceeds the governing' in result) == (basis == 'furnace')
    assert 'name="measured_mm"' not in panel('B31_8_841_1_1')


def test_api650_sample_separate_hydro_height_and_construction_floor():
    form = dict(D_m='12', H_m='1', hydro_H_m='2', G='.85',
                Sd_psi='25000', St_psi='25000', CA_mm='0', course_position='lowest')
    result = panel('API650_ONE_FOOT_PRODUCT', form)
    assert 'Hydrotest wall</dt><dd>0.5799 mm' in result
    assert 'Code nominal plate minimum</dt><dd>6 mm' in result
    assert 'Governing shell thickness candidate</dt><dd>6 mm' in result
    assert 'Code nominal plate minimum</dt><dd>5 mm' in panel(
        'API650_ONE_FOOT_PRODUCT', dict(form, course_position='upper'))
    assert 'name="measured_mm"' not in result


def test_api570_short_term_method_does_not_require_initial_reading():
    rule = 'API570_PIPE'
    form = sample_form(rule)
    form.update(initial_mm='', long_years='', service_class='1', rate_basis='short', next_years='4')
    result = panel(rule, form)
    assert 'Next-inspection MAWP candidate</dt><dd>' in result
    assert 'Long-term corrosion rate</dt>' not in result
    assert 'name="nominal_mm"' not in result
