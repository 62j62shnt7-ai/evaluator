# Workbook evaluation method and app differences

Reviewed 4 November 2026 directly from the three originals under `sources/workbooks/`, with formulas and saved calculation values read separately. This is a record of workbook behavior and app differences, not confirmation that every workbook formula is correct. No workbook or app behavior was changed in this review.

## Evaluation sequence

1. Identify the asset, inspection event, physical component and measurement location. For TL-B, section/joint/band is sometimes insufficient without the branch/diameter. Replaced sections need separate measurement histories.
2. Assemble dated minimum UT measurements. Keep actual measurements, copied evaluation values and projected thicknesses distinguishable.
3. Attach the component's material property, pressure scenario, geometry, dimensions, joint/design factors and thickness limits. An asset can contain different materials, sizes and limits.
4. Compute historical corrosion rates from suitable measured pairs: `(older thickness - newer thickness) / elapsed years`. The source workbooks generally use 365 days per year. Multiple ST columns represent different pairs, not one universal historical rate.
5. Keep the selected corrosion rate as a separate input. Source selected rates are often literals and are not necessarily the maximum observed rate.
6. Calculate thickness margin and remaining life: `(current thickness - governing minimum) / selected rate`.
7. Calculate the maximum inspection interval where a formula exists, and preserve a separately chosen inspection interval where supplied. The next scheduled inspection can be earlier than the calculated maximum.
8. Calculate thickness available at the specified pressure-assessment horizon. Several sheets use `current - 2 * selected rate * horizon`. Preserve the factor and horizon as explicit source assumptions.
9. Calculate component pressure capacity using that thickness and the applicable component formula. Preserve the scenario and distinguish present from forecast capacity.
10. Retain row exceptions and report the limiting results across the applicable component scope. A minimum over the successfully calculated subset alone does not establish coverage of the whole asset.

## Separator 204

The XLSX and XLSM have identical cell values/formulas on all shared worksheets. The XLSM additionally contains four assistant/control preview sheets. This comparison does not establish equality of macros or drawing objects.

### Evaluation 2026

There are 19 CML/head/shell rows (5–23) and 19 nozzle rows (27–45).

| Quantity | CML/head/shell | Nozzles |
| --- | --- | --- |
| Current copied UT | M | M |
| Required thickness result | N | S |
| Selected rate | R, literal 0.25 mm/year | V, literal 0.25 mm/year |
| Thickness margin | S = M - N | W = M - S |
| Remaining life | T = S / R | X = W / V |
| Calculated maximum interval | U = MIN(10, T/2) | Y = MIN(10, X/2) |
| Forecast thickness | V = M - 2*R*1 | Z = M - 2*V*1 |
| Forecast pressure capacity | W | AA |
| Scheduled due date | X = M4 + 365 days | AB = M26 + 365 days |

The October-22-2026 evaluation date and one-year horizon produce October-22-2027 scheduled dates. The one-year follow-up is also stated in A49. It is distinct from the half-life/capped interval.

Example: Plate 1 / CML 1, row 6, contains 17 mm current thickness, 14.955453149 mm source required thickness, and 0.25 mm/year selected rate. Its saved results are 8.178187404 years remaining life, 4.089093702 years calculated maximum interval, 16.5 mm forecast thickness and 191.423487544 psi forecast capacity. Its scheduled follow-up remains one year.

Nozzle minima use a multi-step sequence: pressure expression N, 1/16-inch minimum O, a second expression P, literal tabulated value Q, R = MIN(Q,P), and S = MAX(R,N). P27 and P38 use a different expression from the other nozzle rows. The app currently imports S as a provided result; it does not reconstruct this entire sequence.

### Source inconsistencies to retain for review

