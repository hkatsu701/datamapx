"""Limited condition evaluator for when mappings."""

from __future__ import annotations

import ast
import operator
import tokenize
from functools import reduce
from io import StringIO
from typing import Any

import pandas as pd

from datamapx.transform.errors import MappingError

ALLOWED_BOOL_OPS: tuple[type[ast.boolop], ...] = (ast.And, ast.Or)
ALLOWED_COMPARE_OP_TYPES: tuple[type[ast.cmpop], ...] = (
    ast.Eq,
    ast.NotEq,
    ast.Gt,
    ast.GtE,
    ast.Lt,
    ast.LtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
)
ALLOWED_OPERATOR_NODES: tuple[type[ast.AST], ...] = ALLOWED_BOOL_OPS + ALLOWED_COMPARE_OP_TYPES


def evaluate_condition(
    condition: str,
    input_df: pd.DataFrame,
    input_name: str,
    derived_values: dict[str, pd.Series] | None = None,
) -> pd.Series:
    """Evaluate one supported when condition against the input dataframe."""

    derived_values = derived_values or {}
    if "(" in condition or ")" in condition:
        raise MappingError(f"Unsupported condition expression: {condition}")
    try:
        tree = ast.parse(_rewrite_condition_literals(condition), mode="eval")
    except SyntaxError as exc:
        raise MappingError(f"Unsupported condition expression: {condition}") from exc

    _validate_condition_tree(tree, condition)
    try:
        result = _evaluate_node(tree.body, input_df, input_name, derived_values, condition)
    except TypeError as exc:
        raise MappingError(f"Unsupported condition expression: {condition}") from exc
    return _as_boolean_series(result, input_df)


def _rewrite_condition_literals(condition: str) -> str:
    tokens: list[tokenize.TokenInfo] = []
    for token in tokenize.generate_tokens(StringIO(condition).readline):
        if token.type == tokenize.NAME and token.string in {"true", "false", "null"}:
            replacement = {
                "true": "True",
                "false": "False",
                "null": "None",
            }[token.string]
            token = token._replace(string=replacement)
        tokens.append(token)
    return tokenize.untokenize(tokens)


def _validate_condition_tree(tree: ast.Expression, condition: str) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Expression | ast.Load | ast.Constant):
            continue
        if isinstance(node, ast.BoolOp):
            if not isinstance(node.op, ALLOWED_BOOL_OPS):
                raise MappingError(f"Unsupported condition expression: {condition}")
            continue
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1 or len(node.comparators) != 1:
                raise MappingError(f"Unsupported condition expression: {condition}")
            if not isinstance(node.ops[0], ALLOWED_COMPARE_OP_TYPES):
                raise MappingError(f"Unsupported condition expression: {condition}")
            continue
        if isinstance(node, ALLOWED_OPERATOR_NODES):
            continue
        if isinstance(node, ast.Attribute):
            if not isinstance(node.value, ast.Name):
                raise MappingError(f"Unsupported condition expression: {condition}")
            continue
        if isinstance(node, ast.Name):
            continue
        if isinstance(node, ast.List | ast.Tuple):
            continue
        raise MappingError(f"Unsupported condition expression: {condition}")


def _evaluate_node(
    node: ast.AST,
    input_df: pd.DataFrame,
    input_name: str,
    derived_values: dict[str, pd.Series],
    condition: str,
) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Attribute):
        reference = _attribute_reference(node, condition)
        series = _reference_series(reference, input_df, input_name, derived_values, "when.if")
        if series is None:
            raise MappingError(f"when.if: field is not defined: {reference}")
        return series
    if isinstance(node, ast.Name):
        raise MappingError(f"Unsupported condition expression: {condition}")
    if isinstance(node, ast.BoolOp):
        values = [
            _evaluate_node(value, input_df, input_name, derived_values, condition)
            for value in node.values
        ]
        if isinstance(node.op, ast.And):
            return reduce(operator.and_, (_as_boolean_series(value, input_df) for value in values))
        if isinstance(node.op, ast.Or):
            return reduce(operator.or_, (_as_boolean_series(value, input_df) for value in values))
        raise MappingError(f"Unsupported condition expression: {condition}")
    if isinstance(node, ast.Compare):
        left = _evaluate_node(node.left, input_df, input_name, derived_values, condition)
        right = _evaluate_node(
            node.comparators[0],
            input_df,
            input_name,
            derived_values,
            condition,
        )
        return _evaluate_compare(left, right, node.ops[0], input_df, condition)
    if isinstance(node, ast.List):
        return [
            _evaluate_node(item, input_df, input_name, derived_values, condition)
            for item in node.elts
        ]
    if isinstance(node, ast.Tuple):
        return [
            _evaluate_node(item, input_df, input_name, derived_values, condition)
            for item in node.elts
        ]
    raise MappingError(f"Unsupported condition expression: {condition}")


