import pytest
from evaluator.engineering.row_example import calculate, EXAMPLE


def test_row_seven():
    r = calculate(EXAMPLE)
    assert r['elapsed_days'] == 1169
    assert r['calculated_cr'] == pytest.approx(.09366980325064124)
    assert r['required_mm'] == 4.3125
    assert r['remaining_life'] == pytest.approx(74.5971461187)
    assert r['interval'] == 10
    assert r['mawp_psi'] == pytest.approx(1782.52508872)
    assert r['result'] == 'Safe'
    assert r['next_inspection'] == '2036-11-03'


@pytest.mark.parametrize('previous', ['11.3', '11.0'])
def test_manual_fallback(previous):
    r = calculate(dict(EXAMPLE, previous_mm=previous))
    assert r['cr_used'] == .2
    assert r['cr_basis'] == 'Selected manual CR'


def test_dates_drive_rate():
    r = calculate(dict(EXAMPLE, previous_date='2025-11-06'))
    assert r['calculated_cr'] == pytest.approx(.3)
    with pytest.raises(ValueError):
        calculate(dict(EXAMPLE, previous_date=EXAMPLE['current_date']))


def test_material_alias_and_month_headers():
    r = calculate(dict(EXAMPLE, material='ASTM A106 Grade B', previous_date='2023-08', current_date='2026-11'))
    assert r['elapsed_years'] == 3.25
    assert r['cr_used'] == pytest.approx(.3 / 3.25)


def test_x52_fixed_stress_and_mawp_equality_boundary():
    r=calculate(dict(EXAMPLE,material='API 5L X52'))
    assert r['s_psi']==22000
    r=calculate(dict(EXAMPLE,previous_mm='12.3',current_mm='10.1'))
    assert r['mawp_psi']==pytest.approx(800)
    assert r['result']=='Not safe'


def test_batch_row_uses_shared_logic():
    from evaluator.batch import BatchService
    reading = lambda oid, value, dt: dict(observation_id=oid, raw_value=value, raw_unit='mm', inspection_date=dt,
        cell='K7', sheet_name='UT', source_id='source', location_candidates='["Joint 2", "Band 2"]')
    item = dict(current=reading('current','11.3','2026-11-06'), previous=reading('previous','11.6','2023-08-25'),
                pair=dict(id='pair',kind='matched',accepted=True), profile=None,candidates=[],nominal_size=None,assignment_basis='test')
    config = dict(basis='row7', row_overrides={'current':dict(P_psi='800',D_outside_in='8.625',material='A106 B',nominal_thickness_mm='12.7',structural_minimum_mm='2.8',adopted_rate_mm_year='.2')})
    service = object.__new__(BatchService)
    row = service._calculate_row(item, config)
    assert float(row['remaining_life_years']) == pytest.approx(74.5971461187)
    assert row['row7']['result'] == 'Safe'
    assert row['due_date'] == '2036-11-03'


def test_sample_style_ut_headers_import_previous_and_current(tmp_path):
    from openpyxl import Workbook
    from evaluator.importing.detect import extract
    book=Workbook();sheet=book.active;sheet.title='UT 11-2026'
    sheet['A6']='section #1'
    for column,value in enumerate(['JOINT#','BAND','DIAM.','MIN 5-2020','MIN 8-2023','MIN 11-2026','MAX','NOM.T','SCH'],1):
        sheet.cell(133,column,value)
    for column,value in enumerate([2,2,'8"',None,11.6,11.3,12,12.7,'80'],1):
        sheet.cell(134,column,value)
    path=tmp_path/'sample.xlsx';book.save(path)
    observations=extract(path,sheet.title).observations
    assert len(observations)==2
    assert [o.source.cell for o in observations]==['E134','F134']
    assert [o.inspection_date for o in observations]==['2023-08','2026-11']
    assert all(o.location_candidates==('section #1','2','2') for o in observations)