- N5:N23 use the same `P*ID/(2*S*E - 0.2*P)` expression, including shell rows. W6:W23 instead use a shell pressure expression involving radius and 0.6 times thickness. A forward/inverse consistency check is needed before adopting this as a recalculation method.
- Both caps use the same required-thickness expression, but W5 uses a head pressure expression while W23 uses the shell expression. Geometry cannot be established just by copying these formulas.
- Inside diameter I is derived from M, the evaluation-sheet current thickness. If current measured UT is corrected, dependent geometry and pressure calculations must be recomputed or explicitly preserved as provided records; they cannot silently mix bases.
- For example, `UT 10-2026!E34` is 39 mm while `Evaluation 2026!M27` is 12.5 mm. E35 is 19.8 mm while M28 is 12.4 mm. Resolve copied-current conflicts without replacing measured UT.
- A49 is narrative text containing minimum-life and MAWP recommendations. It is not a live calculation and should not become a computed app result.

## TL-B pipeline

The workbook contains historical B31.3 and B31.8 evaluations and a separate 1500-psi reassessment. Preserve each as its own scenario; identical row labels across scenarios do not make their assumptions interchangeable.

### Evaluation 6-2025

All 80 component records have pressure-thickness formulas in I. The source expression is `P_psi * OD_in / (2 * strength_psi * 0.8) * 25.4`. The heading names B31.8-2020. The pressure-thickness result is not labeled as a structural/governing minimum. The older B31.3 sheet explicitly distinguishes pressure thickness I, structural minimum H and governing thickness J = MAX(I,H).

The date headers K5, L5 and N5 define historical pairs. O, P and Q carry separate apparent rates. S is the selected rate: 78 rows use 0.13 mm/year, one uses 0.16 and one uses 0.37. This demonstrates why selection cannot be inferred as MAX of the apparent rates.

T uses `(N-I)/S`. Of 80 U interval cells, 54 use `MIN(T/2,10)` and 26 contain the literal 6 years. V uses `N - 2*S*U`, so the chosen interval also determines pressure-assessment thickness. W uses `2*0.8*strength*V/(OD*25.4)`. Some Y cells derive dates from U and N5; others are blank. X compares forecast pressure capacity with the selected scenario pressure and contains the workbook's result wording.

Example, row 7: pressure thickness 3.949669471 mm; current 11.9 mm; selected rate 0.13; remaining life 61.156388683 years; interval 10 years; forecast thickness 9.3 mm; forecast pressure capacity 3531.941116056 psi. The source's apparent rates in O7/P7/Q7 are approximately 0.01899/0.02284/0.02865, all below the selected 0.13.

P22 tee rows 62–63 have OD 8.625 and 6.625 inches; P23 reducer rows 64–65 reverse those sizes. Treat those as distinct component sides. F62:F65 contains 35000 psi despite the API 5L X52 material caption, whereas F7 contains 52000 psi. Preserve and flag the property discrepancy; do not overwrite it through material-name grouping.

### Evalation 4-2026

All 80 O current cells are projections: `N - T * elapsed_years`, from June 8, 2025 to April 7, 2026. They are not 80 new UT measurements. Selected rate T is 0.15 in 79 rows and 0.37 in one.

The dated columns K, L and N contain literal minimum UT readings, with their inspection dates in the header row (K5, L5 and N5). These can be imported as separate campaigns from this worksheet and compared with each other to calculate an apparent rate; a second workbook sheet is not required. Formula cells such as O15 are projections, and maximum-reading columns must never be included as measured UT history.

U remaining life uses projected O. V has 41 half-life/capped formulas, 28 literal five-year intervals and 11 literal ten-year intervals. W forecast thickness uses prior measured N, not projected O: `N - 2*T*V`. This mixes time bases relative to U and must be exposed as a source discrepancy before defining a consistent forecast mode. Z date formulas generally use the April evaluation date O5. Z7 is a pressure minimum `MIN(X7:X500)`, despite being in the remarks/due-date column; do not interpret every nonblank Z value as a date.

### Older scenarios

The B31.3 August-2023 sheet includes design pressure 1400 psi and a parallel 1000-psi derating scenario. It preserves structural minima and governing thickness separately. Some previous/current columns contain NA or projected values; the latest column label alone does not establish a usable measured reading. The B31.8 August-2023 sheet uses a B31.8-style pressure-thickness expression but some pressure-capacity formulas have the B31.3-style denominator correction. That source inconsistency requires explicit review.

## Concrete differences in the current app

### MAWP rule clarified from the TL-B row 15 example

