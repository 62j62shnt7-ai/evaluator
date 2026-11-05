#!/usr/bin/env python3
"""Run each reference workbook template and write cell-level CSV/HTML reports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluator.template_engine import reproduce_workbook

PAIRS = (
    ("separator_204_xlsx_v1.json", "Separator-204 Inspection Report.xlsx"),
    ("separator_204_xlsm_v1.json", "Separator-204 Inspection Report.xlsm"),
    ("tlb_v1.json", "TL-B from SAG Gas MFD to GP.xlsx"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=ROOT / "sources", help="folder containing workbooks/")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/reproduction")
    args = parser.parse_args()
    templates = ROOT / "src/evaluator/data/templates"
    failed = False
    for template_name, workbook_name in PAIRS:
        template_path = templates / template_name
        workbook_path = args.sources / "workbooks" / workbook_name
        report = reproduce_workbook(template_path, workbook_path, args.output)
        mismatch_count = len(report.mismatches)
        missing_count = len(report.cached_values_missing)
        print(
            f"{workbook_name}: {len(report.comparisons) - mismatch_count}/{len(report.comparisons)} "
            f"matched; {mismatch_count} mismatches; {missing_count} missing formula caches"
        )
        failed |= bool(mismatch_count or missing_count)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
