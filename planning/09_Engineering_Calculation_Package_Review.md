# Engineering calculation package review

Reviewed 4 November 2026 at the user's request. This document records artifact review only; it does not approve engineering methods or enable calculations.

## Artifact and integrity

- Archive: `engineering-calculations/evaluator_calculations_verified.zip`
- SHA-256: `7f707773b67921e5c55097137507163fd645a210366e8bc45690ec47b1427f26`
- Five entries; 31,874 expanded bytes. All entry names are relative and contain no traversal paths.
- Contains `CODEX_START_HERE.md`, a seven-row source inventory, a draft engineering specification v0.1, a JSON candidate rule registry v0.1, and synthetic arithmetic vectors.
- All seven source PDF names, editions, byte counts, and SHA-256 values in the archive inventory match the local files under `sources/codes/`.

## Gaps it helps close

The package provides a useful first draft for T10/T11: 11 candidate rules with named dependencies and applicability guards; rate, remaining-life, required-thickness, VIII-1 shell/head, B31.3, B31.4, and B31.8 formula candidates; input/provenance expectations; excluded cases; and synthetic vectors covering negative/zero rates, missing current readings, lifecycle mismatch, and several unit/formula examples. It also gives page-index references for focused source verification and records that proprietary PDFs should not be redistributed.

Use these files as review inputs and test scaffolding, not as approved specifications or expected engineering benchmarks. The CSV calls its vectors synthetic and asks for human validation; the JSON labels the registry `ENGINEER_APPROVAL_PENDING`; the Markdown calls itself a source-reviewed draft and requires qualified engineering review.

## Remaining blockers

- No qualified approver, approval date, governing-scope decision, or independent engineering sign-off is included.
- No independently approved design calculations or tolerances are included. Synthetic arithmetic vectors can test implementation plumbing but cannot validate code interpretation.
- Material lookup rows, table notes, verification provenance and redistribution rights are absent. Factor selections, table branches and applicability limits still need direct verification against the licensed PDFs and approved component records.
- Structural minimum inputs/calculation and API 574 guidance are absent. The draft correctly says required thickness and acceptability must remain incomplete without them.
- Owner-approved corrosion-rate selection, inspection interval policy, jurisdiction, operating/service scope and approved overrides are not supplied.
- API 510/570 interval candidates appear in the prose draft but are absent from the machine-readable rule registry. They should not be silently added as enabled rules.
- Importer acceptance still requires independently checked expected readings and source locations for the actual workbook set.
- `CODEX_START_HERE.md` says the Separator XLSM is unavailable, but it is present at `sources/workbooks/Separator-204 Inspection Report.xlsm`; this package caveat is stale. Its statement that the package is calculation extraction rather than a verified importer remains consistent with current status.

## Plan changes

T10 should ingest/archive this package as a draft input, hash-check its source inventory, reconcile every candidate against the local licensed reference files, and produce a qualified approval record before any rule can be registered as enabled. Track the prose-only interval candidates and missing material/structural sources explicitly.

T11 may use the synthetic vectors for unit-conversion and formula-arithmetic plumbing after independent implementation tests are written. These vectors must not satisfy the independent benchmark gate. Add two independently checked cases per approved core rule, applicability boundaries, and invalid/missing-input cases before an engineering rule can run. Keep calculations disabled until both T10 approval and T11 benchmark gates pass.
