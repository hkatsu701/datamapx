"""Schema type conversion helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd

from datamapx.config import SchemaFieldConfig

DEFAULT_TRUE_VALUES = {"true", "1", "yes", "y", "Y", "TRUE", "True"}
DEFAULT_FALSE_VALUES = {"false", "0", "no", "n", "N", "FALSE", "False"}


def convert_series_type(
    series: pd.Series,
    field_name: str,
    field_config: SchemaFieldConfig,
) -> pd.Series:
    """Convert a normalized series according to schema field type."""

    if field_config.type == "string":
        return series.map(_to_string_or_na)
    if field_config.type == "integer":
        return _to_integer(series, field_name)
    if field_config.type == "decimal":
        return _to_decimal(series, field_name)
    if field_config.type == "boolean":
        return _to_boolean(series, field_name, field_config)
    if field_config.type == "date":
        return _to_date(series, field_name, field_config)
    raise ValueError(f"{field_name}: unsupported type '{field_config.type}'")


def _is_missing(value: Any) -> bool:
    return bool(pd.isna(value))


def _to_string_or_na(value: Any) -> Any:
    if _is_missing(value):
        return pd.NA
    return str(value)


def _non_missing_mask(series: pd.Series) -> pd.Series:
    return ~series.isna()


def _to_integer(series: pd.Series, field_name: str) -> pd.Series:
    converted = pd.to_numeric(series, errors="coerce")
    invalid = _non_missing_mask(series) & converted.isna()
    if invalid.any():
        examples = _invalid_examples(series, invalid)
        raise ValueError(f"{field_name}: integer conversion failed for values: {examples}")
    return converted.astype("Int64")


def _to_decimal(series: pd.Series, field_name: str) -> pd.Series:
    converted = pd.to_numeric(series, errors="coerce")
    invalid = _non_missing_mask(series) & converted.isna()
    if invalid.any():
        examples = _invalid_examples(series, invalid)
        raise ValueError(f"{field_name}: decimal conversion failed for values: {examples}")
    return converted


def _to_boolean(series: pd.Series, field_name: str, field_config: SchemaFieldConfig) -> pd.Series:
    true_values = set(field_config.true_values or DEFAULT_TRUE_VALUES)
    false_values = set(field_config.false_values or DEFAULT_FALSE_VALUES)

    converted: list[Any] = []
    invalid_values: list[str] = []
    for value in series:
        if _is_missing(value):
            converted.append(pd.NA)
            continue
        text_value = str(value)
        if text_value in true_values:
            converted.append(True)
        elif text_value in false_values:
            converted.append(False)
        else:
            converted.append(pd.NA)
            invalid_values.append(text_value)

    if invalid_values:
        examples = ", ".join(repr(value) for value in invalid_values[:5])
        raise ValueError(f"{field_name}: boolean conversion failed for values: {examples}")
    return pd.Series(converted, index=series.index, dtype="boolean")


def _to_date(series: pd.Series, field_name: str, field_config: SchemaFieldConfig) -> pd.Series:
    normalized = series.map(_date_value_or_missing)
    parse_format = field_config.date_format or "mixed"
    converted = pd.to_datetime(normalized, errors="coerce", format=parse_format)
    invalid = _non_missing_mask(normalized) & converted.isna()
    if invalid.any():
        examples = _invalid_examples(series, invalid)
        raise ValueError(f"{field_name}: date conversion failed for values: {examples}")
    return converted


def _date_value_or_missing(value: Any) -> Any:
    if _is_missing(value):
        return pd.NA
    if isinstance(value, str) and value.strip() == "":
        return pd.NA
    return value


def _invalid_examples(series: pd.Series, invalid: pd.Series) -> str:
    return ", ".join(repr(value) for value in series[invalid].head(5).tolist())
