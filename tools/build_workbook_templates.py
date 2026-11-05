#!/usr/bin/env python3
"""Build versioned formula templates from read-only reference workbooks."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import warnings
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluator.template_engine.expression import FormulaError, parse_formula, references
from evaluator.template_engine.template import validate_template

CODE_PATTERN = re.compile(r"API\s*-?\s*(510|570|574)|ASME\s+(B31\.[348]|VIII(?:\s*[- ]?1)?)", re.I)
YEAR_PATTERN = re.compile(r"(?:B31\.[348]|VIII(?:\s*[- ]?1)?)[^\n]{0,30}?(?:[- ](20\d{2})|\b(20\d{2})\b)", re.I)


def _formula_cells(workbook):
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    yield sheet, cell


def _code_reference(sheet):
    header = " ".join(
        str(cell.value)
        for row in sheet.iter_rows(min_row=1, max_row=min(8, sheet.max_row))
        for cell in row
        if cell.value is not None and not (isinstance(cell.value, str) and cell.value.startswith("="))
    )
    matches = list(dict.fromkeys(match.group(0).strip() for match in CODE_PATTERN.finditer(header)))
    year = YEAR_PATTERN.search(header)
    if not matches:
        return {
            "code": None, "edition": None, "clause": None, "status": "unmapped",
            "reason": "No code/edition basis is stated in the source sheet header.",
        }
    return {
        "code": "; ".join(matches),
        "edition": next((value for value in year.groups() if value), None) if year else None,
        "clause": None,
        "status": "sheet_header",
        "reason": "Code basis is copied from the source sheet header; clause mapping remains pending.",
    }


def _column_label(sheet, column, first_formula_row):
    values = []
    for row in range(2, min(first_formula_row, 8) + 1):
        value = sheet.cell(row, column).value
        if value is not None and not (isinstance(value, str) and value.startswith("=")):
            values.append(str(value).replace("\n", " ").strip())
    if values:
        return values[0]
    for row in range(max(1, first_formula_row - 8), first_formula_row):
        value = sheet.cell(row, column).value
        if value is not None and not (isinstance(value, str) and value.startswith("=")):
            values.append(str(value).replace("\n", " ").strip())
    return values[-1] if values else f"{sheet.title} column {column}"


def _unit(label):
    match = re.search(r"\(([^()]{1,30})\)", label)
    return match.group(1).strip() if match else "unspecified"


def build_template(source: Path, template_id: str) -> dict:
    keep_vba = source.suffix.lower() == ".xlsm"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        workbook = load_workbook(source, data_only=False, read_only=False, keep_vba=keep_vba)

    formulas: dict[tuple[str, str], tuple[str, object]] = {}
    asts = {}
    formula_dependents: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    referenced: set[tuple[str, str]] = set()
    formula_sheets = []
    for sheet, cell in _formula_cells(workbook):
        key = (sheet.title, cell.coordinate)
        formulas[key] = (cell.value, cell)
        try:
            ast = parse_formula(cell.value)
        except FormulaError as exc:
            raise ValueError(f"Unsupported formula in {sheet.title}!{cell.coordinate}: {exc}") from exc
        asts[key] = ast
        if sheet.title not in formula_sheets:
            formula_sheets.append(sheet.title)
        for reference in references(ast, sheet.title):
            reference_key = (reference.sheet or sheet.title, reference.coordinate)
            referenced.add(reference_key)
    # Resolve dependents after collecting all formula cells; references may point forward.
    for formula_key, ast in asts.items():
        sheet_title, _ = formula_key
        for reference in references(ast, sheet_title):
            reference_key = (reference.sheet or sheet_title, reference.coordinate)
            if reference_key in formulas:
                formula_dependents[reference_key].add(formula_key)

    node_by_key = {}
    for key in sorted(referenced):
        if key not in formulas:
            node_by_key[key] = "input"
    for key in formulas:
        node_by_key[key] = "output" if not formula_dependents.get(key) else "formula"

    header_context = {}
    for (sheet_name, coordinate), (_, cell) in formulas.items():
        col_label = _column_label(workbook[sheet_name], cell.column, cell.row)
        header_context[(sheet_name, cell.column)] = col_label

    def node_id(key):
        return f"cell|{key[0]}|{key[1]}"

    nodes = []
    for (sheet_name, coordinate), kind in sorted(node_by_key.items()):
        sheet = workbook[sheet_name]
        cell = sheet[coordinate]
        label = header_context.get((sheet_name, cell.column))
        if label is None:
            label = _column_label(sheet, cell.column, cell.row)
        node = {
            "id": node_id((sheet_name, coordinate)),
            "label": label if kind != "input" else f"Input: {sheet_name}!{coordinate} ({label})",
            "kind": kind,
            "unit": _unit(label),
            "source_cells": [{"sheet": sheet_name, "cell": coordinate}],
            "code_reference": _code_reference(sheet),
            "provenance_required": ["sheet"] if kind == "input" else [],
        }
        if kind in {"formula", "output"}:
            node["expression"] = formulas[(sheet_name, coordinate)][0]
        nodes.append(node)

    outputs = sorted(node_id(key) for key, kind in node_by_key.items() if kind == "output")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    payload = {
        "schema_version": "1.0",
        "template_id": template_id,
        "version": "1.0.0",
        "description": f"Workbook-formula reproduction template for {source.name}; it preserves sheet formulas and does not generalize their applicability.",
        "source_file": source.name,
        "source_sha256": digest,
        "sheets": formula_sheets,
        "outputs": outputs,
        "nodes": nodes,
    }
    validate_template(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("template_id")
    parser.add_argument("--output", type=Path, help="defaults to evaluator data/templates")
    args = parser.parse_args()
    if not args.workbook.is_file():
        parser.error(f"Workbook not found: {args.workbook}")
    output = args.output or ROOT / "src/evaluator/data/templates" / f"{args.template_id}_v1.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_template(args.workbook, args.template_id)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}: {len(payload['nodes'])} nodes, {len(payload['outputs'])} outputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
