# Master development plan — planning only

## Product and architecture
Offline portable Python UT Inspection Evaluator for Windows. Main workflow: choose reports → inspect coverage → propose mappings → resolve grouped exceptions → evaluate eligible components → review and export. One decision should resolve compatible groups; individual review is reserved for exceptions.

Proposed architecture: read-only ingestion adapters; immutable source store; normalized SQLite repository; matching and validation services; versioned engineering rule modules; batch-review service; local user interface; traceable export service. NiceGUI is a candidate interface requiring an offline packaging spike, not a committed dependency. Prefer deterministic extraction first; offline OCR/vision is optional and separately assessed. No runtime cloud dependency. Localhost-only UI and bundled assets; no automatic downloads. Preserve sources and isolate imported macros.

## Phases and exit gates
1. Evidence closure: acquire missing TL-B, API 570 and B31.3; reconcile workbook variants, produce visual/object maps and reviewer-approved expected reading sets. Exit: all source regions accounted for, including unextractable content.
2. Engineering specification: choose editions, supported component geometries, jurisdiction/site policies, inputs, equations, limits, units and property sources; commission independent worked examples. Exit: qualified engineering approval of each supported rule and dataset.
3. Ingestion prototype: package inspection, cell extraction, drawing extraction, region classification and provenance. Exit: fixture agreement and explicit unresolved counts; no silent loss.
4. History and review: lifecycle matching, union of locations, grouped proposals, atomic bulk actions, audit, undo and policy versions. Exit: batch scenarios pass and incompatible records cannot be swept into approval.
5. Calculation engine: implement only approved rules, separate apparent historical trends from adopted rates, expose readiness reasons and invalidate stale results. Exit: independent numerical benchmarks and boundary tests pass.
6. Outputs and operations: evaluation tables, exception summaries, engineering basis, assumptions, revision history, backup/restore and reproducible exports. Exit: reviewer can trace every result to input and rule edition.
7. Portable Windows release: select supported OS/architecture, bundle Python/dependencies/assets, test clean offline machines, writable data location, long/non-ASCII paths, locked/corrupt files, interrupted transactions and backup restoration. Exit: signed release checklist, dependency/license inventory and user pilot approval.

## Implementation backlog and dependencies
E01 source registry and immutable storage → E02 package inventory → E03 region adapters → E04 normalized observations → E05 lifecycle matching → E06 batch proposals/audit. E07 engineering rules depends on approved engineering specification and benchmarks; E08 evaluation integrates E06/E07; E09 exports; E10 packaging and pilot. Each task must name fixtures, acceptance IDs, expected failures and reviewer before implementation starts. No application implementation is included in this workspace.

## Alternatives and decisions
Template-specific adapters are more predictable for initial known reports; generic heuristics broaden coverage but increase ambiguity. Recommended staged hybrid: verified adapters plus evidence-based generic detection and explicit unsupported regions. A desktop UI avoids a local server but needs separate table/image tooling; evaluate against NiceGUI during packaging spike. SQLite is proposed for transactional local history; preserve portable backup/export formats to avoid lock-in.

## Outstanding decisions
Target Windows versions; expected maximum file size/reading volume; reviewer roles and local identity; code editions and permitted scope; corrosion-rate policy and uncertainty treatment; material-property licensing; structural minimum inputs; acceptable OCR tools; required export formats. Establish performance budgets using measured fixtures rather than invented timing promises.
