# Evaluation logic discovery: Separator-204 Inspection Report.xlsx

Source: `sources/workbooks/Separator-204 Inspection Report.xlsx` (read-only analysis). Cached values checked with `data_only=True`; no source file was modified.

## Workbook structure

- Sheets: 15. Defined names: 0 (`none`).
- Formula cells total: 998.
- The workbook contains no formula lookup functions (`VLOOKUP`, `HLOOKUP`, `INDEX`, `MATCH`, `XLOOKUP`) and no named-range lookup definitions. Engineering properties such as allowable stress, joint factors, pipe dimensions, and assumed thicknesses are typed into the sheets; their original code-table/source provenance is not encoded in the cell formulas.
- Formula cache coverage: every formula cell has a cached value, including Excel error values; cached errors are retained as findings, not treated as numbers.

## Sheet inventory

| Sheet | Dimensions | Formula cells | Classification |
|---|---:|---:|---|
| `HISTORY REPORTS` | 78 × 19 | 0 | UT readings / evidence |
| `2010 UT REPORT` | 1 × 1 | 0 | UT readings / evidence |
| `UT REPORT 2019` | 140 × 147 | 35 | UT readings / evidence |
| `UT REP.JUNE 2019-CML ` | 94 × 147 | 4 | UT readings / evidence |
| `UT-JUL 2021` | 175 × 24 | 79 | UT readings / evidence |
| `Evaluation` | 97 × 24 | 142 | Evaluation / formula sheet |
| `Conclusion` | 10 × 19 | 0 | Other / no formulas |
| `UT Jul-2023` | 133 × 24 | 89 | UT readings / evidence |
| `UT Aug-2024` | 133 × 27 | 120 | UT readings / evidence |
| `UT Jan 2026` | 139 × 27 | 111 | UT readings / evidence |
| `Asset Transfer` | 7 × 1 | 0 | Other / no formulas |
| `Actions Taken` | 10 × 3 | 0 | Other / no formulas |
| `UT 10-2026` | 57 × 27 | 38 | UT readings / evidence |
| `Visual Inspection 2026` | 21 × 19 | 0 | Other / no formulas |
| `Evaluation 2026` | 57 × 31 | 380 | Evaluation / formula sheet |

## Formula inventory and outputs

For each formula sheet below, formulas are grouped by their relative-reference pattern within a column. Cells in a group share the same translated formula structure; cell lists expose exceptions and manually typed holes. The column heading is the workbook’s stated output meaning. “UNMAPPED” means no specific code clause can be established from the formula sheet alone.

### `UT REPORT 2019` (35 formula cells)

| Output column | Formula pattern (translated to fixed anchor) | Cells / count |
|---|---|---|
| `E` — UNLABELED | `=(ZY10000-ZX10000)/ZY10000` | 24: E85, E87, E88, E89, E90, E91, E92, E95, E97, E100, E102, E110 … |
| `R` — UNLABELED | `=(ZY10000-ZX10000)/ZY10000` | 11: R85, R87, R88, R89, R90, R91, R92, R95, R97, R100, R102 |

Observed Excel functions: none.

Input and method notes: formula dependencies are cell references in this sheet unless cross-sheet references are explicitly listed above. Typed input cells (readings, design pressure, allowable stress, efficiency/factors, nominal dimensions, selected rates, dates, corrosion allowance) have no embedded authorship/source record. Their cell coordinates are exposed by the formula groups and trace tool; unreferenced typed fields are not inputs to a formula output.

### `UT REP.JUNE 2019-CML ` (4 formula cells)

| Output column | Formula pattern (translated to fixed anchor) | Cells / count |
|---|---|---|
| `E` — UNLABELED | `=(ZY10000-ZX10000)/ZY10000` | 2: E86, E87 |
| `R` — UNLABELED | `=(ZY10000-ZX10000)/ZY10000` | 2: R86, R87 |

Observed Excel functions: none.

Input and method notes: formula dependencies are cell references in this sheet unless cross-sheet references are explicitly listed above. Typed input cells (readings, design pressure, allowable stress, efficiency/factors, nominal dimensions, selected rates, dates, corrosion allowance) have no embedded authorship/source record. Their cell coordinates are exposed by the formula groups and trace tool; unreferenced typed fields are not inputs to a formula output.

