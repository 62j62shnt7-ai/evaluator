# Implementation status

Updated 4 November 2026. The requested macOS/offline prototype workflows are implemented: workbook intake and correction, history matching, grouped proposals, reversible review, integrated draft calculations, revisioned export and backup/restore. Source workbooks and licensed PDFs remain unchanged. Formal engineering approval was waived as a build blocker by the user; calculated outputs remain DRAFT / NOT VALIDATED.

|Task|Status|Evidence / remaining boundary|
|---|---|---|
|T01 Baselines and feasibility|Local baseline implemented; Windows deferred|Ten original source hashes preserved. Certified extraction counts/visual completeness remain separate validation work.|
|T02 Source custody and storage|Implemented for local single-project use|Hash-addressed source copies; atomic nested SQLite transactions; future schema rejection; consistent database snapshot backup and separate-location restore with path/hash checks.|
|T03 Package inventory|Implemented inventory foundation|Exact sheet names/states, merged ranges, formula strings, external relationships and package drawing/media objects are inventoried. Vector/image reading extraction and full named-range/cache coverage are not certified.|
|T04 Template extraction|Supported table adapters implemented|TL-B numeric/text joint labels, merged joint/band context, separate MIN campaigns, duplicate headers and conflicting dates are retained. Separator CML/nozzle tables resolve merged component context separately. Other formats/images remain explicit unresolved content.|
|T05 Normalization and persistence|Implemented for supported mm table observations|Raw source cells/hash retained; correction overlay, stable identity, preserved sheet/campaign date overrides, repeat extraction, count reconciliation and contributor helper.|
|T06 History matching|Implemented|Explicit campaign/asset/lifecycle scope; exact physical-location candidates, historical union, duplicate/unresolved/lifecycle cases, explicit manual pairing. No unverified replacement caption becomes automatic continuity.|
|T07 Grouped proposals|Implemented|Eligible/excluded preview; grouped exact-match confirmation and issue follow-up. Missing readings are never generated or silently accepted.|
|T08 Revision/undo|Implemented|Revision-checked proposal and form actions; transactional review/corrections/date changes; append-only decision history; undo as new revision; stale results after dependency changes. Source add/delete creates an undo boundary.|
|T09 Local review UI|Implemented|Upload/inventory/extract, searchable selectable reading grid, corrections, sheet/campaign dates, comparison filters, proposals, manual mapping, design/profile forms, saved results, audit, export and restore UI.|
|T10–T11 Draft calculation workflow|Implemented as unvalidated candidates|Eleven standalone arithmetic candidates; seven pressure-design forms tied to comparisons; selected-pair historical rates/remaining life; explicit adopted rate/required thickness or pressure+structural input. Source/input/version trace and null outputs for unresolved cases. No fitness/PASS declaration. Material tables are user-supplied inputs; advanced FFS/external pressure remain out of scope.|
|T12 Revisioned exports and recovery|Implemented|Immutable ZIP per project revision containing XLSX, CSV, HTML, JSON, audit and SHA-256 manifest; prior packages downloadable; failed writes leave prior exports intact. Complete database/source backup and staged restore into a new folder.|
|T13 Windows pilot|First-run portable bootstrap implemented; Windows acceptance pending|Run UT Review.bat downloads embedded Python and pinned workbook-reader wheels into the app folder on first launch. Move the complete folder for offline use; clean Windows execution remains unverified.|

## Component-aware batch engineering evaluation — implementation in progress, 4 November 2026

The target is now partially implemented. Read-only record adapters, draft arithmetic, per-row assignments/readiness, grouped overrides, a local review page, revision invalidation, and batch CSV/HTML/JSON revision exports are present. The simple comparison/report flow remains available; a saved comparison can open the component batch page. Results remain **DRAFT / NOT VALIDATED** and never declare equipment fitness.

Verification this turn: **60 tests passed** using `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q`; Python compilation and launcher shell syntax passed. New integration coverage checks the batch review page, group input form, per-row mapping isolation, and inclusion of saved rows in revision exports. Isolated actual-source acceptance passed for Separator and TL-B, checked all revision-export hashes, and confirmed original workbook hashes stayed unchanged. A read-only browser smoke check rendered the actual Separator batch page with all 37 current rows, 29 historical candidates, and visible per-row assignment controls for unresolved records. Cached workbook formulas remain proposals, not validated calculations.

