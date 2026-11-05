"""Versioned mappings for readings-only workbook layouts."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


BUILTIN_LAYOUTS = {
    "separator_min_v1": {
        "id": "separator_min_v1", "version": 1, "kind": "adapter",
        "label": "Separator CML / MIN columns", "adapter": "separator",
        "location_columns": [1, 2, 3], "measurement": "explicit MIN columns",
        "dates": "MIN header dates; ambiguous campaign dates remain unresolved",
    },
    "tlb_dated_v1": {
        "id": "tlb_dated_v1", "version": 1, "kind": "adapter",
        "label": "TL-B joint / band / dated MIN columns", "adapter": "tlb",
        "location_columns": [1, 2], "measurement": "dated MIN columns",
        "dates": "explicit date cells aligned with MIN columns",
    },
}


def _col_number(value: Any) -> int:
    if isinstance(value, int) and value > 0:
        return value
    text = str(value).strip().upper()
    if not text.isalpha():
        raise ValueError(f"Invalid Excel column {value!r}")
    number = 0
    for char in text:
        number = number * 26 + ord(char) - 64
    return number


def preview_layout(path: str | Path, sheet: str, *, rows: int = 20) -> dict[str, Any]:
    """Read-only mapping preview with dimensions and exact cell addresses."""
    path = Path(path)
    wb = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    try:
        if sheet not in wb.sheetnames:
            raise KeyError(f"Unknown exact sheet name: {sheet!r}")
        ws = wb[sheet]
        samples = []
        for row in ws.iter_rows(min_row=1, max_row=min(rows, ws.max_row), max_col=min(ws.max_column, 40)):
            samples.append([{"cell": cell.coordinate, "value": cell.value.isoformat() if isinstance(cell.value, (date, datetime)) else cell.value} for cell in row if cell.value is not None])
        return {"sheet": sheet, "max_row": ws.max_row, "max_column": ws.max_column, "samples": samples}
    finally:
        wb.close()


def validate_custom_profile(profile: dict[str, Any]) -> dict[str, Any]:
    required = {"id", "label", "header_row", "first_data_row", "location_columns", "previous_thickness_column", "current_thickness_column", "previous_date_cell", "current_date_cell", "unit"}
    if set(profile) != required:
        raise ValueError(f"Custom layout profile fields must be exactly: {', '.join(sorted(required))}")
    if not profile["id"].strip() or not profile["label"].strip():
        raise ValueError("Profile ID and label are required")
    for key in ("header_row", "first_data_row"):
        if int(profile[key]) < 1:
            raise ValueError(f"{key} must be a positive row number")
    if not profile["location_columns"]:
        raise ValueError("At least one location column is required")
    if profile["unit"] != "mm":
        raise ValueError("Current source templates bind thickness in mm; convert readings explicitly before import")
    result = dict(profile)
    result.update({"kind": "custom", "version": 1, "header_row": int(profile["header_row"]), "first_data_row": int(profile["first_data_row"]),
                   "location_columns": [_col_number(x) for x in profile["location_columns"]],
                   "previous_thickness_column": _col_number(profile["previous_thickness_column"]),
                   "current_thickness_column": _col_number(profile["current_thickness_column"]),
                   "confirmed_utc": datetime.now(timezone.utc).isoformat()})
    return result

