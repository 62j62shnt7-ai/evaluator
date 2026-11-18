# Code-specific pressure assessment implementation plan

**Goal.** From a measured UT location, produce a reproducible assessment at the selected next inspection date, in the user's field-specific units, with the governing method, values and evidence visible. Deliver this through the existing workbook → Location Review → batch calculation → export workflow.

**Baseline and specification.** Use branch `feat/mawp-v08-code-routing-phase1`, reviewed at `47500e2`. Read the master blueprint, rule register, decision register, reference arithmetic and test matrix inside `sources/plans/MAWP_Implementation_Plan_v0.8_REATTACHED.zip`. Apply the user's current requirements for fittings and psi throughout. Use `docs/local_files.md` for the source inventory. The earlier Row 7 workbook provides a reproduction fixture. An independent engineering example establishes whether a method implements its governing edition.

**Implementation approach.** Extend the Python engineering modules, SQLite project storage, existing JavaScript workspace and existing export writers. Implement in sequence using the executing-plans skill. Each numbered task has a deliverable and an acceptance check. Add the regression case first, implement through the normal workflow, run the focused tests and review the diff before continuing.

## Inspector workflow and live interaction requirements

Deliver the new workspace with the first mixed pipe-and-fitting release. The existing screen layout is replaceable. Retain import, calculation and audit services that pass the acceptance tests. Prototype the following journey against Section 2 data before building out additional code families.

1. **Open work.** Start on recent projects with a clear Import workbook action. Preview sheets, campaigns, date precision, units, detected component types and unmatched readings before import. Reopening a project returns to its last sheet and location.
2. **Review the sheet.** Put a searchable location list beside the location editor. Show location, component, latest measured wall (mm), adopted rate (mm/year), next date, scoped pressure (psi) and assessment status. Include filters for missing UT, missing engineering evidence and changed results, each with a count. Retain selection, scroll and filters when moving between locations.
3. **Assess one location.** Keep location, component and method visible while editing. Group the minimum necessary fields under UT history, construction and inspection basis, and next inspection. Distinguish editable measurements or overrides from read-only derived values. Show units at the point of entry. Beside a prefill, offer its source and a scoped override or restore action. Show earlier campaigns in date order; identify the points used in each rate.
4. **See the consequence.** Keep a results panel alongside the inputs. Lead with the next assessment date and applicable component pressure in psi, or a precise missing requirement. Show today's comparable pressure, expected physical wall, credited wall, governing minimum, adopted rate and interval immediately below. Expand a result to inspect the equation, substitutions, units and source. For a documented fitting check, lead with projected wall versus the documented minimum and show the pressure/temperature at which that check applies.
5. **Save and continue.** Editing creates a live draft. Save the inputs and calculated snapshot together with a revision; offer Save and next unresolved location. Warn before discarding pending edits. Export uses the saved revision and identifies rows with withheld results. Preview batch changes with affected locations, exceptions and changed results before applying. Offer undo.

### What updates during entry

| Change | Immediate feedback | When information is missing |
|---|---|---|
| Previous/current UT or inspection dates | Elapsed time, loss and observed rate; eligible short/long-term rates; basis for the adopted rate | Keep valid measurements visible. Highlight invalid chronology, mismatched location or units. An increase in wall flags review. |
| Material, product form, size, temperature or edition | Refresh eligible dimension/property lookups, identify changed factors and recompute dependent values | Remove values that lost their basis. Show the precise missing qualifier or eligible source choices. |
| Code, geometry or fitting type | Switch required fields, applicable pressure label, units and evidence requirements | Preserve shared measurements. Exclude incompatible prior values from calculations. |
| Governing wall, adopted rate or design factors | Recompute affected pressure checks, governing minimum, margin, life and interval as prerequisites become available | Show any independently available outputs; explain the first missing dependency beside each blocked result. |
| Next inspection date or interval | Synchronize the other field under the selected date policy, show interval-limit issues, and update expected wall, credited wall and next-date pressure | Clear the dependent forecast for invalid input. Preserve today's result if its inputs remain valid. |
| Fitting rating, rating temperature, qualification or minimum wall | Update the applicable fitting check or qualified pressure calculation and show the governing evidence | Offer a direct action such as “Add reducer qualification” or “Match previous UT”. |

