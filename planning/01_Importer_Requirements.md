# Importer requirements — draft, 4 November 2026

## Evidence and boundaries
Actual cell/object inventories are in ../evidence. Separator XLSM and XLSX are distinct supplied variants; neither is automatically authoritative. TL-B is unavailable, so a two-workbook layout comparison cannot yet be completed. No reading counts have been certified. Shape-based measurements require package-level and visual inspection beyond openpyxl, whose DrawingML support is incomplete. No macros were executed and no source was saved through openpyxl.

## Observed comparison
| Feature | Separator-204 XLSM | TL-B |
|---|---|---|
| History | Multiple dated report sheets, including 2003/2008 history and 2010–2026 campaigns | Unknown |
| Image-only content | 2010 UT REPORT has no populated cells and eight image objects | Unknown |
| Repeated forms | UT REPORT 2019 repeats headers at rows 1 and 40; 114 merged ranges | Unknown |
| Changing positions | Dates Q1 in 2019/2021/2023, T1 in Aug-2024, S1 in Jan-2026 | Unknown |
| Conflicting dates | UT 10-2026 S1 contains 20 January 2026 while E10 contains 20 October 2026 | Unknown |
| Engineering tables | Evaluation and Evaluation 2026 have different field arrangements | Unknown |
| Derived content | Import/comparison/assistant preview and control sheets coexist with raw reports | Unknown |
| Repairs | Actions Taken records build-up; Visual Inspection 2026 mentions replaced nozzles | Unknown |

## Required extraction contract
IMP-01 Inventory every sheet, visibility, used range, merged region, formula/cache, named range, external link, image, drawing, shape, anchor and macro presence before proposing mappings. Preserve raw package and source checksum. Treat dimension ranges as bounds, never measurement counts.

IMP-02 Detect disconnected regions and repeated page headers. Classify report, drawing, evaluation, narrative and previously generated preview regions. Exclude derived evaluation/preview values from raw UT acquisition unless explicitly selected and provenance labeled.

IMP-03 Retain raw text/value, unit, formula and cached value separately. Never execute VBA, external links or workbook formulas. Missing/stale caches are exceptions. Parse dates using explicit locale rules; retain conflicting date candidates and block date-dependent evaluation until resolved. Do not infer date exclusively from a sheet name.

IMP-04 Extract images and vector/shape text with anchors and relationships. Image-only sheets must be represented as unresolved content, never empty successful imports. Offline OCR is a candidate aid; uncertain numbers require evidence and review. Image coordinate is not a stable TML identifier.

IMP-05 Canonical entities: asset, component, component lifecycle, inspection event, location, observation, design input, mapping proposal, resolution, evaluation revision. Every observation stores workbook hash, sheet, cell/range or object anchor, raw value/unit, normalized value/unit, extraction method and confidence basis. Preserve individual readings before computing a minimum or maximum.

IMP-06 Map locations using asset + component lifecycle + CML/band + physical position. Preserve one-to-many and ambiguous candidates; labels alone cannot establish equivalence. Retain the union across selected inspections. Separate current-only, historical-only, matched and uncertain records.

IMP-07 Parameter precedence is explicit and reviewable: approved asset/component records, verified report fields, then proposed inference. Contradictions create grouped exceptions. Distinguish design pressure, operating pressure, PSV setting, allowable pressure and rerating basis. Preserve mm/in, psi/MPa and F/C conversions with original units.

IMP-08 Replacement, build-up and repair evidence creates candidate lifecycle boundaries. Do not calculate loss across a physical replacement without an approved basis. Missing current UT stays uninspected. A missing prior value may use a separately approved assumed rate. Negative apparent rates remain visible and unresolved rather than silently becoming zero.

## Batch review
Group only records sharing issue type, engineering basis, component/lifecycle, material, units and policy scope. Proposals show evidence, eligible/excluded counts, before/after effects and unresolved exceptions. Offer bulk date correction, material mapping, location matches, approved assumed-rate assignment, exclusion and remeasurement requests. Require explicit reviewer action and justification for engineering choices. Apply changes atomically, retain per-record audit links and support undo as a new revision. Changing inputs invalidates dependent results and approvals. Reusable profiles are versioned and cannot conceal severe loss or missing current readings.

## Pending TL-B examination
Record sheet anatomy, block boundaries, measurement cell/object sources, drawing linkage, dates, units, material/design data, formulas and history; compare each row above. Produce an independently checked expected extraction set for both samples before declaring generic workbook support.
