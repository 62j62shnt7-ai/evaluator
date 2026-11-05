# UT Inspection Evaluator Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task. Use subagent-driven-development only if the user selects that execution method. Checkboxes track implementation, not work completed during planning.

**Goal:** Build a portable offline Windows Python application that imports the two supplied inspection report families, matches inspection history and resolves routine issues through batch decisions before traceable engineering evaluation.

**Architecture:** Immutable source files feed package inventory and template adapters, then normalized observations in SQLite. Matching, exception grouping and versioned engineering rules feed a local review interface and revisioned exports. Extraction, reviewer approval and equipment integrity disposition are separate states.

**Tech stack:** Python 3.12 baseline; openpyxl for cell access; standard ZIP/XML tools for package objects; SQLite; Pydantic for boundary validation; NiceGUI candidate local UI; pytest; PyInstaller candidate Windows packaging. Pin compatible dependencies after the Windows packaging spike. No required cloud service or model. OCR is optional and deferred until a fixture proves the need.

**Updated execution decision (4 November 2026):** User removed qualified engineering approval as a blocker to completing the app. Implement the draft calculation workflow from the reviewed package with explicit `DRAFT / NOT VALIDATED` state and no equipment fitness/pass declaration. Engineering approval and Windows testing are follow-up release validation, not prerequisites to a usable application prototype.

**Spec:** 01_Importer_Requirements.md plus 07_Source_Closure_and_Comparison.md (the latter supersedes earlier missing-source claims); 03_Acceptance_and_Limitations.md; 05_Code_Reference_Matrix.md. This consolidated plan governs execution order and proposed defaults; approved engineering specifications govern numerical rules.

## Global constraints

- Preserve originals and never execute imported macros, external links or embedded executables.
- Support .xlsx and .xlsm intake; no silent loss of cells, images, drawings or unmatched locations.
- Retain original units, values, dates, source coordinates and hashes beside normalized data.
- Review must be batch-first and exception-based; automation of extraction does not approve equipment integrity.
- Missing current thickness remains uninspected; negative rates never silently become zero.
- Approved material, code edition, lifecycle and rate basis constrain every bulk decision.
- No production calculation rule is enabled without an approved specification and independent benchmark.
- Sources and proprietary code tables are not automatically bundled with redistributable software.
- Planning has not validated engineering calculations, workbook formulas or equipment fitness.

## Review focus

1. Reimporting the same workbook must not duplicate observations (T02/T05).
2. An image-only report or unsupported shape must remain visible as unresolved content (T03/T04).
3. Conflicting date/header and repeated section labels must not create false matches (T04/T06).
4. A batch approval based on an obsolete revision must be rejected (T07/T08).
5. Interrupted writes and export failures must preserve the last committed evaluation (T02/T12/T13).

## Product scope and workflow

V1 supports the two supplied report families and their explicitly tested variations. Start → select source files → show sheet/region inventory → select campaign dates and component scope → inspect extraction coverage → propose history matches → group issues → preview and apply eligible decisions → assess calculation readiness → evaluate approved rules → review/export a revision. Every screen provides a count reconciliation: detected, imported, excluded with reason, unresolved. Unsupported regions are visible.

Dashboard shows campaign coverage, open issue groups and prioritized severe-loss/engineering exceptions. The grid supports multi-select, filtering, source-image/cell evidence and CSV-safe copy/export. Batch proposal cards show rationale, records included/excluded, parameter/rate source, before/after impacts and approval scope. Individual record drill-down remains available without becoming the default workflow. Never claim a fixed automation percentage before measuring the fixtures.

V1 engineering scope is selected by approved component-specific rules, not every component named in a code. Initial candidates: straight pipe internal pressure and vessel cylindrical shell/head cases supported by verified inputs. External pressure, complex loads, local metal-loss fitness-for-service, reinforcement, fatigue and unsupported repairs remain explicit referrals unless separately specified and benchmarked. No automated rerating or inspection authorization.

## Repository layout to create during implementation

