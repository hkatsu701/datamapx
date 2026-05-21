"""Safe arithmetic expression evaluator for expression mappings."""

from __future__ import annotations

import ast
import operator
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from datamapx.transform.errors import MappingError

FIELD_REFERENCE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")

ALLOWED_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "round": round,
    "abs": abs,
    "min": min,
    "max": max,
}

BIN_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

UNARY_OPS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


@dataclass(frozen=True)
class CompiledExpression:
    """A parsed expression with field references replaced by safe names."""

    expression: str
    rewritten_expression: str
    references: dict[str, str]
    tree: ast.Expression


def extract_expression_references(expression: str) -> list[str]:
    """Return dotted field references found in an expression."""

    return list(dict.fromkeys(match.group(0) for match in FIELD_REFERENCE_RE.finditer(expression)))


def compile_safe_expression(
    expression: str,
    input_name: str,
    fields: set[str],
    derived_fields: set[str] | None = None,
) -> CompiledExpression:
    """Compile a safe arithmetic expression without executing it."""

    if not isinstance(expression, str):
        raise MappingError("expression: expression must be a string")

    derived_fields = derived_fields or set()
    references = extract_expression_references(expression)
    safe_names: dict[str, str] = {}
    for index, reference in enumerate(references):
        namespace, field_name = reference.split(".", 1)
        if namespace == "derived":
            if field_name not in derived_fields:
                raise MappingError(f"expression: derived field is not defined: {reference}")
        elif namespace == input_name:
            if field_name not in fields:
                raise MappingError(f"expression: field is not defined: {reference}")
        else:
            raise MappingError(f"expression: unknown input namespace: {reference}")
        safe_names[reference] = f"__dmx_field_{index}"

    rewritten = FIELD_REFERENCE_RE.sub(lambda match: safe_names[match.group(0)], expression)
    try:
        tree = ast.parse(rewritten, mode="eval")
    except SyntaxError as exc:
        raise MappingError(f"expression: invalid syntax: {expression}") from exc

    _validate_ast(tree)
    return CompiledExpression(
        expression=expression,
        rewritten_expression=rewritten,
        references=safe_names,
        tree=tree,
    )


def evaluate_expression_series(
    expression: str,
    input_df: pd.DataFrame,
    input_name: str,
    output_column: str,
    derived_values: dict[str, pd.Series] | None = None,
) -> pd.Series:
    """Evaluate an expression for each input row."""

    derived_values = derived_values or {}
    compiled = compile_safe_expression(
        expression,
        input_name,
        set(input_df.columns),
        set(derived_values),
    )
    _validate_no_missing_values(compiled, input_df, output_column, derived_values)

    values: list[Any] = []
    for row_index, row in input_df.iterrows():
        names = {
            safe_name: _reference_value(reference, row, row_index, derived_values)
            for reference, safe_name in compiled.references.items()
        }
        try:
            values.append(_eval_node(compiled.tree.body, names))
        except Exception as exc:
            if isinstance(exc, MappingError):
                raise
            row_label = _row_label(row, row_index)
            formatted_values = ", ".join(
                f"{reference}={_format_value(names[safe_name])}"
                for reference, safe_name in compiled.references.items()
            )
            raise MappingError(
                f"{output_column}: expression evaluation failed at row {row_label}: "
                f"{compiled.expression}; values: {formatted_values}; "
                f"cause: {type(exc).__name__}: {exc}"
            ) from exc
    return pd.Series(values, index=input_df.index)


def _validate_ast(tree: ast.Expression) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Expression | ast.Load | ast.Constant | ast.Name):
            continue
        if isinstance(node, ast.BinOp):
            if type(node.op) not in BIN_OPS:
                raise MappingError("expression: unsupported operator")
            continue
        if isinstance(node, ast.UnaryOp):
            if type(node.op) not in UNARY_OPS:
                raise MappingError("expression: unsupported operator")
            continue
        if isinstance(node, ast.Call):
            _validate_call(node)
            continue
        if isinstance(node, tuple(BIN_OPS) + tuple(UNARY_OPS)):
            continue
        raise MappingError(f"expression: unsupported syntax: {type(node).__name__}")


def _validate_call(node: ast.Call) -> None:
    if not isinstance(node.func, ast.Name):
        raise MappingError("expression: unsupported function call")
    if node.func.id not in ALLOWED_FUNCTIONS:
        raise MappingError(f"expression: function is not allowed: {node.func.id}")
    if node.keywords:
        raise MappingError("expression: keyword arguments are not supported")


def _validate_no_missing_values(
    compiled: CompiledExpression,
    input_df: pd.DataFrame,
    output_column: str,
    derived_values: dict[str, pd.Series],
) -> None:
    for reference in compiled.references:
        series = _reference_series(reference, input_df, derived_values)
        missing = series.isna()
        if missing.any():
            row_label = _first_row_label(input_df, missing)
            raise MappingError(
                f"{output_column}: expression field has missing value: "
                f"{reference} at row {row_label}"
            )


def _reference_series(
    reference: str,
    input_df: pd.DataFrame,
    derived_values: dict[str, pd.Series],
) -> pd.Series:
    namespace, field_name = reference.split(".", 1)
    if namespace == "derived":
        return derived_values[field_name]
    return input_df[field_name]


def _reference_value(
    reference: str,
    row: pd.Series,
    row_index: Any,
    derived_values: dict[str, pd.Series],
) -> Any:
    namespace, field_name = reference.split(".", 1)
    if namespace == "derived":
        return derived_values[field_name].loc[row_index]
    return row[field_name]


def _first_row_label(input_df: pd.DataFrame, missing: pd.Series) -> Any:
    first_index = missing[missing].index[0]
    if "__row_number" in input_df.columns:
        return input_df.loc[first_index, "__row_number"]
    return first_index


def _row_label(row: pd.Series, row_index: Any) -> Any:
    if "__row_number" in row.index:
        return row["__row_number"]
    return row_index


def _format_value(value: Any) -> str:
    if pd.isna(value):
        return f"<missing> ({type(value).__name__})"
    return f"{value!r} ({type(value).__name__})"


def _eval_node(node: ast.AST, names: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, int | float | bool) or node.value is None:
            return node.value
        raise MappingError("expression: unsupported literal")
    if isinstance(node, ast.Name):
        if node.id not in names:
            raise MappingError(f"expression: unknown name: {node.id}")
        return names[node.id]
    if isinstance(node, ast.BinOp):
        op = BIN_OPS.get(type(node.op))
        if op is None:
            raise MappingError("expression: unsupported operator")
        return op(_eval_node(node.left, names), _eval_node(node.right, names))
    if isinstance(node, ast.UnaryOp):
        op = UNARY_OPS.get(type(node.op))
        if op is None:
            raise MappingError("expression: unsupported operator")
        return op(_eval_node(node.operand, names))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCTIONS:
            raise MappingError("expression: function is not allowed")
        args = [_eval_node(argument, names) for argument in node.args]
        return ALLOWED_FUNCTIONS[node.func.id](*args)
    raise MappingError(f"expression: unsupported syntax: {type(node).__name__}")
