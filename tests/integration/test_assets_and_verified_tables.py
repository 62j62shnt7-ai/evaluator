from decimal import Decimal

import pytest

from evaluator.engineering.verified_tables import ReferenceLookupError, VerifiedTables
from evaluator.storage.assets import AssetStore
from tests.source_config import SOURCE_ROOT


def test_asset_inputs_are_versioned_reused_and_audited(tmp_path):
    store = AssetStore(tmp_path / "project.sqlite")
    store.create_asset("LINE-01", "Line 01", who="Ahmed")
    first = store.set_input("LINE-01", "design_pressure_psi", Decimal("1500"), "psi", who="Ahmed", why="Initial approved design basis")
    second = store.set_input("LINE-01", "design_pressure_psi", Decimal("1450"), "psi", who="Ahmed", why="Documented design change")
    assert (first, second) == (1, 2)
    assert store.inputs("LINE-01")["design_pressure_psi"].value == "1450"
    history = store.history("LINE-01", "design_pressure_psi")
    assert [item["version"] for item in history] == [1, 2]
    assert history[-1]["old_value"] == "1500"
    assert history[-1]["reason"] == "Documented design change"


def test_asset_updates_require_author_reason_and_verified_code_table_provenance(tmp_path):
    store = AssetStore(tmp_path / "project.sqlite")
    store.create_asset("V-1", "Vessel 1", who="Ahmed")
    with pytest.raises(ValueError, match="author, and change reason"):
        store.set_input("V-1", "design_pressure_psi", 100, "psi", who="", why="")
    with pytest.raises(ValueError, match="verification status and a source SHA-256"):
        store.set_input("V-1", "stress", 20000, "psi", who="Ahmed", why="Look up", source_type="code_table")


def test_reference_tables_require_exact_match_and_withhold_discrepant_rows():
    code_dir = SOURCE_ROOT / "codes"
    if not (code_dir / "B31_3_2024.pdf").is_file():
        pytest.skip("Original B31.3 reference PDF is unavailable")
    tables = VerifiedTables(code_dir=code_dir)
    row = tables.allowable_stress("ASTM A106 Grade B", "pipe", "ASME B31.3", "2024", "300")
    assert row["S_allow_psi"] == "20000"
    assert row["provenance"]["source_type"] == "code_table"
    assert row["provenance"]["source_sha256"] == row["source_sha256"]
    with pytest.raises(ReferenceLookupError, match="available exact temperatures"):
        tables.allowable_stress("ASTM A106 Grade B", "pipe", "ASME B31.3", "2024", "350")
    with pytest.raises(ReferenceLookupError, match="No exact API RP 574"):
        tables.pipe_dimension("ferritic", "2.5", "40")
    with pytest.raises(ReferenceLookupError, match="withheld for source discrepancy"):
        tables.pipe_dimension("ferritic", "14", "140")


def test_annular_tables_are_available_offline(monkeypatch, tmp_path):
    from evaluator.engineering.annular_reference import annular_minimum
    from decimal import Decimal

    monkeypatch.setenv('UT_EVALUATOR_CODES', str(tmp_path))
    for gravity, expected, table in (('.9', '4.32', 'API 653 Table 4.5a'),
                                     ('1', '6', 'API 650 Table 5.1a')):
        value, source = annular_minimum(Decimal(gravity), Decimal('19'), Decimal('160'))
        assert value == Decimal(expected)
        assert source['reference'].startswith(table)
        assert len(source['source_sha256']) == 64


def test_b318_packaged_smys_respects_grade_and_manufacturing_form():
    from evaluator.engineering.reference_rules import gas_pipe_smys

    assert gas_pipe_smys('API Spec 5L Grade A25', 'CW') == 25400
    assert gas_pipe_smys('API 5L A25', 'SAWL') is None
    assert gas_pipe_smys('API 5L X80', 'SAWL') == 80500
    assert gas_pipe_smys('API 5L X80', 'CW') is None
    assert gas_pipe_smys('API 5L X46', 'SMLS') == 46400


@pytest.mark.parametrize('material,geometry,code,edition,temp,form,psi', [
    ('ASTM A420 WPL6','elbow','ASME B31.3','2024','400',None,19900),
    ('ASTM A234 WPC','tee','ASME B31.3','2024','300',None,23300),
    ('ASTM A403 WP304L','reducer','ASME B31.3','2024','400',None,15800),
    ('ASTM A403 WP316L','elbow','ASME B31.3','2024','400',None,15700),
    ('SA-516 Grade 65','shell','ASME VIII-1','2025','302','plate',18564.83),
    ('SA-515 Grade 70','ellipsoidal_head_2to1','ASME VIII-1','2025','302','plate',20015.21),
])
def test_expanded_offline_material_rows(material, geometry, code, edition, temp, form, psi):
    from evaluator.engineering.references import material_stress

    match = material_stress(material, geometry, code, edition, temp, form)
    assert float(match['S_allow_psi']) == pytest.approx(psi, abs=.02)
    assert material_stress(material, geometry, code, edition, '351', form) is None
    assert material_stress(material, geometry, code, '2023', temp, form) is None
    if form:
        assert material_stress(material, geometry, code, edition, temp, 'pipe') is None


def test_vessel_nozzle_stress_requires_section_and_condition_records():
    from evaluator.engineering.references import material_stress

    def lookup(material, form, **conditions):
        return material_stress(material, 'nozzle', 'ASME VIII-1', '2025', '302', form, **conditions)

    condition = {'material_condition_reference': 'Reviewed MTR with treatment record'}
    assert lookup('SA-106 Grade B', 'pipe')['S_allow_MPa'] == '118'
    assert lookup('SA-105', 'forging') is None
    assert lookup('SA-105', 'forging', **condition)['S_allow_MPa'] == '138'
    assert lookup('SA-350 LF2', 'forging', **condition) is None
    assert lookup('SA-182 F316', 'forging', **condition) is None
    assert lookup('SA-182 F316', 'forging', material_thickness_mm='130') is None
    for thickness, line in [('130', 'line 8;'), ('130.01', 'line 45;')]:
        row = lookup('SA-182 F316', 'forging', material_thickness_mm=thickness, **condition)
        assert line in row['reference']
        assert row['S_allow_MPa'] == '107'
