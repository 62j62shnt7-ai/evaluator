from __future__ import annotations

from decimal import Decimal

import pytest

from evaluator.template_engine.engine import (
    DependencyError,
    InputValue,
    MissingInputError,
    evaluate_template,
)
from evaluator.template_engine.expression import ExcelError, evaluate_expression, parse_formula
from evaluator.template_engine.template import validate_template


def evaluate(formula, cells=None):
    cells = cells or {}
    ast = parse_formula(formula)
    return evaluate_expression(ast, "Sheet 1", lambda sheet, cell: cells.get((sheet, cell)))


def test_restricted_formula_grammar_and_excel_functions():
    assert evaluate("=MAX(A1:A3)", {("Sheet 1", "A1"): 3, ("Sheet 1", "A2"): 9, ("Sheet 1", "A3"): None}) == 9
    assert evaluate("=MIN(A1,A2)", {("Sheet 1", "A1"): 3, ("Sheet 1", "A2"): 9}) == 3
    assert evaluate('=IF(AND(ISNUMBER(A1),A1>0),ROUND(A1,1),"bad")', {("Sheet 1", "A1"): 2.25}) == Decimal("2.3")
    assert evaluate('=IF(OR(FALSE,TRUE),ABS(-3),0)') == 3
    assert evaluate("=ROUNDUP(-2.51,1)") == Decimal("-2.6")
    assert evaluate("=ROUNDDOWN(-2.59,1)") == Decimal("-2.5")
    assert evaluate("=IFERROR(1/0,7)") == 7
    assert evaluate("=1+A1", {("Sheet 1", "A1"): None}) == Decimal("1")
    assert evaluate("=A1*2", {("Sheet 1", "A1"): "3"}) == Decimal("6")
    assert evaluate("=ISNUMBER(A1)", {("Sheet 1", "A1"): "3"}) is False


def test_formula_errors_and_unsupported_functions_are_visible():
    assert evaluate("=1/0") == ExcelError("#DIV/0!")
    assert evaluate("=A1+1", {("Sheet 1", "A1"): "-ve value"}) == ExcelError("#VALUE!")
    with pytest.raises(ValueError, match="Unsupported Excel function VLOOKUP"):
        parse_formula("=VLOOKUP(A1,B1:C2,2,FALSE)")


def _template(nodes, outputs):
    return {
        "schema_version": "1.0",
        "template_id": "test-template",
        "version": "1.0.0",
        "description": "Test template",
        "source_file": "fixture.xlsx",
        "source_sha256": "0" * 64,
        "sheets": ["Sheet 1"],
        "outputs": outputs,
        "nodes": nodes,
    }


def _node(node_id, cell, kind, expression=None, provenance_required=None):
    result = {
        "id": node_id,
        "label": node_id,
        "kind": kind,
        "unit": "mm",
        "source_cells": [{"sheet": "Sheet 1", "cell": cell}],
        "code_reference": {"code": None, "edition": None, "clause": None, "status": "unmapped", "reason": "test"},
        "provenance_required": provenance_required or [],
    }
    if expression is not None:
        result["expression"] = expression
    return result


def test_template_requires_provenance_and_evaluates_graph_with_trace():
    source = _node("cell|Sheet 1|A1", "A1", "input", provenance_required=["sheet"])
    output = _node("cell|Sheet 1|B1", "B1", "output", "=A1*2")
    template = validate_template(_template([source, output], [output["id"]]))
    with pytest.raises(MissingInputError, match="Missing required input"):
        evaluate_template(template, {})
    with pytest.raises(MissingInputError, match="no provenance"):
        evaluate_template(template, {source["id"]: InputValue(3, "mm", None)})
    result = evaluate_template(template, {
        source["id"]: InputValue(Decimal("3"), "mm", {"source_type": "sheet", "sheet": "Sheet 1", "cell": "A1"})
    })
    assert result.outputs[output["id"]] == Decimal("6")
    assert len(result.trace) == 1
    assert result.trace[0].inputs[0]["provenance"]["cell"] == "A1"


def test_template_detects_cycles_and_rejects_invalid_nodes():
    node = _node("cell|Sheet 1|A1", "A1", "output", "=A1")
    template = validate_template(_template([node], [node["id"]]))
    with pytest.raises(DependencyError, match="cycle"):
        evaluate_template(template, {})
    with pytest.raises(ValueError, match="Unsupported Excel function"):
        validate_template(_template([_node("cell|Sheet 1|A1", "A1", "output", "=VLOOKUP(A1,A1,1,FALSE)")], ["cell|Sheet 1|A1"]))
