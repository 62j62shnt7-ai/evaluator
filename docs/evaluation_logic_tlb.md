# Evaluation logic discovery: TL-B from SAG Gas MFD to GP.xlsx

Source: `sources/workbooks/TL-B from SAG Gas MFD to GP.xlsx` (read-only analysis). Cached values checked with `data_only=True`; no source file was modified.

## Workbook structure

- Sheets: 22. Defined names: 0 (`none`).
- Formula cells total: 5163.
- The workbook contains no formula lookup functions (`VLOOKUP`, `HLOOKUP`, `INDEX`, `MATCH`, `XLOOKUP`) and no named-range lookup definitions. Engineering properties such as allowable stress, joint factors, pipe dimensions, and assumed thicknesses are typed into the sheets; their original code-table/source provenance is not encoded in the cell formulas.
- Formula cache coverage: every formula cell has a cached value, including Excel error values; cached errors are retained as findings, not treated as numbers.

## Sheet inventory

| Sheet | Dimensions | Formula cells | Classification |
|---|---:|---:|---|
| `2019` | 302 × 19 | 0 | Other / no formulas |
| `Photos 2019` | 68 × 19 | 0 | UT readings / evidence |
| ` 2021` | 318 × 19 | 0 | Other / no formulas |
| `Evaluation 2021` | 129 × 17 | 236 | Evaluation / formula sheet |
| `10-2022` | 51 × 19 | 0 | Other / no formulas |
| `Photos 10-2022` | 72 × 30 | 0 | UT readings / evidence |
| `UT 12-2022 & Sec-6 (8-2023)` | 342 × 19 | 0 | UT readings / evidence |
| `Leak & Photos 12-2022` | 524 × 23 | 0 | UT readings / evidence |
| `Cutting Points 1-2023` | 90 × 22 | 12 | UT readings / evidence |
| `Cutting & Replacement 3-2023` | 43 × 22 | 0 | UT readings / evidence |
| `leak 12-2023` | 43 × 25 | 0 | Other / no formulas |
| `Eval 8-2023 - ASME B31.3` | 158 × 34 | 1846 | Evaluation / formula sheet |
| `Eval 8-2023 - ASME B31.8` | 157 × 24 | 1007 | Evaluation / formula sheet |
| `UT-FEB 2025 Sec-1&2` | 109 × 20 | 0 | UT readings / evidence |
| `Attached Photos 2-2025` | 1 × 1 | 0 | UT readings / evidence |
| `Reassess 1500 Psi May-2025` | 165 × 30 | 796 | Evaluation / formula sheet |
| `UT 5-2025` | 238 × 30 | 0 | UT readings / evidence |
| `photos 5-2025` | 106 × 20 | 0 | UT readings / evidence |
| `Evaluation 6-2025` | 113 × 26 | 575 | Evaluation / formula sheet |
| `UT 4- 2026` | 157 × 30 | 0 | UT readings / evidence |
| `Evalation 4-2026` | 113 × 27 | 691 | Evaluation / formula sheet |
| `Visual Insp. 2026` | 314 × 24 | 0 | Other / no formulas |

## Formula inventory and outputs

For each formula sheet below, formulas are grouped by their relative-reference pattern within a column. Cells in a group share the same translated formula structure; cell lists expose exceptions and manually typed holes. The column heading is the workbook’s stated output meaning. “UNMAPPED” means no specific code clause can be established from the formula sheet alone.

### `Evaluation 2021` (236 formula cells)

| Output column | Formula pattern (translated to fixed anchor) | Cells / count |
|---|---|---|
| `N` — CR (MM/Year) | `=(ZX10000-ZV10000)/1.58` | 8: N5, N6, N7, N11, N20, N21, N22, N23 |
| `O` — Thk used for MAWP Calculations (MM) | `=ZU10000-1` | 114: O5, O6, O7, O8, O9, O10, O11, O12, O13, O14, O15, O16 … |
| `P` — MAWP till next inspection (Psi) | `=(2*ZO10000*1*ZY10000)/(ZQ10000*25.4)` | 114: P5, P6, P7, P8, P9, P10, P11, P12, P13, P14, P15, P16 … |