- pyproject.toml, README.md: locked application dependencies, entry point and setup.
- src/evaluator/domain/models.py: typed records and states.
- src/evaluator/storage/{repository,sources,migrations}.py: SQLite transactions, immutable files and schema upgrades.
- src/evaluator/importing/{package_inventory,cells,objects,regions,separator,tlb,normalize}.py: extraction and adapter contracts.
- src/evaluator/history/{matching,lifecycle}.py: candidates and component continuity.
- src/evaluator/review/{issues,proposals,actions,policies}.py: groups, decisions and versioned profiles.
- src/evaluator/engineering/{registry,readiness,properties,rates,runner}.py: approved rule execution only.
- src/evaluator/engineering/rules/: one module per approved rule identifier.
- src/evaluator/ui/{app,intake,coverage,review,evaluation}.py: local workflow views.
- src/evaluator/exporting/{reports,backup}.py: revisioned reports and portable recovery.
- tests/{unit,integration,acceptance}/ and tests/fixtures/: synthetic fixtures and approved manifests; avoid committing proprietary sources to public repositories.
- docs/engineering/: rule specifications, approval records and benchmark manifests.
- packaging/: Windows build specification, dependency notices and release checklist.

## Domain and interface contract

Identifiers are UUID strings. Decimal-valued engineering inputs are serialized as decimal strings, with units mandatory; dates are ISO dates after resolution. Original workbook precision is preserved. No blanket rounding before final display.

SourceRef: source_id, sha256, sheet, cell_range or package_object_id, anchor, raw_value, raw_unit, method. Region: region_id, source_id, sheet, bounds/object IDs, classification, extraction_status and reason. Observation: observation_id, asset_id, component_id, lifecycle_id, location_id, inspection_id, thickness_mm optional, raw SourceRef, status, revision. Inspection: inspection_id, selected_date optional, date_candidates and date_resolution. DesignInput: name, raw/normalized value/unit, source, approval and revision. MatchCandidate: current_id, previous_id, evidence, confidence_basis, status. No arbitrary confidence score substitutes for evidence.

Issue: issue_id, code, severity, affected_ids, evidence, blocking_scope. Proposal: proposal_id, action, eligible_ids, excluded_ids/reasons, basis, expected_revision and preview effects. Decision: reviewer, timestamp, justification, proposal snapshot and affected record revisions. Evaluation: evaluation_id, input_revision, rule/property/policy versions, readiness, outputs, assumptions and approval status.

States: extracted → mapped → reviewed → calculation_ready → calculated → engineering_reviewed. A record can be excluded, unresolved or superseded with a reason. Any dependent input change marks downstream results stale; no approval silently carries forward. Local reviewer identity is an audit label in V1, not a claim of tamper-proof multi-user authentication. Store timestamps in UTC and show local display time.

## Data and calculation policies

Location key includes asset, component lifecycle, section, joint/CML/band and physical position. Historical union is retained; repeated labels across sections cannot match automatically. Measurement minimum/maximum are summaries with contributing observation IDs. No nominal thickness substitutes for a measured value.

Date precedence is approved event resolution, supported by explicit report/column dates; sheet names are hints. Conflicts block affected rate calculations, not unrelated extraction. Mixed campaign columns create separate observations. Preserve both design and operating pressure plus PSV/rerating claims as separate inputs.

Corrosion policy stores apparent historical rates separately from adopted rates. Short/long term selection, minimum positive adopted rate, uncertainty threshold, year-length convention, interval caps, allowances and structural minimum source require approved policy records; no numerical defaults are invented. Negative rate, zero elapsed time and replaced components are blocking conditions for ordinary trend-based evaluation. Missing prior UT may use an approved component/circuit assumption with applicable scope and justification. Missing current UT cannot be batch accepted as measured. Remaining life, MAWP and interval outputs are withheld when their rule dependencies are unapproved or incomplete.

## Engineering rule approval package

For every enabled rule record: identifier/version; governing code/edition/addenda; source clauses/tables; component geometry; service and applicability boundaries; input units and definitions; formula transcription; property lookup keys and notes; allowance and efficiency/strength factors; structural minimum basis; arithmetic precision/rounding; exceptional states; independent benchmark origin, expected outputs and tolerances; qualified reviewer/date. Validate lower/upper applicability limits and conversion equivalence. Table interpolation/extrapolation must follow the approved rule; default extrapolation is prohibited. Workbook formulas are comparison evidence only.

API 510/API 570 supply in-service context subject to verified scope; VIII-1/B31 codes provide applicable construction bases. II-D material data cannot automatically replace pipeline strength values. TL-B labels B31.8-2020 while supplied PDF is 2025: require explicit edition selection before engineering evaluation. Reference page indexes are discovery aids, not approved equation specifications.

