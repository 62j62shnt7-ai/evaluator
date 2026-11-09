# Windows fonts and readings table

## Intent

Make the in-app readings workspace render text correctly and make its wide table easier to use in Windows Chrome.

## Goals

- Decode the workspace HTML as UTF-8 on Windows so punctuation renders correctly.
- Use a predictable Windows system font for page text and form controls.
- Preserve the full editable table while making its horizontal layout easier to navigate.

## Non-goals

- Change reading data, calculations, matching, or exports.
- Replace the editable table with a different interaction model.

## Approaches

1. Fix UTF-8 decoding, define a Windows-first font stack, and improve the existing scrollable table. **Recommended** because it addresses the observed mojibake and keeps the current workflow intact.
2. Change only the font and spacing. This leaves the observed Windows encoding bug and current wide-table navigation unresolved.

## Chosen direction

Use approach 1. The app's HTML is UTF-8, but the server reads it with the platform default encoding; the open Windows page visibly shows `Â·` in place of `·`. The readings grid is about 2,812 px wide inside a 1,682 px scroll area, with 12 px inputs. Set an explicit Windows-friendly font stack and inherited control fonts, then keep horizontal scrolling while improving the table's persistent location context and readability.

## Builder decisions

Keep changes scoped to the workspace HTML loading path and workspace CSS. Use a Segoe UI-first font stack and explicitly inherit it in form controls. Preserve the current horizontal scroller and all row fields, while pinning the selection and identity columns during horizontal scrolling and slightly increasing table/control text for legibility. Verify the rendered app in the available Windows Chrome session and inspect the final diff.