Observed Excel functions: none.

Input and method notes: formula dependencies are cell references in this sheet unless cross-sheet references are explicitly listed above. Typed input cells (readings, design pressure, allowable stress, efficiency/factors, nominal dimensions, selected rates, dates, corrosion allowance) have no embedded authorship/source record. Their cell coordinates are exposed by the formula groups and trace tool; unreferenced typed fields are not inputs to a formula output.

### `Cutting Points 1-2023` (12 formula cells)

| Output column | Formula pattern (translated to fixed anchor) | Cells / count |
|---|---|---|
| `H` — UNLABELED | `=((ZX10000-ZV10000)/ZX10000)` | 12: H44, H45, H46, H47, H48, H49, H50, H51, H52, H53, H54, H55 |

Observed Excel functions: none.

Input and method notes: formula dependencies are cell references in this sheet unless cross-sheet references are explicitly listed above. Typed input cells (readings, design pressure, allowable stress, efficiency/factors, nominal dimensions, selected rates, dates, corrosion allowance) have no embedded authorship/source record. Their cell coordinates are exposed by the formula groups and trace tool; unreferenced typed fields are not inputs to a formula output.

### `Eval 8-2023 - ASME B31.3` (1846 formula cells)

| Output column | Formula pattern (translated to fixed anchor) | Cells / count |
|---|---|---|
| `I` — tPd (mm) | `=((ZU10000*ZV10000)/((2*ZW10000)+(0.8*ZU10000)))*25.4` | 124: I8, I9, I10, I11, I12, I13, I14, I16, I17, I18, I19, I20 … |
| `I` — tPd (mm) | `=((ZU10000*ZV10000)/((2*ZW10039)+(0.8*ZU10000)))*25.4` | 1: I47 |
| `J` — tReq (mm) | `=MAX(ZY10000,ZX10000)` | 125: J8, J9, J10, J11, J12, J13, J14, J16, J17, J18, J19, J20 … |
| `M` — 11.8 | `=ZY10000-($P$6*AAF10000)` | 96: M31, M32, M34, M35, M37, M38, M39, M40, M42, M43, M44, M45 … |
| `P` — CR  (mm/yr) | `=(ZV10000-ZW10000)/$P$6` | 19: P8, P9, P10, P11, P12, P13, P16, P17, P18, P19, P20, P21 … |
| `P` — CR  (mm/yr) | `=(ZW10001-ZV10001)/365` | 1: P6 |
| `Q` — UNLABELED | `=(ZT10000-ZX10000)/$Q$6` | 9: Q144, Q145, Q146, Q147, Q148, Q149, Q150, Q151, Q152 |
| `Q` — UNLABELED | `=(ZX10001-ZT10001)/365` | 1: Q6 |
| `T` — RL   (Yr.) | `=(ZS10000-ZP10000)/(ZY10000)` | 81: T8, T9, T10, T11, T12, T13, T53, T54, T70, T71, T72, T73 … |
| `U` — Interv. (Yr.) | `=MIN(10,(ZY10000/2))` | 81: U8, U9, U10, U11, U12, U13, U53, U54, U70, U71, U72, U73 … |
| `V` — t in MAWP  (mm) | `=(ZQ10000)-(2*ZW10000*2)` | 81: V8, V9, V10, V11, V12, V13, V53, V54, V70, V71, V72, V73 … |
| `W` — MAWP (psi) | `=(2*ZI10000*(ZY10000))/((ZH10000*25.4)-(0.8*ZY10000))` | 81: W8, W9, W10, W11, W12, W13, W53, W54, W70, W71, W72, W73 … |
| `X` — Result | `=IF(ZY10000>ZF10000,"Safe","Reduce Interval, Otherwise Derate. Repair if Derate is NA")` | 81: X8, X9, X10, X11, X12, X13, X53, X54, X70, X71, X72, X73 … |
| `Y` — Remarks (Due Date, critical items, ,,) | `=$M$7+(2*365)` | 81: Y8, Y9, Y10, Y11, Y12, Y13, Y53, Y54, Y70, Y71, Y72, Y73 … |
| `AA` — t Pd (mm) | `=((ZY10000*ZD10000)/((2*ZE10000)+(0.8*ZY10000)))*25.4` | 123: AA8, AA9, AA10, AA11, AA12, AA13, AA16, AA17, AA18, AA19, AA20, AA21 … |
| `AB` — tReq (mm) | `=MAX(ZF10000,ZY10000)` | 123: AB8, AB9, AB10, AB11, AB12, AB13, AB16, AB17, AB18, AB19, AB20, AB21 … |
| `AC` — RL (Yr.) | `=(ZJ10000-ZY10000)/(ZP10000)` | 123: AC8, AC9, AC10, AC11, AC12, AC13, AC16, AC17, AC18, AC19, AC20, AC21 … |
| `AD` — Interv. (Yr.) | `=MIN(10,(ZY10000/2))` | 123: AD8, AD9, AD10, AD11, AD12, AD13, AD16, AD17, AD18, AD19, AD20, AD21 … |
| `AE` — t in MAWP  (mm) | `=(ZH10000)-(2*ZN10000*2)` | 121: AE8, AE9, AE10, AE11, AE12, AE13, AE16, AE17, AE18, AE19, AE20, AE21 … |
| `AE` — t in MAWP  (mm) | `=(ZH10000)-(2*ZN10000*1.7)` | 2: AE32, AE35 |
| `AF` — MAWP (psi) | `=(2*YZ10000*(ZY10000))/((YY10000*25.4)-(0.8*ZY10000))` | 123: AF8, AF9, AF10, AF11, AF12, AF13, AF16, AF17, AF18, AF19, AF20, AF21 … |
| `AG` — Result | `=IF(ZY10000>ZS10000,"Safe","Reduce Interval, Otherwise Derate. Repair if Derate is NA")` | 123: AG8, AG9, AG10, AG11, AG12, AG13, AG16, AG17, AG18, AG19, AG20, AG21 … |
| `AH` — Remarks (Due Date, critical items, ,,) | `=$M$7+(2*365)` | 121: AH8, AH9, AH10, AH11, AH12, AH13, AH16, AH17, AH18, AH19, AH20, AH21 … |
| `AH` — Remarks (Due Date, critical items, ,,) | `=$M$7+(1.7*365)` | 2: AH32, AH35 |