## Implementation tasks

For every task: first write its named failing tests, run them and confirm the intended failure, implement the interface minimally, run the named tests plus affected earlier tests, review the diff and commit only the task's files. Never mark a gate passed on the basis of a plan checkbox alone.

### T01: Fixture baselines and Windows feasibility

**Files:** tests/fixtures/manifests/, tests/acceptance/test_sources.py, packaging/offline_spike.md

**Interfaces:** No production dependencies. Produce manifest schema source_hash, sheet/region IDs, expected observations, unresolved regions and reviewer status.

**Acceptance:** A01/A02/A12

- [ ] Write failing tests: Verify all 10 source hashes against evidence/source_inventory.json. Establish clean Windows offline UI/packaging feasibility; record exact versions and baseline timings. Tests assert original hashes unchanged after intake, exact sheet-name preservation including leading whitespace and no macro execution. Create human-reviewable manifests; expected reading counts require independent verification, not parser-derived self-approval.
- [ ] Run the task's named pytest file(s) with `python -m pytest <test-file> -v`; record the intended failure before implementation. For documentation/Windows gates, record missing evidence instead of pretending a unit test proves approval.
- [ ] Implement the interfaces in the listed files; keep engineering-gated capabilities disabled until their gate passes.
- [ ] Rerun those tests and affected integration tests; all must pass, with required external evidence attached.
- [ ] Review the diff for source preservation and scope; commit the task after checks pass. Record commit and evidence in IMPLEMENTATION_STATUS.md.

### T02: Transactional repository and source custody

**Files:** src/evaluator/domain/models.py; src/evaluator/storage/{repository,sources,migrations}.py; tests/integration/test_storage.py

**Interfaces:** register_source(path: Path) -> SourceRecord; transact(expected_revision: int, changes: ChangeSet) -> Revision; backup(destination: Path) -> BackupRecord. Define all domain types above here.

**Acceptance:** A01/A12

- [ ] Write failing tests: Test hash-addressed copy, duplicate reimport idempotence, locked/unreadable files, rollback after simulated interruption, schema version rejection and restore to a separate location. Original files never change. Source reference paths remain valid after project relocation.
- [ ] Run the task's named pytest file(s) with `python -m pytest <test-file> -v`; record the intended failure before implementation. For documentation/Windows gates, record missing evidence instead of pretending a unit test proves approval.
- [ ] Implement the interfaces in the listed files; keep engineering-gated capabilities disabled until their gate passes.
- [ ] Rerun those tests and affected integration tests; all must pass, with required external evidence attached.
- [ ] Review the diff for source preservation and scope; commit the task after checks pass. Record commit and evidence in IMPLEMENTATION_STATUS.md.

### T03: Full workbook package inventory

**Files:** src/evaluator/importing/{package_inventory,cells,objects}.py; tests/integration/test_package.py

**Interfaces:** inventory(source_id: str) -> WorkbookInventory with sheets, regions, objects, links, formulas, caches and warnings. Consumes SourceRecord.

**Acceptance:** A02/A04/A05

- [ ] Write failing tests: Test merged/hidden sheets, image-only 2010, shape anchors, relationship targets, absent formula cache and malformed ZIP/XML. Inventory external references without fetching them; enforce configurable file/expanded-size limits and reject path traversal during extraction. Preserve unsupported object entries rather than dropping them.
- [ ] Run the task's named pytest file(s) with `python -m pytest <test-file> -v`; record the intended failure before implementation. For documentation/Windows gates, record missing evidence instead of pretending a unit test proves approval.
- [ ] Implement the interfaces in the listed files; keep engineering-gated capabilities disabled until their gate passes.
- [ ] Rerun those tests and affected integration tests; all must pass, with required external evidence attached.
- [ ] Review the diff for source preservation and scope; commit the task after checks pass. Record commit and evidence in IMPLEMENTATION_STATUS.md.

### T04: Template adapters and campaign extraction

**Files:** src/evaluator/importing/{regions,separator,tlb,normalize}.py; tests/integration/test_adapters.py

**Interfaces:** extract(inventory: WorkbookInventory, adapter_id: str) -> ExtractionResult[Region, ObservationDraft, Issue]. ObservationDraft includes unresolved date/location candidates.

