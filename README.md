# UT Evaluator

The active app follows one pipe evaluation workflow:

1. Import an XLSX/XLSM UT sheet and select previous/current inspections.
2. Select readings and apply group inputs: material, pipe size/schedule, Pd, structural thickness and selected CR.
3. Pipe size/schedule fills OD and nominal thickness; custom dimensions remain editable.
4. Click a location and choose **Edit this row only** for an individual override.
5. Calculate all readings, review missing inputs and export the evaluation CSV.

A106 B and A234 WPB currently use fixed S = 20,000 psi. Calculated CR uses each reading pair’s inspection dates and a 365-day year. A positive calculated CR governs; otherwise a positive selected manual CR is required. Required thickness is the maximum of structural and pressure thickness. Interval is `MIN(10, remaining life / 2)`; MAWP thickness is `current UT − 2 × CR used × interval`. MAWP is compared with Pd. The next inspection uses the calculated interval.

Month-only source dates retain month precision. Missing readings or inputs remain visible. Original source files, correction history and undo are retained.

Run with `.venv/bin/python -m evaluator` or the desktop launcher. Open [the local app](http://127.0.0.1:8765/).

The alternate calculators, vessel configuration screens, source-scenario controls and legacy HTTP workflows have been retired from the active app. Internal import/storage modules remain where the current workflow depends on them.