Observed Excel functions: IF (204), MAX (248), MIN (204).
Cached formula errors: T144=#VALUE!, U144=#VALUE!, V144=#VALUE!, W144=#VALUE!, X144=#VALUE!, AC144=#VALUE!, AD144=#VALUE!, AE144=#VALUE!, AF144=#VALUE!, AG144=#VALUE!, T145=#VALUE!, U145=#VALUE!, V145=#VALUE!, W145=#VALUE!, X145=#VALUE!, AC145=#VALUE!, AD145=#VALUE!, AE145=#VALUE!, AF145=#VALUE!, AG145=#VALUE!, T146=#VALUE!, U146=#VALUE!, V146=#VALUE!, W146=#VALUE!, X146=#VALUE!, AC146=#VALUE!, AD146=#VALUE!, AE146=#VALUE!, AF146=#VALUE!, AG146=#VALUE! ….

Input and method notes: formula dependencies are cell references in this sheet unless cross-sheet references are explicitly listed above. Typed input cells (readings, design pressure, allowable stress, efficiency/factors, nominal dimensions, selected rates, dates, corrosion allowance) have no embedded authorship/source record. Their cell coordinates are exposed by the formula groups and trace tool; unreferenced typed fields are not inputs to a formula output.

### `Eval 8-2023 - ASME B31.8` (1007 formula cells)

