"""Normalize functions for schema fields."""

from __future__ import annotations

import unicodedata
from typing import Any

import pandas as pd

SUPPORTED_NORMALIZERS = {
    "trim",
    "remove_commas",
    "remove_currency_symbol",
    "zenkaku_to_hankaku",
}


def is_missing(value: Any) -> bool:
    """Return True for pandas missing values without treating normal strings as missing."""

    return bool(pd.isna(value))


def apply_normalizers(series: pd.Series, normalizers: list[str], field_name: str) -> pd.Series:
    """Apply configured normalizers in order."""

    normalized = series.copy()
    for normalizer in normalizers:
        if normalizer not in SUPPORTED_NORMALIZERS:
            raise ValueError(f"{field_name}: unsupported normalize function '{normalizer}'")
        if normalizer == "trim":
            normalized = normalized.map(_trim_value)
        elif normalizer == "zenkaku_to_hankaku":
            normalized = normalized.map(_zenkaku_to_hankaku)
        elif normalizer == "remove_commas":
            normalized = normalized.map(_remove_commas)
        elif normalizer == "remove_currency_symbol":
            normalized = normalized.map(_remove_currency_symbol)
    return normalized


def _trim_value(value: Any) -> Any:
    if is_missing(value):
        return value
    if isinstance(value, str):
        return value.strip()
    return value


def _remove_commas(value: Any) -> Any:
    if is_missing(value):
        return value
    if isinstance(value, str):
        return value.replace(",", "")
    return value


def _remove_currency_symbol(value: Any) -> Any:
    if is_missing(value):
        return value
    if isinstance(value, str):
        return value.replace("¥", "").replace("￥", "").replace("$", "")
    return value


def _zenkaku_to_hankaku(value: Any) -> Any:
    if is_missing(value):
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFKC", value)
    return value