### `UT-JUL 2021` (79 formula cells)

| Output column | Formula pattern (translated to fixed anchor) | Cells / count |
|---|---|---|
| `G` — UNLABELED | `=(ZY10000-ZX10000)/ZY10000*100` | 49: G85, G86, G87, G88, G89, G90, G91, G92, G93, G94, G95, G96 … |
| `G` — UNLABELED | `=((ZW10000-ZX10000)/ZW10000)*100` | 15: G156, G157, G158, G159, G160, G161, G162, G163, G164, G165, G166, G167 … |
| `J` — UNLABELED | `=((ZT10000-ZX10000)/ZT10000)*100` | 15: J156, J157, J158, J159, J160, J161, J162, J163, J164, J165, J166, J167 … |

Observed Excel functions: none.
Cached formula errors: G156=#DIV/0!, J156=#DIV/0!, G157=#DIV/0!, J157=#DIV/0!, G158=#DIV/0!, J158=#DIV/0!, G159=#DIV/0!, J159=#DIV/0!, G160=#DIV/0!, J160=#DIV/0!, G161=#DIV/0!, J161=#DIV/0!, G162=#DIV/0!, J162=#DIV/0!, G163=#DIV/0!, J163=#DIV/0!, G164=#DIV/0!, J164=#DIV/0!, G165=#DIV/0!, J165=#DIV/0!, G166=#DIV/0!, J166=#DIV/0!, G167=#DIV/0!, J167=#DIV/0!, G168=#DIV/0!, J168=#DIV/0!, G169=#DIV/0!, J169=#DIV/0!, G170=#DIV/0!, J170=#DIV/0!.

Input and method notes: formula dependencies are cell references in this sheet unless cross-sheet references are explicitly listed above. Typed input cells (readings, design pressure, allowable stress, efficiency/factors, nominal dimensions, selected rates, dates, corrosion allowance) have no embedded authorship/source record. Their cell coordinates are exposed by the formula groups and trace tool; unreferenced typed fields are not inputs to a formula output.

### `Evaluation` (142 formula cells)

| Output column | Formula pattern (translated to fixed anchor) | Cells / count |
|---|---|---|
| `I` — ST | `=(ZW10000-ZX10000)/(2.4)` | 13: I62, I63, I64, I65, I68, I69, I70, I71, I72, I73, I74, I75 … |
| `K` — RLT    (y) | `=(ZV10000-ZT10000)/(ZX10000)` | 1: K71 |
| `M` — t in MAWP (mm) | `=(ZT10000)-(4*0.125)` | 64: M13, M14, M15, M16, M17, M18, M19, M20, M21, M22, M23, M24 … |
| `N` — MAWP (psi) | `=(15700*0.85*(ZY10000/25.4))/((38.1)+(0.6*(ZY10000/25.4)))` | 41: N17, N18, N19, N20, N21, N22, N23, N24, N25, N26, N27, N28 … |
| `N` — MAWP (psi) | `=(2*17100*0.85*(ZY10000/25.4))/(ZP10000)` | 15: N62, N63, N64, N65, N66, N67, N68, N69, N70, N71, N72, N73 … |
| `N` — MAWP (psi) | `=(15700*0.85*(ZY10000/25.4))/((0.885*78)+(0.1*(ZY10000/25.4)))` | 6: N14, N15, N16, N54, N55, N56 |
| `N` — MAWP (psi) | `=(2*15700*0.85*(ZY10000/25.4))/((78)+(0.2*(ZY10000/25.4)))` | 2: N13, N53 |

Observed Excel functions: none.

Input and method notes: formula dependencies are cell references in this sheet unless cross-sheet references are explicitly listed above. Typed input cells (readings, design pressure, allowable stress, efficiency/factors, nominal dimensions, selected rates, dates, corrosion allowance) have no embedded authorship/source record. Their cell coordinates are exposed by the formula groups and trace tool; unreferenced typed fields are not inputs to a formula output.

### `UT Jul-2023` (89 formula cells)

