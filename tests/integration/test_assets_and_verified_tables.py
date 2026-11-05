from decimal import Decimal

import pytest

from evaluator.engineering.verified_tables import ReferenceLookupError, VerifiedTables
from evaluator.storage.assets import AssetStore


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
    tables = VerifiedTables()
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
