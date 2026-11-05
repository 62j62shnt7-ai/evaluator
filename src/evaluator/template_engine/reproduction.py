"""Per-cell comparison of template results with cached Excel outputs."""

from __future__ import annotations

import csv
import hashlib
import html
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel, to_excel

from .engine import Evaluation, evaluate_template, inputs_from_workbook
from .expression import ExcelError
from .template import Template, load_template

EXCEL_PRECISION_TOLERANCE = Decimal("5e-15")


@dataclass(frozen=True)
class CellComparison:
    workbook: str
    sheet: str
    cell: str
    expected: Any
    actual: Any
    difference: Any
    equal: bool
    trace: dict[str, Any]


@dataclass(frozen=True)
class ReproductionReport:
    source_file: str
    template_id: str
    comparisons: tuple[CellComparison, ...]
    cached_values_missing: tuple[str, ...]
    evaluation: Evaluation

    @property
    def mismatches(self) -> tuple[CellComparison, ...]:
        return tuple(item for item in self.comparisons if not item.equal)


def _numeric(value: Any) -> Decimal | None:
    if isinstance(value, ExcelError):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    return None


def _canonical(value: Any) -> Any:
    if isinstance(value, ExcelError):
        return value.code
    if isinstance(value, Decimal):
        return value
    return value


def _compare(expected: Any, actual: Any) -> tuple[bool, Any]:
    date_precision = isinstance(expected, (date, datetime))
    if date_precision:
        expected = _serial(expected)
    expected = _canonical(expected)
    actual = _canonical(actual)
    expected_number = _numeric(expected)
    actual_number = _numeric(actual)
    if expected_number is not None and actual_number is not None:
        difference = actual_number - expected_number
        scale = max(Decimal(1), abs(expected_number), abs(actual_number))
        tolerance = (
            Decimal(1) / Decimal(86_400_000)
            if date_precision
            else EXCEL_PRECISION_TOLERANCE * scale
        )
        return abs(difference) <= tolerance, difference
    return expected == actual, None


def _serial(value: Any) -> Any:
    if hasattr(value, "year") and hasattr(value, "month"):
        return Decimal(str(to_excel(value)))
    return value


def reproduce_workbook(
    template_path: str | Path,
    workbook_path: str | Path,
    output_dir: str | Path | None = None,
) -> ReproductionReport:
    """Evaluate a workbook template and compare every formula cell cache."""
    template = load_template(template_path)
    source = Path(workbook_path)
    keep_vba = source.suffix.lower() == ".xlsm"
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if source_hash != template.data["source_sha256"]:
        raise ValueError(
            f"Template {template.template_id} is bound to {template.data['source_file']} "
            f"({template.data['source_sha256']}), but {source.name} hashes to {source_hash}"
        )
    inputs = inputs_from_workbook(source, template)
    evaluation = evaluate_template(template, inputs)
    formulas = load_workbook(source, data_only=False, read_only=False, keep_vba=keep_vba)
    cached = load_workbook(source, data_only=True, read_only=False, keep_vba=keep_vba)
    trace_by_id = {entry.node_id: entry for entry in evaluation.trace}
    comparisons: list[CellComparison] = []
    missing: list[str] = []

    for node in template.nodes:
        if node["kind"] not in {"formula", "output"}:
            continue
        location = node["source_cells"][0]
        sheet, cell = location["sheet"], location["cell"]
        formula = formulas[sheet][cell].value
        expected = cached[sheet][cell].value
        if expected is None:
            missing.append(f"{sheet}!{cell}")
            continue
        if not isinstance(formula, str) or not formula.startswith("="):
            raise ValueError(f"Template formula node no longer points to formula {sheet}!{cell}")
        actual = evaluation.values[node["id"]]
        expected_display = expected
        equal, difference = _compare(expected, actual)
        report_actual = (
            from_excel(float(actual))
            if isinstance(expected, (date, datetime)) and _numeric(actual) is not None
            else actual
        )
        trace_entry = trace_by_id[node["id"]]
        trace = {
            "node_id": trace_entry.node_id,
            "label": trace_entry.label,
            "expression": trace_entry.expression,
            "inputs": list(trace_entry.inputs),
            "value": trace_entry.value,
        }
        comparisons.append(CellComparison(
            workbook=source.name,
            sheet=sheet,
            cell=cell,
            expected=expected_display,
            actual=report_actual,
            difference=difference,
            equal=equal,
            trace=trace,
        ))

    report = ReproductionReport(
        source_file=source.name,
        template_id=template.template_id,
        comparisons=tuple(comparisons),
        cached_values_missing=tuple(missing),
        evaluation=evaluation,
    )
    if output_dir is not None:
        write_report(report, Path(output_dir))
    return report


def _json_value(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    return str(value) if value is not None else ""


def write_report(report: ReproductionReport, output_dir: Path) -> tuple[Path, Path]:
    """Write reproducible per-cell CSV and HTML reports with dependency traces."""
    output_dir.mkdir(parents=True, exist_ok=True)
    source_name = Path(report.source_file)
    stem = f"{source_name.stem}_{source_name.suffix.lstrip('.')}".lower().replace(" ", "_").replace("-", "_")
    csv_path = output_dir / f"{stem}_reproduction.csv"
    html_path = output_dir / f"{stem}_reproduction.html"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["workbook", "sheet", "cell", "expected", "actual", "difference", "equal", "trace"],
        )
        writer.writeheader()
        for item in report.comparisons:
            writer.writerow({
                "workbook": item.workbook,
                "sheet": item.sheet,
                "cell": item.cell,
                "expected": _json_value(item.expected),
                "actual": _json_value(item.actual),
                "difference": _json_value(item.difference),
                "equal": item.equal,
                "trace": json.dumps(item.trace, ensure_ascii=False, default=str, separators=(",", ":")),
            })
    mismatches = report.mismatches
    body = []
    for item in report.comparisons:
        status = "MATCH" if item.equal else "MISMATCH"
        body.append(
            "<tr class='" + status.lower() + "'><td>" + html.escape(status) + "</td><td>"
            + html.escape(item.sheet) + "</td><td>" + html.escape(item.cell) + "</td><td>"
            + html.escape(_json_value(item.expected)) + "</td><td>"
            + html.escape(_json_value(item.actual)) + "</td><td>"
            + html.escape(_json_value(item.difference)) + "</td><td><details><summary>Trace</summary><pre>"
            + html.escape(json.dumps(item.trace, ensure_ascii=False, indent=2, default=str))
            + "</pre></details></td></tr>"
        )
    summary = (
        f"{len(report.comparisons) - len(mismatches)} / {len(report.comparisons)} matched; "
        f"{len(mismatches)} mismatches; {len(report.cached_values_missing)} formula caches missing."
    )
    document = (
        "<!doctype html><html><head><meta charset='utf-8'><title>Workbook reproduction</title>"
        "<style>body{font:14px system-ui;margin:2rem;color:#18212b}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #d5dbe2;padding:.4rem;text-align:left;vertical-align:top}"
        ".mismatch{background:#fff1f0}.match{background:#f2fbf5}pre{white-space:pre-wrap;max-width:70rem}</style>"
        "</head><body><h1>Workbook reproduction</h1><p>" + html.escape(report.source_file)
        + "</p><p>" + html.escape(summary) + "</p><table><thead><tr><th>Status</th><th>Sheet</th>"
        "<th>Cell</th><th>Expected</th><th>Actual</th><th>Difference</th><th>Trace</th></tr></thead><tbody>"
        + "".join(body) + "</tbody></table></body></html>"
    )
    html_path.write_text(document, encoding="utf-8")
    return csv_path, html_path
