"""Row-wise execution helper for datamapx mapping pipelines."""

from __future__ import annotations

from collections.abc import Callable
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
from datamapx.transform.mapper import (
    MappingExecutionContext,
    build_output_dataframe,
    compute_derived_fields,
)
from datamapx.validation.errors import ValidationErrorRow


@dataclass(frozen=True)
class PreparedRow:
    """A single filtered row with precomputed derived values."""

    input_df: pd.DataFrame
    derived_values: dict[str, pd.Series]


@dataclass(frozen=True)
class RowPreparationResult:
    """Shared row preparation result before output-specific mapping."""

    prepared_rows: list[PreparedRow]
    skipped_rows: list[SkippedRow]
    mapping_error_rows: list[ValidationErrorRow]
    input_rows_before_filter: int
    input_rows_after_filter: int
    stop_info: StopInfo | None


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


RowProgressCallback = Callable[[int, int], None]


def prepare_rowwise_inputs(
    *,
    config: DatamapxConfig,
    input_df: pd.DataFrame,
    input_name: str,
    reference_dfs: dict[str, pd.DataFrame],
    base_error_count: int,
    execution_context: MappingExecutionContext | None = None,
    progress_callback: RowProgressCallback | None = None,
) -> RowPreparationResult:
    """Compute derived values and filters, falling back to row isolation on errors."""

    execution_context = execution_context or MappingExecutionContext()
    prepared_rows: list[PreparedRow] = []
    skipped_rows: list[SkippedRow] = []
    mapping_error_rows: list[ValidationErrorRow] = []
    rows_after_filter = 0
    total_rows = len(input_df)

    try:
        derived_values = compute_derived_fields(
            config,
            input_df,
            reference_dfs,
            execution_context,
        )
        filter_result = apply_filters(
            config,
            input_df,
            input_name,
            derived_values,
        )
    except MappingError:
        pass
    else:
        if not filter_result.input_df.empty:
            prepared_rows.append(
                PreparedRow(
                    input_df=filter_result.input_df,
                    derived_values=filter_result.derived_values,
                )
            )
        if progress_callback is not None:
            progress_callback(total_rows, total_rows)
        return RowPreparationResult(
            prepared_rows=prepared_rows,
            skipped_rows=filter_result.skipped_rows,
            mapping_error_rows=[],
            input_rows_before_filter=total_rows,
            input_rows_after_filter=filter_result.rows_after_filter,
            stop_info=None,
        )

    for processed, (index, row) in enumerate(input_df.iterrows(), start=1):
        row_df = input_df.loc[[index]]
        row_number = _row_number(row)
        normalized_row = row.to_dict()
        try:
            derived_values = compute_derived_fields(
                config,
                row_df,
                reference_dfs,
                execution_context,
            )
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
            prepared_rows.append(
                PreparedRow(
                    input_df=filter_result.input_df,
                    derived_values=filter_result.derived_values,
                )
            )
        except MappingError as exc:
            stop_info = classify_mapping_error(exc)
            mapping_error_rows.append(
                ValidationErrorRow(
                    row_number=row_number,
                    stage="mapping",
                    output_name=None,
                    field=_mapping_error_field(str(exc)),
                    rule=stop_info.reason,
                    message=str(exc),
                    normalized_row=normalized_row,
                )
            )
            if mapping_error_policy(config.error_handling, stop_info) == "stop":
                return RowPreparationResult(
                    prepared_rows=prepared_rows,
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
                return RowPreparationResult(
                    prepared_rows=prepared_rows,
                    skipped_rows=skipped_rows,
                    mapping_error_rows=mapping_error_rows,
                    input_rows_before_filter=len(input_df),
                    input_rows_after_filter=rows_after_filter,
                    stop_info=max_errors_stop,
                )
        if progress_callback is not None and (
            processed == total_rows or processed % 1000 == 0
        ):
            progress_callback(processed, total_rows)

    return RowPreparationResult(
        prepared_rows=prepared_rows,
        skipped_rows=skipped_rows,
        mapping_error_rows=mapping_error_rows,
        input_rows_before_filter=len(input_df),
        input_rows_after_filter=rows_after_filter,
        stop_info=None,
    )


def build_rowwise_output(
    *,
    config: DatamapxConfig,
    input_df: pd.DataFrame,
    input_name: str,
    output_columns: list[str],
    reference_dfs: dict[str, pd.DataFrame],
    base_error_count: int,
    output_name: str | None = None,
    progress_callback: RowProgressCallback | None = None,
) -> RowwiseOutputResult:
    """Execute derived, filter, and mapping steps row by row."""

    execution_context = MappingExecutionContext()
    preparation = prepare_rowwise_inputs(
        config=config,
        input_df=input_df,
        input_name=input_name,
        reference_dfs=reference_dfs,
        base_error_count=base_error_count,
        execution_context=execution_context,
        progress_callback=progress_callback,
    )
    if preparation.stop_info is not None:
        return RowwiseOutputResult(
            output_df=pd.DataFrame(columns=output_columns),
            output_row_numbers=pd.Series(dtype="object"),
            skipped_rows=preparation.skipped_rows,
            mapping_error_rows=preparation.mapping_error_rows,
            input_rows_before_filter=preparation.input_rows_before_filter,
            input_rows_after_filter=preparation.input_rows_after_filter,
            stop_info=preparation.stop_info,
        )

    output_result = build_output_from_prepared_rows(
        config=config,
        prepared_rows=preparation.prepared_rows,
        output_columns=output_columns,
        reference_dfs=reference_dfs,
        output_name=output_name,
        base_error_count=base_error_count + len(preparation.mapping_error_rows),
        execution_context=execution_context,
        progress_callback=progress_callback,
    )
    return RowwiseOutputResult(
        output_df=output_result.output_df,
        output_row_numbers=output_result.output_row_numbers,
        skipped_rows=preparation.skipped_rows,
        mapping_error_rows=preparation.mapping_error_rows + output_result.mapping_error_rows,
        input_rows_before_filter=preparation.input_rows_before_filter,
        input_rows_after_filter=preparation.input_rows_after_filter,
        stop_info=output_result.stop_info,
    )


@dataclass(frozen=True)
class OutputBuildResult:
    """Output dataframe build result for a single output."""

    output_df: pd.DataFrame
    output_row_numbers: pd.Series
    mapping_error_rows: list[ValidationErrorRow]
    stop_info: StopInfo | None


def build_output_from_prepared_rows(
    *,
    config: DatamapxConfig,
    prepared_rows: list[PreparedRow],
    output_columns: list[str],
    reference_dfs: dict[str, pd.DataFrame],
    output_name: str | None,
    base_error_count: int,
    execution_context: MappingExecutionContext | None = None,
    progress_callback: RowProgressCallback | None = None,
) -> OutputBuildResult:
    execution_context = execution_context or MappingExecutionContext()
    output_rows: list[dict[str, object]] = []
    output_row_numbers: list[object] = []
    mapping_error_rows: list[ValidationErrorRow] = []
    total_rows = sum(len(prepared_row.input_df) for prepared_row in prepared_rows)
    processed_rows = 0
    for prepared_row in prepared_rows:
        try:
            output_df = build_output_dataframe(
                config,
                prepared_row.input_df,
                reference_dfs=reference_dfs,
                derived_values=prepared_row.derived_values,
                output_name=output_name,
                execution_context=execution_context,
            )
        except MappingError as exc:
            if len(prepared_row.input_df) > 1:
                row_result = build_output_from_prepared_rows(
                    config=config,
                    prepared_rows=_split_prepared_batch(prepared_row),
                    output_columns=output_columns,
                    reference_dfs=reference_dfs,
                    output_name=output_name,
                    base_error_count=base_error_count + len(mapping_error_rows),
                    execution_context=execution_context,
                    progress_callback=None,
                )
                output_rows.extend(row_result.output_df.to_dict("records"))
                output_row_numbers.extend(row_result.output_row_numbers.tolist())
                mapping_error_rows.extend(row_result.mapping_error_rows)
                processed_rows += len(prepared_row.input_df)
                if progress_callback is not None:
                    progress_callback(processed_rows, total_rows)
                if row_result.stop_info is not None:
                    return OutputBuildResult(
                        output_df=pd.DataFrame(output_rows, columns=output_columns),
                        output_row_numbers=pd.Series(output_row_numbers, dtype="object"),
                        mapping_error_rows=mapping_error_rows,
                        stop_info=row_result.stop_info,
                    )
                continue

            stop_info = classify_mapping_error(exc)
            mapping_error_rows.append(
                _mapping_error_row(prepared_row, output_name, stop_info.reason, str(exc))
            )
            stop_info_to_return = (
                stop_info
                if mapping_error_policy(config.error_handling, stop_info) == "stop"
                else evaluate_max_errors(
                    config.error_handling,
                    base_error_count + len(mapping_error_rows),
                )
            )
            if stop_info_to_return is not None:
                return OutputBuildResult(
                    output_df=pd.DataFrame(output_rows, columns=output_columns),
                    output_row_numbers=pd.Series(output_row_numbers, dtype="object"),
                    mapping_error_rows=mapping_error_rows,
                    stop_info=stop_info_to_return,
                )
        else:
            output_rows.extend(output_df.to_dict("records"))
            output_row_numbers.extend(
                _row_number(row) for _, row in prepared_row.input_df.iterrows()
            )
        processed_rows += len(prepared_row.input_df)
        if progress_callback is not None and (
            processed_rows == total_rows or processed_rows % 1000 == 0
        ):
            progress_callback(processed_rows, total_rows)
    return OutputBuildResult(
        output_df=pd.DataFrame(output_rows, columns=output_columns),
        output_row_numbers=pd.Series(output_row_numbers, dtype="object"),
        mapping_error_rows=mapping_error_rows,
        stop_info=None,
    )


def _split_prepared_batch(prepared_row: PreparedRow) -> list[PreparedRow]:
    indexes = prepared_row.input_df.index
    midpoint = len(indexes) // 2
    return [
        _slice_prepared_row(prepared_row, indexes[:midpoint]),
        _slice_prepared_row(prepared_row, indexes[midpoint:]),
    ]


def _slice_prepared_row(
    prepared_row: PreparedRow,
    indexes: pd.Index,
) -> PreparedRow:
    return PreparedRow(
        input_df=prepared_row.input_df.loc[indexes],
        derived_values={
            name: series.loc[indexes]
            for name, series in prepared_row.derived_values.items()
        },
    )


def _mapping_error_row(
    prepared_row: PreparedRow,
    output_name: str | None,
    reason: str,
    message: str,
) -> ValidationErrorRow:
    row = prepared_row.input_df.iloc[0]
    return ValidationErrorRow(
        row_number=_row_number(row),
        stage="mapping",
        output_name=output_name,
        field=_mapping_error_field(message),
        rule=reason,
        message=message,
        normalized_row=row.to_dict(),
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
