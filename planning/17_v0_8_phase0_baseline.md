# MAWP v0.8 implementation — phase 0 baseline and first safe slice

**Status:** PARTIAL PHASE 0 / NON-INTEGRATED PHASE 1 FOUNDATION.  
**Date:** 2026-11-17.  
**Target:** active `evaluator` app, not `inspection_app` or `inspection_app_local`.

## Baseline identified

- The active UI is the workbook → group inputs → per-row overrides → calculate → review/export workflow (`README.md`, `START_HERE.md`). Existing import, history, audit and export modules are to be preserved.
- `src/evaluator/engineering/draft.py` contains eleven candidate numerical rules labelled `DRAFT / NOT VALIDATED`; `batch_rules.py` includes inverse-pressure arithmetic, not full system MAWP.
- `planning/16_Revamp_Audit_and_Delivery.md` reports 114 tests passed on November 5, **not** on this branch.
- The current README documents fixed A106 B/A234 WPB allowable-stress assumptions and a half-life/10-year interval convention. v0.8 calls for component-specific code, edition and reviewed inspection-policy selection rather than global defaults.
- Original reference workbooks and licensed PDFs were not available in this isolated repository-connector audit; prior source verification cannot substitute for a fresh full acceptance run.

## First additive, non-integrated change

`src/evaluator/engineering/code_context.py` provides a fail-closed component code/edition *routing foundation*:

1. Requires component identity, construction code and edition, explicit owner scope confirmation, and traceable code-basis evidence.
2. Never guesses B31.3, B31.4 or B31.8 solely from the label “production flowline.”
3. Only references arithmetic candidate IDs already in the active app; unsupported fittings, nozzles and tank calculations remain `NOT_ASSESSED`.
4. Keeps pipe design, vessel-component capacity and tank assessments separate; it does not emit PASS, operating MAOP or certified MAWP.
5. Does not change existing UI behavior until separately integrated and regression-tested.

## Verification

- `tests/integration/test_code_context.py`: **13/13 passed** in isolated Python unittest execution.
- The full repository test suite was **not run** in this environment, and source-workbook acceptance was not repeated.
- The **176 proposed tests** in v0.8 remain unexecuted in the actual application. The 13 new routing unit tests must not be represented as completed engineering benchmarks.

## Follow-up gates

1. Run fresh full-suite and source-workbook acceptance, verify source hashes and geometry/drawing preservation.
2. Map current UI and batch assignment fields to `CodeContext` without inventing code or edition for existing records.
3. Add backward-compatible, auditable component code decisions; test undo, export/import and historical changes.
4. Only then integrate routing into existing draft calculations, with regression tests preventing silent pressure status changes.
5. Progress through vetted B31.3/API 570, pipeline/B31G, VIII/API 510 and API 650/653 modules with independent benchmarks, explicit unsupported-case flags and no unlicensed bulk table redistribution.

**No operational engineering approval is claimed.** This is a safe control-plane foundation, not a complete MAWP/MAOP or tank-fill-height system.
