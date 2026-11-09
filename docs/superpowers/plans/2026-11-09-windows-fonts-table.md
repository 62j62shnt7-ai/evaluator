# Windows Fonts and Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix Windows text decoding and make the in-app readings table easier to read and navigate horizontally.

**Architecture:** Explicitly decode workspace HTML as UTF-8 in the HTTP server. Adjust workspace CSS to use a Windows-first font stack and keep the table's first identity columns visible while scrolling.

**Tech Stack:** Python standard library HTTP server; HTML and CSS.

**Spec:** `docs/superpowers/specs/2026-11-09-windows-fonts-table-design.md`

## Global Constraints

- Preserve the current table fields, interactions, and horizontal scrolling.
- Do not change imported data, calculations, matching, or exports.
- Keep changes scoped to `src/evaluator/webapp.py` and `src/evaluator/static/workspace.css`.

## Review Focus

- Windows default encoding must no longer corrupt UTF-8 punctuation in the page.
- Sticky table cells must not cover header labels or block interaction.
- The font must be inherited by inputs and selects as well as page text.

---

### Task 1: Fix Windows rendering and table navigation

**Files:**
- Modify: `src/evaluator/webapp.py`
- Modify: `src/evaluator/static/workspace.css`

**Interfaces:**
- The HTTP handler continues to return the existing workspace page and assets.
- The table remains `#locations` inside `.table-scroll`.

- [ ] Read workspace HTML with explicit UTF-8 encoding.
- [ ] Use a Segoe UI-first font stack and explicitly apply inherited fonts to form controls.
- [ ] Keep selection and identity columns sticky during horizontal scroll; layer sticky header cells above body cells.
- [ ] Slightly increase table and control text for legibility without changing row data or interactions.
- [ ] Inspect the rendered workspace in Windows Chrome and confirm punctuation, table scroll, and sticky columns visually; inspect the final diff.
