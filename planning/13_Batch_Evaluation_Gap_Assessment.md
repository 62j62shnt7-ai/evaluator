# Batch evaluation: evidence and remaining implementation

Assessed 4 November 2026 against the application state before component-batch implementation and all three original workbooks. The initial gaps below are the design basis; implementation progress and current remaining gaps are tracked in [14_Batch_Implementation_Ledger.md](14_Batch_Implementation_Ledger.md) and `IMPLEMENTATION_STATUS.md`. Formal engineering approval remains waived as an app-build blocker; results must remain draft and must not declare equipment fitness.

## Target

One **Evaluate inspection** action must assess the whole current inspection using the correct component-specific records. It should calculate every supported, ready output, retain every unresolved location, and explain the exact missing dependency per output. Common input corrections should be applied once to a compatible group, not retyped for every reading.

The output needs a location/component grid with measurement history, applicable profile and source cells, required-thickness basis, apparent/adopted rates, remaining life, and exception status. To reach the evaluation coverage of the supplied sheets, MAWP, interval and due-date outputs also need implementations and explicit policy inputs; they are not present in the current engine.

## Current application boundary

- Whole inspection sheet import, raw/cached/formula evidence, canonical workbook preservation, history matching, grouped location decisions, undo and revisioned export exist.
- `Workflow.calculate()` accepts a single required thickness, adopted rate and optional design result for a selection of pairs. Those values are scalar at evaluation level. This supports a manually selected homogeneous profile, not automatic heterogeneous component evaluation.
- The simple flow applies the same two manually supplied thickness/rate values to all exact matches. A scope checkbox cannot establish different component inputs automatically.
- `engineering/draft.py` has seven pressure-thickness candidates plus historical rates, remaining life and maximum-of-supplied-minima arithmetic. It does not have a source-profile importer, typed material/property lookup, a per-location assignment resolver, or a batch runner.
- Evaluation sheets are correctly excluded as measured UT tables, but their design/property/policy records are not yet imported into the calculation model. Their contents remain accessible in the original workbook.
- Remaining-life computation is currently nested under confirmed old/current pairs with resolved dates and nonnegative apparent rate. Dependency handling must be separated per output: a missing historical date prevents a historical rate, whereas any permitted use of an independently supplied adopted-rate record needs its own explicit policy and readiness basis.
- MAWP, inspection interval, due dates, nozzle UG-45 design, and separate fitting/tee/reducer design paths are not implemented in the engine. Existing report exports cannot manufacture these results.

## What the workbooks already supply

Evidence and exact source-cell references are in `evidence/batch_evaluation/workbook_readiness.json`. The read-only audit is repeatable with:

```sh
PYTHONPATH=src .venv/bin/python tools/audit_batch_evaluation.py
```

All matches below are **label candidates** after punctuation/spacing and CAP/HEAD normalization. They are not approved physical identities or code-applicability decisions. Counts reconcile current observations to candidate/ambiguous/unmapped categories.

### Separator — both XLSX and XLSM agree

`Evaluation 2026` contains **38 component rows**: CML/head/shell rows 5–23 and nozzle rows 27–45. There are 38 formula-based required-thickness records with numeric caches and 38 literal selected rates. Material, pressure, temperature, stress, efficiency and diameter fields are available in the same rows. These are source records to propose, not values to ask the user to re-enter.

Against the 38 tabular current observations in `UT 10-2026`:

| Finding | Observation count | Meaning |
|---|---:|---|
| Unique component/point label candidates | 36 | Can propose profile assignments, subject to physical scope and record consistency |
| Same current thickness in the unique candidate | 19 | CML/head/shell values reconcile; this does not validate their design formulas |
| Different current thickness in the unique candidate | 17 | Nozzle evaluation rows conflict with the inspection readings and require explicit record reconciliation |
| Ambiguous observations | 2 | `N#3 / S` has two inspection rows and two evaluation rows |

Examples: `UT 10-2026!E34` is 39 mm while `Evaluation 2026!M27` is 12.5 mm; `E35` is 19.8 mm while `M28` is 12.4 mm. Preserve both and use measured inspection cells for current UT. Do not replace measurements with evaluation-sheet copies.

