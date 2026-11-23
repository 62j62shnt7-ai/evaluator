# Local files and verification

The Windows collection is in `Desktop/My repos/evaluator`. The checkout uses
the draft PR branch `feat/mawp-v08-code-routing-phase1`. The source folders,
evidence, project data and runtime are ignored by Git and stored locally.

| Folder | Contents |
| --- | --- |
| `sources/codes` | 13 Desktop reference PDFs, including B31.3-2024, API 570 and API RP 574. |
| `sources/workbooks` | Section 2 gas-line inspection workbook in its original XLS and XLSX formats. Use the XLSX for app intake. |
| `sources/plans` | Reattached MAWP v0.8 implementation plan ZIP. |
| `sources/demo` | Synthetic pipe, vessel and tank UT workbooks. |
| `evidence/rp574` | Local API RP 574 inspection script and page captures. |
| `evidence/project-backups` | Previous cleanup archive. |
| `evidence/earlier-preview` | Earlier preview database archive. |
| `outputs/integrity-desk-preview-snapshot` | SQLite snapshot of the working preview and its registered source workbooks. |

`sources/local-manifest.json` records SHA-256 and byte counts for the gathered
files. Original Desktop sources were preserved. The snapshot passed SQLite
`quick_check`. Preserve the snapshot as evidence and run the app on a
separate working copy.

From a PowerShell window in the Desktop evaluator folder with its Windows
portable runtime installed:

```powershell
$workingCopy = Join-Path (Get-Location) ('outputs/preview-' + [guid]::NewGuid())
Copy-Item -Path './outputs/integrity-desk-preview-snapshot' -Destination $workingCopy -Recurse
.\runtime\python.exe -m evaluator --project $workingCopy --port 8768 --no-browser
```

Open [localhost:8768](http://127.0.0.1:8768/). The development preview on
port 8766 uses its original project.

## Workbook coverage

The Section 2 preview below is a separate dataset from the oil-line pilot.
For the current oil-line comparison and verification of the **Calculations**
preview and Excel export, see the [inspection workflow handoff](inspection-workflow-handoff.md).

The Section 2 XLSX supplied four dated UT campaigns in Evaluation Nov-26.
A clean import identified 31 straight-pipe, 13 elbow, 4 tee and 6 reducer
locations. The straight-pipe batch produced draft pressure results for all
31. The fitting workflow was exercised with synthetic documented limits,
using real UT readings for one fitting of each geometry.

Actual fitting checks require pressure and minimum-wall limits tied to the
applicable listing or qualification, a source reference and paired UT. The
saved preview shows three unmatched fitting locations at M9, M21 and M51.
Original TL-B and Separator-204 workbooks and the independent engineering
benchmark package were unavailable for this collection. Tests that require
those originals continue to skip until they are placed under the configured
source root. All engineering outputs are **DRAFT / NOT VALIDATED**.

## Offline code references

Runtime calculations use the versioned datasets in `src/evaluator/data`.
The API RP 574 Annex D structural examples and the supported SI annular
tables from API 650 and API 653 were extracted from the supplied copies
after checking the SHA-256 hashes. The dataset records the source edition
through the identified source file, table, page and hash. Material stress
and pipe dimensions retain their existing reviewed row provenance and
exact-match policy. The original PDFs can be kept separately for audit
and future reference additions. Build and test with an empty
`UT_EVALUATOR_CODES` directory to check runtime independence.

The `code_reference_values.json` dataset holds edition-scoped B31.8 grade
and manufacturing-form matches, temperature and basic class factors,
B31.4 weld factors and their separately sourced material strengths, API 650
shell erection minima, and API 653 bottom design minima. The B31.8 A25 row
has its own manufacturing-form list. A basic location class factor still
requires review of the applicable service and design conditions.