| Output column | Formula pattern (translated to fixed anchor) | Cells / count |
|---|---|---|
| `G` — UNLABELED | `=((ZY10000-ZX10000)/ZY10000)*100` | 15: G114, G115, G116, G117, G118, G119, G120, G121, G122, G123, G124, G125 … |
| `G` — UNLABELED | `=(ZY10000-ZX10000)/ZY10000` | 12: G85, G86, G87, G88, G89, G90, G91, G92, G93, G96, G98, G100 |
| `J` — UNLABELED | `=(ZY10000-ZX10000)/ZY10000` | 16: J85, J86, J87, J88, J89, J90, J91, J92, J93, J94, J95, J96 … |
| `J` — UNLABELED | `=((ZY10000-ZX10000)/ZY10000)*100` | 15: J114, J115, J116, J117, J118, J119, J120, J121, J122, J123, J124, J125 … |
| `M` — UNLABELED | `=(ZY10000-ZX10000)/ZY10000` | 31: M85, M86, M87, M88, M89, M90, M91, M92, M93, M94, M95, M96 … |

Observed Excel functions: none.
Cached formula errors: G118=#VALUE!, G119=#VALUE!.

Input and method notes: formula dependencies are cell references in this sheet unless cross-sheet references are explicitly listed above. Typed input cells (readings, design pressure, allowable stress, efficiency/factors, nominal dimensions, selected rates, dates, corrosion allowance) have no embedded authorship/source record. Their cell coordinates are exposed by the formula groups and trace tool; unreferenced typed fields are not inputs to a formula output.

### `UT Aug-2024` (120 formula cells)

| Output column | Formula pattern (translated to fixed anchor) | Cells / count |
|---|---|---|
| `G` — UNLABELED | `=((ZY10000-ZX10000)/ZY10000)*100` | 15: G114, G115, G116, G117, G118, G119, G120, G121, G122, G123, G124, G125 … |
| `G` — UNLABELED | `=(ZY10000-ZX10000)/ZY10000` | 12: G85, G86, G87, G88, G89, G90, G91, G92, G93, G96, G98, G100 |
| `J` — UNLABELED | `=(ZY10000-ZX10000)/ZY10000` | 16: J85, J86, J87, J88, J89, J90, J91, J92, J93, J94, J95, J96 … |
| `J` — UNLABELED | `=((ZY10000-ZX10000)/ZY10000)*100` | 15: J114, J115, J116, J117, J118, J119, J120, J121, J122, J123, J124, J125 … |
| `M` — UNLABELED | `=(ZY10000-ZX10000)/ZY10000` | 31: M85, M86, M87, M88, M89, M90, M91, M92, M93, M94, M95, M96 … |
| `P` — UNLABELED | `=(ZY10000-ZX10000)/ZY10000` | 31: P85, P86, P87, P88, P89, P90, P91, P92, P93, P94, P95, P96 … |

Observed Excel functions: none.
Cached formula errors: G118=#VALUE!, G119=#VALUE!.

Input and method notes: formula dependencies are cell references in this sheet unless cross-sheet references are explicitly listed above. Typed input cells (readings, design pressure, allowable stress, efficiency/factors, nominal dimensions, selected rates, dates, corrosion allowance) have no embedded authorship/source record. Their cell coordinates are exposed by the formula groups and trace tool; unreferenced typed fields are not inputs to a formula output.

### `UT Jan 2026` (111 formula cells)

| Output column | Formula pattern (translated to fixed anchor) | Cells / count |
|---|---|---|
| `G` — UNLABELED | `=(ZY10000-ZX10000)/ZY10000` | 22: G84, G85, G86, G87, G88, G89, G90, G91, G92, G93, G94, G95 … |
| `G` — UNLABELED | `=((ZY10000-ZX10000)/ZY10000)*100` | 15: G120, G121, G122, G123, G124, G125, G126, G127, G128, G129, G130, G131 … |
| `J` — UNLABELED | `=(ZY10000-ZX10000)/ZY10000` | 22: J84, J85, J86, J87, J88, J89, J90, J91, J92, J93, J94, J95 … |
| `J` — UNLABELED | `=((ZY10000-ZX10000)/ZY10000)*100` | 15: J120, J121, J122, J123, J124, J125, J126, J127, J128, J129, J130, J131 … |
| `M` — UNLABELED | `=(ZY10000-ZX10000)/ZY10000` | 37: M84, M85, M86, M87, M88, M89, M90, M91, M92, M93, M94, M95 … |

