"""Merge pipeline for multiple CSV inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from datamapx.io.csv_reader import ROW_NUMBER_COLUMN, apply_schema, read_csv_frame
from datamapx.io.csv_writer import resolve_output_path
from datamapx.io.errors import CsvReadError
from datamapx.merge.config import MergeConfig, MergeInputConfig
from datamapx.merge.errors import MergeError, MergeErrorRow, MergeSkippedRow

MERGE_KEY_PREFIX = "__merge_key_"


@dataclass(frozen=True)
class MergeInputSummary:
    """Summary for one merge input."""

    name: str
    path: str
    rows_loaded: int
    key: str | list[str]


@dataclass(frozen=True)
class MergeResult:
    """Merge execution result."""

    run_id: str
    project_name: str
    status: str
    started_at: str
    finished_at: str
    config_path: str
    output_name: str
    output_path: str
    output_df: pd.DataFrame
    inputs: list[MergeInputSummary]
    error_rows: list[MergeErrorRow]
    skipped_rows: list[MergeSkippedRow]
    input_rows: int
    output_rows: int
    error_count: int
    skipped_count: int
    output_file_written: bool = False


def run_merge_pipeline(
    config: MergeConfig,
    config_path: Path,
    reports_dir: Path | None = None,
) -> MergeResult:
    """Run the merge pipeline and return the merged dataframe and reports."""

    started_at = _utc_now()
    run_id = _resolve_run_id(config.runtime.run_id)
    input_name_order = list(config.inputs)
    input_frames: dict[str, pd.DataFrame] = {}
    input_summaries: list[MergeInputSummary] = []
    error_rows: list[MergeErrorRow] = []
    skipped_rows: list[MergeSkippedRow] = []
    base_name = config.merge.base

    for input_name in input_name_order:
        input_config = config.inputs[input_name]
        frame, input_error_rows = _load_merge_input(input_name, input_config, config_path.parent)
        input_frames[input_name] = frame
        input_summaries.append(
            MergeInputSummary(
                name=input_name,
                path=input_config.path,
                rows_loaded=len(frame),
                key=input_config.key,
            )
        )
        error_rows.extend(input_error_rows)

    if error_rows:
        finished_at = _utc_now()
        return MergeResult(
            run_id=run_id,
            project_name=config.project.name,
            status="failed",
            started_at=started_at,
            finished_at=finished_at,
            config_path=str(config_path),
            output_name="output",
            output_path=str(resolve_output_path(config.output.path, config_path.parent)),
            output_df=pd.DataFrame(columns=config.output.columns),
            inputs=input_summaries,
            error_rows=error_rows,
            skipped_rows=skipped_rows,
            input_rows=len(input_frames[base_name]) if base_name in input_frames else 0,
            output_rows=0,
            error_count=len(error_rows),
            skipped_count=len(skipped_rows),
            output_file_written=False,
        )

    base_frame = input_frames[base_name]
    base_key_columns = _key_columns(config.inputs[base_name])
    base_prefixed = _with_prefixed_columns(base_name, base_frame, base_key_columns)
    merged_frame = base_prefixed.copy()

    for input_name in input_name_order:
        if input_name == base_name:
            continue
        input_frame = input_frames[input_name]
        key_columns = _key_columns(config.inputs[input_name])
        merged_frame, merge_error_rows, merge_skipped_rows = _merge_one(
            merged_frame,
            input_name,
            input_frame,
            key_columns,
            config.merge.join_type,
        )
        error_rows.extend(merge_error_rows)
        skipped_rows.extend(merge_skipped_rows)
        if error_rows:
            break

    output_df = pd.DataFrame(columns=config.output.columns)
    output_written = False
    if not error_rows:
        output_df = _build_output_dataframe(config, merged_frame)

    finished_at = _utc_now()
    status = "completed" if not error_rows else "failed"
    return MergeResult(
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
        input_rows=len(base_frame),
        output_rows=len(output_df),
        error_count=len(error_rows),
        skipped_count=len(skipped_rows),
        output_file_written=output_written,
    )


def _load_merge_input(
    input_name: str,
    input_config: MergeInputConfig,
    base_path: Path,
) -> tuple[pd.DataFrame, list[MergeErrorRow]]:
    raw_df = read_csv_frame(
        input_config.path,
        input_config.encoding,
        input_config.delimiter,
        input_config.header,
        base_path,
    )
    if input_config.fields_schema:
        df = apply_schema(raw_df, input_config.fields_schema, f"inputs.{input_name}")
    else:
        df = raw_df.copy()
        df.insert(0, ROW_NUMBER_COLUMN, range(1, len(df) + 1))
    return df, _validate_merge_input_keys(input_name, input_config, df)


def _validate_merge_input_keys(
    input_name: str,
    input_config: MergeInputConfig,
    df: pd.DataFrame,
) -> list[MergeErrorRow]:
    key_columns = _key_columns(input_config)
    for key_column in key_columns:
        if key_column not in df.columns:
            raise CsvReadError(f"inputs.{input_name}.key: missing key column '{key_column}'")

    error_rows: list[MergeErrorRow] = []
    missing_mask = df[key_columns].isna().any(axis=1)
    if missing_mask.any():
        for _, row in df.loc[missing_mask].iterrows():
            error_rows.append(
                MergeErrorRow(
                    input_name=input_name,
                    row_number=int(row[ROW_NUMBER_COLUMN]),
                    stage="merge",
                    field=",".join(key_columns),
                    rule="missing_key",
                    message=f"missing key values for ({', '.join(key_columns)})",
                    row_json=_row_json(row),
                )
            )

    duplicate_mask = df.duplicated(subset=key_columns, keep=False)
    if duplicate_mask.any():
        for _, row in df.loc[duplicate_mask].iterrows():
            error_rows.append(
                MergeErrorRow(
                    input_name=input_name,
                    row_number=int(row[ROW_NUMBER_COLUMN]),
                    stage="merge",
                    field=",".join(key_columns),
                    rule="duplicate_key",
                    message=f"duplicate key values for ({', '.join(key_columns)})",
                    row_json=_row_json(row),
                )
            )
    return error_rows


def _merge_one(
    merged_df: pd.DataFrame,
    input_name: str,
    input_df: pd.DataFrame,
    key_columns: list[str],
    join_type: str,
) -> tuple[pd.DataFrame, list[MergeErrorRow], list[MergeSkippedRow]]:
    prefixed_input = _with_prefixed_columns(input_name, input_df, key_columns)
    merged_keys = [column for column in merged_df.columns if column.startswith(MERGE_KEY_PREFIX)]
    if len(merged_keys) != len(key_columns):
        raise MergeError("merge key count mismatch")

    working = merged_df.merge(
        prefixed_input,
        how="left",
        on=merged_keys,
        suffixes=("", f"__{input_name}"),
        indicator=True,
    )

    skipped_rows: list[MergeSkippedRow] = []
    if join_type == "inner":
        dropped = working[working["_merge"] != "both"]
        for _, row in dropped.iterrows():
            skipped_rows.append(
                MergeSkippedRow(
                    row_number=int(row[ROW_NUMBER_COLUMN]),
                    reason=f"No merge match in {input_name}",
                    row_json=_row_json(row),
                )
            )
        working = working[working["_merge"] == "both"].copy()
    working = working.drop(columns=["_merge"])
    return working, [], skipped_rows


def _build_output_dataframe(config: MergeConfig, merged_frame: pd.DataFrame) -> pd.DataFrame:
    output_columns = config.output.columns
    merged_data: dict[str, pd.Series] = {}
    for output_column in output_columns:
        rule = config.merge.columns[output_column]
        merged_data[output_column] = _evaluate_merge_rule(rule, merged_frame, output_column)
    return pd.DataFrame(merged_data, columns=output_columns)


def _evaluate_merge_rule(
    rule: Any,
    merged_frame: pd.DataFrame,
    output_column: str,
) -> pd.Series:
    if rule.source is not None:
        return _reference_series(merged_frame, rule.source, output_column)
    if rule.first is not None:
        return _first_non_missing(merged_frame, rule.first, output_column)
    if rule.last is not None:
        return _last_non_missing(merged_frame, rule.last, output_column)
    if rule.sum is not None:
        return _sum_series(merged_frame, rule.sum, output_column)
    if rule.min is not None:
        return _numeric_reduce(merged_frame, rule.min, output_column, "min")
    if rule.max is not None:
        return _numeric_reduce(merged_frame, rule.max, output_column, "max")
    if rule.count is not None:
        return _count_series(merged_frame, rule.count)
    raise MergeError(f"{output_column}: unsupported merge rule")


def _reference_series(merged_frame: pd.DataFrame, reference: str, output_column: str) -> pd.Series:
    if reference not in merged_frame.columns:
        raise MergeError(f"{output_column}: unknown merge reference: {reference}")
    return merged_frame[reference]


def _first_non_missing(
    merged_frame: pd.DataFrame,
    references: list[str],
    output_column: str,
) -> pd.Series:
    series_list = [
        _reference_series(merged_frame, reference, output_column)
        for reference in references
    ]
    result = pd.Series([pd.NA] * len(merged_frame), index=merged_frame.index, dtype="object")
    for series in series_list:
        result = result.where(result.notna(), series)
    return result


def _last_non_missing(
    merged_frame: pd.DataFrame,
    references: list[str],
    output_column: str,
) -> pd.Series:
    series_list = [
        _reference_series(merged_frame, reference, output_column)
        for reference in references
    ]
    result = pd.Series([pd.NA] * len(merged_frame), index=merged_frame.index, dtype="object")
    for series in series_list:
        result = series.where(series.notna(), result)
    return result


def _sum_series(merged_frame: pd.DataFrame, references: list[str], output_column: str) -> pd.Series:
    values = [_reference_series(merged_frame, reference, output_column) for reference in references]
    numeric = pd.concat([pd.to_numeric(series, errors="coerce") for series in values], axis=1)
    summed = numeric.sum(axis=1, min_count=1)
    return summed


def _numeric_reduce(
    merged_frame: pd.DataFrame,
    references: list[str],
    output_column: str,
    op: str,
) -> pd.Series:
    values = [_reference_series(merged_frame, reference, output_column) for reference in references]
    numeric = pd.concat([pd.to_numeric(series, errors="coerce") for series in values], axis=1)
    if op == "min":
        return numeric.min(axis=1, skipna=True)
    if op == "max":
        return numeric.max(axis=1, skipna=True)
    raise MergeError(f"{output_column}: unsupported numeric reduce operation: {op}")


def _count_series(merged_frame: pd.DataFrame, references: list[str]) -> pd.Series:
    values = [_reference_series(merged_frame, reference, "count") for reference in references]
    numeric = pd.concat([series.notna().astype(int) for series in values], axis=1)
    return numeric.sum(axis=1)


def _key_columns(input_config: MergeInputConfig) -> list[str]:
    return [input_config.key] if isinstance(input_config.key, str) else input_config.key


def _with_prefixed_columns(
    input_name: str,
    df: pd.DataFrame,
    key_columns: list[str],
) -> pd.DataFrame:
    prefixed = df.copy()
    rename_map = {
        column: f"{input_name}.{column}"
        for column in prefixed.columns
        if column != ROW_NUMBER_COLUMN
    }
    prefixed = prefixed.rename(columns=rename_map)
    for index, key_column in enumerate(key_columns):
        prefixed[f"{MERGE_KEY_PREFIX}{index}"] = prefixed[f"{input_name}.{key_column}"]
    return prefixed


def _row_json(row: pd.Series) -> dict[str, Any]:
    return {
        column: value
        for column, value in row.items()
        if column != "_merge" and not column.startswith(MERGE_KEY_PREFIX)
    }


def _resolve_run_id(run_id: str) -> str:
    if run_id != "auto":
        return run_id
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
