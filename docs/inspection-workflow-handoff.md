# Inspection workflow handoff

Saved November 18, 2026 on branch `feat/mawp-v08-code-routing-phase1`. Implementation changes are in the working tree. The live project database is under the user's `UT Inspection Evaluator` folder.

## Resume here

Open the [oil-line comparison](http://127.0.0.1:8765/?comparison=0d7f7b42-4464-463f-9e4d-875d059f6353) for the 8-inch oil line from WD 33-15 to WD 33-1 MFD. The user asked to use Chrome for browser tests. Finish piping and pipelines before returning to vessels and tanks. The broader implementation plan is in [the code-specific pressure assessment plan](superpowers/plans/2026-11-18-code-specific-pressure-assessment.md).

- The comparison has 72 UT locations. Under **Review straight pipes in batch**, 43 of 51 straight-pipe locations have workbook input proposals with source cells. The proposals require inspector confirmation. The owner-confirmed correction for the oil-line workbook changes the interpretation of `Evaluation 11-2024!F1` from B31.5 to B31.3 and retains the original label in the trace.
- **Review Sleeve-T locations** lists the three readings for joint 1362 at `F204:F206`. The app withholds pressure pending a dedicated approved assessment.
- Chrome testing on a copy of the real comparison exported 72 rows, including 43 next-inspection pressures in psi with workbook references and three withheld Sleeve-T readings. The live comparison retains the workbook correction and awaits inspector review.
- On the Section 2 gas-line workbook, tee and reducer qualifications carry forward within the same imported sheet by physical fitting tag and exact UT location. Cross-workbook carryover still needs a verified identity mapping. Bend-position checks, UT-linked B31G, and documented pipeline MAOP/MOP workflows are implemented.

## Records still needed

- Oil-line straight-pipe locations `F151:F153`, `F167:F170`, and `F183` need matching reviewed design and corrosion inputs.
- Sleeve-T needs the as-built drawing, sleeve and carrier dimensions and materials, weld or reinforcement details, mapped UT coverage, and an approved pressure assessment.
- The remaining 18 oil-line fitting UT locations need documented pressure limits, applicable minimum wall, and assessment references.
- Pipeline production validation needs real segment and defect IDs, UT or ILI records with depth and axial length, pipe OD and nominal wall, grade and SMYS, and the documented limits that establish MAOP or MOP.

## Piping and pipeline method coverage

Construction editions below are the editions implemented by the app. The reviewer establishes the applicable construction and in-service basis for each asset. Pressure inputs and outputs are shown in psi, OD in inches, measured and required walls in mm, and corrosion rates in mm/year.

| Service and component | Rule and result | Evidence and limits | Verification |
|---|---|---|---|
| Process piping or confirmed production flowline, straight pipe | B31.3-2024 §304.1.2, local internal-pressure candidate at measured or projected wall | Confirm code boundary, OD, stress at temperature, E/W/Y, allowances, dated UT and rate. Thick-wall and high-pressure cases require a separate design route. API 570 fifth edition + Addendum 1 §7.5 supplies the applicable in-service wall deduction when selected. | Equation/inverse tests and oil-line workbook workflow exercised. Approved asset inputs and independent calculation still required. |
| Process piping, reviewed bend positions | B31.3-2024 §304.2.1, local internal-pressure candidate by bend position | Confirm OD, centerline radius, position, stress and factors, allowances and mapped UT. A grouped result needs coverage of each required position under the same basis and horizon. | Position arithmetic and incomplete coverage tested. Section 2 exercise used a synthetic design basis. |
| Process piping, listed elbow, tee or reducer | B31.3-2024 §§302.2, 303 and component clause, documented wall check at the entered rating and temperature | Match the fitting and location to its qualification, documented minimum and temperature. A stepped qualification requires a reviewed pressure/wall schedule within its documented bounds. | Withholding, scope isolation and qualified steps tested. Field fitting records remain outstanding. |
| Oil-line Sleeve-T | Pressure withheld | Dedicated approved design and mapped measurements required. | Withholding exercised on three workbook readings. |
| Liquid line or confirmed production flowline, straight pipe | B31.4-2025 §403.2.1, pipe design-pressure candidate | Confirm route, OD, credited wall, SMYS, design and weld factors, and applicable deductions. | Equation/inverse tests. Asset-specific source verification remains open. |
| Gas line or confirmed production flowline, straight pipe | B31.8-2025 §841.1.1, pipe design-pressure candidate | Confirm route, OD, credited wall, SMYS, class/design, seam and temperature factors, and applicable deductions. | Equation/inverse and selected lookups tested. Original TL-B workbook and reviewed pipeline basis remain open. |
| Pipeline metal loss, reviewed defect or cluster | B31G-2023 §2.2(b), modified Level 1 failure and screening pressure | Review scope and interaction, supply OD, nominal wall, axial length, depth, flow stress, safety factor and applicability reference. Linked depth uses a dated UT reading plus entered uncertainty. Original Level 1 and Levels 0, 2 and 3 remain outside this workflow. | Archived G-BENCH-04–07 exercised against Appendix A §§A-4–A-6, including the effect of uncertainty on the published pressure comparison. G-BENCH-01–03 require original Level 1. Real segment validation is open. |
| Pipeline segment, documented operating limits | MAOP/MOP pressure comparison using the lowest applicable documented limit | Record the segment and the evidence or inapplicability decision for design, test, operating/history, component and other limits. Applicable code and jurisdictional limits require an approved basis. | Workflow exercised with supplied test inputs. Approved segment limit records remain open. |

## Evidence check on November 18, 2026

- All 29 files listed in `sources/local-manifest.json` matched their SHA-256 hashes, including the Section 2 originals, the v0.8 archive and the saved project evidence.
- `python -m pytest -q -rs` with Python 3.15.2 exited successfully with 180 passed and 49 skipped. This rerun used the checkout's default source directory and did not write to the live comparison.

| Missing acceptance evidence | Skipped tests |
|---|---:|
| `TL-B from SAG Gas MFD to GP.xlsx` | 32 |
| `Separator-204 Inspection Report.xlsx` | 13 |
| `Separator-204 Inspection Report.xlsm` | 3 |
| `engineering-calculations/evaluator_calculations_verified.zip` | 1 |

The skip counts above refer to the original workbooks and benchmark package. The tests use pytest, including pytest-style functions. Use the development environment for the release suite. The bundled launcher runtime lacks pytest and uses an isolated import path.
