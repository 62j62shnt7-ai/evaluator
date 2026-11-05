from pathlib import Path

import pytest

from evaluator.template_engine import reproduce_workbook
from tests.source_config import SOURCE_ROOT

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("template", "workbook", "expected_formula_count"),
    [
        ("separator_204_xlsx_v1.json", "Separator-204 Inspection Report.xlsx", 998),
        ("separator_204_xlsm_v1.json", "Separator-204 Inspection Report.xlsm", 1043),
        ("tlb_v1.json", "TL-B from SAG Gas MFD to GP.xlsx", 5163),
    ],
)
def test_reference_formula_cells_match_cached_values(template, workbook, expected_formula_count):
    report = reproduce_workbook(
        ROOT / "src/evaluator/data/templates" / template,
        SOURCE_ROOT / "workbooks" / workbook,
    )
    assert len(report.comparisons) == expected_formula_count
    assert report.cached_values_missing == ()
    assert report.mismatches == ()
