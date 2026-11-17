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
    assert 'Wall used for next-inspection mawp candidate</dt><dd>9.5 mm' in result
    assert 'Current MAWP candidate</dt><dd>2033.1093 psi' in result
    assert 'Next-inspection MAWP candidate</dt><dd>1796.9027 psi' in result
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
            if key in {'E_quality', 'W_reduction', 'Y_coefficient', 'F_design', 'E_weld', 'F_class', 'T_temp', 'E_joint'}
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