**Acceptance:** IMP01–05/A02–05

- [ ] Write failing tests: Separator tests: Q/T/S date movement, repeated headers, 2010 unresolved images, UT 10-2026 S1/E10 conflict. TL-B tests: 10-2022 row28 fields; UT 5-2025 AD1 versus K150/L150; duplicate G150/H150 campaign labels; multi-campaign columns; section boundaries and whitespace sheet names. Numeric strings, blanks and zero are distinct. Assert source locators for every extracted field and no evaluation/preview double counting.
- [ ] Run the task's named pytest file(s) with `python -m pytest <test-file> -v`; record the intended failure before implementation. For documentation/Windows gates, record missing evidence instead of pretending a unit test proves approval.
- [ ] Implement the interfaces in the listed files; keep engineering-gated capabilities disabled until their gate passes.
- [ ] Rerun those tests and affected integration tests; all must pass, with required external evidence attached.
- [ ] Review the diff for source preservation and scope; commit the task after checks pass. Record commit and evidence in IMPLEMENTATION_STATUS.md.

### T05: Normalized persistence and coverage reconciliation

**Files:** src/evaluator/importing/normalize.py; tests/integration/test_coverage.py

**Interfaces:** persist_extraction(result: ExtractionResult, expected_revision: int) -> ImportSummary; coverage(source_id: str) -> CoverageSummary.

**Acceptance:** IMP05/07/A02/A05

- [ ] Write failing tests: Test mm/in and F/C/psi/MPa conversion equivalence without changing originals; unknown units remain unresolved. Reimport produces the same observation identity; revised source creates a new source/revision. Every inventoried region has imported/excluded/unresolved status and displayed counts reconcile; derived min values retain contributors.
- [ ] Run the task's named pytest file(s) with `python -m pytest <test-file> -v`; record the intended failure before implementation. For documentation/Windows gates, record missing evidence instead of pretending a unit test proves approval.
- [ ] Implement the interfaces in the listed files; keep engineering-gated capabilities disabled until their gate passes.
- [ ] Rerun those tests and affected integration tests; all must pass, with required external evidence attached.
- [ ] Review the diff for source preservation and scope; commit the task after checks pass. Record commit and evidence in IMPLEMENTATION_STATUS.md.

### T06: History candidates and component lifecycle

**Files:** src/evaluator/history/{matching,lifecycle}.py; tests/unit/test_matching.py

**Interfaces:** propose_matches(current: list[Observation], history: list[Observation], lifecycles: list[Lifecycle]) -> list[MatchCandidate]; compare_union(...) -> ComparisonSet.

**Acceptance:** IMP06/08/A06/A07

- [ ] Write failing tests: Test current-only, previous-only and ambiguous candidates; same band in different sections; alternate historical dates; separator replaced nozzles/build-up; TL-B planned versus completed replacement captions. Never establish lifecycle events solely from an inferred caption. Changed/replaced components cannot receive automatic historical pairs.
- [ ] Run the task's named pytest file(s) with `python -m pytest <test-file> -v`; record the intended failure before implementation. For documentation/Windows gates, record missing evidence instead of pretending a unit test proves approval.
- [ ] Implement the interfaces in the listed files; keep engineering-gated capabilities disabled until their gate passes.
- [ ] Rerun those tests and affected integration tests; all must pass, with required external evidence attached.
- [ ] Review the diff for source preservation and scope; commit the task after checks pass. Record commit and evidence in IMPLEMENTATION_STATUS.md.

### T07: Issue grouping and suggested resolutions

**Files:** src/evaluator/review/{issues,proposals,policies}.py; tests/unit/test_proposals.py

**Interfaces:** classify(comparison: ComparisonSet) -> list[Issue]; propose(issues: list[Issue], policy: PolicyVersion, revision: int) -> list[Proposal].

**Acceptance:** IMP08/A08/A09

