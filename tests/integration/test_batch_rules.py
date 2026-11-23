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


def test_workspace_pressure_uses_selected_interval_and_current_wall():
    rule, inputs = CASES[-1]
    result = outputs('10', '4', '.5', '2026-01-01', year_days='365',
                     rule=rule, design_inputs=inputs, allowance_mm='0',
                     interval_fraction='.25', interval_cap_years='10',
                     forecast_factor='1', inspection_pressure=True)
    assert result['inspection_interval_years'] == '3.00'
    assert result['due_date'] == '2028-12-31'
    assert result['trace']['mawp_MPa']['horizon_basis'] == 'current_measurement'
    assert result['trace']['forecast_mawp_MPa']['forecast_years'] == '3.00'
    assert Decimal(result['trace']['forecast_mawp_MPa']['projected_physical_wall_mm']) == Decimal('8.5')
    assert Decimal(result['trace']['forecast_mawp_MPa']['credited_wall_mm']) == Decimal('7')
    assert result['trace']['forecast_mawp_MPa']['forecast_factor'] == '2'
    assert Decimal(result['remaining_life_years']) == Decimal('12')
    assert Decimal(result['mawp_MPa']) > Decimal(result['forecast_mawp_MPa'])


def test_workspace_pressure_preserves_month_only_inspection_date():
    rule, inputs = CASES[-1]
    result = outputs('10', '4', '.5', '2026-01', rule=rule, design_inputs=inputs,
                     allowance_mm='0', interval_fraction='.25', interval_cap_years='10',
                     forecast_factor='2', inspection_pressure=True)
    assert result['due_date'] == '2029-01'
    assert result['trace']['due_date']['rounding'] == 'floor whole months'
    assert result['forecast_mawp_MPa'] is not None


def test_api570_returns_zero_life_and_withholds_forecast_at_required_wall():
    rule, inputs = CASES[-1]
    result = outputs('4', '4', '.5', '2026-01', rule=rule, design_inputs=inputs,
                     interval_fraction='.5', interval_cap_years='10', inspection_pressure=True)
    assert result['remaining_life_years'] == '0'
    assert result['forecast_mawp_MPa'] is None


def test_b313_bend_pressure_varies_by_wall_position():
    from evaluator.engineering.fitting_review import bend_pressure_psi

    inputs = dict(wall_mm='8', allowance_mm='1', outside_diameter_in='8',
                  radius_in='12', stress_psi='20000', quality='1', weld='1', coefficient='.4')
    inside = bend_pressure_psi(position='intrados', **inputs)
    outside = bend_pressure_psi(position='extrados', **inputs)
    assert float(inside) == pytest.approx(1133.60, abs=.02)
    assert outside > inside
    with pytest.raises(ValueError, match='D/6'):
        bend_pressure_psi(position='intrados', **dict(inputs, wall_mm='40'))


@pytest.mark.parametrize(
    'depth_mm,length_mm,safety_factor,expected_stress_psi,clears_example_pressure',
    [
        pytest.param('1.524', '203.2', '1.39', 55563, True, id='G-BENCH-04-isolated-pit'),
        pytest.param('4.826', '251.46', '1.39', 36411, False, id='G-BENCH-05-reviewed-cluster'),
        pytest.param('3.175', '152.4', '1.39', 49416, False, id='A-5-higher-safety-factor'),
        pytest.param('3.175', '152.4', '1.25', 49416, True, id='G-BENCH-06-direct-measurement'),
        pytest.param('3.97002', '152.4', '1.25', 45406, False, id='G-BENCH-07-ili-uncertainty'),
    ],
)
def test_modified_b31g_level_one_matches_published_examples(
    depth_mm, length_mm, safety_factor, expected_stress_psi, clears_example_pressure,
):
    from evaluator.engineering.pipeline_corrosion import modified_level_one

    result = modified_level_one(
        outside_diameter_in='24', nominal_wall_mm='7.9502',
        depth_mm=depth_mm, length_mm=length_mm, flow_stress_psi='62000',
        safety_factor=safety_factor, applicability_reference='B31G-2023 A-4 through A-6',
    )
    # Printed intermediate values are rounded. Calculate from the original dimensions.
    assert float(result['failure_stress_psi']) == pytest.approx(expected_stress_psi, abs=50)
    assert (float(result['defect_screening_pressure_psi']) > 976) == clears_example_pressure


def test_modified_b31g_level_one_requires_supported_depth_and_scope_evidence():
    from evaluator.engineering.pipeline_corrosion import modified_level_one

    inputs = dict(outside_diameter_in='24', nominal_wall_mm='7.9502', depth_mm='3.175',
                  length_mm='152.4', flow_stress_psi='62000', safety_factor='1.39',
                  applicability_reference='B31G-2023 A-5 single-pit example')
    with pytest.raises(ValueError, match='80%'):
        modified_level_one(**dict(inputs, depth_mm='7'))
    with pytest.raises(ValueError, match='applicability'):
        modified_level_one(**dict(inputs, applicability_reference=''))


def test_bend_summary_withholds_partial_coverage_and_uses_lowest_position():
    from evaluator.engineering.fitting_review import BEND_COVERAGE, summarize_bends

    def row(position, pressure):
        return dict(current_id=position, location=position, inspection_date='2026-01-01',
                    input_trace={'overrides': {'bend_tag': 'B-1'}},
                    fitting_check=dict(bend_position=position, bend_pressure_psi=pressure,
                                       projection_years='1', bend_design_reference='Reviewed UT map'))

    rows = [row(position, '800' if position == 'tangent_end' else '900') for position in sorted(BEND_COVERAGE)]
    partial = [item for item in rows if item['current_id'] != 'tangent_end']
    summarize_bends(partial)
    assert partial[0]['bend_summary']['pressure_psi'] is None
    assert 'tangent_end' in partial[0]['bend_summary']['issues'][0]
    summarize_bends(rows)
    assert rows[0]['bend_summary']['pressure_psi'] == '800'
    assert rows[0]['bend_summary']['governing'][0]['position'] == 'tangent_end'


def test_fitting_qualification_uses_documented_steps_without_extrapolation():
    from evaluator.engineering.fitting_review import qualified_pressure_psi

    schedule = '3,600\n5,800\n8,1000'
    assert qualified_pressure_psi('5', schedule)['pressure_psi'] == '800'
    assert qualified_pressure_psi('7.9', schedule)['pressure_psi'] == '800'
    assert qualified_pressure_psi('10', schedule)['pressure_psi'] == '1000'
    with pytest.raises(ValueError, match='does not support'):
        qualified_pressure_psi('2.9', schedule)
    with pytest.raises(ValueError, match='strictly ascending'):
        qualified_pressure_psi('10', '5,800\n8,700')
