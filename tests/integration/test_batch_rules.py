"""Draft arithmetic benchmarks, not engineering applicability certification."""
from decimal import Decimal
import pytest
from evaluator.engineering.batch_rules import convert, outputs
from evaluator.engineering.draft import evaluate


def test_units_are_decimal_and_reject_nonfinite():
    assert convert('1', 'psi', 'MPa') == Decimal('0.006894757293')
    assert convert('1', 'in', 'mm') == Decimal('25.4')
    assert convert('32', 'F', 'C') == 0
    assert convert('100', 'C', 'F') == 212
    assert convert(convert('9', 'mm', 'in'), 'in', 'mm') == Decimal('9')
    for bad in ('NaN', 'Infinity', True, 'oops'):
        with pytest.raises(ValueError): convert(bad, 'in', 'mm')
    with pytest.raises(ValueError): convert('1', 'psi', 'mm')


def test_independent_life_interval_due_date_and_schema():
    result = outputs('8', '4', '.5', '2026-01-01', interval_fraction='.5', interval_cap_years='3')
    assert result['thickness_margin_mm'] == '4'
    assert result['remaining_life_years'] == '8'
    assert result['inspection_interval_years'] == '3'
    assert result['maximum_inspection_interval_years'] == '3'
    assert result['due_date'] == '2028-12-31'  # floor(3*365.2425) days
    assert result['status'] == 'DRAFT / NOT VALIDATED'
    assert result['trace']['due_date']['rounding'] == 'floor whole days'
    assert result['issues']['remaining_life_years'] == []
    no_date = outputs('8', '4', '.5', interval_fraction='.5', interval_cap_years='3')
    assert no_date['remaining_life_years'] == '8'
    assert no_date['inspection_interval_years'] == '3'
    assert no_date['due_date'] is None
    assert outputs('8', '4', '.5')['inspection_interval_years'] is None


def test_selected_schedule_override_and_distinct_interval_outputs():
    result = outputs('8', '4', '.5', '2026-01-01', interval_fraction='.5',
                     interval_cap_years='3', selected_interval_years='5',
                     scheduled_due_date='2027-10-22')
    assert result['maximum_inspection_interval_years'] == '3'
    assert result['inspection_interval_years'] == '5'
    assert result['due_date'] == '2027-10-22'
    assert 'SELECTED_INTERVAL_EXCEEDS_CALCULATED_MAXIMUM' in result['issues']['inspection_interval_years']
    assert result['trace']['due_date']['basis'] == 'provided schedule record'


def test_mawp_matches_at_life_and_next_inspection_unless_interval_is_overridden():
    rule, inputs = CASES[-1]
    automatic = outputs('10', '4', '.5', rule=rule, design_inputs=inputs,
                        interval_fraction='.5', interval_cap_years='10')
    life_thickness = evaluate(rule, dict(inputs, P_MPa=automatic['mawp_MPa']))['value']
    next_thickness = evaluate(rule, dict(inputs, P_MPa=automatic['forecast_mawp_MPa']))['value']
    assert Decimal(life_thickness) == Decimal(next_thickness) == Decimal('4')
    overridden = outputs('10', '4', '.5', '2026-01-01', rule=rule, design_inputs=inputs,
                         interval_fraction='.5', interval_cap_years='10',
                         selected_interval_years='3', manual_interval_override=True,
                         manual_selected_interval=True)
    life_thickness = evaluate(rule, dict(inputs, P_MPa=overridden['mawp_MPa']))['value']
    next_thickness = evaluate(rule, dict(inputs, P_MPa=overridden['forecast_mawp_MPa']))['value']
    assert Decimal(life_thickness) == Decimal('4')
    assert Decimal(next_thickness) == Decimal('7')
    assert overridden['due_date'] == '2028-12-31'
    assert overridden['trace']['forecast_mawp_MPa']['horizon_basis'] == 'manual_interval_override'