- [ ] Write failing tests: Test missing prior/current, negative apparent rate, zero days, conflicting dates, uncertain material and severe loss. Group only compatible material/lifecycle/code/rate policy and issue basis. Preview eligible/excluded IDs and before/after readiness; withhold numerical effects until rules are enabled. Missing current and severe-loss exceptions cannot disappear through routine acceptance.
- [ ] Run the task's named pytest file(s) with `python -m pytest <test-file> -v`; record the intended failure before implementation. For documentation/Windows gates, record missing evidence instead of pretending a unit test proves approval.
- [ ] Implement the interfaces in the listed files; keep engineering-gated capabilities disabled until their gate passes.
- [ ] Rerun those tests and affected integration tests; all must pass, with required external evidence attached.
- [ ] Review the diff for source preservation and scope; commit the task after checks pass. Record commit and evidence in IMPLEMENTATION_STATUS.md.

### T08: Atomic batch decisions and revision invalidation

**Files:** src/evaluator/review/actions.py; tests/integration/test_actions.py

**Interfaces:** apply(proposal_id: str, reviewer: str, justification: str, expected_revision: int) -> Decision; undo(decision_id: str, expected_revision: int) -> Decision.

**Acceptance:** A09/A11

- [ ] Write failing tests: Test stale revision rejection, all-or-nothing commit, per-record provenance, partial eligibility, dependent result invalidation and undo as a new revision. Saved policies store scope/version and require fresh compatibility checks on reuse. No silent overwrite of raw observations or blanket engineering approval.
- [ ] Run the task's named pytest file(s) with `python -m pytest <test-file> -v`; record the intended failure before implementation. For documentation/Windows gates, record missing evidence instead of pretending a unit test proves approval.
- [ ] Implement the interfaces in the listed files; keep engineering-gated capabilities disabled until their gate passes.
- [ ] Rerun those tests and affected integration tests; all must pass, with required external evidence attached.
- [ ] Review the diff for source preservation and scope; commit the task after checks pass. Record commit and evidence in IMPLEMENTATION_STATUS.md.

### T09: Offline review user interface

**Files:** src/evaluator/ui/{app,intake,coverage,review,evaluation}.py; tests/acceptance/test_review_flow.py

**Interfaces:** UI calls repository/import/review services; never computes engineering values directly. Launch loopback-only with bundled static assets.

**Acceptance:** A02/A09/A11/A12

- [ ] Write failing tests: Exercise source selection, region coverage, campaign choice, grouped evidence preview, eligible/excluded filter, bulk action and undo. Assert a synthetic 300-record compatible issue set can be resolved by one group action and incompatible records remain excluded; this tests behavior, not an automation-rate promise. Keyboard navigation and source drill-down work. Missing rules show actionable readiness reasons.
- [ ] Run the task's named pytest file(s) with `python -m pytest <test-file> -v`; record the intended failure before implementation. For documentation/Windows gates, record missing evidence instead of pretending a unit test proves approval.
- [ ] Implement the interfaces in the listed files; keep engineering-gated capabilities disabled until their gate passes.
- [ ] Rerun those tests and affected integration tests; all must pass, with required external evidence attached.
- [ ] Review the diff for source preservation and scope; commit the task after checks pass. Record commit and evidence in IMPLEMENTATION_STATUS.md.

### T10: Draft engineering rule specifications and property catalog

**Files:** docs/engineering/rules/, docs/engineering/benchmarks/, src/evaluator/engineering/{registry,properties,readiness}.py; tests/unit/test_readiness.py

**Interfaces:** register_rule(spec: DraftRuleSpec) -> RuleVersion; assess(inputs: EvaluationInputs, rule: RuleVersion) -> ReadinessResult; lookup_property(key: PropertyKey) -> PropertyResult.

**Acceptance:** A10/A11

- [ ] Review `engineering-calculations/evaluator_calculations_verified.zip` as a **source-reviewed draft**, not an approved ruleset. Review findings are tracked in `planning/09_Engineering_Calculation_Package_Review.md`. Verify its seven source hashes/editions against local source custody before using it as evidence; hashes matched in the initial review. Treat the package's statement that the Separator XLSM is unavailable as stale; the local workbook exists.
- [ ] Write failing tests: Prototype rule registry may execute candidate formulas without engineering approval, but every result is `DRAFT / NOT VALIDATED`; no output may state `PASS` or equipment fitness. Readiness checks still reject missing inputs, unsupported geometry, mismatched editions, out-of-range temperature, product-form/notes mismatch and prohibited extrapolation. Property candidates retain table edition, row/notes and provenance; synthetic data is clearly marked.
- [ ] Reconcile every draft formula, clause/page pointer, branch limit and factor against the locally supplied code edition and candidate component/service scope. The archive's 11 JSON rules omit interval candidates described in its prose; do not silently promote those candidates. Record unresolved interpretations and licensing limits for property data; engineering sign-off is deferred, not required to finish the prototype.
- [ ] Run the task's named pytest file(s) with `python -m pytest <test-file> -v`; record the intended failure before implementation. For documentation/Windows gates, record missing evidence instead of pretending a unit test proves approval.
- [ ] Implement the interfaces in the listed files; candidate rules produce only `DRAFT / NOT VALIDATED` results with no equipment fitness disposition.
- [ ] Rerun those tests and affected integration tests; all must pass, with required external evidence attached.
- [ ] Review the diff for source preservation and scope; commit the task after checks pass. Record commit and evidence in IMPLEMENTATION_STATUS.md.