Read-only audit found substantial source inputs already present: 38 Separator component rows with cached required-thickness candidates/selected rates, and 80 TL-B June-2025 records with pressure-thickness candidates (`tPd`, not automatically governing tRequired) and selected rates. Manual per-row source-record assignment is now available for unresolved rows, with explicit physical-point confirmation and revision tracking. Remaining work includes broader profile/policy controls and independent review of assignment/readiness logic. The rule engine currently withholds unsupported nozzle UG-45 and fitting paths.

Actual data gaps/conflicts: Separator has 36 unique label candidates, of which 19 have identical current values and 17 nozzle records differ from the UT sheet; two N#3/S readings remain ambiguous. TL-B May/June has 76 unique label candidates with identical current values, four tee/reducer branch observations ambiguous under the current key, and one missing profile. Its April two new points have no old-profile match; all 80 April evaluation current O values are projected formulas and must not become measured UT. Source event dates and B31.8 edition/scenario choices also need explicit scope resolution.

Detailed assessment and unchecked acceptance: `planning/13_Batch_Evaluation_Gap_Assessment.md`. Exact audit counts/cells/caches/hashes: `evidence/batch_evaluation/workbook_readiness.json`. Repeat with `PYTHONPATH=src .venv/bin/python tools/audit_batch_evaluation.py`.

Engineering approval remains waived as an app-build blocker. Batch outputs must remain draft, with provided-record versus recalculated-rule bases distinguished and unsupported outputs withheld. The actual data conflicts and code-edition uncertainties listed above still require explicit resolution for applicable numerical outputs.

## Fresh end-to-end user workflow — 4 November 2026

Completed a fresh run from real multipart workbook upload through whole-sheet import, matching, report generation and download for all three supplied XLSX/XLSM workbooks. The actual browser also completed the full Separator XLSX flow from an empty test project, selected both whole sheets, generated 29 historical rates, downloaded the report, and verified its manifest/source bytes. User's original sources and default working project were untouched.

Friction removed / defects fixed:
- Added **Import both sheets & find matches** to the main workbook intake page. The user selects previous/current inspection sheets once; both complete sheets import and the latest measured campaigns open in the match preview automatically. Individual import and detailed coverage are collapsed.
- Default comparison selectors show one current inspection per sheet; historical columns stay hidden until **Show historical columns** is enabled (existing historical selections remain visible).
- Complete source evidence survives even when an unsupported sheet has no normalized readings; the import commits and links to full evidence instead of discarding it with a failed comparison.
- Older Separator sheets used JOINT/CML headers without a standalone CMLS caption. All cells had already been preserved, but section metadata omitted the CML label. Whole-sheet schema 2 recognizes those headings, merges repeated adjacent captions and automatically refreshes legacy indexes. August-2024 XLSX now lists both CMLS and NOZZLES, including N92 and N114 in their proper sections.
- Reports with unresolved dates directly explain why rates are missing and link to the optional date fields on the same screen.
- Adding another workbook no longer stales existing reports; importing or resolving dates on one source only invalidates comparisons/results using that source. Unscoped changes retain conservative invalidation. Own-source changes still correctly require refresh.
- Importer controls now use explicit associated labels and a compact layout; the browser verified selecting sheets by their visible labels. Upload lands directly on that workbook’s two-sheet importer instead of returning to the top of the intake page.

Verification: **61 pytest tests passed** in 19.40s using `PYTHONPATH=src .venv/bin/python -m pytest -q`. Launcher shell syntax and Python compilation passed. Independent review found no actionable issue in import transaction/selection, unsupported-evidence preservation, section indexing or scoped invalidation.

Real acceptance: both Separator formats yielded 29 unique match candidates and 29 historical rates for August-2024 → January-2026. TL-B yielded 19 candidates; rates remain withheld for conflicting dates, with a direct date-resolution prompt. Both full sheets and untouched workbook bytes were present in every scoped report; all manifest checksums and source bytes matched. All earlier comparison/evaluation records stayed current after importing unrelated workbooks.

