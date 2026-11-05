"""A small parser and Excel-compatible evaluator for the approved formula grammar."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, localcontext
from typing import Any, Callable, Iterable

from openpyxl.formula import Tokenizer
from openpyxl.utils.cell import range_boundaries
from openpyxl.utils import get_column_letter


class FormulaError(ValueError):
    """A formula cannot be parsed or uses syntax outside the template grammar."""


@dataclass(frozen=True)
class ExcelError:
    code: str


@dataclass(frozen=True)
class CellRef:
    sheet: str | None
    coordinate: str


@dataclass(frozen=True)
class CellRange:
    sheet: str | None
    start: str
    end: str


@dataclass(frozen=True)
class Unary:
    operator: str
    operand: Any


@dataclass(frozen=True)
class Binary:
    operator: str
    left: Any
    right: Any


@dataclass(frozen=True)
class Call:
    name: str
    arguments: tuple[Any, ...]


@dataclass(frozen=True)
class Literal:
    value: Any


Node = CellRef | CellRange | Unary | Binary | Call | Literal

REFERENCE = re.compile(
    r"^(?:(?:'(?P<quoted>(?:[^']|'')+)'|(?P<plain>[A-Za-z_][A-Za-z0-9_. ]*))!)?"
    r"(?P<first>\$?[A-Za-z]{1,3}\$?\d+)"
    r"(?::(?P<last>\$?[A-Za-z]{1,3}\$?\d+))?$"
)
ALLOWED_FUNCTIONS = {
    "MAX", "MIN", "IF", "AND", "OR", "ROUND", "ROUNDUP", "ROUNDDOWN",
    "ABS", "IFERROR", "ISNUMBER",
}
PRECEDENCE = {"=": 1, "<>": 1, "<": 1, ">": 1, "<=": 1, ">=": 1,
              "+": 2, "-": 2, "*": 3, "/": 3, "^": 4}


def parse_reference(value: str) -> CellRef | CellRange:
    match = REFERENCE.fullmatch(value.strip())
    if not match:
        raise FormulaError(f"Unsupported cell reference or name: {value!r}")
    quoted, plain = match.group("quoted"), match.group("plain")
    sheet = quoted.replace("''", "'") if quoted is not None else plain
    first = match.group("first").replace("$", "").upper()
    last = match.group("last")
    if last is None:
        return CellRef(sheet, first)
    return CellRange(sheet, first, last.replace("$", "").upper())


class _Parser:
    def __init__(self, formula: str):
        if not isinstance(formula, str) or not formula.startswith("="):
            raise FormulaError("Formula must start with '='")
        try:
            self.tokens = Tokenizer(formula).items
        except Exception as exc:
            raise FormulaError(f"Invalid formula: {exc}") from exc
        self.position = 0

    def _take(self):
        if self.position >= len(self.tokens):
            raise FormulaError("Unexpected end of formula")
        token = self.tokens[self.position]
        self.position += 1
        return token

    def _peek(self):
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def parse(self) -> Node:
        expression = self._expression(0)
        if self._peek() is not None:
            raise FormulaError(f"Unexpected token {self._peek().value!r}")
        return expression

    def _expression(self, minimum: int) -> Node:
        token = self._take()
        if token.type == "OPERAND":
            if token.subtype == "NUMBER":
                left: Node = Literal(Decimal(token.value))
            elif token.subtype == "TEXT":
                left = Literal(token.value[1:-1].replace('""', '"'))
            elif token.subtype == "LOGICAL":
                left = Literal(token.value.upper() == "TRUE")
            elif token.subtype == "RANGE":
                left = parse_reference(token.value)
            else:
                raise FormulaError(f"Unsupported operand {token.value!r}")
        elif token.type == "OPERATOR-PREFIX" and token.value in {"+", "-"}:
            left = Unary(token.value, self._expression(5))
        elif token.type == "PAREN" and token.subtype == "OPEN":
            left = self._expression(0)
            close = self._take()
            if close.type != "PAREN" or close.subtype != "CLOSE":
                raise FormulaError("Expected closing parenthesis")
        elif token.type == "FUNC" and token.subtype == "OPEN":
            name = token.value[:-1].upper()
            if name not in ALLOWED_FUNCTIONS:
                raise FormulaError(f"Unsupported Excel function {name}")
            arguments: list[Node] = []
            if self._peek() is not None and not (
                self._peek().type == "FUNC" and self._peek().subtype == "CLOSE"
            ):
                while True:
                    arguments.append(self._expression(0))
                    separator = self._peek()
                    if separator is None or separator.type != "SEP":
                        break
                    self.position += 1
            close = self._take()
            if close.type != "FUNC" or close.subtype != "CLOSE":
                raise FormulaError(f"Expected closing parenthesis for {name}")
            left = Call(name, tuple(arguments))
        else:
            raise FormulaError(f"Unsupported token {token.type}/{token.subtype}: {token.value!r}")

        while True:
            next_token = self._peek()
            if next_token is None or next_token.type != "OPERATOR-INFIX":
                break
            operator = next_token.value.upper()
            precedence = PRECEDENCE.get(operator)
            if precedence is None:
                raise FormulaError(f"Unsupported operator {operator!r}")
            if precedence < minimum:
                break
            self.position += 1
            right = self._expression(precedence + (0 if operator == "^" else 1))
            left = Binary(operator, left, right)
        return left


def parse_formula(formula: str) -> Node:
    """Parse an Excel formula, rejecting unsupported functions and syntax."""
    return _Parser(formula).parse()


def expand_range(reference: CellRange, default_sheet: str) -> tuple[CellRef, ...]:
    min_col, min_row, max_col, max_row = range_boundaries(
        f"{reference.start}:{reference.end}"
    )
    if (max_col - min_col + 1) * (max_row - min_row + 1) > 100_000:
        raise FormulaError("Range exceeds the 100,000-cell safety limit")
    sheet = reference.sheet or default_sheet
    return tuple(
        CellRef(sheet, f"{get_column_letter(col)}{row}")
        for row in range(min_row, max_row + 1)
        for col in range(min_col, max_col + 1)
    )


def references(node: Node, default_sheet: str) -> tuple[CellRef, ...]:
    """Return every cell dependency in an expression, including expanded ranges."""
    found: list[CellRef] = []

    def visit(current: Node) -> None:
        if isinstance(current, CellRef):
            found.append(CellRef(current.sheet or default_sheet, current.coordinate))
        elif isinstance(current, CellRange):
            found.extend(expand_range(current, default_sheet))
        elif isinstance(current, Unary):
            visit(current.operand)
        elif isinstance(current, Binary):
            visit(current.left)
            visit(current.right)
        elif isinstance(current, Call):
            for argument in current.arguments:
                visit(argument)

    visit(node)
    return tuple(dict.fromkeys(found))


def _excel_error(value: Any) -> ExcelError | None:
    if isinstance(value, ExcelError):
        return value
    if isinstance(value, str) and value.startswith("#"):
        return ExcelError(value)
    return None


def _number(value: Any) -> Decimal | ExcelError:
    if isinstance(value, ExcelError):
        return value
    if value is None:
        return Decimal(0)
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return Decimal(0)
        try:
            return Decimal(text)
        except InvalidOperation:
            return ExcelError("#VALUE!")
    return ExcelError("#VALUE!")


def _truth(value: Any) -> bool | ExcelError:
    if isinstance(value, ExcelError):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, (Decimal, int, float)):
        return value != 0
    if value is None:
        return False
    return ExcelError("#VALUE!")


def _flatten(values: Iterable[Any]) -> list[Any]:
    flattened: list[Any] = []
    for value in values:
        if isinstance(value, list):
            flattened.extend(_flatten(value))
        else:
            flattened.append(value)
    return flattened


def _round(value: Any, places: Any, mode: str) -> Decimal | ExcelError:
    number, digits = _number(value), _number(places)
    if isinstance(number, ExcelError):
        return number
    if isinstance(digits, ExcelError):
        return digits
    try:
        exponent = Decimal(1).scaleb(-int(digits))
        rounding = {"ROUND": ROUND_HALF_UP, "ROUNDUP": ROUND_UP, "ROUNDDOWN": ROUND_DOWN}[mode]
        return number.quantize(exponent, rounding=rounding)
    except (ValueError, OverflowError, ArithmeticError):
        return ExcelError("#NUM!")


def evaluate_expression(
    node: Node,
    current_sheet: str,
    resolve: Callable[[str, str], Any],
) -> Any:
    """Evaluate an AST using Excel-style blank, arithmetic, and error behavior."""

    def value(current: Node) -> Any:
        if isinstance(current, Literal):
            return current.value
        if isinstance(current, CellRef):
            return resolve(current.sheet or current_sheet, current.coordinate)
        if isinstance(current, CellRange):
            return [resolve(ref.sheet or current_sheet, ref.coordinate)
                    for ref in expand_range(current, current_sheet)]
        if isinstance(current, Unary):
            operand = _number(value(current.operand))
            if isinstance(operand, ExcelError):
                return operand
            return operand if current.operator == "+" else -operand
        if isinstance(current, Binary):
            left, right = value(current.left), value(current.right)
            left_error, right_error = _excel_error(left), _excel_error(right)
            if left_error:
                return left_error
            if right_error:
                return right_error
            if current.operator in {"=", "<>", "<", ">", "<=", ">="}:
                a, b = left, right
                if isinstance(a, (int, float)) and not isinstance(a, bool):
                    a = Decimal(str(a))
                if isinstance(b, (int, float)) and not isinstance(b, bool):
                    b = Decimal(str(b))
                try:
                    return {"=": lambda: a == b, "<>": lambda: a != b,
                            "<": lambda: a < b, ">": lambda: a > b,
                            "<=": lambda: a <= b, ">=": lambda: a >= b}[current.operator]()
                except TypeError:
                    return ExcelError("#VALUE!")
            a, b = _number(left), _number(right)
            if isinstance(a, ExcelError):
                return a
            if isinstance(b, ExcelError):
                return b
            try:
                with localcontext() as context:
                    context.prec = 50
                    if current.operator == "+":
                        return a + b
                    if current.operator == "-":
                        return a - b
                    if current.operator == "*":
                        return a * b
                    if current.operator == "/":
                        return ExcelError("#DIV/0!") if b == 0 else a / b
                    if current.operator == "^":
                        return a ** int(b)
            except (ArithmeticError, ValueError):
                return ExcelError("#NUM!")
            return ExcelError("#VALUE!")
        if isinstance(current, Call):
            name = current.name
            if name == "IF":
                if len(current.arguments) not in {2, 3}:
                    return ExcelError("#VALUE!")
                condition = _truth(value(current.arguments[0]))
                if isinstance(condition, ExcelError):
                    return condition
                if condition:
                    return value(current.arguments[1])
                return value(current.arguments[2]) if len(current.arguments) == 3 else False
            if name == "IFERROR":
                if len(current.arguments) != 2:
                    return ExcelError("#VALUE!")
                result = value(current.arguments[0])
                return value(current.arguments[1]) if _excel_error(result) else result
            args = [value(argument) for argument in current.arguments]
            flat = _flatten(args)
            if name in {"AND", "OR"}:
                booleans = [_truth(item) for item in flat]
                error = next((item for item in booleans if isinstance(item, ExcelError)), None)
                if error:
                    return error
                return all(booleans) if name == "AND" else any(booleans)
            if name == "ISNUMBER":
                if len(args) != 1:
                    return ExcelError("#VALUE!")
                item = args[0]
                return isinstance(item, (Decimal, int, float)) and not isinstance(item, bool)
            if name == "ABS":
                if len(args) != 1:
                    return ExcelError("#VALUE!")
                number = _number(args[0])
                return number if isinstance(number, ExcelError) else abs(number)
            if name in {"ROUND", "ROUNDUP", "ROUNDDOWN"}:
                if len(args) != 2:
                    return ExcelError("#VALUE!")
                return _round(args[0], args[1], name)
            if name in {"MIN", "MAX"}:
                values: list[Decimal] = []
                for item in flat:
                    error = _excel_error(item)
                    if error:
                        return error
                    # Excel ignores text and empty cells passed by reference.
                    if item is None or isinstance(item, str) or isinstance(item, bool):
                        continue
                    number = _number(item)
                    if isinstance(number, ExcelError):
                        return number
                    values.append(number)
                if not values:
                    return Decimal(0)
                return min(values) if name == "MIN" else max(values)
            return ExcelError("#NAME?")
        raise FormulaError(f"Unknown expression node: {type(current).__name__}")

    return value(node)
