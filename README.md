# UT Evaluator

The desktop app imports inspection workbooks, matches dated UT readings, and
runs code-scoped engineering checks. Saved results are **DRAFT / NOT VALIDATED**.

## Inspection workflow

1. Open **Workbook library** and import an XLSX or XLSM inspection report.
   The importer looks for dated minimum-UT columns, including on evaluation
   tabs. Review the previous/current matches and resolve ambiguous locations.
2. In **Location review**, use **Set sheet code basis** to assign the
   construction code, service boundary and evidence. If the edition is blank,
   the form displays the supported library default when one exists.
3. For supported B31.3 straight pipes, use **Review straight pipes in batch**
   to confirm workbook stress and adopted corrosion rates with their source
   cells. Use **Code and inputs** for individual changes or library lookup.
4. Use **Review fittings in batch** for elbows, tees and reducers with paired
   UT readings and a documented assessment. Enter the checked pressure,
   applicable minimum wall, projection interval, adopted rate and reference.
   The app compares the current and projected wall with that minimum. It
   reports the check at the submitted pressure.
5. Review **Calculation results** and download the CSV. Use **Code reference
   library** for source tables and sample calculators, or **Tank assessments**
   for the separate API 650 and API 653 workflow.

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