Use the same authoritative calculation service for preview, save and export. Preview must be read-only and scoped to the current edit. Debounce typing, ignore responses from older edits and clear or visibly mark dependent results while recalculating. Support partial decimals, paste, tab navigation and unit-aware validation without moving focus. Preserve draft input on service failure and offer retry. Announce errors and result status to assistive technology. Use text as well as color.

**UI acceptance before rollout.** Exercise the normal browser workflow in addition to service tests. On a laptop viewport, complete pipe, elbow, tee and reducer assessments using the keyboard. Verify narrow layouts and 200% zoom preserve field labels, units and actions. Enter 10.0 mm then 9.5 mm exactly 365 days apart under the 365-day policy and observe 0.5 mm/year without pressing Calculate. Edit the interval twice quickly and verify only the latest date and pressure survive. Remove the previous UT and verify the old forecast disappears. Change fitting type, inspect a prefill source, correct one row in a batch, undo, save/reopen and compare the result to the export. Have an inspector run the pilot from import to export without coaching and record any point where they cannot identify the next action or explain where a result came from.

## 1. Freeze the evidence and define what the app can calculate

- [ ] Back up the project, use a disposable copy of the saved snapshot and record source hashes, branch revision, runtime and baseline test results. Inventory available code editions, addenda, errata, workbooks and benchmarks against v0.8. Record each skipped source-dependent test with its missing file.
- [ ] Build one coverage table keyed by asset/service boundary, component, construction edition, in-service edition, loading or damage case and exact rule. For each route record the output type, equation/clause, applicability limits, required inputs and units, allowed sources, exclusions and benchmark status. Reconcile the archived rule and test IDs with the live implementation and mark each implemented, partial or outstanding.
- [ ] Establish distinct outcomes for calculable component pressure, documented-rating check, missing inputs, outside method scope and superseded result. Show measured history wherever it remains usable. Keep engineering validation status separate from computational success.

**Acceptance.** Every method offered in Location Review maps to a coverage row. Every outstanding calculation has a named missing method, source, decision or benchmark. The run can be repeated without modifying the original workbooks.

## 2. Make routing, required fields and their sources agree

- [ ] Extend `src/evaluator/engineering/code_context.py` to return the construction and inspection bases, method revision, component scope and output kind. Persist both bases and the evidence for the applicable edition, including addenda. Confirm boundaries for mixed sheets and production flowlines. Keep per-location exceptions visible when a sheet default is applied.
- [ ] Define each method's input list once and use it for form generation, server validation, calculation and trace. Tag values as measured, equipment-record, verified table lookup, reviewed manual entry or calculated. Carry the original value/unit, normalized value/unit, source cell or record, edition/table/row and applicable conditions. Give each manual override a scope and basis.
- [ ] Extend `verified_tables.py` and the input resolution in `batch.py`. Resolve dimensions, material, specification, grade, product form, temperature and factors against their own sources. Permit interpolation only where supported by the governing source. Present ambiguous matches as choices. Eliminate the fixed-material stress fallback from code assessments and workbook-inferred unity factors from confirmed engineering inputs. Distinguish a missing allowance, an explicit zero and a method with no allowance term.
- [ ] Invalidate dependent lookups and results on changes to temperature, material, geometry, edition, rating, schedule, units or inspection history. Preview which rows a batch edit will affect and flag conflicting overrides.

**Acceptance.** Changing temperature invalidates the former stress. Changing a tee to a reducer clears incompatible fitting fields. A missing required factor blocks the dependent pressure and names the missing field. No input from one code satisfies a different method solely because its display label matches.

