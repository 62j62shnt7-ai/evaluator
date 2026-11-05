# Gate 2: reference formula reproduction

The user approved proceeding from Gate 1 using the workbook formulas and locally available code references, without blocking on code-year differences. The three versioned templates were then evaluated against their exact source workbooks. The source files were read-only; no original workbook or PDF was saved or changed.

## Result

| Workbook | Cached formula cells checked | Matched | Mismatches | Missing caches |
|---|---:|---:|---:|---:|
| Separator XLSX | 998 | 998 | 0 | 0 |
| Separator XLSM | 1,043 | 1,043 | 0 | 0 |
| TL-B XLSX | 5,163 | 5,163 | 0 | 0 |
| **Total** | **7,204** | **7,204** | **0** | **0** |

The comparison uses a relative tolerance of `5e-15` for numeric formula caches, corresponding to Excel's 15-significant-digit numeric precision. Date caches are compared at one millisecond, the precision exposed by the cached date values returned by openpyxl. Reports retain the raw numeric difference for each cell. There are no formula cells without cached values.

## Cell reports

Each CSV and HTML report contains workbook, sheet, cell, expected cached value, calculated value, difference, match state, and dependency trace with provenance.

- [Separator XLSX CSV](../outputs/reproduction/separator_204_inspection_report_xlsx_reproduction.csv) · [HTML](../outputs/reproduction/separator_204_inspection_report_xlsx_reproduction.html)
- [Separator XLSM CSV](../outputs/reproduction/separator_204_inspection_report_xlsm_reproduction.csv) · [HTML](../outputs/reproduction/separator_204_inspection_report_xlsm_reproduction.html)
- [TL-B CSV](../outputs/reproduction/tl_b_from_sag_gas_mfd_to_gp_xlsx_reproduction.csv) · [HTML](../outputs/reproduction/tl_b_from_sag_gas_mfd_to_gp_xlsx_reproduction.html)

Reproduce the reports with `PYTHONPATH=src .venv/bin/python tools/reproduce_templates.py`. Golden tests run automatically when the source workbooks are present and skip with a configured-source-path reason otherwise.

## Gate 2 review

All formula cells in all three reference workbooks reproduce at the documented cache precision. No discrepancies remain to explain. The engine has **not** been applied to readings-only workbooks. That work starts only after Gate 2 approval, as required by the implementation plan.
