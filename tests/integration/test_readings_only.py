from hashlib import sha256

from openpyxl import Workbook, load_workbook

from evaluator.app_services import ProjectService
from evaluator.readings_only import ReadingsOnlyService


def test_custom_layout_imports_pair_with_cell_provenance_and_refuses_missing_inputs(tmp_path):
    workbook = tmp_path / "readings.xlsx"
    wb = Workbook(); ws = wb.active; ws.title = "UT"
    ws.append(["Point", "2020-01-01", "2025-01-01", "Previous", "Current"])
    ws.append(["Line 1 / CML 2", None, None, 8.2, 7.8])
    wb.save(workbook)

    service = ProjectService(tmp_path / "project")
    source = service.add_source(workbook)
    service.inspect(source.sha256)
    service.assets.create_asset("LINE-1", "Line 1", who="Reviewer")
    intake = ReadingsOnlyService(service)
    profile = intake.save_custom_profile({
        "id": "test_layout", "label": "Test layout", "header_row": 1, "first_data_row": 2,
        "location_columns": ["A"], "previous_thickness_column": "D", "current_thickness_column": "E",
        "previous_date_cell": "B1", "current_date_cell": "C1", "unit": "mm",
    }, who="Reviewer", confirmed=True)
    assert profile["confirmed_by"] == "Reviewer"
    assert intake.import_sheet(source.sha256, "UT", "test_layout", "LINE-1")["imported_pairs"] == 1
    pair_row = intake.pairs(source.sha256)[0]
    assert pair_row["pair"]["previous_thickness_mm_source"] == {"sheet": "UT", "cell": "D2"}
    assert pair_row["pair"]["current_date_source"] == {"sheet": "UT", "cell": "C1"}

    result = intake.evaluate(pair_row["pair_id"], "tlb_b31_3_process_piping")
    assert result["status"] == "missing_inputs"
    assert any("design_pressure_psi" in value for value in result["missing_inputs"])
    assert result["status_label"] == "DRAFT / NOT VALIDATED"


def test_export_is_a_distinct_copy_with_results_and_ledger(tmp_path):
    workbook = tmp_path / "readings.xlsx"
    wb = Workbook(); ws = wb.active; ws.title = "UT"
    ws.append(["Point", "2020-01-01", "2025-01-01", "Previous", "Current"])
    ws.append(["Line 1", None, None, 8.2, 7.8]); wb.save(workbook)
    original_hash = sha256(workbook.read_bytes()).hexdigest()
    service = ProjectService(tmp_path / "project")
    source = service.add_source(workbook); service.inspect(source.sha256)
    service.assets.create_asset("LINE-1", "Line 1", who="Reviewer")
    intake = ReadingsOnlyService(service)
    intake.save_custom_profile({"id":"test","label":"Test","header_row":1,"first_data_row":2,
        "location_columns":["A"],"previous_thickness_column":"D","current_thickness_column":"E",
        "previous_date_cell":"B1","current_date_cell":"C1","unit":"mm"},who="Reviewer",confirmed=True)
    intake.import_sheet(source.sha256,"UT","test","LINE-1")
    pair = intake.pairs(source.sha256)[0]
    intake.evaluate(pair["pair_id"],"tlb_b31_3_process_piping")
    target = intake.export_copy(source.sha256)
    exported = load_workbook(target, data_only=False)
    try:
        assert "Results" in exported.sheetnames
        assert "Calculation Ledger" in exported.sheetnames
        assert exported["Results"]["A1"].value == "DRAFT / NOT VALIDATED"
    finally:
        exported.close()
    assert target != workbook
    assert sha256(workbook.read_bytes()).hexdigest() == original_hash


def test_custom_layout_requires_explicit_confirmation_and_mm_units(tmp_path):
    from evaluator.importing.layout_profiles import validate_custom_profile
    import pytest
    profile = {"id":"x","label":"X","header_row":1,"first_data_row":2,"location_columns":["A"],
               "previous_thickness_column":"B","current_thickness_column":"C","previous_date_cell":"B1",
               "current_date_cell":"C1","unit":"mm"}
    with pytest.raises(ValueError, match="exactly"):
        validate_custom_profile({**profile, "unexpected": True})
    with pytest.raises(ValueError, match="bind thickness in mm"):
        validate_custom_profile({**profile, "unit": "in"})


def test_source_template_evaluates_with_audited_asset_and_reading_inputs(tmp_path):
    workbook = tmp_path / "readings.xlsx"
    wb = Workbook(); ws = wb.active; ws.title = "UT"
    ws.append(["Point", "Previous date", "Current date", "Previous", "Current"])
    ws.append(["Line 1", "2020-01-01", "2025-01-01", 8.2, 7.8]); wb.save(workbook)
    service = ProjectService(tmp_path / "project")
    source = service.add_source(workbook); service.inspect(source.sha256)
    service.assets.create_asset("LINE-1", "Line 1", who="Reviewer")
    for key, value, unit in [
        ("design_pressure_psi", 500, "psi"), ("outside_diameter_in", 8.625, "in"),
        ("allowable_stress_psi", 20000, "psi"), ("structural_minimum_mm", 4, "mm"),
        ("selected_corrosion_rate_mm_y", .1, "mm/year"),
    ]:
        service.assets.set_input("LINE-1", key, value, unit, who="Reviewer", why="Test engineering basis")
    intake = ReadingsOnlyService(service)
    intake.save_custom_profile({"id":"test","label":"Test","header_row":1,"first_data_row":2,
        "location_columns":["A"],"previous_thickness_column":"D","current_thickness_column":"E",
        "previous_date_cell":"B2","current_date_cell":"C2","unit":"mm"},who="Reviewer",confirmed=True)
    intake.import_sheet(source.sha256,"UT","test","LINE-1")
    pair = intake.pairs(source.sha256)[0]
    result = intake.evaluate(pair["pair_id"],"tlb_b31_3_process_piping")
    assert result["status"] == "evaluated"
    assert len(result["outputs"]) == 9
    assert result["trace"]
