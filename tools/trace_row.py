#!/usr/bin/env python3
"""Trace Excel formula dependencies and cached values for cells in a workbook.

Usage: python tools/trace_row.py WORKBOOK SHEET CELL [CELL ...]
Cell arguments may be single A1 cells or a row number (all formula cells in that row).
The workbook is read-only from the tool's perspective; data_only values are shown beside formulas.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.formula import Tokenizer
from openpyxl.utils.cell import range_boundaries

# Sheet-qualified and local A1 references, including ranges and absolute markers.
REF_RE = re.compile(
    r"(?:(?:'(?P<quoted>(?:[^']|'')+)'|(?P<plain>[A-Za-z_][A-Za-z0-9_. ]*))!)?"
    r"\$?(?P<c1>[A-Za-z]{1,3})\$?(?P<r1>\d+)"
    r"(?:\s*:\s*\$?(?P<c2>[A-Za-z]{1,3})\$?(?P<r2>\d+))?"
)


def dependencies(formula: str, current_sheet: str, sheetnames: set[str]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    try:
        tokens = Tokenizer(formula).items
    except Exception:
        tokens = []
    for token in tokens:
        if token.type != "OPERAND" or token.subtype != "RANGE":
            continue
        raw = token.value
        for match in REF_RE.finditer(raw):
            quoted, plain = match.group("quoted"), match.group("plain")
            sheet = (quoted.replace("''", "'") if quoted is not None else plain) or current_sheet
            if sheet not in sheetnames:
                continue  # named ranges, table refs, and external refs are not local cells
            c1, r1 = match.group("c1"), int(match.group("r1"))
            if match.group("c2") is None:
                c2, r2 = c1, r1
            else:
                c2, r2 = match.group("c2"), int(match.group("r2"))
            min_col, min_row, max_col, max_row = range_boundaries(f"{c1}{r1}:{c2}{r2}")
            for row in range(min_row, max_row + 1):
                for col in range(min_col, max_col + 1):
                    from openpyxl.utils import get_column_letter
                    found.append((sheet, f"{get_column_letter(col)}{row}"))
    return list(dict.fromkeys(found))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("sheet")
    parser.add_argument("cells", nargs="+", help="A1 cells or row numbers")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()
    if not args.workbook.is_file():
        parser.error(f"Workbook not found: {args.workbook}")
    keep_vba = args.workbook.suffix.lower() == ".xlsm"
    formulas = load_workbook(args.workbook, data_only=False, read_only=False, keep_vba=keep_vba)
    cached = load_workbook(args.workbook, data_only=True, read_only=False, keep_vba=keep_vba)
    if args.sheet not in formulas.sheetnames:
        parser.error(f"Sheet not found: {args.sheet!r}; available sheets: {', '.join(formulas.sheetnames)}")
    ws, value_ws = formulas[args.sheet], cached[args.sheet]
    roots: list[str] = []
    for item in args.cells:
        if item.isdigit():
            row = int(item)
            roots.extend(c.coordinate for c in ws[row] if isinstance(c.value, str) and c.value.startswith("="))
        else:
            roots.append(item.upper())
    roots = list(dict.fromkeys(roots))
    graph: dict[tuple[str, str], dict[str, Any]] = {}
    visiting: set[tuple[str, str]] = set()

    def walk(sheet: str, coord: str) -> None:
        key = (sheet, coord)
        if key in graph or key in visiting:
            return
        visiting.add(key)
        cell = formulas[sheet][coord]
        value = cell.value
        deps = dependencies(value, sheet, set(formulas.sheetnames)) if isinstance(value, str) and value.startswith("=") else []
        graph[key] = {
            "sheet": sheet,
            "cell": coord,
            "kind": "FORMULA" if isinstance(value, str) and value.startswith("=") else ("INPUT" if value is not None else "BLANK"),
            "formula": value if isinstance(value, str) and value.startswith("=") else None,
            "value": value_ws[coord].value,
            "literal": None if isinstance(value, str) and value.startswith("=") else value,
            "dependencies": [{"sheet": s, "cell": c} for s, c in deps],
        }
        for dep_sheet, dep_coord in deps:
            walk(dep_sheet, dep_coord)
        visiting.remove(key)

    for root in roots:
        walk(args.sheet, root)
    result = {"workbook": str(args.workbook), "roots": roots, "nodes": list(graph.values())}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    by_key = {(n["sheet"], n["cell"]): n for n in result["nodes"]}
    printed: set[tuple[str, str]] = set()

    def display(sheet: str, coord: str, depth: int = 0) -> None:
        key = (sheet, coord)
        node = by_key[key]
        pad = "  " * depth
        if key in printed:
            print(f"{pad}{sheet}!{coord} [already shown]")
            return
        printed.add(key)
        formula = f" formula={node['formula']}" if node["formula"] is not None else ""
        print(f"{pad}{node['kind']} {sheet}!{coord}{formula} | cached={node['value']!r}")
        if node["kind"] == "INPUT":
            print(f"{pad}  INPUT literal={node['literal']!r}")
        for dep in node["dependencies"]:
            display(dep["sheet"], dep["cell"], depth + 1)

    for root in roots:
        print(f"ROOT {args.sheet}!{root}")
        display(args.sheet, root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