Evidence: `evidence/simple_end_to_end/verification.json`, `combined-import.png`, `browser-report.png`; repeatable `tools/validate_simple_workflow.py`; report packages under `outputs/simple-end-to-end-release/exports/`. The user-facing path is upload → choose two whole sheets → import/find matches → confirm physical points → generate/download report. No repeated audit metadata or separate rebuild forms are required.

Remaining source-data boundaries: unresolved dates and physical mapping need explicit user choices for numerical historical rates; required thickness/adopted rate are still needed for remaining life. Image-only readings are retained as source evidence but not OCR-normalized. These do not prevent exporting the comparison/exception report.

## Simple default workflow and whole-sheet import — 4 November 2026

Implemented in response to the user's request to remove repetitive manual inputs and import a whole inspection sheet as one unit.

- Default `/workflow`: previous/current selectors → automatic exact-location preview → physical-point confirmation → **Generate report**. Local OS account/action descriptions populate audit metadata automatically. Asset/lifecycle text entry, repeated proposal confirmation forms and separate calculate/export steps are removed from the normal flow. Dates and remaining life remain optional, collapsed follow-ups.
- Generating a report applies supplied dates, refreshes the comparison, confirms eligible exact points, evaluates and builds the scoped downloadable ZIP. Unmatched/duplicate points remain explicit exceptions. Original thickness/rate basis is not guessed; life needs supplied inputs and scope confirmation.
- Source changes which alter previewed pair membership, thickness or location trigger a fresh preview before confirmation. The P1 identified by independent review was reproduced in a failing test and fixed. Date-only updates can rebuild without another form.
- Whole-sheet importer stores every serialized cell (including formulas/cached values/styles), merges, row/column evidence, worksheet XML and sheet-related drawing/comment/image relationships. Unknown layouts are still imported as full evidence with zero unsupported measurements inferred. The untouched source workbook is canonical.
- `/sheet` reviews complete cell evidence and related images/drawing/comment parts. Export includes full-sheet JSON and original workbook bytes, plus normalized calculations, coverage, XLSX/CSV/HTML and checksums. Default simple exports are scoped to the selected comparison; project-wide export stays in detailed tools.
- Missing whole-sheet evidence in old projects upgrades automatically on Find/Refresh matches. Undo restores sheet evidence using hash-deduplicated payloads; deletion clears active evidence and obsolete undo blobs. Backups contain the database/source copies.
- Real-source simple HTTP acceptance passed for both Separator formats and TL-B. Separator: 29 matched candidates/rates; TL-B: 19 candidates with unresolved dates retained. The source hashes, exported source bytes and every manifest checksum matched. January Separator XLSX preserves 3,085 serialized cells, CMLS+NOZZLES, and 11 related package parts. TL-B May sheet preserves 7,140 cells and its related parts.
- Browser verification: selected real Separator inspections, refreshed candidates, ticked one continuity checkbox, generated a report with 29 rates and no manual metadata, and opened the whole-sheet viewer. Screenshot `evidence/simple_workflow/report-ready.png`.
- Verification: **55 pytest tests passed**, including whole-sheet source/unknown-layout/undo/export tests, simple HTTP/report scope, rollback, missing inputs and stale-preview protection. Existing openpyxl DrawingML/print-area warnings are expected; source files are never resaved. Mac launcher shell syntax and Python compilation passed.
- No blocker for this requested simplification. Image-only readings still require interpretation/OCR follow-up; they are preserved, not represented as normalized or silently omitted. Independent engineering validation and Windows testing remain deferred boundaries.

## Actual-workbook end-to-end verification — 4 November 2026

**Completed:** HTTP upload → inventory → extraction → compare → grouped confirmation → historical evaluation → immutable export, using all three actual source workbooks in a separate project. Nine comparison scenarios passed expected pair-count assertions; an independently calculated rate from source cells also matched exactly. Source hashes remain unchanged. Current suite: **40 tests passed** in 12.732s; launcher shell syntax and Python compilation passed.

