"""Dependency-graph evaluation with per-input provenance and cell traces."""

from __future__ import annotations

import hashlib
import heapq
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from openpyxl import load_workbook
from openpyxl.utils.datetime import to_excel

from .expression import (
    CellRef,
    ExcelError,
    Node,
    evaluate_expression,
    parse_formula,
    references,
)
from .template import Template, validate_template


class MissingInputError(ValueError):
    """An input is missing or lacks a required source record."""


class DependencyError(ValueError):
    """A formula refers to a missing node or the dependency graph contains a cycle."""


@dataclass(frozen=True)
class InputValue:
    value: Any
    unit: str
    provenance: Mapping[str, Any] | None


@dataclass(frozen=True)
class TraceEntry:
    node_id: str
    label: str
    expression: str
    inputs: tuple[dict[str, Any], ...]
    value: Any


@dataclass(frozen=True)
class Evaluation:
    values: Mapping[str, Any]
    outputs: Mapping[str, Any]
    trace: tuple[TraceEntry, ...]


def _cell_key(sheet: str, coordinate: str) -> tuple[str, str]:
    return sheet, coordinate.replace("$", "").upper()


def _flatten_expression_references(node: Node, sheet: str) -> tuple[CellRef, ...]:
    return references(node, sheet)


def _node_source(node: dict[str, Any]) -> tuple[str, str]:
    source = node["source_cells"][0]
    return source["sheet"], source["cell"]


def _code_context(node: dict[str, Any]) -> str:
    code = node.get("code_reference", {})
    label = " ".join(str(code.get(key) or "") for key in ("code", "edition", "clause", "status")).strip()
    return label or "unmapped code reference"


