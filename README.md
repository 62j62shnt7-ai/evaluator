# UT Inspection Evaluator

An offline, component-aware UT workspace: **import once → detect and group → batch-correct exceptions → evaluate → export**.

## Start the app

Double-click **Run UT Review.command** on macOS or **Run UT Review.bat** on Windows. Restart an older running copy after updating the source. The app opens at `http://127.0.0.1:8765` and keeps project data under `~/UT Inspection Evaluator` by default. Keep its terminal window open.

The Windows launcher provisions its embedded Python and pinned workbook reader on first setup. Subsequent use is offline. Windows first-run packaging has not been tested on a Windows machine.

For development:

```sh
PYTHONPATH=src .venv/bin/python -m evaluator --project "$HOME/UT Inspection Evaluator"
```

Python 3.12+ and openpyxl 3.1.5 are required. No new runtime dependencies, CDN assets or external services are used.

## Three-screen workflow

1. **Import & inspection.** Upload a single XLSX/XLSM containing both historical and current readings, open a saved source, or use a supplied project sample. Detection uses the actual Separator and TL-B layouts. It chooses the latest measured campaign and the latest earlier measurement available at each location, preserving each original date. You can also select one fixed previous campaign. The preview keeps source cells and flags missing/conflicting dates. Explicit date corrections are available here. Sheets with only one measured campaign remain evidence and are available through detailed comparison tools.
2. **Configure & evaluate.** The main table shows every current location plus historical exceptions. Filter by segment, geometry, text or review status. Select visible rows, select an entire component/segment from its detail drawer, or tick individual checkboxes. Apply material, geometry, size, schedule, code/edition, conditions, minima and factors together. Blank fields retain existing values. Source design proposals populate their own property/dimension tuples; reusable configurations persist across restarts. Confirm selected assignments and physical history once per batch. Edit either thickness directly in the table, use arrow keys to move vertically, and undo corrections or configuration changes. Values recalculate after saving.
3. **Results & export.** Evaluate the line to save a revision. Download a completed copy of the supplied evaluation form with an embedded calculation ledger, a scoped evidence ZIP, or all saved line evaluations together. Configuration changes invalidate saved results until reevaluation.

Click a location to inspect raw source evidence, assignment candidates, calculation formulas, units and overrides. Ambiguous mappings can be explicitly assigned in the drawer. Different engineering scenarios retain separate row overrides and confirmations.

The **Detailed tools** link retains the previous importer, history matching, standalone calculator, per-component tools, reading evidence, backups and reports. These are also available at `/legacy`, `/workflow`, and `/advanced`.

## Engineering references and boundaries

The project contains API 510 E11 with errata, API 570 E5 with Addendum 1, API RP 574 E5 (February 2024, Addendum 1 March 2025), B31.3-2024, B31.4-2025, B31.8-2025, VIII-1-2025 and II-D Metric 2025.

- **Pipe dimensions:** 229 source-checked API 574 Annex B entries: 148 ferritic and 81 stainless. Cascading table → NPS → schedule selections populate OD and nominal wall with PDF page and source hash. NPS can be suggested from recorded OD; measured UT alone never determines the specification. Two entries have inconsistent inch/mm source values and are withheld from automatic lookup: ferritic NPS 14 Schedule 140, and stainless NPS 1/8 Schedule 80S. No silent correction is made.
- **Allowable stress:** a bounded B31.3-2024 Table A-1C lookup covers ASTM A106 Grade B pipe and A234 WPB fittings at exact tabulated temperatures of 100, 200, 300, 400, 500 and 600°F. No interpolation, extrapolation or cross-code/edition substitution is enabled. Other contexts require a checked record or explicit override. Changing material, code edition or temperature invalidates inherited stress values.
- **Calculation methods:** reuse the existing Decimal pressure, historical corrosion, life, interval and projected pressure calculations. Recalculation with a missing or unavailable code edition is withheld. Elbows, tees, reducers, branches, nozzles and unspecified heads remain separate geometries; unsupported pressure methods are flagged rather than evaluated as straight pipe. A supplied governing minimum can support life arithmetic while geometry-specific pressure assessment remains unresolved.
- **Rates and minima:** negative historical rates remain visible as increasing-reading anomalies and are never adopted for life. A documented positive manual rate can be applied explicitly. Zero rates do not produce infinite life. Pressure-only source values remain distinguishable from governing minima. No PASS or equipment-fitness conclusion is generated.

All engineering results remain **DRAFT / NOT VALIDATED**. Source-checked tables and software arithmetic tests do not establish governing applicability, other load cases, material identification, or engineering acceptance. Full property-table coverage and independent engineering validation remain explicit limitations.

## Source preservation and exports

Original workbook bytes are retained by SHA-256. Import preserves whole sheets and linked drawing evidence. Corrections are overlays. Generated forms patch only copies of the OOXML package, preserve styles/drawings/VBA, clear stale calculations and unresolved template outputs, and add a calculation ledger. Unselected worksheets retain original source content; they are not newly evaluated scenarios. Excel calculation chains are removed so Excel can rebuild them. Exports retain the original XLSX/XLSM format.

## Verification

```sh
.venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python tools/validate_revamped_workspace.py /path/to/fresh-validation-folder
```

The new acceptance path exercises all three supplied workbooks, checks independent rate/life arithmetic, increasing-reading withholding, geometry distinctions, completed-form loading, media/style/VBA preservation, evidence ZIP hashes and unchanged originals. Tests also cover row-scoped confirmations, batch edits, exact lookup scope, scenario isolation, stale revisions, undo, inline correction and local HTTP origin checks.

See `planning/16_Revamp_Audit_and_Delivery.md` for the audit and remaining engineering gaps, and `evidence/revamped_workspace_acceptance_verified/verification.json` for the refreshed actual-workbook evidence.