Fixed findings:
- Separator historical sheets had multiple dated MIN columns, but only the first was being imported and labelled current. All explicitly labelled MIN campaigns now retain their own dates/cells; the latest table campaign is current, NEXT placeholders are ignored, and nozzle scope resets correctly.
- Removed fallback-to-column-E extraction that incorrectly treated `Evaluation 2026` design temperatures as thickness observations.
- Historical/exception reports can be saved with missing required thickness/adopted rate; remaining life is null with explicit missing-input flags. Confirmed points with date problems stay reportable with rates withheld. No invented engineering inputs were used in acceptance reports.
- Project reports now include readable location, previous/current file/sheet/cell/date/thickness, required thickness, basis, exceptions and extraction coverage in CSV/XLSX/HTML/JSON.
- Creating/confirming an unrelated comparison no longer makes other saved reports stale. Mapping changes stale only that comparison's results; source changes and undo retain conservative invalidation.
- UI saved results are scoped to the opened comparison, preventing unrelated assets' results from appearing as its evaluation.

Actual findings (both Separator formats agree):
- August-2024 current → January-2026 current: **29 unique matched candidates**, **6 current-only points**, **1 ambiguous group**. All 29 confirmed test pairs produced historical rates (24 zero, 5 positive); remaining life withheld because no scoped minima/rates were supplied.
- January-2026 historic 2024 column → its current column reproduces the same result.
- January → October-2026: 13 unique nozzle matches; rates withheld because October has January-20 and October-20 date candidates. Its CML labels/layout differ; no silent renumbering occurs.
- TL-B October-2022 → May-2025 (including within-sheet history): 19 unique candidates, 58 current-only locations and 2 ambiguous groups. May sheet labels conflict with its March-31-2026 report header; user date resolution is required for rates.
- TL-B April-2026 supplies only two new text-labelled points and conflicts with March-31 header. No automatic continuity to old numbered points was asserted.

Evidence: `evidence/actual_workbook_workflow/verification.json`, repeatable `tools/validate_actual_workbooks.py`, and `outputs/actual-workbook-verified/actual-workbook-report.zip` / `.html`. Browser saved the real Separator comparison with blank engineering inputs and displayed historical rates plus missing-input flags. Tests confirm exported checksums and source preservation. Independent review found no correctness blocker; its requested stronger count/rate assertions were added and the actual acceptance was rerun successfully.

**To upgrade an existing project:** restart the app, re-extract the affected Separator sheets, rebuild comparisons and reconfirm mappings. Original workbook bytes stay preserved; old reports remain historical evidence.

**Remaining data blockers:** confirm conflicting inspection dates, physical mapping for duplicate/new locations, and applicable required thickness/adopted-rate profiles for numerical remaining life. Image-only older reports and unsupported geometry remain the existing coverage boundaries. These gaps are listed in the report; they do not prevent exporting the complete supported comparison and exception evidence.

## Guided evaluation update — 4 November 2026

- One screen now guides previous/current campaign selection, automatic location matching, confirmation, missing-input completion and evaluation. Navigation is labelled **Evaluate readings**.
- **What is missing?** provides aggregate counts and per-pair instructions for confirmations, unresolved locations, missing/invalid dates and units. Confirmed pairs with valid dates/units become selectable; unresolved pairs stay visible.
- Live input readiness states what enables **Evaluate selected pairs**. Reviewer/evidence and existing selections prefill; saved calculation profiles are reused through repeated rebuild ancestry, while pair selection and scope confirmation remain explicit.
- **Rebuild these pairs** creates a fresh comparison from the existing campaign/asset/lifecycle selections. It uses current reading/date overlays, preserves prior snapshots, records its ancestor, checks revision freshness, and resets confirmations (including manual pairing).
- Previous/current campaign date forms are in the comparison screen and retain its context on save. Optional pressure forms and issue follow-ups are collapsed.
- Verification: **35 tests passed** using `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` (11.442s), including source-hash acceptance. Launcher shell syntax and Python compilation passed. One prior smoke assertion was updated to the intentionally renamed UI heading.
- Browser on an isolated synthetic project verified confirmation → missing-input checklist → enabled button → saved result → one-button rebuild → confirmation reset → saved profile quick-fill. Screenshot: `evidence/guided-evaluation.png`. No user project data was modified.
- Independent review identified repeated-rebuild quick-fill loss; reproduced with a failing test, fixed by following comparison ancestry, and verified passing. No blocking review findings remain.
- Blockers: none for this requested UI workflow. Engineering validation and Windows acceptance remain the existing follow-up boundaries below.

## Verification ledger

