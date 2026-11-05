# Gate 1: reference-workbook discovery package

## Artifacts

- [Separator XLSX logic and formula inventory](evaluation_logic_separator_204.md)
- [Separator XLSM logic and formula inventory](evaluation_logic_separator_204_xlsm.md)
- [TL-B logic and formula inventory](evaluation_logic_tlb.md)
- Exhaustive formula-leaf input inventories: [Separator XLSX](evaluation_inputs_separator_204.csv), [Separator XLSM](evaluation_inputs_separator_204_xlsm.csv), [TL-B](evaluation_inputs_tlb.csv)
- Representative formula traces: [`docs/traces/`](traces/)
- Recursive trace utility: [`tools/trace_row.py`](../tools/trace_row.py)

All three original workbooks were read without saving. Every formula cell had a cached value (including cached Excel errors). The two Separator workbooks are not identical: their formula counts are 998 (XLSX) and 1,043 (XLSM). TL-B has 5,163 formula cells. Defined names: zero in all workbooks.

## Discovery findings

1. **The workbook logic has no lookup functions or named-range tables.** Formulas use arithmetic, `MAX`, `MIN`, `IF`, `AND`, and `ISNUMBER` (the latter appears in the Separator XLSM preview sheet). `ISNUMBER` is outside the function list in the supplied template plan and must be added deliberately if those preview formulas are in the reproduction scope. Allowable stresses, dimensions, factors, materials, dates, corrosion allowance, thicknesses, and code selections are typed into workbook cells. The source provenance for those values is not embedded in the workbook.
2. **Time conventions differ.** Several TL-B elapsed-time formulas divide date differences by 365. A Separator comparison-preview formula uses 365.25. Separator 2026 due-date formulas add 365 days. These are distinct sheet behaviors and cannot be replaced with a single global convention.
3. **Code / edition labels need an explicit decision.** TL-B evaluation sheets identify ASME B31.8-2020, while the available local PDF is B31.8-2025. The B31.3 TL-B sheet says API 570 and ASME B31.3 but does not state editions; local references are API 570 E5 with Addendum 1 and B31.3-2024. Separator 2026 labels its basis “last Edition of API-510 & ASME-VIII DIV-1” without editions; local references are API 510 E11 with errata and VIII-1-2025. No B31.4 calculation sheet was found. API RP 574 appears in a TL-B column label for structural thickness, but no lookup formula/table is present.
4. **The workbook contains formula irregularities and cached errors.** Each logic document groups formula cells by column and normalized relative pattern, listing the cell addresses so singleton formulas and mixed patterns are visible. Cached `#DIV/0!` / `#VALUE!` results are called out in each workbook report. Examples include zero time/rate denominators and text where formulas expect numeric readings. These are reported as found; none were corrected.
5. **The outputs include decision/status text.** Some TL-B sheets contain a formula returning “Safe” or “Reduce Interval, Otherwise Derate. Repair if Derate is NA”. Such outputs exist in the references and must be inventoried, but this discovery does not authorize adding new verdicts or generalizing them to other methods.
6. **Current provenance fails the proposed rule.** The exhaustive CSVs identify each literal cell that feeds a formula, its value/type, and consuming outputs. None of those workbook literals has an in-file source/author record. Code-table matches cannot yet be asserted from cell values alone.

## UNMAPPED items

- Exact code clause and edition for every formula output unless a sheet header states it. Title text is not enough to validate applicability.
- B31.8-2020 formulas against the only local B31.8-2025 PDF; whether the 2020 workbook logic or available 2025 reference governs the template.
- API 510 / VIII-1 edition on the Separator 2026 evaluation sheet.
- API 570 / B31.3 edition on the TL-B August 2023 evaluation sheet.
- Source table/page for manually typed stress, material, joint/quality factors, pipe size, nominal thickness, and selected rate values.
- The owner-approved reference rows for component types and edge cases; workbook layouts contain straight-pipe sections and component/band labels, but row approval and any intended geometry-specific scope needs Ahmed’s review.
- Whether text outputs in the workbook are within the required reproduction scope. (They are formula outputs and currently included in the formula inventory.)

## Gate 1 decision

**Approved to proceed by the user:** “Forget the code year work with what you have.” Continue using the workbook formulas as the authoritative behavior and the locally available code PDFs as the available reference material. Do not block on resolving the workbook/PDF edition-year differences. Keep those differences recorded as provenance limitations, and do not rewrite formula behavior to make editions appear to match.
