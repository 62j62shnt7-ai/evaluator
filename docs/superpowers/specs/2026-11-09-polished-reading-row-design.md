# Polished readings grid rows

## Intent

Make the in-app readings table easier to scan and more visually composed while reviewing many locations at once.

## Goals

- Reduce row height by removing the always-open, four-field identity editor and stacked actions from the primary row view.
- Give each reading a clear location identity and visually grouped previous/current measurements.
- Align editable controls and calculated values consistently across rows.
- Keep the wide comparison grid and its current horizontal scrolling behavior.

## Non-goals

- Change readings, matching, calculation behavior, or saved project data.
- Replace the grid with a vertical card list, which would make comparing many locations slower.

## Approaches

1. **Compact grid row (recommended and selected by default):** retain all existing columns, use a compact location summary, place matching fields in a collapsed “Edit match” disclosure, and refine row spacing, measurement emphasis, and status colors. This retains fast comparison across locations and directly removes the main source of row height.
2. **Expandable reading cards:** show a short summary and reveal all details on demand. This gives each reading more room but makes comparison across dozens of locations harder and increases vertical scrolling.

## Design

Each row should read as one inspection record. The sticky first column holds selection; the sticky identity column shows section/joint prominently with band/size as secondary metadata. Matching fields appear inside a native disclosure labeled “Edit match” and retain the existing save action. Previous and current measurements each show a quiet date label and a prominent value; the previous-reading selector remains available without overpowering the measurement. Controls and derived values use consistent compact dimensions. Subtle alternating row surfaces, clear row boundaries, and restrained result colors distinguish records without adding visual noise.

## Constraints

- Preserve all existing columns, row editing, selection, previous-reading matching, calculation details, and save actions.
- Keep the current horizontal table scroller and sticky selection/location columns.
- Scope changes to the workspace row renderer and CSS; add no dependencies.
- Check the rendered Windows Chrome view and inspect the final diff.