| Output column | Formula pattern (translated to fixed anchor) | Cells / count |
|---|---|---|
| `H` — tPd (mm) | `=(ZV10000*ZW10000)/(2*ZX10000*0.8)*25.4` | 128: H7, H8, H9, H10, H11, H12, H13, H15, H16, H17, H18, H19 … |
| `K` — 12 | `=ZY10000-($N$5*AAG10000)` | 96: K30, K31, K33, K34, K36, K37, K38, K39, K41, K42, K43, K44 … |
| `M` — 2023-08-11 00:00:00 | `=ZW10000-AAE10000*$P$5` | 115: M7, M8, M9, M10, M11, M12, M15, M16, M17, M18, M19, M20 … |
| `M` — 2023-08-11 00:00:00 | `=ZY10000` | 2: M48, M49 |
| `N` — CR  (mm/yr) | `=(ZV10000-ZW10000)/$N$5` | 19: N7, N8, N9, N10, N11, N12, N15, N16, N17, N18, N19, N20 … |
| `N` — CR  (mm/yr) | `=(ZW10001-ZV10001)/365` | 1: N5 |
| `O` — UNLABELED | `=(ZT10000-ZX10000)/$O$5` | 9: O143, O144, O145, O146, O147, O148, O149, O150, O151 |
| `O` — UNLABELED | `=(ZX10001-ZT10001)/365` | 1: O5 |
| `P` — UNLABELED | `=(ZW10001-ZT10001)/365` | 1: P5 |
| `S` — RL (Yr.) | `=(ZT10000-ZO10000)/(ZY10000)` | 127: S7, S8, S9, S10, S11, S12, S15, S16, S17, S18, S19, S20 … |
| `T` — Interv. (Yr.) | `=MIN(10,(ZY10000/2))` | 127: T7, T8, T9, T10, T11, T12, T15, T16, T17, T18, T19, T20 … |
| `U` — t in MAWP  (mm) | `=(ZR10000)-(2*ZW10000*2)` | 127: U7, U8, U9, U10, U11, U12, U15, U16, U17, U18, U19, U20 … |
| `V` — MAWP (psi) | `=(2*ZJ10000*(ZY10000))/((ZI10000*25.4)-(0.8*ZY10000))` | 127: V7, V8, V9, V10, V11, V12, V15, V16, V17, V18, V19, V20 … |
| `W` — Result | `=IF(ZY10000>ZG10000,"Safe","Reduce Interval, Otherwise Derate. Repair if Derate is NA")` | 127: W7, W8, W9, W10, W11, W12, W15, W16, W17, W18, W19, W20 … |

Observed Excel functions: IF (127), MIN (127).

Input and method notes: formula dependencies are cell references in this sheet unless cross-sheet references are explicitly listed above. Typed input cells (readings, design pressure, allowable stress, efficiency/factors, nominal dimensions, selected rates, dates, corrosion allowance) have no embedded authorship/source record. Their cell coordinates are exposed by the formula groups and trace tool; unreferenced typed fields are not inputs to a formula output.

### `Reassess 1500 Psi May-2025` (796 formula cells)

