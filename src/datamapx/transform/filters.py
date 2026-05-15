"""Filter execution for Phase 1 dry-run pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from datamapx.config import DatamapxConfig
from datamapx.transform.conditions import evaluate_condition
from datamapx.transform.errors import MappingError

INCLUDE_MISS_REASON = "No include condition matched"
EXCLUDE_DEFAULT_REASON = "Excluded by filter"


@dataclass(frozen=True)
class SkippedRow:
    """A row skipped by filters."""

    row_number: Any
    reason: str
    normalized_row: dict[str, Any]


@dataclass(frozen=True)
class FilterResult:
    """Filtered input and skipped row metadata."""

    input_df: pd.DataFrame
    derived_values: dict[str, pd.Series]
    skipped_rows: list[SkippedRow]
    rows_before_filter: int
    rows_after_filter: int

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_rows)


def apply_filters(
    config: DatamapxConfig,
    input_df: pd.DataFrame,
    input_name: str,
    derived_values: dict[str, pd.Series],
) -> FilterResult:
    """Apply include then exclude filters."""

    include_rules = config.filters.include
    exclude_rules = config.filters.exclude
    if not isinstance(include_rules, list):
        raise MappingError("filters.include must be a list")
    if not isinstance(exclude_rules, list):
        raise MappingError("filters.exclude must be a list")

    skipped_rows: list[SkippedRow] = []
    kept_df = input_df
    kept_derived = derived_values

    if include_rules:
        include_mask = pd.Series([False] * len(input_df), index=input_df.index)
        for index, rule in enumerate(include_rules):
            condition = _filter_condition(rule, f"filters.include[{index}]")
            include_mask = include_mask | evaluate_condition(
                condition,
                input_df,
                input_name,
                derived_values,
            )
        skipped_rows.extend(
            _skipped_rows(input_df.loc[~include_mask], INCLUDE_MISS_REASON)
        )
        kept_df = input_df.loc[include_mask]
        kept_derived = _filter_derived_values(derived_values, kept_df.index)

    if exclude_rules and not kept_df.empty:
        excluded_mask = pd.Series([False] * len(kept_df), index=kept_df.index)
        exclude_reasons: dict[Any, str] = {}
        for index, rule in enumerate(exclude_rules):
            condition = _filter_condition(rule, f"filters.exclude[{index}]")
            reason = _filter_reason(rule) or EXCLUDE_DEFAULT_REASON
            condition_mask = evaluate_condition(condition, kept_df, input_name, kept_derived)
            apply_mask = condition_mask & ~excluded_mask
            for row_index in kept_df.loc[apply_mask].index:
                exclude_reasons[row_index] = reason
            excluded_mask = excluded_mask | apply_mask

        for row_index, reason in exclude_reasons.items():
            skipped_rows.append(_skipped_row(kept_df.loc[row_index], reason))
        kept_df = kept_df.loc[~excluded_mask]
        kept_derived = _filter_derived_values(kept_derived, kept_df.index)

    return FilterResult(
        input_df=kept_df,
        derived_values=kept_derived,
        skipped_rows=skipped_rows,
        rows_before_filter=len(input_df),
        rows_after_filter=len(kept_df),
    )


def _filter_condition(rule: Any, context: str) -> str:
    if isinstance(rule, dict):
        if "if" not in rule:
            raise MappingError(f"{context}: filter item is missing if")
        return rule["if"]
    if not hasattr(rule, "if_"):
        raise MappingError(f"{context}: filter item is missing if")
    return rule.if_


def _filter_reason(rule: Any) -> str | None:
    if isinstance(rule, dict):
        return rule.get("reason")
    return getattr(rule, "reason", None)


def _filter_derived_values(
    derived_values: dict[str, pd.Series],
    index: pd.Index,
) -> dict[str, pd.Series]:
    return {name: series.loc[index] for name, series in derived_values.items()}


def _skipped_rows(df: pd.DataFrame, reason: str) -> list[SkippedRow]:
    return [_skipped_row(row, reason) for _, row in df.iterrows()]


def _skipped_row(row: pd.Series, reason: str) -> SkippedRow:
    row_number = row["__row_number"] if "__row_number" in row else row.name
    return SkippedRow(
        row_number=row_number,
        reason=reason,
        normalized_row=row.to_dict(),
    )
