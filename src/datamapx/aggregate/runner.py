"""Aggregate pipeline for datamapx."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from datamapx.aggregate.config import AggregateColumnRule, AggregateConfig
from datamapx.aggregate.errors import AggregateErrorRow, AggregateSkippedRow
from datamapx.config import SchemaFieldConfig
from datamapx.io.csv_reader import ROW_NUMBER_COLUMN, apply_schema, read_csv_frame
from datamapx.io.csv_writer import resolve_output_path
from datamapx.io.errors import CsvReadError


@dataclass(frozen=True)
class AggregateInputSummary:
    """Summary for the aggregate input."""

    name: str
    path: str
    rows_loaded: int


@dataclass(frozen=True)
class AggregateResult:
    """Aggregate execution result."""

    run_id: str
    project_name: str
    status: str
    started_at: str
    finished_at: str
    config_path: str
    output_name: str
    output_path: str
    output_df: pd.DataFrame
    inputs: list[AggregateInputSummary]
    error_rows: list[AggregateErrorRow]
    skipped_rows: list[AggregateSkippedRow]
    input_rows: int
    output_rows: int
    error_count: int
    skipped_count: int
    output_file_written: bool = False
    stop_reason: str | None = None
    stop_message: str | None = None


def run_aggregate_pipeline(
    config: AggregateConfig,
    config_path: Path,
) -> AggregateResult:
    """Run the aggregate pipeline and return the summarized dataframe and reports."""

    started_at = _utc_now()
    run_id = _resolve_run_id(config.runtime.run_id)
    input_name = "input"
    input_df = _load_aggregate_input(
        input_name,
        config,
        config_path.parent,
    )
    input_summary = AggregateInputSummary(
        name=input_name,
        path=config.input_.path,
        rows_loaded=len(input_df),
    )

    error_rows: list[AggregateErrorRow] = []
    skipped_rows: list[AggregateSkippedRow] = []
    output_records: list[dict[str, Any]] = []
    group_by = list(config.aggregate.group_by)
    output_columns = list(config.output.columns)

    missing_mask = _missing_group_key_mask(input_df, group_by)
    if missing_mask.any():
        error_rows.extend(
            _build_error_rows(
                input_df.loc[missing_mask],
                input_name=input_name,
                field=",".join(group_by),
                rule="missing_group_key",
                message=f"missing group key values for ({', '.join(group_by)})",
            )
        )

    valid_df = input_df.loc[~missing_mask].copy()
    if not valid_df.empty:
        for _, group_df in valid_df.groupby(group_by, sort=False, dropna=False):
            row, group_error_rows = _aggregate_group(
                group_df,
                config.aggregate.columns,
                config.input_.fields_schema,
                input_name=input_name,
            )
            if group_error_rows:
                error_rows.extend(group_error_rows)
                continue
            output_records.append(row)

    output_df = pd.DataFrame(output_records, columns=output_columns)
    output_written = False
    status = "completed" if not error_rows else "failed"
    stop_reason: str | None = None
    stop_message: str | None = None

    if error_rows:
        output_df = pd.DataFrame(columns=output_columns)
        first_error = error_rows[0]
        stop_reason = first_error.rule
        stop_message = first_error.message
    elif (
        config.runtime.max_output_rows is not None
        and len(output_df) > config.runtime.max_output_rows
    ):
        status = "failed"
        stop_reason = "max_output_rows_exceeded"
        stop_message = (
            f"output row count {len(output_df)} exceeded runtime.max_output_rows "
            f"{config.runtime.max_output_rows}"
        )

    finished_at = _utc_now()
    return AggregateResult(
        run_id=run_id,
        project_name=config.project.name,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        config_path=str(config_path),
        output_name="output",
        output_path=str(resolve_output_path(config.output.path, config_path.parent)),
        output_df=output_df,
        inputs=[input_summary],
        error_rows=error_rows,
        skipped_rows=skipped_rows,
        input_rows=len(input_df),
        output_rows=len(output_df),
        error_count=len(error_rows),
        skipped_count=len(skipped_rows),
        output_file_written=output_written,
        stop_reason=stop_reason,
        stop_message=stop_message,
    )


def _load_aggregate_input(
    input_name: str,
    config: AggregateConfig,
    base_path: Path,
) -> pd.DataFrame:
    input_config = config.input_
    if not input_config.header:
        raise CsvReadError("input.header: false is not supported in aggregate")
    if config.runtime.max_input_rows is not None:
        csv_path = _resolve_path(input_config.path, base_path)
        row_count = _count_csv_data_rows(
            csv_path,
            input_config.encoding,
            input_config.delimiter,
        )
        if row_count > config.runtime.max_input_rows:
            raise CsvReadError(
                f"input: row count {row_count} exceeds runtime.max_input_rows "
                f"{config.runtime.max_input_rows}"
            )

    raw_df = read_csv_frame(
        input_config.path,
        input_config.encoding,
        input_config.delimiter,
        input_config.header,
        base_path,
        schema=input_config.fields_schema,
    )
    return apply_schema(raw_df, input_config.fields_schema, input_name)


def _aggregate_group(
    group_df: pd.DataFrame,
    columns: dict[str, AggregateColumnRule],
    schema: Mapping[str, SchemaFieldConfig],
    *,
    input_name: str,
) -> tuple[dict[str, Any], list[AggregateErrorRow]]:
    row: dict[str, Any] = {}
    error_rows: list[AggregateErrorRow] = []

    for output_name, rule in columns.items():
        rule_name = rule.rule_name()
        source = getattr(rule, rule_name)
        if rule_name == "group_key":
            row[output_name] = _first_non_null(group_df[str(source)])
            continue
        if rule_name == "count":
            row[output_name] = (
                int(group_df[str(source)].notna().sum())
                if source is not None
                else int(len(group_df))
            )
            continue
        if rule_name == "first":
            row[output_name] = _first_non_null(group_df[str(source)])
            continue
        if rule_name == "last":
            row[output_name] = _last_non_null(group_df[str(source)])
            continue

        value, aggregate_errors = _aggregate_numeric_or_temporal(
            group_df,
            source_name=str(source),
            rule_name=rule_name,
            output_name=output_name,
            schema=schema,
            input_name=input_name,
        )
        if aggregate_errors:
            error_rows.extend(aggregate_errors)
            continue
        row[output_name] = value

    return row, error_rows


def _aggregate_numeric_or_temporal(
    group_df: pd.DataFrame,
    *,
    source_name: str,
    rule_name: str,
    output_name: str,
    schema: dict[str, Any],
    input_name: str,
) -> tuple[Any, list[AggregateErrorRow]]:
    series = group_df[source_name]
    field_config = schema[source_name]

    if field_config.type == "date":
        if rule_name == "sum":
            return None, _build_conversion_error_rows(
                group_df,
                input_name=input_name,
                output_name=output_name,
                rule_name=rule_name,
                message=f"{source_name}: sum is not supported for date fields",
            )
        non_null = series.dropna()
        if non_null.empty:
            return pd.NA, []
        if rule_name == "min":
            return non_null.min(), []
        return non_null.max(), []

    if pd.api.types.is_numeric_dtype(series):
        numeric = pd.to_numeric(series, errors="coerce")
        invalid_mask = series.notna() & numeric.isna()
        if invalid_mask.any():
            return None, _build_conversion_error_rows(
                group_df.loc[invalid_mask],
                input_name=input_name,
                output_name=output_name,
                rule_name=rule_name,
                message=f"{source_name}: numeric conversion failed",
            )
        return _reduce_numeric_series(numeric, rule_name), []

    numeric = pd.to_numeric(series, errors="coerce")
    invalid_mask = series.notna() & numeric.isna()
    if invalid_mask.any():
        return None, _build_conversion_error_rows(
            group_df.loc[invalid_mask],
            input_name=input_name,
            output_name=output_name,
            rule_name=rule_name,
            message=f"{source_name}: numeric conversion failed",
        )
    return _reduce_numeric_series(numeric, rule_name), []


def _reduce_numeric_series(series: pd.Series, rule_name: str) -> Any:
    if rule_name == "sum":
        return series.sum(skipna=True)
    if rule_name == "min":
        return series.min(skipna=True)
    return series.max(skipna=True)


def _build_conversion_error_rows(
    df: pd.DataFrame,
    *,
    input_name: str,
    output_name: str,
    rule_name: str,
    message: str,
) -> list[AggregateErrorRow]:
    rows: list[AggregateErrorRow] = []
    for _, row in df.iterrows():
        rows.append(
            AggregateErrorRow(
                input_name=input_name,
                row_number=int(row[ROW_NUMBER_COLUMN]),
                stage="aggregate",
                field=output_name,
                rule=rule_name,
                message=message,
                row_json=_row_json(row),
            )
        )
    return rows


def _build_error_rows(
    df: pd.DataFrame,
    *,
    input_name: str,
    field: str,
    rule: str,
    message: str,
) -> list[AggregateErrorRow]:
    rows: list[AggregateErrorRow] = []
    for _, row in df.iterrows():
        rows.append(
            AggregateErrorRow(
                input_name=input_name,
                row_number=int(row[ROW_NUMBER_COLUMN]),
                stage="input_validation",
                field=field,
                rule=rule,
                message=message,
                row_json=_row_json(row),
            )
        )
    return rows


def _missing_group_key_mask(df: pd.DataFrame, group_by: list[str]) -> pd.Series:
    missing_masks = []
    for column in group_by:
        if column not in df.columns:
            raise CsvReadError(f"input.schema: missing group_by column '{column}'")
        missing_masks.append(_is_missing_series(df[column]))
    combined = missing_masks[0].copy()
    for mask in missing_masks[1:]:
        combined = combined | mask
    return combined


def _is_missing_series(series: pd.Series) -> pd.Series:
    string_series = series.astype("string")
    return series.isna() | string_series.str.strip().eq("")


def _first_non_null(series: pd.Series) -> Any:
    non_null = series.dropna()
    if non_null.empty:
        return pd.NA
    return non_null.iloc[0]


def _last_non_null(series: pd.Series) -> Any:
    non_null = series.dropna()
    if non_null.empty:
        return pd.NA
    return non_null.iloc[-1]


def _row_json(row: pd.Series) -> dict[str, Any]:
    return {column: value for column, value in row.to_dict().items() if column != ROW_NUMBER_COLUMN}


def _count_csv_data_rows(csv_path: Path, encoding: str, delimiter: str) -> int:
    from datamapx.io.csv_reader import _count_csv_data_rows as _count

    return _count(csv_path, encoding, delimiter)


def _resolve_path(path: str, base_path: Path) -> Path:
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return base_path / resolved


def _resolve_run_id(run_id_setting: str) -> str:
    if run_id_setting != "auto":
        return run_id_setting
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