| Output column | Formula pattern (translated to fixed anchor) | Cells / count |
|---|---|---|
| `I` — tPd (mm) | `=(ZU10000*ZV10000)/(2*ZW10000*0.8)*25.4` | 119: I7, I8, I9, I10, I11, I12, I14, I16, I17, I18, I19, I20 … |
| `I` — tPd (mm) | `=((ZU10000*ZV10000)/((2*ZW10000)+(0.8*ZU10000)))*25.4` | 9: I149, I150, I151, I152, I153, I154, I155, I156, I157 |
| `N` — NA | `=ZY10000` | 2: N50, N52 |
| `O` — 2025-05-24 00:00:00 | `=ZV10000-(AAF10000*$P$4)` | 82: O31, O32, O55, O56, O61, O62, O63, O64, O65, O66, O67, O68 … |
| `O` — 2025-05-24 00:00:00 | `=ZW10000-(AAF10000*$S$4)` | 15: O7, O8, O9, O10, O11, O12, O16, O17, O20, O21, O23, O25 … |
| `O` — 2025-05-24 00:00:00 | `=ZY10000-(AAF10000*1.5)` | 9: O149, O150, O151, O152, O153, O154, O155, O156, O157 |
| `O` — 2025-05-24 00:00:00 | `=ZX10000-(AAF10000*2.17)` | 4: O50, O52, O58, O60 |
| `P` — CR  (mm/yr) | `=(ZU10000-ZY10000)/$P$4` | 16: P18, P19, P22, P24, P34, P35, P37, P38, P39, P40, P42, P43 … |
| `P` — CR  (mm/yr) | `=(ZY10001-ZU10001)/365` | 1: P4 |
| `Q` — UNLABELED | `=(ZT10000-ZU10000)/$Q$4` | 19: Q7, Q8, Q9, Q10, Q11, Q12, Q16, Q17, Q18, Q19, Q20, Q21 … |
| `Q` — UNLABELED | `=(ZU10001-ZT10001)/365` | 1: Q4 |
| `R` — UNLABELED | `=(ZR10000-ZV10000)/$R$4` | 9: R149, R150, R151, R152, R153, R154, R155, R156, R157 |
| `R` — UNLABELED | `=(ZV10001-ZR10001)/365` | 1: R4 |
| `S` — UNLABELED | `=(ZV10001-ZS10001)/365` | 1: S4 |
| `V` — RL (Yr.) | `=(ZS10000-ZM10000)/(ZY10000)` | 116: V7, V8, V9, V10, V11, V12, V16, V17, V18, V19, V20, V21 … |
| `V` — RL (Yr.) | `=(ZR10000-ZM10000)/(ZY10000)` | 11: V50, V52, V149, V150, V151, V152, V153, V154, V155, V156, V157 |
| `X` — t in MAWP  (mm) | `=(ZQ10000)-(2*ZW10000*ZY10000)` | 125: X7, X8, X9, X10, X11, X12, X16, X17, X18, X19, X20, X21 … |
| `X` — t in MAWP  (mm) | `=(ZP10000)-(2*ZW10000*ZY10000)` | 2: X50, X52 |
| `Y` — MAWP (psi) | `=(2*0.8*ZG10000*ZY10000)/(ZF10000*25.4)` | 118: Y7, Y8, Y9, Y10, Y11, Y12, Y16, Y17, Y18, Y19, Y20, Y21 … |
| `Y` — MAWP (psi) | `=(2*ZG10000*(ZY10000))/((ZF10000*25.4)-(0.8*ZY10000))` | 9: Y149, Y150, Y151, Y152, Y153, Y154, Y155, Y156, Y157 |
| `Z` — Result | `=IF(ZY10000>ZD10000,"Safe","Reduce Interval, Otherwise Derate. Repair if Derate is NA")` | 127: Z7, Z8, Z9, Z10, Z11, Z12, Z16, Z17, Z18, Z19, Z20, Z21 … |

Observed Excel functions: IF (127).

Input and method notes: formula dependencies are cell references in this sheet unless cross-sheet references are explicitly listed above. Typed input cells (readings, design pressure, allowable stress, efficiency/factors, nominal dimensions, selected rates, dates, corrosion allowance) have no embedded authorship/source record. Their cell coordinates are exposed by the formula groups and trace tool; unreferenced typed fields are not inputs to a formula output.

### `Evaluation 6-2025` (575 formula cells)