@pytest.mark.parametrize('kwargs', [{'current_mm':'NaN'}, {'current_mm':'0'}, {'current_mm':'3', 'required_mm':'4'}, {'current_mm':'8', 'required_mm':'4', 'adopted_rate':'0'}, {'current_mm':'8', 'required_mm':'4'}])
def test_invalid_inputs_withhold_life_without_crashing(kwargs):
    result = outputs(**kwargs)
    assert result['remaining_life_years'] is None
    assert result['issues']['remaining_life_years']


CASES = [
 ('VIII_UG27_HOOP', {'R_inside_mm':'500','S_allow_MPa':'100','E_joint':'.8'}),
 ('VIII_UG27_LONG', {'R_inside_mm':'500','S_allow_MPa':'100','E_joint':'.8'}),
 ('VIII_UG32_ELLIP', {'D_inside_mm':'1000','S_allow_MPa':'100','E_joint':'.8'}),
 ('VIII_UG32_TORI', {'L_inside_crown_mm':'1000','S_allow_MPa':'100','E_joint':'.8'}),
 ('B31_3_304_1_2', {'D_outside_mm':'500','S_B313_MPa':'100','E_quality':'1','W_reduction':'1','Y_coefficient':'.4'}),
 ('B31_4_403_2_1', {'D_outside_mm':'500','SMYS_MPa':'350','F_design':'.72','E_weld':'1'}),
 ('B31_8_841_1_1', {'D_outside_mm':'500','SMYS_MPa':'350','F_class':'.5','E_weld':'1','T_temp':'1'}),
]


@pytest.mark.parametrize('rule,inputs', CASES)
def test_inverse_roundtrip_and_forecast(rule, inputs):
    result = outputs('10', '4', '.5', rule=rule, design_inputs=inputs, allowance_mm='1', forecast_years='2', forecast_factor='2', interval_fraction='.5', interval_cap_years='10')
    assert result['mawp_MPa'] is not None
    thickness = evaluate(rule, dict(inputs, P_MPa=result['mawp_MPa']))['value']
    assert abs(Decimal(thickness)-3) < Decimal('1e-24')
    future = evaluate(rule, dict(inputs, P_MPa=result['forecast_mawp_MPa']))['value']
    assert abs(Decimal(future)-7) < Decimal('1e-24')
    assert result['trace']['mawp_MPa']['horizon_basis'] == 'remaining_life_endpoint'
    assert result['trace']['forecast_mawp_MPa']['forecast_years'] == '2'


def test_mawp_exact_known_value_and_independent_errors():
    rule, inputs = CASES[-1]
    result = outputs('11', '4', '.5', rule=rule, design_inputs=inputs, allowance_mm='1', interval_fraction='.5', interval_cap_years='10')
    assert Decimal(result['mawp_MPa']) == Decimal('2.1')
    assert result['forecast_mawp_MPa'] is not None
    assert result['trace']['forecast_mawp_MPa']['forecast_factor'] == '1'
    assert result['remaining_life_years'] == '14'
    assert outputs('11', rule=rule, design_inputs=inputs)['mawp_MPa'] is None
    assert outputs('11', rule='UG45_NOZZLE', design_inputs=inputs, allowance_mm='0')['mawp_MPa'] is None
    bad = outputs('11', '4', '.5', rule=rule, design_inputs={}, allowance_mm='0')
    assert bad['remaining_life_years'] == '14'
    assert bad['mawp_MPa'] is None
    for years, factor in [('20','2'), ('-1','2'), ('2','0')]:
        assert outputs('11', rule=rule, design_inputs=inputs, allowance_mm='1', required_mm='4', adopted_rate='1', interval_fraction='.5', interval_cap_years='10', forecast_years=years, forecast_factor=factor)['forecast_mawp_MPa'] is None


def test_invalid_factor_and_domain_withheld():
    rule, inputs = CASES[4]
    assert outputs('100', rule=rule, design_inputs=inputs, allowance_mm='0')['mawp_MPa'] is None
    rule, inputs = CASES[5]
    assert outputs('10', rule=rule, design_inputs=dict(inputs,F_design='.8'), allowance_mm='0')['mawp_MPa'] is None
