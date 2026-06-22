"""Consolidate pipeline for datamapx."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from datamapx.consolidate.config import ChildSettings, ConsolidateConfig, ParentColumnRule
from datamapx.consolidate.errors import ConsolidateErrorRow, ConsolidateSkippedRow
from datamapx.io.csv_reader import apply_schema, read_csv_frame
from datamapx.io.csv_writer import resolve_output_path
from datamapx.io.errors import CsvReadError


@dataclass(frozen=True)
class ConsolidateInputSummary:
    """Summary for the consolidate input."""

    name: str
    path: str
    rows_loaded: int


@dataclass(frozen=True)
class ConsolidateOutputResult:
    """One consolidate output dataframe."""

    name: str
    path: str
    df: pd.DataFrame
    rows_written: int
    file_written: bool = False


@dataclass(frozen=True)
class ConsolidateResult:
    """Consolidate execution result."""

    run_id: str
    project_name: str
    status: str
    started_at: str
    finished_at: str
    config_path: str
    outputs: list[ConsolidateOutputResult]
    inputs: list[ConsolidateInputSummary]
    error_rows: list[ConsolidateErrorRow]
    skipped_rows: list[ConsolidateSkippedRow]
    input_rows: int
    output_rows: int
    error_count: int
    skipped_count: int
    output_file_written: bool = False
    stop_reason: str | None = None
    stop_message: str | None = None


def run_consolidate_pipeline(
    config: ConsolidateConfig,
    config_path: Path,
) -> ConsolidateResult:
    """Run the consolidate pipeline and return parent/child dataframes and reports."""

    started_at = _utc_now()
    run_id = _resolve_run_id(config.runtime.run_id)
    input_name = "input"
    input_df = _load_consolidate_input(input_name, config, config_path.parent)
    input_summary = ConsolidateInputSummary(
        name=input_name,
        path=config.input_.path,
        rows_loaded=len(input_df),
    )

    group_by = list(config.consolidate.group_by)
    error_rows: list[ConsolidateErrorRow] = []
    skipped_rows: list[ConsolidateSkippedRow] = []

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

    parent_records: list[dict[str, Any]] = []
    child_records: dict[str, list[dict[str, Any]]] = {
        child.name: [] for child in config.consolidate.children
    }

    valid_df = input_df.loc[~missing_mask].copy()
    if not valid_df.empty:
        for _, group_df in valid_df.groupby(group_by, sort=False, dropna=False):
            parent_row, group_errors = _build_parent_row(
                group_df,
                config,
                input_name=input_name,
            )
            if group_errors:
                error_rows.extend(group_errors)
                continue
            parent_records.append(parent_row)
            for child in config.consolidate.children:
                child_records[child.name].extend(_build_child_rows(group_df, child, parent_row))

    outputs = _build_outputs(config, config_path.parent, parent_records, child_records)
    output_rows = sum(output.rows_written for output in outputs)
    status = "completed" if not error_rows else "failed"
    stop_reason: str | None = None
    stop_message: str | None = None

    if error_rows:
        outputs = _empty_outputs(config, config_path.parent)
        output_rows = 0
        first_error = error_rows[0]
        stop_reason = first_error.rule
        stop_message = first_error.message
    elif (
        config.runtime.max_output_rows is not None
        and output_rows > config.runtime.max_output_rows
    ):
        actual_output_rows = output_rows
        outputs = _empty_outputs(config, config_path.parent)
        output_rows = 0
        status = "failed"
        stop_reason = "max_output_rows_exceeded"
        stop_message = (
            f"output row count {actual_output_rows} exceeded runtime.max_output_rows "
            f"{config.runtime.max_output_rows}"
        )

    finished_at = _utc_now()
    return ConsolidateResult(
        run_id=run_id,
        project_name=config.project.name,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        config_path=str(config_path),
        outputs=outputs,
        inputs=[input_summary],
        error_rows=error_rows,
        skipped_rows=skipped_rows,
        input_rows=len(input_df),
        output_rows=output_rows,
        error_count=len(error_rows),
        skipped_count=len(skipped_rows),
        output_file_written=False,
        stop_reason=stop_reason,
        stop_message=stop_message,
    )


def _build_outputs(
    config: ConsolidateConfig,
    base_path: Path,
    parent_records: list[dict[str, Any]],
    child_records: dict[str, list[dict[str, Any]]],
) -> list[ConsolidateOutputResult]:
    parent_df = pd.DataFrame(parent_records, columns=config.consolidate.parent.output.columns)
    outputs = [
        ConsolidateOutputResult(
            name="parent",
            path=str(resolve_output_path(config.consolidate.parent.output.path, base_path)),
            df=parent_df,
            rows_written=len(parent_df),
        )
    ]
    for child in config.consolidate.children:
        child_df = pd.DataFrame(child_records[child.name], columns=child.output.columns)
        outputs.append(
            ConsolidateOutputResult(
                name=child.name,
                path=str(resolve_output_path(child.output.path, base_path)),
                df=child_df,
                rows_written=len(child_df),
            )
        )
    return outputs


def _empty_outputs(config: ConsolidateConfig, base_path: Path) -> list[ConsolidateOutputResult]:
    empty_outputs = [
        ConsolidateOutputResult(
            name="parent",
            path=str(resolve_output_path(config.consolidate.parent.output.path, base_path)),
            df=pd.DataFrame(columns=config.consolidate.parent.output.columns),
            rows_written=0,
        )
    ]
    for child in config.consolidate.children:
        empty_outputs.append(
            ConsolidateOutputResult(
                name=child.name,
                path=str(resolve_output_path(child.output.path, base_path)),
                df=pd.DataFrame(columns=child.output.columns),
                rows_written=0,
            )
        )
    return empty_outputs


def _build_parent_row(
    group_df: pd.DataFrame,
    config: ConsolidateConfig,
    *,
    input_name: str,
) -> tuple[dict[str, Any], list[ConsolidateErrorRow]]:
    row: dict[str, Any] = {}
    error_rows: list[ConsolidateErrorRow] = []

    for output_name, rule in config.consolidate.parent.columns.items():
        value, rule_errors = _apply_parent_rule(
            group_df,
            output_name,
            rule,
            input_name=input_name,
        )
        if rule_errors:
            error_rows.extend(rule_errors)
            continue
        row[output_name] = value

    return row, error_rows


def _apply_parent_rule(
    group_df: pd.DataFrame,
    output_name: str,
    rule: ParentColumnRule,
    *,
    input_name: str,
) -> tuple[Any, list[ConsolidateErrorRow]]:
    rule_name = rule.rule_name()
    source = getattr(rule, rule_name)
    series = group_df[source]

    if rule_name == "first":
        return _first_non_null(series), []
    if rule_name == "last":
        return _last_non_null(series), []
    if rule_name == "sum":
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.isna().any() and series.notna().any():
            return None, _build_error_rows(
                group_df,
                input_name=input_name,
                field=output_name,
                rule="invalid_sum_value",
                message=f"{source}: numeric conversion failed for sum",
            )
        return numeric.sum(min_count=1), []
    if rule_name == "count":
        return int(series.notna().sum()), []

    distinct = {_serialize_value(value) for value in series if not pd.isna(value)}
    if len(distinct) > 1:
        return None, _build_error_rows(
            group_df,
            input_name=input_name,
            field=output_name,
            rule="require_same_conflict",
            message=f"{source}: group contains conflicting values",
        )
    return _first_non_null(series), []


def _build_child_rows(
    group_df: pd.DataFrame,
    child: ChildSettings,
    parent_row: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in group_df.iterrows():
        child_row: dict[str, Any] = {}
        for output_name, rule in child.columns.items():
            rule_name = rule.rule_name()
            source = getattr(rule, rule_name)
            if rule_name == "source":
                child_row[output_name] = row[source]
            else:
                child_row[output_name] = parent_row[source]
        rows.append(child_row)
    return rows


def _load_consolidate_input(
    input_name: str,
    config: ConsolidateConfig,
    base_path: Path,
) -> pd.DataFrame:
    input_config = config.input_
    if not input_config.header:
        raise CsvReadError("input.header: false is not supported in consolidate")
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


def _missing_group_key_mask(frame: pd.DataFrame, group_by: list[str]) -> pd.Series:
    mask = pd.Series(False, index=frame.index)
    for column in group_by:
        values = frame[column]
        mask = mask | values.isna() | (values.astype("string").str.strip() == "")
    return mask


def _build_error_rows(
    frame: pd.DataFrame,
    *,
    input_name: str,
    field: str,
    rule: str,
    message: str,
) -> list[ConsolidateErrorRow]:
    rows: list[ConsolidateErrorRow] = []
    for _, row in frame.iterrows():
        row_json = {column: _serialize_value(value) for column, value in row.items()}
        rows.append(
            ConsolidateErrorRow(
                input_name=input_name,
                row_number=int(row["__row_number"]),
                stage="consolidate",
                field=field,
                rule=rule,
                message=message,
                row_json=row_json,
            )
        )
    return rows


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


def _serialize_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    return value


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
