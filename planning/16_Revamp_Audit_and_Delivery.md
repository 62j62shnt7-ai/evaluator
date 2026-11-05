# UT evaluator revamp audit and delivery

Updated 5 November 2026.

## Delivered workflow

The default local page is now a three-screen workflow: import and inspect one workbook, configure and evaluate selected component readings, then review and export results. The project keeps its Python standard-library HTTP server, SQLite revision history, existing import adapters and whole-workbook evidence. Detailed prior workflows remain available under **Detailed tools**.

The new workspace detects the supplied Separator and TL-B table layouts from workbook structure rather than filenames. It opens the newest measured campaign, and proposes the latest earlier reading at each exact source location while retaining each observation's original campaign and date. A fixed earlier campaign remains selectable. Ambiguous physical locations and conflicting dates stay visible for reviewer resolution. Confirmations and overrides are scoped to the selected rows and evaluation scenario; changes are revisioned and undoable.

The batch editor supports component and segment selection, filters, inline previous/current thickness corrections, source-profile proposals, per-row exceptions, reusable configurations, reference-driven dimensions, code/edition, pressure, temperature, minima and factors. Context changes invalidate inherited material properties and dependent saved results. The results view offers completed source-form copies, a scoped evidence export and saved line evaluations.

## Source review and bounded references

Inspected source inventory includes three actual workbooks (Separator XLSX, Separator XLSM and TL-B XLSX) and these supplied references: API 510 E11 with errata, API 570 E5 with Addendum 1, API RP 574 E5 with Addendum 1, ASME B31.3-2024, B31.4-2025, B31.8-2025, VIII-1-2025 and II-D Metric 2025. Source files are retained unchanged.

API 574 Annex B dimensions include 229 checked entries: 148 ferritic and 81 stainless. Each lookup carries the source/page trace. Ferritic NPS 14 Schedule 140 and stainless NPS 1/8 Schedule 80S have conflicting inch/mm values in the source and are deliberately unavailable to automatic lookup.

The checked stress lookup is deliberately narrow: B31.3-2024 Table A-1C, ASTM A106 Grade B straight pipe and A234 WPB fittings at exact 100, 200, 300, 400, 500 and 600°F table points. No interpolation or substitution across code, edition, temperature or product form is performed. Other contexts remain unverified and require a checked record or explicit reviewed input. The application does not claim a complete material-property database.

The existing Decimal calculation paths remain draft candidates. B31.3 straight-pipe pressure thickness uses the checked 304.1.2 equation within its stated limits; the existing limited B31.4, B31.8 and VIII paths remain subject to edition and input gates. Unsupported fitting/nozzle methods are withheld. A provided governing minimum can support life arithmetic while pressure assessment remains unresolved. Increasing readings are flagged and excluded from life unless a positive manual rate is explicitly reviewed; zero rates do not produce infinite life. No PASS or equipment fitness conclusion is emitted.

## Source-form exports

Completed XLSX/XLSM forms are built by patching copies of the original OOXML package. Export logic preserves original styles, drawing/media parts and VBA payloads, clears stale or unsupported mapped outputs, adds a `UT Calculation Ledger`, labels the result as draft and removes stale formula calculation-chain references. The original workbooks and source packages are not rewritten. Exported unselected scenarios are not represented as evaluated.

## Verification and evidence

- Project suite: 114 tests passed in the final run after the reviewed geometry warning fix.
- Actual-source acceptance: all three supplied workbooks, independent rate/life arithmetic, withholding of increasing-reading life and unsupported geometry pressure, completed-form loading, style/media/VBA preservation, report-archive hashes and original source hashes.
- Browser smoke walkthrough: import a real TL-B source, confirm selected history, apply dimensions to selected rows, undo, evaluate and download a populated form with the calculation ledger.
- Reproduce the all-workbook acceptance with `PYTHONPATH=src .venv/bin/python tools/validate_revamped_workspace.py /path/to/fresh-validation-folder`.
- Machine-readable evidence: `evidence/revamped_workspace_acceptance_verified/verification.json`.

## Remaining engineering and platform boundaries

These checks establish software behavior and source preservation, not engineering approval. The workbook material/property records can conflict; original report dates and measurement dates can disagree; the supplied sample scenarios may name code editions absent from the supplied edition package. Physical continuity, applicable code/edition, product specification, material identity, all required loads and governing minima still require qualified review. The stress lookup and pressure-rule coverage are not complete for the supplied codes. Image-only/shape content and clean Windows first-run acceptance also remain outside this completed verification. Every numerical result is labelled **DRAFT / NOT VALIDATED**.
