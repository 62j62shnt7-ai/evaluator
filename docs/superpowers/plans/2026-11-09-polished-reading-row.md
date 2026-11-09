# Polished Reading Row Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the in-app readings grid rows compact, scannable, and visually cohesive without changing its data or behavior.

**Architecture:** Update the existing row renderer to show a compact location summary, collapsed native identity editor, and grouped measurement markup. Refine the existing workspace CSS for row hierarchy, alignment, striping, and result states.

**Tech Stack:** Existing HTML template strings, vanilla JavaScript, CSS.

**Spec:** `docs/superpowers/specs/2026-11-09-polished-reading-row-design.md`

## Global Constraints

- Preserve all existing columns, row editing, selection, previous-reading matching, calculation details, and save actions.
- Keep the current horizontal table scroller and sticky selection/location columns.
- Add no dependencies and change no calculation or saved-data behavior.

## Review Focus

- Collapsed identity fields remain reachable and retain the save action.
- Previous-reading selection and measurement inputs remain functional.
- Sticky columns, row striping, hover, and selected styles layer correctly.

---

### Task 1: Compact row content and visual hierarchy

**Files:**
- Modify: `src/evaluator/static/workspace.js`
- Modify: `src/evaluator/static/workspace.css`

**Interfaces:**
- Preserve existing delegated `data-identity`, `data-save-identity`, `data-detail`, `data-previous`, and `data-engineering` hooks.
- Keep the `#locations` table and `.table-scroll` wrapper.

- [ ] Render location identity as a compact summary with matching fields inside a collapsed `Edit match` disclosure.
- [ ] Keep calculation details accessible in the location cell.
- [ ] Group previous/current date, reading, and previous-match control with clear visual hierarchy.
- [ ] Style rows, controls, and result states consistently while preserving sticky columns.
- [ ] Review the live Windows Chrome grid and final diff; do not run tests for this visual-only change.
