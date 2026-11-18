# UT Evaluator

The desktop app imports inspection workbooks, matches dated UT readings, and
runs code-scoped engineering checks. Saved results are **DRAFT / NOT VALIDATED**.

## Inspection workflow

1. Open **Workbook library**, import an XLSX or XLSM report, and select the UT
   comparison sheet. This import uses the selected sheet for its readings and
   source inputs. Choose fitting-specific calculations or straight-pipe
   screening for elbows, tees, and reducers.
2. In **Inspection grid**, check the previous and current UT matches and set
   the construction code, service boundary, and evidence. Select materials
   from the library and use **Batch inputs** for shared values. Click a
   missing input in its row to correct it in the app.
3. Use **Fitting review** if you want an optional check against a documented
   fitting rating. Straight-pipe screening produces draft results under its
   stated assumptions. A Sleeve-T requires a separate approved assessment.
4. Click **Calculate ready locations**. The **Calculations** tab opens a
   read-only table with the saved results and reasons for withheld results.
   **Download Excel (.xlsx)** exports the same snapshot. The workbook has a
   frozen header and location column, filters, and numeric result cells.

Use **Code reference library** for source tables and sample calculators,
or **Tank assessments** for the separate API 650 and API 653 workflow.

Run the Windows or macOS launcher, or run `python -m evaluator` with the
package installed. The default URL is [localhost:8765](http://127.0.0.1:8765/).
See [Local files and verification](docs/local_files.md) for the Desktop
collection, snapshot, source inventory and workbook coverage.

### Local annular reference lookup

For a Python installation, install the optional PDF reference reader with
`python -m pip install ".[pdf-reference]"` from the repository folder. In Tank
assessments, choose **Generate from verified local PDF** for the API 653 annular
ring. The app looks for matching code PDFs in `UT_EVALUATOR_CODES`, then
`UT_EVALUATOR_SOURCES/codes` if configured, or the checkout's `sources/codes`
and Windows user's `Desktop/Codes`. A manual reviewed lookup is available in
the portable app if the PDF reader is unavailable.
