# Connected application workflow completion

Implemented 4 November 2026 against the user's request to finish history matching, grouped proposals, undo, integrated calculations and revisioned exports together. Engineering approval is waived as an implementation blocker; Windows validation remains deferred.

- [x] Select baseline/current extracted campaigns across sources or within multi-campaign sheets.
- [x] Identify asset and component lifecycle; preserve exact-location candidates, duplicates, current-only, previous-only and lifecycle-mismatch cases.
- [x] Preview grouped mapping and issue-follow-up proposals with eligible/excluded counts; reject stale previews.
- [x] Resolve a physical pair manually with reviewer/evidence and continuity confirmation.
- [x] Correct thickness/location via an overlay, preserving raw cell/hash evidence.
- [x] Resolve dates for an entire sheet or a specific campaign; preserve original candidates and carry date choices through re-extraction/upgrades.
- [x] Undo review, correction, date, mapping and calculation actions transactionally as a new revision; workbook add/delete is an undo boundary.
- [x] Save code-specific draft pressure-design results and use a scoped pressure-plus-structural or manual required thickness in an integrated history evaluation.
- [x] Require explicit adopted rate, selected physical pairs and year-length convention; retain apparent rates separately; withhold outputs for unresolved dates, missing current readings, invalid continuity or negative historical rates.
- [x] Mark dependent comparisons/evaluations stale after inputs change.
- [x] Export immutable revision ZIPs with XLSX, CSV, self-contained HTML, complete JSON trace, audit, original source hashes and a checksum manifest; retain downloadable prior exports.
- [x] Back up a consistent SQLite/source snapshot and restore into a separate new folder with safe-path/hash/schema validation.
- [x] Exercise real localhost HTTP forms/downloads and browser grouped confirmation, selected-pair evaluation, export download and undo.

The original long-form task checklists include validation beyond this usable prototype; their unchecked certified-reading, drawing/OCR, advanced geometry and clean Windows gates are not represented as passed. Current scope and evidence are in IMPLEMENTATION_STATUS.md. Runtime implementation is split across app_services.py (intake/review), workflow.py (transactions/history/proposals/evaluations/exports), workflow_ui.py (connected screens) and webapp.py (localhost routing).