| Output column | Formula pattern (translated to fixed anchor) | Cells / count |
|---|---|---|
| `I` — tPd (mm) | `=(ZU10000*ZV10000)/(2*ZW10000*0.8)*25.4` | 80: I7, I8, I9, I10, I11, I12, I15, I16, I17, I18, I19, I20 … |
| `O` — CR  (mm/yr) | `=(ZW10000-ZY10000)/$O$4` | 18: O7, O8, O9, O10, O11, O12, O15, O16, O17, O18, O19, O20 … |
| `O` — CR  (mm/yr) | `=(ZY10001-ZW10001)/365` | 1: O4 |
| `P` — UNLABELED | `=(ZU10000-ZX10000)/$P$4` | 55: P7, P8, P9, P10, P11, P12, P15, P16, P17, P18, P19, P20 … |
| `P` — UNLABELED | `=(ZX10001-ZU10001)/365` | 1: P4 |
| `Q` — UNLABELED | `=(ZT10000-ZU10000)/$Q$4` | 18: Q7, Q8, Q9, Q10, Q11, Q12, Q15, Q16, Q17, Q18, Q19, Q20 … |
| `Q` — UNLABELED | `=(ZU10001-ZT10001)/365` | 1: Q4 |
| `T` — RL (Yr.) | `=(ZT10000-ZO10000)/(ZY10000)` | 80: T7, T8, T9, T10, T11, T12, T15, T16, T17, T18, T19, T20 … |
| `U` — Interv. (Yr.) | `=MIN(ZY10000/2,10)` | 54: U7, U8, U9, U10, U11, U12, U15, U16, U17, U18, U19, U20 … |
| `V` — t in MAWP  (mm) | `=(ZR10000)-(2*ZW10000*ZY10000)` | 80: V7, V8, V9, V10, V11, V12, V15, V16, V17, V18, V19, V20 … |
| `W` — MAWP (psi) | `=(2*0.8*ZI10000*ZY10000)/(ZH10000*25.4)` | 80: W7, W8, W9, W10, W11, W12, W15, W16, W17, W18, W19, W20 … |
| `X` — Result | `=IF(ZY10000>ZF10000,"Safe","Reduce Interval, Otherwise Derate. Repair if Derate is NA")` | 80: X7, X8, X9, X10, X11, X12, X15, X16, X17, X18, X19, X20 … |
| `Y` — Remarks (Due Date, critical items, ,,) | `=ZV10000*365+$N$5` | 25: Y27, Y28, Y29, Y30, Y33, Y34, Y35, Y36, Y38, Y39, Y44, Y45 … |
| `Y` — Remarks (Due Date, critical items, ,,) | `=ZV10000*365+ZO9934` | 1: Y71 |
| `Y` — Remarks (Due Date, critical items, ,,) | `=ZV10000*365+ZO9922` | 1: Y83 |

Observed Excel functions: IF (80), MIN (54).

Input and method notes: formula dependencies are cell references in this sheet unless cross-sheet references are explicitly listed above. Typed input cells (readings, design pressure, allowable stress, efficiency/factors, nominal dimensions, selected rates, dates, corrosion allowance) have no embedded authorship/source record. Their cell coordinates are exposed by the formula groups and trace tool; unreferenced typed fields are not inputs to a formula output.

### `Evalation 4-2026` (691 formula cells)

| Output column | Formula pattern (translated to fixed anchor) | Cells / count |
|---|---|---|
| `I` — tPd (mm) | `=(ZU10000*ZV10000)/(2*ZW10000*0.8)*25.4` | 80: I7, I8, I9, I10, I11, I12, I15, I16, I17, I18, I19, I20 … |
| `O` — 2026-04-07 00:00:00 | `=ZY10000-(AAE10000*$S$4)` | 80: O7, O8, O9, O10, O11, O12, O15, O16, O17, O18, O19, O20 … |
| `P` — CR  (mm/yr) | `=(ZV10000-ZX10000)/$P$4` | 18: P7, P8, P9, P10, P11, P12, P15, P16, P17, P18, P19, P20 … |
| `P` — CR  (mm/yr) | `=(ZX10001-ZV10001)/365` | 1: P4 |
| `Q` — UNLABELED | `=(ZT10000-ZW10000)/$Q$4` | 55: Q7, Q8, Q9, Q10, Q11, Q12, Q15, Q16, Q17, Q18, Q19, Q20 … |
| `Q` — UNLABELED | `=(ZW10001-ZT10001)/365` | 1: Q4 |
| `R` — UNLABELED | `=(ZS10000-ZT10000)/$R$4` | 18: R7, R8, R9, R10, R11, R12, R15, R16, R17, R18, R19, R20 … |
| `R` — UNLABELED | `=(ZT10001-ZS10001)/365` | 1: R4 |
| `S` — UNLABELED | `=(ZV10001-ZU10001)/365` | 1: S4 |
| `U` — RL (Yr.) | `=(ZT10000-ZN10000)/(ZY10000)` | 80: U7, U8, U9, U10, U11, U12, U15, U16, U17, U18, U19, U20 … |
| `V` — Interv. (Yr.) | `=MIN(ZY10000/2,10)` | 41: V7, V8, V9, V10, V11, V12, V55, V56, V57, V58, V59, V60 … |
| `W` — t in MAWP  (mm) | `=(ZQ10000)-(2*ZW10000*ZY10000)` | 80: W7, W8, W9, W10, W11, W12, W15, W16, W17, W18, W19, W20 … |
| `X` — MAWP (psi) | `=(2*0.8*ZH10000*ZY10000)/(ZG10000*25.4)` | 80: X7, X8, X9, X10, X11, X12, X15, X16, X17, X18, X19, X20 … |
| `Y` — Result | `=IF(ZY10000>ZE10000,"Safe","Reduce Interval, Otherwise Derate. Repair if Derate is NA")` | 80: Y7, Y8, Y9, Y10, Y11, Y12, Y15, Y16, Y17, Y18, Y19, Y20 … |
| `Z` — Remarks (Due Date, critical items, ) | `=ZV10000*365+$O$5` | 74: Z15, Z16, Z17, Z18, Z19, Z20, Z21, Z22, Z23, Z24, Z25, Z26 … |
| `Z` — Remarks (Due Date, critical items, ) | `=MIN(ZX10000:ZX10493)` | 1: Z7 |