The user clarified that the batch should report MAWP at the remaining-life endpoint and MAWP at the next inspection. Both use the full remaining life by default. A manually selected interval changes the next-inspection projection using the workbook's two-rate multiplier. This preserves matching MAWP projections in the ordinary formula-driven case and lets explicit interval overrides produce different results.

TL-B `Evalation 4-2026` row 11 has the interval formula `MIN(remaining_life/2, 10)`. The user asked to apply this formula to row 15 by default. Row 15's literal five-year V15 remains available as a manual override. When that override is used, W15 is `N15 - 2*T15*V15` = 5.3 mm and X15 is 2012.8267 psi. N15 is the preceding measured 6.8 mm value; O15 is a projected 6.6755 mm value. The source schedule Z15 is five years from the April 7, 2026 event. Keep that source basis and the measured/projected distinction in the trace.

Separator's one-year due-date formulas are explicit schedule inputs, separate from its calculated maximum interval. TL-B due-date formulas generally derive from the selected interval. Retain source formula/cache provenance. If a reviewer changes the interval, recompute the due date and next-inspection projection from the override.

| Priority | App behavior found in code | Workbook-driven requirement |
| --- | --- | --- |
| 1 | `engineering/records.py::_policy` recognizes half-life/capped MIN formulas but a literal row like TL-B row 15 does not inherit the adjacent formula | Propose the neighboring copied formula for row 15 as the default and retain its literal five-year value as a manual override |
| 1 | `engineering/batch_rules.py::outputs` derives due date from the half-life/capped interval | Preserve supplied schedule dates; recompute them only when a reviewer overrides the interval |
| 1 | MAWP forecasts do not use the remaining-life endpoint and next-inspection bases | Calculate both forecast bases; use the workbook's two-rate projection at the next inspection |
| 1 | Forecast years/factor are not linked to the selected inspection schedule | Derive the next-inspection horizon from the source schedule/selected interval and retain formula/cache provenance |
| 1 | MAWP and forecast MAWP are distinct outputs, but source pressure results are not captured as provided output records | Preserve source forecast result and basis; compare against equivalent app outputs rather than present-thickness MAWP |
| 2 | The app uses 365.2425 days/year by default | Expose and preserve 365-day source arithmetic for workbook comparisons; store the date-rounding convention |
| 2 | History comparison expects two campaigns but import recognizes only one date per conventional UT sheet | Import dated minimum-reading columns as campaigns so two dates from one worksheet can be compared; keep apparent rates separate from adopted rate |
| 2 | The app supports provided required-thickness caches and selected rates, but cannot rebuild the nozzle sequence | Retain provided-record mode and visibly distinguish it from a fresh component design calculation |
| 2 | Recalculation and provided results can use geometry/property caches derived from conflicting copied measurements | Track dependency basis and invalidate/recompute affected results when measurements or scope change |
| 3 | Source scenarios are proposed using thickness consistency; latest event and projection basis need review | Keep inspection event, evaluation date and projection horizon explicit in scenario selection |
| 3 | Component minima are available per row | Summarize limiting location, life, forecast capacity and schedule with coverage and unresolved rows retained |

The app already contains batch profiles, typed conversions, component assignments, independent draft outputs and persisted results. Earlier planning text describing MAWP/interval/due-date as entirely unimplemented is stale. The correction should extend the existing model rather than create a second evaluation engine.

## Checks completed and implementation basis

- Read source formulas and saved results separately, including all 80 current TL-B evaluation records and all 38 Separator records.
- Compared all shared Separator worksheet cell values/formulas across XLSX and XLSM: zero differences.
- Grouped formulas by their relative references to find exceptions instead of assuming all rows copy the first row.
- Compared adapters, batch orchestration, output arithmetic and UI inputs against those source rules.
- Regression tests exercise the TL-B dated minimum columns and a same-sheet comparison using rows from `Evalation 4-2026`. Workbook cached results are comparison fixtures, not independent engineering validation.

Implement the selected-interval/scheduled-date/forecast dependencies first. Preserve discrepancies as reviewable source facts and add focused regression cases for the one-year Separator follow-up, TL-B row 15's inherited interval formula and five-year override, selected rates differing from apparent rates, mixed measured/projected thickness and branch identity.