## 3. Fix corrosion, interval and pressure semantics together

- [ ] In `batch.py`, `engineering/batch_rules.py` and `engineering/row_example.py`, separate measured history, adopted corrosion rate, interval selection and pressure assessment. Share date and unit arithmetic. Retain each method's rate-selection rules. Where the inspection basis calls for short- and long-term rates, calculate both from eligible campaigns and record which governed and why. Require review of replacement, ambiguous pairings, increased wall and nonpositive rates.
- [ ] Establish the governing required wall using the checks required by the selected method. Resolve the permissible interval and the selected next date separately. Check a selected interval against the applicable limit. Record date precision and interval basis. A missing date or invalid interval must explain why the next-date result is unavailable.
- [ ] Calculate expected physical wall and the wall credited in the pressure equation separately. Record elapsed years, adopted rate, projected loss, method-specific deduction and allowances so each deduction is applied once. Remove the automatic remaining-life endpoint from the next-inspection path. Withhold positive next-service conclusions when the wall is exhausted, outside the equation domain or already at a governing limit.
- [ ] Compute today's and next-date pressures independently where supported. Give each result its date, wall, equation, pressure meaning and units. Retain a remaining-life endpoint only as an explicitly identified separate calculation if required by the workbook. Replace Row 7's blanket “Safe” result with a scoped comparison and supporting figures.

**Acceptance.** The historical Row 7 fixture reproduces its observed 0.09367 mm/year, 10-year interval, 9.427 mm credited wall and approximately 1,782.5 psi within declared rounding. In a separate independently checked case, remaining life exceeds the selected interval and today's pressure differs from next-date pressure. Selecting code factors preserves the selected date. A higher manual rate exercises the different fitting and Row 7 rate paths against their documented bases.

## 4. Deliver process piping and fittings in the first usable release

| Route | Inputs and evidence to resolve | Intended result |
|---|---|---|
| B31.3 straight pipe | Design conditions, verified diameter, material/product form and allowable stress at temperature, applicable E/W/Y, allowances, wall and inspection basis | Required wall and component pressures at the two assessment dates for the supported internal-pressure case |
| Elbow or bend | Component identity, product standard or qualification, size, angle/radius and measurement position where required, material, conditions, dimensions or rating evidence | Geometry-specific pressure if qualified, otherwise a documented-pressure and wall check where evidenced |
| Tee or branch | Run and branch identities and dimensions, reading location, listed fitting or fabricated connection, applicable qualification or reinforcement evidence | Result for the identified fitting/connection and location under its supported method |
| Reducer | Large/small ends, measured location, reducer type and applicable transition geometry, standard or qualification, material and rating evidence | Result for the applicable section and documented construction |

- [ ] Extend `engineering/fitting_review.py`, batch dispatch and the workspace forms. Populate each row from its matched component record, drawing, manufacturer data or reviewed reference table. Separate listed/rated components, components with a supported design calculation and components requiring individual qualification. A nominal piping class, adjoining pipe schedule or common line ID alone cannot establish a fitting's capacity.
- [ ] For each qualified pressure method implement its own applicability checks and dated wall-to-pressure calculation. For a rating check, capture pressure in psi, its temperature basis, minimum wall, reference and assessment date. Display the rating as an input and the wall-check outcome as the result. Display exactly which qualification or field would enable a withheld calculation.
- [ ] Exercise import, batch prefill, single-row correction, calculation and export for pipe, elbow, tee and reducer on the same sheet. Prevent a group edit from propagating size, end, rating or minimum wall to incompatible fittings.

**Acceptance.** The Section 2 fixture accounts for all 54 locations by identity and disposition, including 31 pipes, 13 elbows, 4 tees and 6 reducers. Reconcile M9, M21 and M51 using physical-location evidence or retain their unresolved status. Synthetic documented limits can test software behavior. Real fitting results require actual supporting records. Include positive, missing-evidence and wrong-geometry cases for each fitting route.

## 5. Deliver the remaining code families independently