def _date_to_excel(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return Decimal(str(to_excel(value)))
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    if isinstance(value, str) and value.startswith("#"):
        return ExcelError(value)
    return value


def inputs_from_workbook(path: str | Path, template: Template | dict[str, Any]) -> dict[str, InputValue]:
    """Read only template input cells and attach workbook-cell provenance."""
    data = validate_template(template).data if isinstance(template, dict) else template.data
    workbook_path = Path(path)
    digest = hashlib.sha256(workbook_path.read_bytes()).hexdigest()
    keep_vba = workbook_path.suffix.lower() == ".xlsm"
    # Random source-cell access is frequent here; a normal workbook avoids
    # reparsing the XML row-by-row for each bound input as read-only mode does.
    workbook = load_workbook(workbook_path, data_only=False, read_only=False, keep_vba=keep_vba)
    result: dict[str, InputValue] = {}
    for node in data["nodes"]:
        if node["kind"] != "input":
            continue
        sheet, coordinate = _node_source(node)
        if sheet not in workbook.sheetnames:
            raise MissingInputError(f"Missing input {node['label']} ({node['id']}): sheet {sheet!r} is absent")
        raw = workbook[sheet][coordinate].value
        if isinstance(raw, str) and raw.startswith("="):
            raise MissingInputError(f"Input node {node['id']} points to a formula cell")
        result[node["id"]] = InputValue(
            value=_date_to_excel(raw),
            unit=node["unit"],
            provenance={
                "source_type": "sheet",
                "workbook": workbook_path.name,
                "workbook_sha256": digest,
                "sheet": sheet,
                "cell": coordinate,
            },
        )
    return result


def _ast_for_node(node: dict[str, Any]) -> Node:
    return parse_formula(node["expression"])


def _dependencies(template_data: dict[str, Any]) -> tuple[
    dict[str, dict[str, Any]], dict[tuple[str, str], str], dict[str, Node], dict[str, set[str]]
]:
    by_id = {node["id"]: node for node in template_data["nodes"]}
    location_to_id = {_cell_key(*_node_source(node)): node["id"] for node in template_data["nodes"]}
    expressions: dict[str, Node] = {}
    dependencies: dict[str, set[str]] = {node_id: set() for node_id in by_id}
    for node in template_data["nodes"]:
        if node["kind"] not in {"formula", "output"}:
            continue
        ast = _ast_for_node(node)
        expressions[node["id"]] = ast
        sheet, _ = _node_source(node)
        for reference in _flatten_expression_references(ast, sheet):
            dependency_id = location_to_id.get(_cell_key(reference.sheet or sheet, reference.coordinate))
            if dependency_id is None:
                raise DependencyError(
                    f"Node {node['id']} references missing template input/node "
                    f"{reference.sheet or sheet}!{reference.coordinate}"
                )
            dependencies[node["id"]].add(dependency_id)
    return by_id, location_to_id, expressions, dependencies


def _topological_order(by_id: dict[str, dict[str, Any]], dependencies: dict[str, set[str]]) -> list[str]:
    indegree = {key: len(value) for key, value in dependencies.items()}
    dependents: dict[str, list[str]] = {key: [] for key in by_id}
    for node_id, deps in dependencies.items():
        for dependency in deps:
            dependents[dependency].append(node_id)
    ready = [key for key, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        current = heapq.heappop(ready)
        order.append(current)
        for node_id in dependents[current]:
            indegree[node_id] -= 1
            if indegree[node_id] == 0:
                heapq.heappush(ready, node_id)
    if len(order) != len(by_id):
        cycle = sorted(node_id for node_id, count in indegree.items() if count)
        raise DependencyError(f"Template dependency cycle detected: {', '.join(cycle[:12])}")
    return order


def _display(value: Any) -> Any:
    if isinstance(value, ExcelError):
        return value.code
    return value


def evaluate_template(
    template: Template | dict[str, Any],
    inputs: Mapping[str, InputValue],
) -> Evaluation:
    """Validate provenance, evaluate in dependency order, and return a cell trace."""
    data = validate_template(template).data if isinstance(template, dict) else template.data
    by_id, location_to_id, ast_by_id, dependencies = _dependencies(data)
    order = _topological_order(by_id, dependencies)
    values: dict[str, Any] = {}
    provenance: dict[str, Mapping[str, Any] | None] = {}
    trace: list[TraceEntry] = []

    for node_id in order:
        node = by_id[node_id]
        if node["kind"] == "lookup":
            raise MissingInputError(f"Lookup node {node_id} has no verified lookup-table value")
        if node["kind"] == "input":
            datum = inputs.get(node_id)
            code_context = _code_context(node)
            if datum is None:
                raise MissingInputError(
                    f"Missing required input {node['label']} ({node_id}); code/table: {code_context}"
                )
            if datum.provenance is None:
                raise MissingInputError(
                    f"Input {node['label']} ({node_id}) has no provenance; code/table: {code_context}"
                )
            source_type = datum.provenance.get("source_type")
            for required_type in node["provenance_required"]:
                if source_type != required_type:
                    raise MissingInputError(
                        f"Input {node['label']} ({node_id}) requires {required_type} provenance, "
                        f"received {source_type!r}; code/table: {code_context}"
                    )
            values[node_id] = _date_to_excel(datum.value)
            provenance[node_id] = datum.provenance
            continue

        def resolve(sheet: str, coordinate: str) -> Any:
            dependency_id = location_to_id.get(_cell_key(sheet, coordinate))
            if dependency_id is None or dependency_id not in values:
                raise DependencyError(f"Value for {sheet}!{coordinate} is not ready")
            return values[dependency_id]

        value = evaluate_expression(ast_by_id[node_id], _node_source(node)[0], resolve)
        values[node_id] = value
        inputs_for_trace = []
        for dependency_id in sorted(dependencies[node_id]):
            dependency = by_id[dependency_id]
            inputs_for_trace.append({
                "node_id": dependency_id,
                "label": dependency["label"],
                "source_cells": dependency["source_cells"],
                "value": _display(values[dependency_id]),
                "provenance": provenance.get(dependency_id),
            })
        trace.append(TraceEntry(
            node_id=node_id,
            label=node["label"],
            expression=node["expression"],
            inputs=tuple(inputs_for_trace),
            value=_display(value),
        ))

    output_values = {node_id: _display(values[node_id]) for node_id in data["outputs"]}
    return Evaluation(
        values={node_id: _display(value) for node_id, value in values.items()},
        outputs=output_values,
        trace=tuple(trace),
    )