Dates also disagree: the current inspection has January-20/October-20 candidates, while evaluation cells M4/M26 say October-22. These are separate records until the inspection event is confirmed. Earlier January CML numbering differs from October; do not apply October profiles to January using point numbers alone.

Required-thickness cells include head/shell formulas and nozzle UG-45-related expressions. A numeric cache is a **provided result candidate**, not proof that the app has recomputed the appropriate rule or other loading minima.

### TL-B — May/June 2025

`Evaluation 6-2025` contains **80 populated component rows**, all with numeric caches for `tPd` and literal selected rates. `tPd` is a **pressure-thickness candidate**, not an established governing required thickness including structural minima and other applicable loads.

Against the 81 tabular May-2025 current observations:

| Finding | Observation count | Meaning |
|---|---:|---|
| Unique section/joint/band candidates with identical current thickness | 76 | Strong source-record consistency candidates, not engineering approval |
| Ambiguous observations | 4 | P22 tee and P23 reducer each have two sides/sizes currently collapsed by the location key |
| No profile candidate | 1 | Section 1 / joint 7 / band 2, inspection cell K157 |

The source preserves the branch information: `UT 5-2025!C195/C196` are 8-inch/6-inch, and `C197/C198` are 6-inch/8-inch. Corresponding evaluation rows 62–65 have different OD values. The normalized point model currently omits that branch/size distinction. Nominal pipe size and actual OD must remain distinct quantities; do not compare or convert them by guessing.

The header names B31.8-2020, while the supplied local B31.8 reference is 2025. The selected scenario/edition needs a once-per-scope decision. The F-column quantity must retain its property kind and source context: B31.8 strength is not interchangeable with VIII/B31.3 allowable stress. Even identical material captions have different F values in different component rows (for example 52,000 at row 7 and 35,000 at rows 62–65); grouping by material text alone is insufficient.

The UT May sheet's March-31-2026 header conflicts with the May-2025 campaign label. Evaluation 6-2025 has a June-8-2025 current-event date; another scenario uses May-24. These provide date proposals, not permission to silently replace the inspection date.

### TL-B — April 2026

The supported tabular UT region has **two new text-labelled points**, F151/F152. Neither has a corresponding section/joint/band record among the 80 rows of `Evalation 4-2026`.

All 80 evaluation-row O-column current values are **formulas**, such as previous thickness minus selected rate times time. They are projected values, not measured current UT. The whole source, including drawings, remains preserved, but these formulas must never fill missing measured readings. New/replaced points need their own lifecycle and profile linkage.

## Missing software, in implementation order

| Priority | Missing part | Required behavior |
|---|---|---|
| P0 | Engineering-record adapters | Import component records from the evaluation/design sheets with source hash, row/cell, literal/formula/cache distinction, units, code/scenario context, and record date. Do not import their calculated current cells as measured UT. |
| P0 | Component and lifecycle assignments | Connect profiles to physical current locations; retain section, joint, CML/band, branch/side/size and replacement identity. Normalize aliases only as review proposals. Expose conflicting or ambiguous assignments. |
| P0 | Versioned profiles and group defaults | Store per-component geometry/minima/material/property kind/rate inputs plus shared code/pressure/temperature/policy values. Apply common values once to compatible groups; allow per-row overrides. Do not apply one thickness to the whole asset by default. |
| P0 | Per-output readiness | Separate required-thickness, historical-rate, adopted-rate and remaining-life dependencies. Give exact missing fields and source conflicts per row. One blocked location must not prevent other ready rows calculating. |
| P0 | Batch runner and persistent row inputs | Resolve a profile for each current location, calculate supported outputs or retain null with reasons, then save the entire batch atomically with input/profile/policy/rule versions. Preserve stale-revision protection and undo. |
| P0 | Batch review/results/report UI | One readiness preview → apply grouped fixes/confirm proposed input groups → **Evaluate ready locations** → one combined report containing evaluated and unresolved rows. Add per-row input values/bases to exports; existing top-level scalar thickness/rate cannot represent heterogeneous results correctly. |
| P1 | Typed units and design-rule routing | Convert source psi/inch/F to the engine's unit contract, distinguish nominal/inside/outside diameter and allowable stress/SMYS, and choose a supported rule by geometry/code/edition. Preserve factors, allowances, structural minima and applicability limits. |
| P1 | Adopted-rate policy | Keep measured apparent ST/LT values separate from the adopted rate; import existing selected-rate proposals, version fallback/zero/increase/replacement policies, and confirm them once per compatible scope. Do not silently take the largest rate or a cached source value. |
| P1 | Fresh required-thickness calculations | Bind the supported pressure rules to component records, combine only justified additional minima, and flag unsupported nozzle/fitting/head geometry. Compare source caches to independently computed draft results without treating Excel as ground truth. |
| P2 / full evaluation coverage | MAWP, interval and due-date rules | Implement the missing output rules and policy parameters, including limitations and withholding. The supplied workbooks show these outputs, but current application code does not calculate them. Full source-like evaluation coverage is not complete until these are supported or explicitly reported unsupported. |