| Delivery | Method work and acceptance |
|---|---|
| B31.4 liquid pipelines | Verify service boundary, material strength, applicable design/joint factors, dimensions and pressure constraints. Hand-check the eligible component design-pressure calculation and identify missing operating-limit evidence. |
| B31.8 gas pipelines | Verify location class and applicable exceptions, material strength, design, joint and temperature factors and their sources. Test a case where a basic class factor is inapplicable. Report calculated design pressure and the status of MAOP constraints separately. |
| Pipeline corrosion | Implement eligible B31G assessments from the v0.8 register using the required defect dimensions and applicability checks. Include an excluded defect and a missing length/profile case. A single UT minimum cannot supply missing defect geometry. |
| Section VIII-1 and API 510 | Verify stress from the applicable II-D material table and temperature, dimensions, joint efficiency, shell stress directions, head geometry and applicable pressure/head corrections. Benchmark shells and each supported head separately. Resolve the governing component and pressure reference before reporting vessel MAWP. Give nozzles and other unresolved components explicit dispositions. |
| API 650/653 tanks | Preserve the tank workflow and its field-specific units. Verify course-specific thickness, product and liquid level inputs and applicable in-service limits. Deliver supported thickness or fill-height results in the tank view. |

For every family, use the licensed edition to verify equations, limits, factors, allowances and result terminology. Include fittings in the coverage table for **each** family. Reuse identification and source lookup infrastructure; qualify fitting arithmetic separately under the governing code. Preserve a documented limit as a constraint when assembling a system result. An unresolved potentially governing component leaves the system result incomplete.

**Acceptance.** Each enabled method has a reviewed source entry, a positive independent benchmark, a boundary test and an excluded case. Track unsupported combinations in the UI and release scope. Complete the family in the table before claiming support for it.

## 6. Enforce the user's units, persistence and export contract

- [ ] Inventory actual workbook headers and the user's earlier field definitions. Adopt psi for user-facing pressures, MAWP, ratings and stresses; inches for pipe diameters where specified; mm for UT, wall, allowances and minima; mm/year for corrosion; °F for temperature; years for intervals. Preserve other geometry- and tank-specific units from their own field definitions. Distinguish nominal size from measured diameter. Preserve source units alongside conversions.
- [ ] Use one tested conversion and formatting path at the boundary. Internal, explicitly unit-tagged MPa may remain. Change `static/workspace.js`, calculation traces, sample pages, fitting forms, `form_export.py` and every active CSV/XLSX/HTML/JSON writer to consume the same result. Give machine fields explicit unit names. Preserve precision until display. Carry pressure kind, date, governing wall, input provenance and reasons for withheld results through export.
- [ ] Version results and export schemas. Recognize legacy MPa fields and convert exactly once. Preserve historical exports and audit records. Flag ambiguous legacy horizons for recalculation before presenting them as a new next-date result. Verify backup, restore, undo and stale-result handling on a disposable copy.

**Acceptance.** A known 1,000 psi result displays and exports as 1,000 psi after fresh calculation, save/reopen, legacy-project read and backup/restore. A missing pressure remains blank with its reason. The table, detail view and export all identify the same component, date, pressure type and value.

## 7. Validate and release

- [ ] For each active route record independent expected values, units, intermediate steps, source and tolerance established before comparing with the app. Keep workbook parity and engineering verification as separate test outcomes. Exercise date precision, zero loss, wall increase, overlapping allowances, temperature limits, wrong units, manual intervals and mixed-code sheets. Reconcile cases to the archived v0.8 test matrix.
- [ ] Run `python -m pytest -q -rs` from the checkout with the development dependencies installed. Run source-dependent acceptance with available originals. Record passes, failures and skips separately. The [handoff](../../inspection-workflow-handoff.md) records the November 18 run and the missing sources. Repeat at the release revision.
- [ ] Pilot the real Windows launcher against a fresh project and a restored copy. Have an inspector import Section 2, assign bases, prefill a mixed batch, resolve one exception, compare current and future results and export. Reconcile each row and inspect the generated workbook and reports. Confirm original source hashes, workbook layout and historical project recovery.
- [ ] Ship a versioned release with supported editions/methods, known exclusions, migration and rollback steps, and a short example using the user's units. Preserve draft status for methods awaiting engineering verification. Record review of the source mapping and independent calculations before describing a route as validated.