Observed Excel functions: IF (80), MIN (42).

Input and method notes: formula dependencies are cell references in this sheet unless cross-sheet references are explicitly listed above. Typed input cells (readings, design pressure, allowable stress, efficiency/factors, nominal dimensions, selected rates, dates, corrosion allowance) have no embedded authorship/source record. Their cell coordinates are exposed by the formula groups and trace tool; unreferenced typed fields are not inputs to a formula output.

## Representative trace checks

Representative traces were checked with `tools/trace_row.py`; each trace reports formulas, cached values, and recursively referenced literal cells. Literal leaves are labelled `INPUT`. A typed lookup value cannot be distinguished from a manually entered value by workbook structure alone, so no leaf is claimed as a verified `LOOKUP`.

## Representative formula traces

- [`tlb_b31_3_J8.json`](traces/tlb_b31_3_J8.json)
- [`tlb_b31_8_H7.json`](traces/tlb_b31_8_H7.json)
- [`tlb_evaluation_6_2025_X7.json`](traces/tlb_evaluation_6_2025_X7.json)
- [`tlb_evaluation_4_2026_O7.json`](traces/tlb_evaluation_4_2026_O7.json)

## Code basis and UNMAPPED items

- `Eval 8-2023 - ASME B31.3` title/header cites: API-570 & ASME B31.3 PACK - TLS, API 574 tPd (mm) tReq (mm) Min. UT Reading (mm) CR  (mm/yr) RL   (Yr.) Interv. (Yr.) t in MAWP  (mm) MAWP (psi) Result Remarks.
- `Eval 8-2023 - ASME B31.8` title/header cites: ASME B31.8 -2020 Gas Transmission PL PACK - TLS.
- `Reassess 1500 Psi May-2025` title/header cites: ASME B31.8 -2020 Gas Transmission PL PACK - TLS.
- `Evaluation 6-2025` title/header cites: ASME B31.8 -2020 Gas Transmission PL PACK - TLS.
- `Evalation 4-2026` title/header cites: ASME B31.8 -2020 Gas Transmission PL PACK - TLS.
- Corrosion rate / remaining-life formulas can be compared with the API 510/API 570 clause map in the provided plan, but specific clause and edition applicability is **UNMAPPED pending engineering review** where the sheet does not state it.
- Pressure-thickness, MAWP, interval and status formulas are described by their worksheet labels/formulas above. Their code clause is **UNMAPPED** unless the sheet title explicitly states a code; titles do not establish clause correctness.
- No lookup table range/content or named range is present in the formula logic. Typed material values, factors, nominal sizes and prior/current UT readings have no file-level cell provenance.