Observed Excel functions: none.
Cached formula errors: M84=#DIV/0!, M85=#DIV/0!, M86=#DIV/0!, M87=#DIV/0!, M88=#DIV/0!, M89=#DIV/0!, M90=#DIV/0!, M91=#DIV/0!, G92=#VALUE!, M92=#DIV/0!, G93=#VALUE!, M93=#DIV/0!, M94=#DIV/0!, G95=#VALUE!, M95=#DIV/0!, G96=#VALUE!, M96=#DIV/0!, G97=#VALUE!, M97=#DIV/0!, M98=#DIV/0!, M99=#DIV/0!, M100=#DIV/0!, M101=#DIV/0!, M102=#DIV/0!, G103=#VALUE!, M103=#DIV/0!, M104=#DIV/0!, M105=#DIV/0!, M120=#DIV/0!, M121=#DIV/0! ….

Input and method notes: formula dependencies are cell references in this sheet unless cross-sheet references are explicitly listed above. Typed input cells (readings, design pressure, allowable stress, efficiency/factors, nominal dimensions, selected rates, dates, corrosion allowance) have no embedded authorship/source record. Their cell coordinates are exposed by the formula groups and trace tool; unreferenced typed fields are not inputs to a formula output.

### `UT 10-2026` (38 formula cells)

| Output column | Formula pattern (translated to fixed anchor) | Cells / count |
|---|---|---|
| `G` — Red.% | `=(ZY10000-ZX10000)/ZY10000` | 38: G12, G13, G14, G15, G16, G17, G18, G19, G20, G21, G22, G23 … |

Observed Excel functions: none.

Input and method notes: formula dependencies are cell references in this sheet unless cross-sheet references are explicitly listed above. Typed input cells (readings, design pressure, allowable stress, efficiency/factors, nominal dimensions, selected rates, dates, corrosion allowance) have no embedded authorship/source record. Their cell coordinates are exposed by the formula groups and trace tool; unreferenced typed fields are not inputs to a formula output.

### `Evaluation 2026` (380 formula cells)

| Output column | Formula pattern (translated to fixed anchor) | Cells / count |
|---|---|---|
| `I` — ID - IN | `=ZY10000-((2*AAD10000)/25.4)` | 38: I5, I6, I7, I8, I9, I10, I11, I12, I13, I14, I15, I16 … |
| `N` — Min. Req. Thick. (mm) | `=(ZP10000*0.5*ZU10000*25.4)/((ZR10000*ZS10000)-(0.6*ZP10000))` | 19: N27, N28, N29, N30, N31, N32, N33, N34, N35, N36, N37, N38 … |
| `N` — Min. Req. Thick. (mm) | `=((ZP10000*ZU10000)/((2*ZR10000*ZS10000)-(0.2*ZP10000)))*25.4` | 19: N5, N6, N7, N8, N9, N10, N11, N12, N13, N14, N15, N16 … |
| `O` — STCR1 | `=1/16*25.4` | 19: O27, O28, O29, O30, O31, O32, O33, O34, O35, O36, O37, O38 … |
| `P` — STCR2 | `=MAX(ZY10000,(ZN10000*0.5*ZS10000*25.4)/((ZP10000*1)-(0.6*ZN10000)))` | 17: P28, P29, P30, P31, P32, P33, P34, P35, P36, P37, P39, P40 … |
| `P` — STCR2 | `=MAX(ZY10000,(ZN10000*ZS10000*25.4)/((2*ZP10000*0.85)-(0.2*ZN10000)))` | 2: P27, P38 |
| `R` — 0.25 | `=MIN(ZY10000,ZX10000)` | 19: R27, R28, R29, R30, R31, R32, R33, R34, R35, R36, R37, R38 … |
| `S` — FCA (mm) | `=ZT10000-ZU10000` | 19: S5, S6, S7, S8, S9, S10, S11, S12, S13, S14, S15, S16 … |
| `S` — FCA (mm) | `=MAX(ZY10000,ZU10000)` | 19: S27, S28, S29, S30, S31, S32, S33, S34, S35, S36, S37, S38 … |
| `T` — RL (Yrs) | `=ZY10000/ZX10000` | 19: T5, T6, T7, T8, T9, T10, T11, T12, T13, T14, T15, T16 … |
| `U` — Future Insp. Interval (Yrs) | `=MIN(10,ZY10000/2)` | 19: U5, U6, U7, U8, U9, U10, U11, U12, U13, U14, U15, U16 … |
| `V` — Thick. used in MAWP calc. (mm) | `=(ZQ10000)-(2*ZV10000*1)` | 19: V5, V6, V7, V8, V9, V10, V11, V12, V13, V14, V15, V16 … |
| `W` — MAWP till next inspection | `=ZP10000-ZV10000` | 19: W27, W28, W29, W30, W31, W32, W33, W34, W35, W36, W37, W38 … |
| `W` — MAWP till next inspection | `=(ZI10000*ZJ10000*(ZY10000/25.4)/((ZL10000/2)+(0.6*(ZY10000/25.4))))` | 18: W6, W7, W8, W9, W10, W11, W12, W13, W14, W15, W16, W17 … |
| `W` — MAWP till next inspection | `=(2*ZI10000*ZJ10000*(ZY10000/25.4)/((ZL10000)+(0.2*(ZY10000/25.4))))` | 1: W5 |
| `X` — Due Dates | `=ZY10000/ZX10000` | 19: X27, X28, X29, X30, X31, X32, X33, X34, X35, X36, X37, X38 … |
| `X` — Due Dates | `=$M$4+(1*365)` | 19: X5, X6, X7, X8, X9, X10, X11, X12, X13, X14, X15, X16 … |
| `Y` — Remarks | `=MIN(10,ZY10000/2)` | 19: Y27, Y28, Y29, Y30, Y31, Y32, Y33, Y34, Y35, Y36, Y37, Y38 … |
| `Z` — UNLABELED | `=(ZM10000)-(2*ZV10000*1)` | 19: Z27, Z28, Z29, Z30, Z31, Z32, Z33, Z34, Z35, Z36, Z37, Z38 … |
| `AA` — UNLABELED | `=(2*ZE10000*ZF10000*(ZY10000/25.4)/((ZH10000)+(0.2*(ZY10000/25.4))))` | 19: AA27, AA28, AA29, AA30, AA31, AA32, AA33, AA34, AA35, AA36, AA37, AA38 … |
| `AB` — UNLABELED | `=$M$26+(1*365)` | 19: AB27, AB28, AB29, AB30, AB31, AB32, AB33, AB34, AB35, AB36, AB37, AB38 … |