- Source inventory: all ten local source files matched original recorded byte counts and SHA-256s before this update; acceptance tests repeat that check.
- Expected RED tests preceded workflow implementation; tests exercise history union, duplicates, stale proposals, selected calculation scope, negative rates, missing current, lifecycle mismatch, manual pairing, design integration, transaction interruption, failed exports and 300-record batch undo.
- Synthetic arithmetic from the supplied engineering ZIP is test scaffolding, not independent engineering validation.
- Browser verification on an isolated temporary project: TL-B 10-2022 vs May-2025 campaigns produced proposed matches and unmatched/duplicate groups. Group confirmation unlocked integrated inputs; a single selected location produced a saved draft result while unselected rows stayed explicitly outside scope.
- Direct `/workflow` HTTP navigation regression was found and corrected; the HTTP smoke test now covers it.
- Existing project databases are extended through additive tables. No destructive migration is performed.
- Final verification: `.venv/bin/python -m unittest discover -s tests -v` passed **30 tests** in the launcher virtual environment (Python 3.14.6 / openpyxl 3.1.5). A further 13 targeted app/workflow tests passed after adding revision guards to existing sheet/date/delete forms. Shell syntax validation and Python compilation also pass.
- Final independent code review found no Critical issues, one Important conflicting-report-date readiness issue and one Minor redundant-preview-storage issue. The date issue was reproduced RED then fixed GREEN through extraction and integrated evaluation; the preview issue was fixed by stable comparison/revision proposal IDs.
- Additional regressions cover existing-project date migration, repeat uploads under different filenames, future schemas, corrupt/traversal backups, re-extraction preserving dates and immutable exports under write failures.

## Boundaries and decisions

- Ruling: use the existing Python/openpyxl + standard-library localhost UI rather than introduce NiceGUI (the earlier plan called NiceGUI a candidate). This keeps the runtime dependencies portable; cost if wrong is a later UI-framework migration.
- Ruling: asset/lifecycle scope and physical continuity are explicit reviewer inputs. Labels alone cannot establish component history; unmatched or duplicate locations need manual confirmation.
- Independent certified reading counts, complete visual/shape extraction, code applicability/editions, verified material/property sources, advanced damage mechanisms, and independent engineering benchmarks remain follow-up validation. They are not represented as completed.
- Workbooks may emit openpyxl warnings for unsupported DrawingML and an invalid print-area defined name. They are never resaved, and package objects stay in the original source copy.
- No Git metadata exists in this project folder; no task commits or PR were created.

## Final review decisions

- Final: fixed conflicting report dates — `test_conflicting_report_dates_withhold_integrated_outputs` RED → GREEN; selected date stays null until reviewer resolution.
- Final: fixed repeated preview storage — unchanged comparison/revision/action proposals reuse stable IDs.
- Final: Ruling: engineering certification and licensed-code applicability remain follow-up verification; all results are explicitly draft and never assert equipment fitness. This follows the user's waived build gate, and the cost of ignoring the label would be unvalidated engineering decisions.
- Final: Ruling: Windows validation and drawing/OCR extraction remain deferred/out of the supported tabular prototype; their content is not claimed as extracted or verified. Cost if a different layout is assumed supported is incomplete coverage; the app exposes unresolved sheets instead.
- Final: no unresolved Critical or Important review findings; no known functional blocker remains for the five requested workflows.

## UT evaluator revamp delivery — 5 November 2026

The default entry point is now the requested three-screen local workflow. It adds automatic per-location historical selection, row-scoped batch configuration and confirmations, the API 574 Annex B pipe dimension selector, bounded material stress lookup, reversible edits, and source-form exports with a calculation ledger. See `planning/16_Revamp_Audit_and_Delivery.md` for implementation scope, checked reference boundaries and remaining engineering review requirements.

Verification after final code review fixes: **114 pytest tests passed**. The fresh three-workbook acceptance passed for both Separator formats (37 current points each) and TL-B (81 current points), including arithmetic cross-checks, source-form load checks, preservation of style/media/VBA package parts and original source hashes. Evidence: `evidence/revamped_workspace_acceptance_verified/verification.json`. Browser smoke workflow completed import → selected configuration → undo → evaluation → form download. Outputs remain **DRAFT / NOT VALIDATED**; no engineering fitness conclusion is produced.