### T11: Versioned calculations and rate policy

**Files:** src/evaluator/engineering/{rates,runner}.py; src/evaluator/engineering/rules/; tests/acceptance/test_engineering_benchmarks.py

**Interfaces:** evaluate(inputs: EvaluationInputs, rule_version: str, policy_version: str) -> EvaluationResult. Inputs reference observation/design revisions; outputs carry units, rule versions and trace.

**Acceptance:** A08/A10/A11

- [ ] Write failing tests: Implement one candidate rule at a time from the supplied draft. Compare arithmetic against synthetic vectors, clearly marked as test-only, in both unit systems. Test negative/zero/unknown rates, missing current UT, lifecycle mismatch, nonpositive denominators and pressure versus structural-minimum basis. Withhold unsupported outputs, preserve apparent/adopted-rate distinction, and force every result to `DRAFT / NOT VALIDATED`. Independent engineering benchmarks are follow-up release validation, not a prototype implementation blocker.
- [ ] Keep affected outputs null with a readiness reason when structural minima, material properties, applicable factors, rate selection or other loads are incomplete. Design equations alone do not establish in-service fitness. The prototype may show partial draft arithmetic but must never infer an overall acceptability result.
- [ ] Run the task's named pytest file(s) with `python -m pytest <test-file> -v`; record the intended failure before implementation. For documentation/Windows gates, record missing evidence instead of pretending a unit test proves approval.
- [ ] Implement the interfaces in the listed files; expose candidate calculations as `DRAFT / NOT VALIDATED` and do not produce fitness or PASS dispositions.
- [ ] Rerun those tests and affected integration tests; all must pass, with required external evidence attached.
- [ ] Review the diff for source preservation and scope; commit the task after checks pass. Record commit and evidence in IMPLEMENTATION_STATUS.md.

### T12: Revisioned exports and backup recovery

**Files:** src/evaluator/exporting/{reports,backup}.py; tests/integration/test_exports.py

**Interfaces:** export_evaluation(evaluation_id: str, destination: Path) -> ExportManifest; restore_backup(archive: Path, destination: Path) -> RestoreResult.

**Acceptance:** A11/A12

- [ ] Write failing tests: Export XLSX evaluation and CSV exception/audit tables plus a self-contained HTML engineering summary with source hashes, assumptions, basis/edition, statuses and revision. Escape formula-like CSV strings. Never overwrite sources; atomic file replacement prevents partial reports. Test export failure, stale results labeling, backup restore hash checks and archive path traversal. PDF output is a later optional task requiring layout verification.
- [ ] Run the task's named pytest file(s) with `python -m pytest <test-file> -v`; record the intended failure before implementation. For documentation/Windows gates, record missing evidence instead of pretending a unit test proves approval.
- [ ] Implement the interfaces in the listed files; keep engineering-gated capabilities disabled until their gate passes.
- [ ] Rerun those tests and affected integration tests; all must pass, with required external evidence attached.
- [ ] Review the diff for source preservation and scope; commit the task after checks pass. Record commit and evidence in IMPLEMENTATION_STATUS.md.

### T13: Portable Windows acceptance and pilot

**Files:** packaging/, tests/acceptance/test_offline_release.py, docs/release_checklist.md

**Interfaces:** Produce versioned portable directory and release manifest with executable, bundled assets, dependency notices and checksums.

**Acceptance:** A01–A12