Observed Excel functions: MAX (38), MIN (57).

Input and method notes: formula dependencies are cell references in this sheet unless cross-sheet references are explicitly listed above. Typed input cells (readings, design pressure, allowable stress, efficiency/factors, nominal dimensions, selected rates, dates, corrosion allowance) have no embedded authorship/source record. Their cell coordinates are exposed by the formula groups and trace tool; unreferenced typed fields are not inputs to a formula output.

## Representative trace checks

Representative traces were checked with `tools/trace_row.py`; each trace reports formulas, cached values, and recursively referenced literal cells. Literal leaves are labelled `INPUT`. A typed lookup value cannot be distinguished from a manually entered value by workbook structure alone, so no leaf is claimed as a verified `LOOKUP`.

## Representative formula traces

- [`separator_204_evaluation_N13.json`](traces/separator_204_evaluation_N13.json)
- [`separator_204_evaluation_2026_N5.json`](traces/separator_204_evaluation_2026_N5.json)

## Code basis and UNMAPPED items

- `Evaluation` title/header cites: API 510).
- `Evaluation 2026` title/header cites: API-510 & ASME-VIII DIV-1  Band Vessel Comp. Material Design Press. (PSI) Design Temp. (F) Allowable stress (S)(Psi) Weld Joint Effic. (E) OD - IN ID - IN T nom (mm) UT Readings (mm) Min. Req. Thick. (mm) Corrosion Rate .
- Corrosion rate / remaining-life formulas can be compared with the API 510/API 570 clause map in the provided plan, but specific clause and edition applicability is **UNMAPPED pending engineering review** where the sheet does not state it.
- Pressure-thickness, MAWP, interval and status formulas are described by their worksheet labels/formulas above. Their code clause is **UNMAPPED** unless the sheet title explicitly states a code; titles do not establish clause correctness.
- No lookup table range/content or named range is present in the formula logic. Typed material values, factors, nominal sizes and prior/current UT readings have no file-level cell provenance.
