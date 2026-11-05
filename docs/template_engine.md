# Workbook formula templates and calculation engine

## Phase 2: versioned template format

Templates are JSON data files under `src/evaluator/data/templates/`, separate from the Python engine. Each template binds to the exact source workbook SHA-256 and stores a version, formula sheets, output node IDs, and source-cell nodes. Nodes record their label, unit, source cell(s), code reference status, and required provenance. Formula expressions retain the workbook’s expression string and are parsed with `openpyxl`'s tokenizer plus the engine’s restricted parser. There is no `eval()` path.

The accompanying [`template.schema.json`](../src/evaluator/data/templates/template.schema.json) documents the JSON shape; `validate_template()` enforces it at load time and parses every formula before evaluation. Unsupported functions and invalid references stop template loading with the node and reason.

Generated templates:

- [`separator_204_xlsx_v1.json`](../src/evaluator/data/templates/separator_204_xlsx_v1.json): 2,277 nodes, 667 terminal formula outputs.
- [`separator_204_xlsm_v1.json`](../src/evaluator/data/templates/separator_204_xlsm_v1.json): 2,382 nodes, 682 terminal formula outputs.
- [`tlb_v1.json`](../src/evaluator/data/templates/tlb_v1.json): 9,365 nodes, 2,008 terminal formula outputs.

Each formula cell is represented. Formula nodes used by other formulas are `formula`; terminal formula cells are `output`; referenced non-formula cells are `input`. Workbook-derived inputs require `sheet` provenance. Code references preserve explicit code/edition text from the source sheet and leave unspecified clauses or editions unmapped. No lookup table is present in these source sheets, so the templates do not invent one.

Rebuild a template after a reviewed workbook change with:

```sh
PYTHONPATH=src .venv/bin/python tools/build_workbook_templates.py /path/to/reference.xlsx template_id
```

## Phase 3: evaluation behavior

The engine builds a cell dependency graph, rejects missing dependencies and cycles, checks that each input has its required provenance, and evaluates formula nodes in topological order with `Decimal`. Each formula trace records its expression, direct dependencies, values, source cells, and input provenance. A complete workbook trace is assembled by following those node references. Missing values, unsupported functions, invalid numeric text, divide-by-zero, and unverified lookup nodes remain visible errors.

Supported functions: `MAX`, `MIN`, `IF`, `AND`, `OR`, `ROUND`, `ROUNDUP`, `ROUNDDOWN`, `ABS`, `IFERROR`, and `ISNUMBER`. `ISNUMBER` is included because the Separator XLSM contains it. No `VLOOKUP`, `HLOOKUP`, `INDEX`, `MATCH`, or `XLOOKUP` was found. Arithmetic, comparisons, unary signs, cell references, ranges, and quoted sheet references are supported.

Excel behavior implemented for this workbook set includes blank-to-zero arithmetic, numeric text coercion in arithmetic, ignored text/blank range values for `MIN`/`MAX`, Excel errors, lazy `IF`/`IFERROR`, Decimal half-up `ROUND`, away-from-zero `ROUNDUP`, toward-zero `ROUNDDOWN`, and Excel date serial arithmetic. Date inputs carry their source workbook, sheet, cell, and SHA-256. Per-sheet date formulas are retained as written (including 365- and 365.25-day conventions).

## Phase 4: reproduction harness

Run all supplied reference workbooks and create per-cell CSV and HTML reports:

```sh
PYTHONPATH=src .venv/bin/python tools/reproduce_templates.py
```

The harness refuses a source workbook whose SHA-256 does not match its template and stops reporting a formula as reproduced if its cached value is missing. It compares every formula cell, not only terminal outputs. Numeric comparisons use a relative tolerance of `5e-15` to recognize Excel’s 15-significant-digit calculation precision while retaining each unrounded difference in the report. Cached date values are compared at millisecond precision, the precision available after openpyxl reads the workbook’s date cache.

Current reproduction run:

| Reference workbook | Formula cells | Matched | Mismatches | Missing cached values |
|---|---:|---:|---:|---:|
| Separator XLSX | 998 | 998 | 0 | 0 |
| Separator XLSM | 1,043 | 1,043 | 0 | 0 |
| TL-B XLSX | 5,163 | 5,163 | 0 | 0 |

Reports with per-cell expressions, dependency values, and provenance are in `outputs/reproduction/`. The engine and harness have not been applied to readings-only workbooks; that remains behind Gate 2 approval.