- [ ] Write failing tests: Run on a clean supported disconnected Windows 11 x64 machine; keep data in a selected writable project directory, not installation files. Test non-ASCII/long paths, no admin rights, locked/corrupt inputs, interrupted action recovery, relocation and restore. Establish measured launch/import/review budgets on recorded hardware and fixtures before pilot sign-off. Check zero external runtime requests. Pilot both complete sample workflows against approved manifests.
- [ ] Run the task's named pytest file(s) with `python -m pytest <test-file> -v`; record the intended failure before implementation. For documentation/Windows gates, record missing evidence instead of pretending a unit test proves approval.
- [ ] Implement the interfaces in the listed files; keep engineering-gated capabilities disabled until their gate passes.
- [ ] Rerun those tests and affected integration tests; all must pass, with required external evidence attached.
- [ ] Review the diff for source preservation and scope; commit the task after checks pass. Record commit and evidence in IMPLEMENTATION_STATUS.md.

## Milestones, dependencies and stopping conditions

M1: T01–T05 yields reviewable, traceable extraction without engineering calculations. M2: T06–T09 yields batch-first comparison/review. M3: T10–T11 implements draft calculations from candidate rules, marked `NOT VALIDATED` and without fitness/pass declarations; independent validation remains a later release gate. M4: T12–T13 yields portable pilot release; Windows acceptance is deferred by user direction. Start in this order. Each milestone must demonstrate both supplied workbooks with unresolved content visible.

Stop the affected task for absent engineering approval, contradictory expected fixture data, destructive schema migration without backup, or failed source-integrity check. Continue independent ungated work and document the blocker. Do not invent missing engineering constants, acceptance counts or sign-offs. Implementation estimates should follow T01 evidence and the first adapter; no unsupported delivery date is committed.

## Decisions register

Approved by request: offline portable Python target; batch-first review; preservation of source files; planning-only work so far; both workbook families and seven code references in scope for planning. Proposed execution defaults: Python 3.12, Windows 11 x64, SQLite, local NiceGUI interface, PyInstaller portable directory, local single-reviewer audit identity. T01 must confirm feasibility before substantial UI work. Record any changed default with reason and impact.

User decision: qualified engineering approval is waived as a blocker to prototype implementation. T10/T11 must still mark draft rules/results `NOT VALIDATED`, withhold unsupported outputs and avoid fitness/pass claims. Follow-up release validation remains: permitted code editions (including B31.8-2020 versus supplied 2025), scope/jurisdiction, corrosion-rate selection and uncertainty policy, required structural minima, allowances, material sources/notes, independent benchmarks/tolerances, and interval policies. Requires user operational decision before pilot: supported machines, dataset scale, report branding/retention, reviewer identity requirements and permissible material-data distribution. Windows acceptance is deferred by user direction.

## Requirements traceability

IMP01–04 → T03/T04; IMP05 → T02/T05; IMP06 → T06; IMP07 → T05/T10; IMP08 → T06/T07/T11. Batch review contract → T07–T09. A01 → T01/T02/T13; A02 → T01/T03–T05; A03 → T04; A04 → T03/T04; A05 → T03–T05; A06/A07 → T06; A08 → T07/T11; A09 → T07–T09; A10 → T10/T11; A11 → T08/T10–T12; A12 → T01/T02/T09/T12/T13.

## Plan review and completion evidence

**Implementation update:** The five connected workflows requested by the user are implemented; see `planning/10_Completed_App_Workflows.md` and `IMPLEMENTATION_STATUS.md` for scope, executable evidence and remaining validation boundaries. The per-task checklists above retain the original broader specification and are not a claim that every certified/Windows/engineering gate passed.

Plan checked for source coverage, explicit task interfaces, dependencies, revision invalidation, batch-first workflow, offline deployment and unresolved engineering gates. The original plan began with all tasks pending. Application implementation and software checks have since run; current evidence is recorded in IMPLEMENTATION_STATUS.md. Independent drawing completeness, certified reading counts and engineering benchmark certification remain follow-up validation.


## Batch evaluation gap audit — 4 November 2026

The current prototype's homogeneous optional profile is not full component-aware batch engineering evaluation. Use [13_Batch_Evaluation_Gap_Assessment.md](13_Batch_Evaluation_Gap_Assessment.md) as the implementation-order assessment for engineering-record import, component/branch/lifecycle mapping, profile/policy storage, output readiness, batch execution and full evaluation reporting. Original T10/T11 validation items remain uncompleted where no evidence exists.
