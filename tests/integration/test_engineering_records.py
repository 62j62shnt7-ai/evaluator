from hashlib import sha256
from pathlib import Path
from decimal import Decimal
from evaluator.engineering.records import import_records, identity
from evaluator.engineering.batch_rules import convert, outputs

SOURCES = Path(__file__).resolve().parents[2] / 'sources/workbooks'

def test_separator_records_preserve_provenance():
    path = SOURCES / 'Separator-204 Inspection Report.xlsx'
    digest = sha256(path.read_bytes()).hexdigest()
    rows = import_records(path)
    assert len(rows) == 38
    first, nozzle = rows[0], rows[19]
    assert first['fields']['required_thickness_mm']['cell'] == 'N5'
    assert first['fields']['required_thickness_mm']['kind'] == 'formula'
    assert isinstance(first['fields']['required_thickness_mm']['cached'], (int, float))
    assert nozzle['fields']['required_thickness_mm']['cell'] == 'S27'
    assert nozzle['fields']['current_mm']['value'] == 12.5
    assert first['inspection_date'].startswith('2026-10-22')
    assert first['code_edition'] is None
    assert first['interval_policy'] == {'fraction': .5, 'cap_years': 10.0}
    assert first['fields']['selected_interval_years']['kind'] == 'formula'
    assert first['fields']['scheduled_date']['cached'].startswith('2027-10-22')
    assert first['forecast_policy']['horizon_basis'] == 'fixed_years'
    assert first['forecast_policy']['forecast_years'] == 1
    assert first['forecast_policy']['factor'] == 2
    assert len({r['id'] for r in rows}) == 38
    assert rows == import_records(path)
    assert sha256(path.read_bytes()).hexdigest() == digest

def test_pipeline_scenarios_preserve_projections_and_pressure_only():
    path = SOURCES / 'TL-B from SAG Gas MFD to GP.xlsx'
    digest = sha256(path.read_bytes()).hexdigest()
    rows = import_records(path)
    june = [r for r in rows if r['sheet'] == 'Evaluation 6-2025']
    april = [r for r in rows if r['sheet'] == 'Evalation 4-2026']
    assert len(june) == len(april) == 80
    assert all(r['fields']['current_mm']['kind'] == 'formula' for r in april)
    assert all(r['fields']['required_thickness_mm']['kind'] == 'missing' for r in june)
    assert june[0]['fields']['pressure_thickness_mm']['cell'] == 'I7'
    assert june[0]['fields']['SMYS_psi']['value'] == 52000
    assert next(r for r in june if r['row'] == 62)['fields']['SMYS_psi']['value'] == 35000
    assert june[0]['fields']['adopted_rate_mm_year']['cell'] == 'S7'
    assert april[0]['fields']['adopted_rate_mm_year']['value'] == .15
    assert april[0]['fields']['selected_interval_years']['kind'] == 'formula'
    assert april[0]['forecast_policy']['horizon_basis'] == 'selected_interval'
    selected = next(r for r in april if r['row'] == 15)
    assert selected['fields']['selected_interval_years']['value'] == 5
    assert selected['fields']['selected_interval_years']['kind'] == 'literal'
    assert selected['interval_policy_basis'] == 'neighbor_formula'
    assert selected['interval_policy']['fraction'] == .5
    assert selected['interval_policy']['cap_years'] == 10
    assert selected['fields']['forecast_thickness_mm']['cached'] == 5.3
    assert selected['fields']['forecast_pressure_psi']['cached'] > 2000
    assert selected['schedule_candidate']['cached'].startswith('2031-04-06')

    def batch_mawp(current_mm, pressure_mm, rate, source, interval=None, manual=False):
        fields=source['fields']
        inputs={
            'D_outside_mm':str(convert(fields['D_outside_in']['value'],'in','mm')),
            'SMYS_MPa':str(convert(fields['SMYS_psi']['value'],'psi','MPa')),
            'F_class':'0.8','E_weld':'1','T_temp':'1',
        }
        result=outputs(current_mm,pressure_mm,rate,source['inspection_date'],
                       year_days='365',interval_fraction='.5',interval_cap_years='10',
                       rule='B31_8_841_1_1',design_inputs=inputs,
                       selected_interval_years=interval,
                       manual_selected_interval=manual,
                       scheduled_due_date=source['fields']['scheduled_date']['value'])
        return result

    formula_interval=next(r for r in april if r['row']==11)
    # A formula-derived interval is not a manual override. Both MAWPs use
    # remaining life even though the half-life interval is capped at ten years.
    formula_result=batch_mawp(
        formula_interval['fields']['current_mm']['value'],
        formula_interval['fields']['pressure_thickness_mm']['value'],
        formula_interval['fields']['adopted_rate_mm_year']['value'],
        formula_interval,
    )
    assert formula_result['maximum_inspection_interval_years']=='10'
    assert formula_result['mawp_MPa']==formula_result['forecast_mawp_MPa']
    assert formula_result['trace']['forecast_mawp_MPa']['horizon_basis']=='remaining_life_endpoint'

    # Row 15 inherits row 11's formula by default. The workbook's literal
    # five-year value remains a manual override candidate.
    formula_default=batch_mawp(
        selected['fields']['current_mm']['value'],
        selected['fields']['pressure_thickness_mm']['value'],
        selected['fields']['adopted_rate_mm_year']['value'],
        selected,
    )
    assert formula_default['maximum_inspection_interval_years'] is not None
    assert formula_default['inspection_interval_years']==formula_default['maximum_inspection_interval_years']
    assert formula_default['mawp_MPa']==formula_default['forecast_mawp_MPa']

    # Applying the workbook's explicit five-year override from measured 6.8 mm
    # gives 6.8 - 2*.15*5 = 5.3 mm, matching its saved forecast MAWP.
    override_result=batch_mawp('6.8','3.949669471153846','.15',selected,5,True)
    calculated_psi=convert(override_result['forecast_mawp_MPa'],'MPa','psi')
    assert abs(calculated_psi-Decimal(str(selected['fields']['forecast_pressure_psi']['value'])))<Decimal('.000001')
    assert override_result['mawp_MPa']!=override_result['forecast_mawp_MPa']
    assert june[0]['code_edition'] == '2020'
    assert june[0]['factor_candidates']['design_factor']['cell'] == 'I7'
    older = [r for r in rows if r['sheet'] == 'Eval 8-2023 - ASME B31.3']
    assert older[0]['fields']['required_thickness_mm']['cell'] == 'J8'
    assert older[0]['fields']['structural_minimum_mm']['cell'] == 'H8'
    assert older[0]['fields']['S_allow_psi']['cell'] == 'F8'
    assert len({r['fields']['pressure_thickness_mm']['value'] for r in june}) > 1
    assert len({r['fields']['adopted_rate_mm_year']['value'] for r in rows}) > 1
    assert sha256(path.read_bytes()).hexdigest() == digest

def test_identity_aliases_are_only_candidates():
    assert identity('SECTION 1 [from SAG]', 'P-22', '1', 'pipeline') == ('SECTION1', 'P22', '1')
    assert identity('CMLS', 'CAP-1', 'CML #1', 'separator') == identity('CMLS', 'Head 1', '1', 'separator')
