"""Row-wise execution helper for datamapx mapping pipelines."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from datamapx.config import DatamapxConfig
from datamapx.transform.error_policy import (
    StopInfo,
    classify_mapping_error,
    evaluate_max_errors,
    mapping_error_policy,
)
from datamapx.transform.errors import MappingError
from datamapx.transform.filters import SkippedRow, apply_filters
from datamapx.transform.mapper import build_output_dataframe, compute_derived_fields
from datamapx.validation.errors import ValidationErrorRow


@dataclass(frozen=True)
class RowwiseOutputResult:
    """Row-wise output construction result."""

    output_df: pd.DataFrame
    output_row_numbers: pd.Series
    skipped_rows: list[SkippedRow]
    mapping_error_rows: list[ValidationErrorRow]
    input_rows_before_filter: int
    input_rows_after_filter: int
    stop_info: StopInfo | None


def build_rowwise_output(
    *,
    config: DatamapxConfig,
    input_df: pd.DataFrame,
    input_name: str,
    output_columns: list[str],
    reference_dfs: dict[str, pd.DataFrame],
    base_error_count: int,
) -> RowwiseOutputResult:
    """Execute derived, filter, and mapping steps row by row."""

    output_rows: list[dict[str, object]] = []
    output_row_numbers: list[object] = []
    skipped_rows: list[SkippedRow] = []
    mapping_error_rows: list[ValidationErrorRow] = []
    rows_after_filter = 0

    for index, row in input_df.iterrows():
        row_df = input_df.loc[[index]]
        row_number = _row_number(row)
        normalized_row = row.to_dict()
        try:
            derived_values = compute_derived_fields(config, row_df, reference_dfs)
            filter_result = apply_filters(
                config,
                row_df,
                input_name,
                derived_values,
            )
            skipped_rows.extend(filter_result.skipped_rows)
            if filter_result.input_df.empty:
                continue
            rows_after_filter += 1
            output_df = build_output_dataframe(
                config,
                filter_result.input_df,
                reference_dfs=reference_dfs,
                derived_values=filter_result.derived_values,
            )
            output_rows.append(output_df.iloc[0].to_dict())
            output_row_numbers.append(filter_result.input_df.iloc[0]["__row_number"])
        except MappingError as exc:
            stop_info = classify_mapping_error(exc)
            mapping_error_rows.append(
                ValidationErrorRow(
                    row_number=row_number,
                    stage="mapping",
                    field=_mapping_error_field(str(exc)),
                    rule=stop_info.reason,
                    message=str(exc),
                    normalized_row=normalized_row,
                )
            )
            if mapping_error_policy(config.error_handling, stop_info) == "stop":
                return RowwiseOutputResult(
                    output_df=pd.DataFrame(output_rows, columns=output_columns),
                    output_row_numbers=pd.Series(output_row_numbers),
                    skipped_rows=skipped_rows,
                    mapping_error_rows=mapping_error_rows,
                    input_rows_before_filter=len(input_df),
                    input_rows_after_filter=rows_after_filter,
                    stop_info=stop_info,
                )
            max_errors_stop = evaluate_max_errors(
                config.error_handling,
                base_error_count + len(mapping_error_rows),
            )
            if max_errors_stop is not None:
                return RowwiseOutputResult(
                    output_df=pd.DataFrame(output_rows, columns=output_columns),
                    output_row_numbers=pd.Series(output_row_numbers),
                    skipped_rows=skipped_rows,
                    mapping_error_rows=mapping_error_rows,
                    input_rows_before_filter=len(input_df),
                    input_rows_after_filter=rows_after_filter,
                    stop_info=max_errors_stop,
                )

    return RowwiseOutputResult(
        output_df=pd.DataFrame(output_rows, columns=output_columns),
        output_row_numbers=pd.Series(output_row_numbers),
        skipped_rows=skipped_rows,
        mapping_error_rows=mapping_error_rows,
        input_rows_before_filter=len(input_df),
        input_rows_after_filter=rows_after_filter,
        stop_info=None,
    )


def _mapping_error_field(message: str) -> str:
    if ":" not in message:
        return "mapping"
    field, _, _ = message.partition(":")
    return field.strip() or "mapping"


def _row_number(row: pd.Series) -> object:
    if "__row_number" in row:
        return row["__row_number"]
    return row.name
