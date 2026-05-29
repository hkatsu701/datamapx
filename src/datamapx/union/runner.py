"""Vertical union pipeline for datamapx."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from datamapx.io.csv_reader import ROW_NUMBER_COLUMN, apply_schema, read_csv_frame
from datamapx.io.csv_writer import resolve_output_path
from datamapx.io.errors import CsvReadError
from datamapx.union.config import UnionConfig, UnionInputConfig
from datamapx.union.errors import UnionError, UnionErrorRow, UnionSkippedRow

INPUT_ORDER_COLUMN = "__input_order"
INPUT_NAME_COLUMN = "__input_name"


@dataclass(frozen=True)
class UnionInputSummary:
    """Summary for one union input."""

    name: str
    path: str
    rows_loaded: int
    key: str | list[str]


@dataclass(frozen=True)
class UnionResult:
    """Union execution result."""

    run_id: str
    project_name: str
    status: str
    started_at: str
    finished_at: str
    config_path: str
    output_name: str
    output_path: str
    output_df: pd.DataFrame
    inputs: list[UnionInputSummary]
    error_rows: list[UnionErrorRow]
    skipped_rows: list[UnionSkippedRow]
    input_rows: int
    output_rows: int
    error_count: int
    skipped_count: int
    output_file_written: bool = False
    stop_reason: str | None = None
    stop_message: str | None = None


def run_union_pipeline(
    config: UnionConfig,
    config_path: Path,
) -> UnionResult:
    """Run the union pipeline and return the appended dataframe and reports."""

    started_at = _utc_now()
    run_id = _resolve_run_id(config.runtime.run_id)
    input_name_order = list(config.inputs)
    input_frames: list[pd.DataFrame] = []
    input_summaries: list[UnionInputSummary] = []
    error_rows: list[UnionErrorRow] = []
    skipped_rows: list[UnionSkippedRow] = []

    for input_order, input_name in enumerate(input_name_order):
        input_config = config.inputs[input_name]
        frame = _load_union_input(input_name, input_config, config_path.parent)
        _validate_input_columns(frame, config.output.columns, input_name)
        frame = frame.copy()
        frame[INPUT_NAME_COLUMN] = input_name
        frame[INPUT_ORDER_COLUMN] = input_order
        input_frames.append(frame)
        input_summaries.append(
            UnionInputSummary(
                name=input_name,
                path=input_config.path,
                rows_loaded=len(frame),
                key=input_config.key,
            )
        )

    combined_frame = pd.concat(input_frames, ignore_index=True, sort=False)
    key_columns = _key_columns(config.inputs[input_name_order[0]])
    missing_mask = _missing_key_mask(combined_frame, key_columns)
    if missing_mask.any():
        error_rows.extend(
            _build_error_rows(
                combined_frame.loc[missing_mask],
                input_name_column=INPUT_NAME_COLUMN,
                stage="input_validation",
                field=",".join(key_columns),
                rule="missing_key",
                message=f"missing key values for ({', '.join(key_columns)})",
            )
        )

    valid_frame = combined_frame.loc[~missing_mask].copy()
    duplicate_mask = valid_frame.duplicated(subset=key_columns, keep=False)
    if duplicate_mask.any():
        error_rows.extend(
            _build_error_rows(
                valid_frame.loc[duplicate_mask],
                input_name_column=INPUT_NAME_COLUMN,
                stage="input_validation",
                field=",".join(key_columns),
                rule="duplicate_key",
                message=f"duplicate key values for ({', '.join(key_columns)})",
            )
        )

    final_valid_frame = valid_frame.loc[~duplicate_mask].copy()
    output_columns = config.output.columns
    output_df = pd.DataFrame(columns=output_columns)
    output_written = False
    if not error_rows:
        output_df = final_valid_frame.loc[:, output_columns].copy()

    finished_at = _utc_now()
    status = "completed" if not error_rows else "failed"
    if (
        status == "completed"
        and config.runtime.max_output_rows is not None
        and len(output_df) > config.runtime.max_output_rows
    ):
        status = "failed"
    return UnionResult(
        run_id=run_id,
        project_name=config.project.name,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        config_path=str(config_path),
        output_name="output",
        output_path=str(resolve_output_path(config.output.path, config_path.parent)),
        output_df=output_df,
        inputs=input_summaries,
        error_rows=error_rows,
        skipped_rows=skipped_rows,
        input_rows=sum(summary.rows_loaded for summary in input_summaries),
        output_rows=len(output_df),
        error_count=len(error_rows),
        skipped_count=len(skipped_rows),
        output_file_written=output_written,
        stop_reason=(
            "max_output_rows_exceeded"
            if status == "failed"
            and config.runtime.max_output_rows is not None
            and len(output_df) > config.runtime.max_output_rows
            else None
        ),
        stop_message=(
            f"output row count {len(output_df)} exceeded runtime.max_output_rows "
            f"{config.runtime.max_output_rows}"
            if status == "failed"
            and config.runtime.max_output_rows is not None
            and len(output_df) > config.runtime.max_output_rows
            else None
        ),
    )


def _load_union_input(
    input_name: str,
    input_config: UnionInputConfig,
    base_path: Path,
) -> pd.DataFrame:
    raw_df = read_csv_frame(
        input_config.path,
        input_config.encoding,
        input_config.delimiter,
        input_config.header,
        base_path,
    )
    if input_config.fields_schema:
        return apply_schema(raw_df, input_config.fields_schema, f"inputs.{input_name}")

    df = raw_df.copy()
    df.insert(0, ROW_NUMBER_COLUMN, range(1, len(df) + 1))
    return df


def _build_error_rows(
    df: pd.DataFrame,
    *,
    input_name_column: str,
    stage: Literal["input_validation", "union"],
    field: str,
    rule: str,
    message: str,
) -> list[UnionErrorRow]:
    rows: list[UnionErrorRow] = []
    for _, row in df.iterrows():
        rows.append(
            UnionErrorRow(
                input_name=str(row[input_name_column]),
                row_number=int(row[ROW_NUMBER_COLUMN]),
                stage=stage,
                field=field,
                rule=rule,
                message=message,
                row_json=_row_json(row, input_name_column=input_name_column),
            )
        )
    return rows


def _row_json(row: pd.Series, *, input_name_column: str) -> dict[str, object]:
    return {
        key: value
        for key, value in row.to_dict().items()
        if key != INPUT_ORDER_COLUMN and key != input_name_column
    }


def _validate_input_columns(
    df: pd.DataFrame,
    expected_columns: list[str],
    input_name: str,
) -> None:
    actual_columns = [column for column in df.columns if column != ROW_NUMBER_COLUMN]
    if actual_columns != expected_columns:
        raise UnionError(
            f"inputs.{input_name}: columns must match output.columns exactly: "
            f"expected {expected_columns}, got {actual_columns}"
        )


def _missing_key_mask(df: pd.DataFrame, key_columns: list[str]) -> pd.Series:
    missing_masks = []
    for key_column in key_columns:
        if key_column not in df.columns:
            raise CsvReadError(f"inputs: missing key column '{key_column}'")
        missing_masks.append(_is_missing_series(df[key_column]))
    combined = missing_masks[0].copy()
    for mask in missing_masks[1:]:
        combined = combined | mask
    return combined


def _is_missing_series(series: pd.Series) -> pd.Series:
    string_series = series.astype("string")
    return series.isna() | string_series.str.strip().eq("")


def _key_columns(input_config: UnionInputConfig) -> list[str]:
    return [input_config.key] if isinstance(input_config.key, str) else input_config.key


def _resolve_run_id(run_id_setting: str) -> str:
    if run_id_setting != "auto":
        return run_id_setting
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
