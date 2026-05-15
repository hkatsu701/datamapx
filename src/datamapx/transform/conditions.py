"""Limited condition evaluator for when mappings."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from datamapx.transform.errors import MappingError

CONDITION_RE = re.compile(
    r"^\s*(?P<field>[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\s*"
    r"(?P<operator>not\s+in|in|==|!=|>=|<=|>|<)\s*"
    r"(?P<literal>.+?)\s*$"
)


def evaluate_condition(
    condition: str,
    input_df: pd.DataFrame,
    input_name: str,
    derived_values: dict[str, pd.Series] | None = None,
) -> pd.Series:
    """Evaluate one supported when condition against the input dataframe."""

    derived_values = derived_values or {}
    match = CONDITION_RE.match(condition)
    if not match:
        raise MappingError(f"Unsupported condition expression: {condition}")

    field_ref = match.group("field")
    operator = match.group("operator")
    literal = _parse_literal(match.group("literal"))
    series = _reference_series(field_ref, input_df, input_name, derived_values, "when.if")
    if series is None:
        raise MappingError(f"when.if: field is not defined: {field_ref}")
    if operator == "in":
        if not isinstance(literal, list):
            raise MappingError(f"Unsupported condition expression: {condition}")
        return series.isin(literal).fillna(False)
    if operator == "not in":
        if not isinstance(literal, list):
            raise MappingError(f"Unsupported condition expression: {condition}")
        return (~series.isin(literal) & series.notna()).fillna(False)

    if literal is None:
        return _compare_null(series, operator, condition)

    non_missing = series.notna()
    try:
        if operator == "==":
            result = series == literal
        elif operator == "!=":
            result = series != literal
        elif operator == ">":
            result = series > literal
        elif operator == ">=":
            result = series >= literal
        elif operator == "<":
            result = series < literal
        elif operator == "<=":
            result = series <= literal
        else:
            raise MappingError(f"Unsupported condition expression: {condition}")
    except TypeError as exc:
        raise MappingError(f"Unsupported condition expression: {condition}") from exc
    return (result & non_missing).fillna(False)


def _compare_null(series: pd.Series, operator: str, condition: str) -> pd.Series:
    if operator == "==":
        return series.isna()
    if operator == "!=":
        return series.notna()
    raise MappingError(f"Unsupported condition expression: {condition}")


def _parse_literal(text: str) -> Any:
    value = text.strip()
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "null":
        return None
    if _is_quoted(value):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        return _parse_list(value)
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        raise MappingError(f"Unsupported literal in condition: {text}") from None


def _parse_list(value: str) -> list[Any]:
    inner = value[1:-1].strip()
    if not inner:
        return []
    parts = [part.strip() for part in inner.split(",")]
    return [_parse_literal(part) for part in parts]


def _is_quoted(value: str) -> bool:
    return len(value) >= 2 and (
        (value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")
    )


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
