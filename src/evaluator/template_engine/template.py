"""Versioned JSON templates and strict structural validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .expression import FormulaError, parse_formula

TEMPLATE_SCHEMA_VERSION = "1.0"
NODE_KINDS = {"input", "lookup", "formula", "output"}
PROVENANCE_TYPES = {"sheet", "manual", "code_table"}
ID_PATTERN = re.compile(r"^[A-Za-z0-9_.| -]+$")
CELL_PATTERN = re.compile(r"^\$?[A-Za-z]{1,3}\$?\d+$")


@dataclass(frozen=True)
class Template:
    """Validated template payload."""

    data: dict[str, Any]

    @property
    def template_id(self) -> str:
        return self.data["template_id"]

    @property
    def nodes(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.data["nodes"])


def _validate_source_cell(location: Any, node_id: str) -> None:
    if not isinstance(location, dict) or set(location) != {"sheet", "cell"}:
        raise ValueError(f"Node {node_id}: source_cells entries require sheet and cell")
    if not isinstance(location["sheet"], str) or not location["sheet"].strip():
        raise ValueError(f"Node {node_id}: source sheet must be non-empty text")
    if not isinstance(location["cell"], str) or not CELL_PATTERN.fullmatch(location["cell"]):
        raise ValueError(f"Node {node_id}: invalid source cell {location['cell']!r}")


def validate_template(data: dict[str, Any]) -> Template:
    """Validate template shape, expression grammar, IDs, and cell bindings."""
    required = {
        "schema_version", "template_id", "version", "description", "source_file",
        "source_sha256", "sheets", "outputs", "nodes",
    }
    if not isinstance(data, dict) or set(data) != required:
        actual = set(data) if isinstance(data, dict) else type(data).__name__
        raise ValueError(f"Template fields must be exactly {sorted(required)}; got {actual}")
    if data["schema_version"] != TEMPLATE_SCHEMA_VERSION:
        raise ValueError(f"Unsupported template schema version {data['schema_version']!r}")
    for key in ("template_id", "version", "description", "source_file", "source_sha256"):
        if not isinstance(data[key], str) or not data[key]:
            raise ValueError(f"Template {key} must be non-empty text")
    if not re.fullmatch(r"\d+\.\d+\.\d+", data["version"]):
        raise ValueError("Template version must use semantic version syntax")
    if not re.fullmatch(r"[0-9a-f]{64}", data["source_sha256"]):
        raise ValueError("Template source_sha256 must be a lowercase SHA-256 digest")
    if not isinstance(data["sheets"], list) or not all(isinstance(item, str) for item in data["sheets"]):
        raise ValueError("Template sheets must be a list of sheet names")
    if len(data["sheets"]) != len(set(data["sheets"])):
        raise ValueError("Template sheet names must be unique")
    if not isinstance(data["outputs"], list) or not all(isinstance(item, str) for item in data["outputs"]):
        raise ValueError("Template outputs must be a list of node IDs")
    if len(data["outputs"]) != len(set(data["outputs"])):
        raise ValueError("Template output IDs must be unique")
    if not isinstance(data["nodes"], list):
        raise ValueError("Template nodes must be a list")

    node_ids: set[str] = set()
    locations: dict[tuple[str, str], str] = {}
    for node in data["nodes"]:
        if not isinstance(node, dict):
            raise ValueError("Every template node must be an object")
        common = {"id", "label", "kind", "unit", "source_cells", "code_reference", "provenance_required"}
        expected = common | ({"expression"} if node.get("kind") in {"formula", "output"} else set())
        if set(node) != expected:
            raise ValueError(f"Node fields must be exactly {sorted(expected)}; got {sorted(node)}")
        node_id = node["id"]
        if not isinstance(node_id, str) or not ID_PATTERN.fullmatch(node_id):
            raise ValueError(f"Invalid node ID {node_id!r}")
        if node_id in node_ids:
            raise ValueError(f"Duplicate node ID {node_id}")
        node_ids.add(node_id)
        if node["kind"] not in NODE_KINDS:
            raise ValueError(f"Node {node_id}: unsupported kind {node['kind']!r}")
        if not isinstance(node["label"], str) or not isinstance(node["unit"], str):
            raise ValueError(f"Node {node_id}: label and unit must be text")
        cells = node["source_cells"]
        if not isinstance(cells, list) or not cells:
            raise ValueError(f"Node {node_id}: source_cells must be a non-empty list")
        for cell in cells:
            _validate_source_cell(cell, node_id)
            key = (cell["sheet"], cell["cell"].replace("$", "").upper())
            if key in locations:
                raise ValueError(f"Cell {key} is assigned to nodes {locations[key]} and {node_id}")
            locations[key] = node_id
        code = node["code_reference"]
        if not isinstance(code, dict) or set(code) != {"code", "edition", "clause", "status", "reason"}:
            raise ValueError(f"Node {node_id}: invalid code_reference object")
        if any(code[field] is not None and not isinstance(code[field], str)
               for field in ("code", "edition", "clause", "reason")):
            raise ValueError(f"Node {node_id}: code reference values must be text or null")
        if code["status"] not in {"sheet_header", "unmapped", "not_applicable"}:
            raise ValueError(f"Node {node_id}: invalid code_reference status")
        provenance = node["provenance_required"]
        if not isinstance(provenance, list) or any(item not in PROVENANCE_TYPES for item in provenance):
            raise ValueError(f"Node {node_id}: invalid provenance_required list")
        if node["kind"] == "input" and not provenance:
            raise ValueError(f"Input node {node_id}: provenance is required")
        if node["kind"] in {"formula", "output"}:
            if not isinstance(node["expression"], str):
                raise ValueError(f"Formula node {node_id}: expression must be text")
            try:
                parse_formula(node["expression"])
            except FormulaError as exc:
                raise ValueError(f"Node {node_id}: invalid formula expression: {exc}") from exc

    if set(data["outputs"]) - node_ids:
        raise ValueError(f"Unknown output node IDs: {sorted(set(data['outputs']) - node_ids)}")
    return Template(data)


def load_template(path: str | Path) -> Template:
    """Load and validate a standalone JSON template file."""
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load template {source}: {exc}") from exc
    return validate_template(payload)
