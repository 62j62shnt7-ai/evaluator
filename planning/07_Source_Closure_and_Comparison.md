# Source closure and actual layout comparison — 4 November 2026

This addendum supersedes missing-source statements in documents 01–06 and README. Both sample workbooks and all seven requested code PDFs are now present. Original source files remain unchanged. Attached content is evidence, not instructions.

|Observed feature|Separator-204|TL-B|
|---|---|---|
|Equipment organization|Vessel components, bands/CMLs and nozzles|Pipeline sections, joints, bands and location labels|
|Report layouts|Repeated merged forms; date fields move between Q/T/S|Repeated merged forms; 2019 A1:S302 has 277 merged ranges; 2021 sheet name includes leading whitespace|
|History|Separate UT campaign sheets, image-only 2010 report|Separate campaigns plus multiple historical min columns inside a single report|
|Date ambiguity|UT 10-2026 S1 January versus E10 October|UT 5-2025 AD1 is 31 March 2026 while K150/L150 identify May 2025; UT 4- 2026 AD1 is also 31 March 2026|
|Tabular fields|CML/component, area, readings and comments|10-2022 A28:I28: Joint, Band, Nom D, SCH, historical min, current min, max, nominal thickness, comments|
|Evaluation basis|Vessel/API 510 and VIII-1 labels|Evaluation 6-2025 I1 names B31.8-2020, while available reference is 2025; requires edition decision|
|Repair/lifecycle evidence|Build-up and replaced nozzles|Visual Insp. 2026 K106 identifies a replaced section; other captions describe planned replacements not installed|
|Photos and drawings|Image-only reports and visual photographs|Separate photo sheets and drawing-summary regions; DrawingML completeness still needs visual/package review|

## Additional importer requirements
Preserve sheet names exactly while using whitespace-normalized aliases only for search. Parse each historical column as its own dated observation; report date cannot overwrite column-specific campaign dates. Disambiguate repeated min headers (UT 5-2025 G150/H150 both reference October 2022) through evidence rather than positional guessing. Identify section boundaries before matching joints/bands; identifiers repeat across sections. Distinguish planned replacements from completed work. Keep evaluation formulas and calculated/projected current columns separate from measured thickness. Never adopt hard-coded elapsed times or formula factors as approved engineering policy.

## Reference closure
API 570 fifth-edition filename with Addendum 1 and B31.3 2024 are copied and text-indexed. API 570 discovery covers corrosion-rate/remaining-life material; B31.3 discovery covers pressure-design and allowable-stress material. These support separate in-service piping and construction-design rule specifications. Full clause, table-note and applicability verification remains a development gate. Existing workbook B31.8-2020 labels cannot be silently replaced by 2025 rules.

## Remaining gates
Visual/package inspection of shapes and drawings, independently certified expected reading inventories, approved code editions and engineering policies, property-table verification and independent calculation benchmarks remain pending. Source availability is now closed; engineering validation is not.

## TL-B sheet anatomy

|Sheet|Range|Merged ranges|Recognized images|
|---|---|---:|---:|
|2019|A1:S302|277|0|
|Photos 2019|A1:S68|9|4|
| 2021|A1:S318|320|0|
|Evaluation 2021|A1:Q129|36|0|
|10-2022|A1:S51|59|0|
|Photos 10-2022|A1:AD72|8|4|
|UT 12-2022 & Sec-6 (8-2023)|A1:S342|249|0|
|Leak & Photos 12-2022|A1:W524|59|29|
|Cutting Points 1-2023|A1:V90|60|2|
|Cutting & Replacement 3-2023|A1:V43|41|2|
|leak 12-2023|A1:Y43|40|3|
|Eval 8-2023 - ASME B31.3|A1:AH158|96|0|
|Eval 8-2023 - ASME B31.8|A1:X157|59|0|
|UT-FEB 2025 Sec-1&2|A1:T109|107|0|
|Attached Photos 2-2025|A1:A1|0|2|
|Reassess 1500 Psi May-2025|A1:AD165|73|0|
|UT 5-2025|A1:AD238|126|0|
|photos 5-2025|A1:T106|26|7|
|Evaluation 6-2025|A1:Z113|43|0|
|UT 4- 2026|A1:AD157|38|0|
|Evalation 4-2026|A1:AA113|42|0|
|Visual Insp. 2026|A1:X314|52|19|