**Completion criteria.** A reviewer can start at any pressure in psi, identify exactly what component, condition and date it covers, reproduce the credited wall and every equation input, and locate the evidence for each value. Every imported location has a result or an actionable explanation. A calculated component pressure, a documented fitting rating, a pipeline operating constraint and a tank level remain distinguishable in every output.

## Implementation status after the Section 2 delivery

- Section 2 import, sheet code basis, pipe review, live measurement preview, fitting rating checks and CSV download have been exercised in Edge. The real workbook contributes 54 locations. The fitting checks use synthetic documented limits until location-specific qualification is supplied.
- The batch workbook ledger, active CSV, revision-package batch columns and saved forecast trace now present pressure in psi. B31.3 code-method forecasts preserve month-only inspection dates.
- The remaining engineering validation needs a clause-level rule register checked against the supplied PDFs, independent expected results and source workbooks. The current source collection contains Section 2, with no original TL-B or Separator workbook and no independent benchmark package. Fitting methods, pipeline metal-loss assessment, system pressure limits and tank methods require individual coverage and verification before release. The existing vessel, pipeline and tank candidates remain draft.

### Records needed to close engineering acceptance

Use the line, equipment tag and UT location identifiers from the source documents so each record can be matched without guessing.

| Scope | Required records |
|---|---|
| Section 2 fitting inventory | Marked-up isometric or fitting register for 13 elbows, 4 tees and 6 reducers. Include tag/location, standard and edition, material specification and grade, size and end dimensions, rating or qualification reference, design pressure and temperature, the applicable minimum wall and its calculation basis. Supply previous UT point matches or replacement history for M9, M21 and M51. |
| Elbows and bends | Drawing and documented basis for applying B31.3 para. 304.2.1, OD and centerline radius, material/stress at temperature, E/W/Y and allowances, UT map identifying intrados, extrados, sidewalls and end tangents. |
| Tees and reducers | Manufacturer rating or qualification report for listed components. For individually designed components supply the approved calculation and dimensioned drawing, including run/branch and reinforcement data for tees and both ends, transition profile and governing minima for reducers. Supply thickness maps at the limiting locations. |
| Pipelines | Original TL-B workbook, tagged alignment and code boundaries, pipe grade and seam records, verified class/design factors and pressure-test, operating and component limits. For metal-loss checks include axial profiles, length, depth and spacing, reference wall, and defect classification. |
| Vessels | Original Separator-204 workbook, nameplate/data report, drawings with shell/head/nozzle dimensions and pressure reference elevation, material records, design temperature, joint efficiencies and UT maps. Include permitted static head and service conditions used by the approved calculation. |
| Tanks | Design and inspection reports, tank/course drawings and elevations, material and weld data, liquid specific gravity and fill limits, course UT and relevant bottom/annular/settlement inspection evidence. |
| Independent verification | For each method supply one approved calculation with inputs, clauses, intermediate values, result and units, plus any known boundary or excluded case. |

### Additional verification

- Edge imported Section 2, entered a synthetic bend design basis against an actual UT pair, switched from intrados to extrados and exported the resulting local pressure in psi. The approved bend records are still needed for field use.
- The code library now offers modified B31G-2023 Level 1 as a standalone defect screen. Annex A Example 4 provides a reference arithmetic check. Project-linked defect assessment and system MAOP/MOP still need segment and defect evidence.
- The source collection contains synthetic vessel and tank UT workbooks. These support software tests. Actual vessel and tank assessment acceptance requires the records in the table above.