def _evaluate_compare(
    left: Any,
    right: Any,
    operator_node: ast.cmpop,
    input_df: pd.DataFrame,
    condition: str,
) -> pd.Series | bool:
    if isinstance(operator_node, ast.Is):
        if right is not None:
            raise MappingError(f"Unsupported condition expression: {condition}")
        return _as_series(left, input_df).isna() if isinstance(left, pd.Series) else left is None
    if isinstance(operator_node, ast.IsNot):
        if right is not None:
            raise MappingError(f"Unsupported condition expression: {condition}")
        if isinstance(left, pd.Series):
            return _as_series(left, input_df).notna()
        return left is not None

    if isinstance(operator_node, ast.In):
        if not isinstance(right, list):
            raise MappingError(f"Unsupported condition expression: {condition}")
        return _compare_in(left, right, input_df, condition, negate=False)
    if isinstance(operator_node, ast.NotIn):
        if not isinstance(right, list):
            raise MappingError(f"Unsupported condition expression: {condition}")
        return _compare_in(left, right, input_df, condition, negate=True)

    left_is_series = isinstance(left, pd.Series)
    right_is_series = isinstance(right, pd.Series)
    if left_is_series and right_is_series:
        raise MappingError(f"Unsupported condition expression: {condition}")

    try:
        if isinstance(operator_node, ast.Eq):
            if right is None:
                if isinstance(left, pd.Series):
                    return _as_series(left, input_df).isna()
                return left is None
            result = left == right
        elif isinstance(operator_node, ast.NotEq):
            if right is None:
                if isinstance(left, pd.Series):
                    return _as_series(left, input_df).notna()
                return left is not None
            result = left != right
        elif isinstance(operator_node, ast.Gt):
            result = left > right
        elif isinstance(operator_node, ast.GtE):
            result = left >= right
        elif isinstance(operator_node, ast.Lt):
            result = left < right
        elif isinstance(operator_node, ast.LtE):
            result = left <= right
        else:
            raise MappingError(f"Unsupported condition expression: {condition}")
    except TypeError as exc:
        raise MappingError(f"Unsupported condition expression: {condition}") from exc
    return result


def _compare_in(
    left: Any,
    right: list[Any],
    input_df: pd.DataFrame,
    condition: str,
    negate: bool,
) -> pd.Series | bool:
    if isinstance(left, pd.Series):
        result = left.isin(right)
        if negate:
            result = ~result & left.notna()
        return result
    result = left in right
    return not result if negate else result


def _attribute_reference(node: ast.Attribute, condition: str) -> str:
    if not isinstance(node.value, ast.Name):
        raise MappingError(f"Unsupported condition expression: {condition}")
    return f"{node.value.id}.{node.attr}"


def _as_series(value: Any, input_df: pd.DataFrame) -> pd.Series:
    if isinstance(value, pd.Series):
        return value
    return pd.Series([value] * len(input_df), index=input_df.index)


def _as_boolean_series(value: Any, input_df: pd.DataFrame) -> pd.Series:
    if isinstance(value, pd.Series):
        return value.apply(lambda item: bool(item) if pd.notna(item) else False)
    if isinstance(value, bool):
        return pd.Series([value] * len(input_df), index=input_df.index)
    if value is None:
        return pd.Series([False] * len(input_df), index=input_df.index)
    if isinstance(value, (int, float, str)):
        return pd.Series([bool(value)] * len(input_df), index=input_df.index)
    raise MappingError("Unsupported condition expression")


def _reference_series(
    reference: str,
    input_df: pd.DataFrame,
    input_name: str,
    derived_values: dict[str, pd.Series],
    context: str,
) -> pd.Series | None:
    namespace, field_name = reference.split(".", 1)
    if namespace == "derived":
        return derived_values.get(field_name)
    if namespace != input_name:
        raise MappingError(f"{context}: unknown input namespace in condition: {reference}")
    if field_name not in input_df.columns:
        return None
    return input_df[field_name]