## Two explicit evaluation bases

1. **Provided-record basis:** propose a source's required-thickness or selected-rate record for the correct component. After its applicable scope is confirmed, evaluate supported outputs using actual inspection measurements. Label the minimum/rate as imported/provided and preserve the source formula/cache. A pressure-only tPd record still needs a governing-minimum basis; it must not silently become tRequired.
2. **Recalculated draft basis:** use typed design inputs and a supported versioned rule, plus structural/other minima and policy inputs. Report formula trace and dependencies. Unsupported geometries or missing governing minima remain exceptions.

This separates usable batch processing from unsupported claims of fresh code calculation. Neither basis implies equipment fitness. Independent engineering validation remains release follow-up and is not reinstated as a software-build approval gate.

## Proposed implementation interfaces

- `import_engineering_records(source_id) -> proposed_records` — scan only recognized design/evaluation layouts; retain original units and typed field provenance.
- `resolve_component_profiles(comparison_id) -> assignments + conflicts` — exact and proposed aliases, lifecycle/branch context, date/UT consistency.
- `preview_batch(comparison_id, policy_id) -> output_readiness + compatible_groups` — counts must reconcile to all current observations and comparison exceptions.
- `evaluate_batch(comparison_id, assignment_revision, policy_id, expected_revision) -> revisioned_result` — per-row inputs, outputs and issues, one atomic persisted batch.

Suggested storage: versioned `component_profiles`, `profile_assignments`, `evaluation_policies` and batch row snapshots. Existing workflow revisions, custody, undo and export mechanisms should be reused rather than rebuilding intake or matching.

## Acceptance required before calling the target complete

- [ ] Import the 38 Separator and 80 relevant TL-B records as proposals with exact source cells and typed property/unit context.
- [ ] Reconcile the 17 Separator nozzle value conflicts and the two N#3/S rows without overwriting measured UT or applying another event's profile silently.
- [ ] Preserve tee/reducer branch identity; account for TL-B's 76 unique candidates, four ambiguous observations and one unmapped point.
- [ ] Keep the two April new points unmapped until actual physical/profile linkage exists; never promote its 80 projected O values into measured current readings.
- [ ] One action evaluates heterogeneous ready locations with different minima/rates. A missing input, invalid row or unsupported rule does not abort other ready results.
- [ ] Distinguish historical-rate readiness from provided-rate remaining-life readiness under the explicit policy; missing current UT always remains missing.
- [ ] Group changes preview affected/excluded locations, require no repeated audit typing, and preserve source/profile/policy/rule revisions.
- [ ] Changing a mapped measurement, profile or policy makes affected batch outputs stale; undo and failed writes preserve the prior complete batch.
- [ ] Export every current location plus unmatched history, per-output status, all actual per-row inputs/bases, source hashes and formula trace. Counts reconcile exactly.
- [ ] No output status declares PASS/SAFE/fitness; `evaluated` means only that the supported calculation completed.
- [ ] Add MAWP/interval/due-date capabilities and benchmarks before claiming full source-like engineering evaluation coverage.

## Verification performed for this assessment

Read-only audit of formulas, cached values, source rows and current inspection observations; candidate counts reconcile per source. All three original workbook SHA-256s were unchanged by the audit. `tests/acceptance/test_sources.py` passed its two source-preservation tests. No runtime evaluation behavior was changed during this assessment, and the earlier 61-test application result is not presented as validation of the missing batch functionality.
