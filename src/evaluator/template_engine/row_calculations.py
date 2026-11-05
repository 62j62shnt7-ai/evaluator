"""Apply source-row formula subtemplates to normalized UT reading pairs."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from .engine import InputValue, MissingInputError, evaluate_template, select_subtemplate
from .template import load_template


class RowInputError(ValueError):
    def __init__(self, missing: list[str]):
        self.missing = tuple(missing)
        super().__init__("Missing row inputs: " + "; ".join(missing))


def load_calculation_profiles(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    profile_path = Path(path) if path else Path(__file__).parents[1] / "data" / "templates" / "row_calculation_profiles.json"
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0" or not isinstance(data.get("profiles"), list):
        raise ValueError(f"Invalid row-calculation profile file: {profile_path}")
    profiles = {}
    for profile in data["profiles"]:
        required = {"id", "label", "template_file", "source_sheet", "source_row", "outputs", "bindings"}
        if set(profile) != required or profile["id"] in profiles:
            raise ValueError(f"Invalid or duplicate row-calculation profile: {profile.get('id')}")
        if not profile["outputs"] or not isinstance(profile["bindings"], dict):
            raise ValueError(f"Profile {profile['id']} must declare formula outputs")
        profiles[profile["id"]] = profile
    return profiles


def _normalize_date(value: Any) -> date | datetime | None:
    if isinstance(value, (date, datetime)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _reading_provenance(pair: Mapping[str, Any], field: str) -> dict[str, Any] | None:
    locator = pair.get(f"{field}_source")
    if not locator:
        return None
    return {
        "source_type": "sheet",
        "workbook": pair.get("workbook_name"),
        "workbook_sha256": pair.get("workbook_sha256"),
        "sheet": locator.get("sheet"),
        "cell": locator.get("cell"),
    }


def evaluate_reading_pair(
    profile_id: str,
    pair: Mapping[str, Any],
    asset_inputs: Mapping[str, InputValue],
    *,
    templates_dir: str | Path | None = None,
    profiles_path: str | Path | None = None,
) -> dict[str, Any]:
    """Evaluate a point using formulas copied from its approved reference row."""
    profiles = load_calculation_profiles(profiles_path)
    try:
        profile = profiles[profile_id]
    except KeyError:
        raise KeyError(f"Unknown row-calculation profile {profile_id!r}") from None
    template_dir = Path(templates_dir) if templates_dir else Path(__file__).parents[1] / "data" / "templates"
    template = load_template(template_dir / profile["template_file"])
    output_ids = [f"cell|{profile['source_sheet']}|{cell}" for cell in profile["outputs"]]
    selected = select_subtemplate(template, output_ids, template_id=f"{profile_id}_runtime_v1")
    input_nodes = {}
    for node in selected.nodes:
        if node["kind"] != "input":
            continue
        source = node["source_cells"][0]
        if source["sheet"] == profile["source_sheet"]:
            input_nodes[source["cell"].replace("$", "").upper()] = node
    bindings = {key.replace("$", "").upper(): value for key, value in profile["bindings"].items()}
    missing: list[str] = []
    input_values: dict[str, InputValue] = {}
    required_types: dict[str, list[str]] = {}

    for cell, node in input_nodes.items():
        binding = bindings.get(cell)
        if binding is None:
            missing.append(f"{node['label']} from {profile['source_sheet']}!{cell}: no row binding is configured")
            continue
        value = provenance = unit = None
        source = binding["source"]
        if source == "asset":
            datum = asset_inputs.get(binding["key"])
            if datum is None:
                missing.append(f"{binding['key']} ({node['label']}) from asset record")
                continue
            if datum.unit != binding["unit"]:
                missing.append(f"{binding['key']} has unit {datum.unit!r}; expected {binding['unit']!r}")
                continue
            value, unit, provenance = datum.value, datum.unit, datum.provenance
        elif source == "reading":
            key = binding["key"]
            value = pair.get(key)
            unit = pair.get(f"{key}_unit", binding["unit"])
            provenance = _reading_provenance(pair, key)
            if value in (None, ""):
                missing.append(f"{key} ({node['label']}) from the selected UT reading")
                continue
            if provenance is None:
                missing.append(f"{key} ({node['label']}) has no source sheet/cell provenance")
                continue
            if unit != binding["unit"]:
                missing.append(f"{key} has unit {unit!r}; expected {binding['unit']!r}")
                continue
        elif source == "campaign":
            key = binding["key"]
            value = _normalize_date(pair.get(key))
            unit = "date"
            locator = pair.get(f"{key}_source")
            if value is None:
                missing.append(f"{key} ({node['label']}) campaign date")
                continue
            if locator is None:
                missing.append(f"{key} ({node['label']}) date has no source cell provenance")
                continue
            provenance = {
                "source_type": "sheet",
                "workbook": pair.get("workbook_name"),
                "workbook_sha256": pair.get("workbook_sha256"),
                "sheet": locator.get("sheet"),
                "cell": locator.get("cell"),
            }
        else:
            missing.append(f"Unsupported binding source {source!r} for {node['label']}")
            continue
        if not provenance:
            missing.append(f"{node['label']} has no recorded provenance")
            continue
        node_id = node["id"]
        input_values[node_id] = InputValue(value=value, unit=unit, provenance=provenance)
        required_types[node_id] = [str(provenance.get("source_type"))]

    if missing:
        return {
            "profile_id": profile_id,
            "location": pair.get("location"),
            "status": "missing_inputs",
            "missing_inputs": missing,
            "outputs": [],
            "trace": [],
        }

    selected = select_subtemplate(
        template,
        output_ids,
        template_id=f"{profile_id}_runtime_v1",
        provenance_requirements=required_types,
    )
    try:
        result = evaluate_template(selected, input_values)
    except MissingInputError as exc:
        return {
            "profile_id": profile_id,
            "location": pair.get("location"),
            "status": "missing_inputs",
            "missing_inputs": list(getattr(exc, "missing", (str(exc),))),
            "outputs": [],
            "trace": [],
        }

    nodes = {node["id"]: node for node in selected.nodes}
    return {
        "profile_id": profile_id,
        "profile_label": profile["label"],
        "location": pair.get("location"),
        "status": "evaluated",
        "missing_inputs": [],
        "outputs": [
            {
                "node_id": node_id,
                "cell": nodes[node_id]["source_cells"][0]["cell"],
                "label": nodes[node_id]["label"],
                "unit": nodes[node_id]["unit"],
                "value": result.outputs[node_id],
                "code_reference": nodes[node_id]["code_reference"],
            }
            for node_id in output_ids
        ],
        "trace": [
            {"node_id": entry.node_id, "label": entry.label, "expression": entry.expression,
             "inputs": list(entry.inputs), "value": entry.value}
            for entry in result.trace
        ],
    }
