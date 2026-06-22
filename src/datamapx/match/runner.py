"""Match pipeline for datamapx."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from datamapx.io.csv_reader import apply_schema, read_csv_frame
from datamapx.io.csv_writer import resolve_output_path
from datamapx.io.errors import CsvReadError
from datamapx.match.config import MatchConfig
from datamapx.match.errors import MatchErrorRow, MatchSkippedRow


@dataclass(frozen=True)
class MatchInputSummary:
    """Summary for the match input."""

    name: str
    path: str
    rows_loaded: int


@dataclass(frozen=True)
class MatchResult:
    """Match execution result."""

    run_id: str
    project_name: str
    status: str
    started_at: str
    finished_at: str
    config_path: str
    output_name: str
    output_path: str
    output_df: pd.DataFrame
    inputs: list[MatchInputSummary]
    error_rows: list[MatchErrorRow]
    skipped_rows: list[MatchSkippedRow]
    input_rows: int
    output_rows: int
    error_count: int
    skipped_count: int
    output_file_written: bool = False
    stop_reason: str | None = None
    stop_message: str | None = None


def run_match_pipeline(
    config: MatchConfig,
    config_path: Path,
) -> MatchResult:
    """Run the match pipeline and return the grouped dataframe and reports."""

    started_at = _utc_now()
    run_id = _resolve_run_id(config.runtime.run_id)
    input_name = "input"
    input_df = _load_match_input(input_name, config, config_path.parent)
    input_summary = MatchInputSummary(
        name=input_name,
        path=config.input_.path,
        rows_loaded=len(input_df),
    )

    match_keys = list(config.match.keys)
    error_rows: list[MatchErrorRow] = []
    skipped_rows: list[MatchSkippedRow] = []
    missing_mask = _missing_match_key_mask(input_df, match_keys)
    if missing_mask.any():
        error_rows.extend(
            _build_error_rows(
                input_df.loc[missing_mask],
                input_name=input_name,
                field=",".join(match_keys),
                rule="missing_match_key",
                message=f"missing match key values for ({', '.join(match_keys)})",
            )
        )

    valid_df = input_df.loc[~missing_mask].copy()
    if not valid_df.empty:
        assigned = _assign_match_ids(valid_df, config.match.keys, config)
        valid_df[config.match.output_column] = assigned
        if not config.match.assign_singletons:
            group_sizes = valid_df.groupby(match_keys, sort=False, dropna=False)[
                match_keys[0]
            ].transform("size")
            valid_df.loc[group_sizes == 1, config.match.output_column] = pd.NA

    output_df = valid_df.reindex(columns=config.output.columns)
    output_written = False
    status = "completed" if not error_rows else "failed"
    stop_reason: str | None = None
    stop_message: str | None = None

    if error_rows:
        output_df = pd.DataFrame(columns=config.output.columns)
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
    return MatchResult(
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


def _assign_match_ids(
    frame: pd.DataFrame,
    match_keys: list[str],
    config: MatchConfig,
) -> list[str]:
    group_map: dict[tuple[Any, ...], str] = {}
    assigned: list[str] = []
    sequence = 1
    for _, row in frame.iterrows():
        key = tuple(row[column] for column in match_keys)
        if key not in group_map:
            group_map[key] = f"{config.match.id_prefix}{sequence:0{config.match.id_padding}d}"
            sequence += 1
        assigned.append(group_map[key])
    return assigned


def _load_match_input(
    input_name: str,
    config: MatchConfig,
    base_path: Path,
) -> pd.DataFrame:
    input_config = config.input_
    if not input_config.header:
        raise CsvReadError("input.header: false is not supported in match")
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


def _missing_match_key_mask(frame: pd.DataFrame, match_keys: list[str]) -> pd.Series:
    mask = pd.Series(False, index=frame.index)
    for column in match_keys:
        values = frame[column]
        mask = mask | values.isna() | (
            values.astype("string").str.strip() == ""
        )
    return mask


def _build_error_rows(
    frame: pd.DataFrame,
    *,
    input_name: str,
    field: str,
    rule: str,
    message: str,
) -> list[MatchErrorRow]:
    rows: list[MatchErrorRow] = []
    for _, row in frame.iterrows():
        row_json = {column: _serialize_value(value) for column, value in row.items()}
        rows.append(
            MatchErrorRow(
                input_name=input_name,
                row_number=int(row["__row_number"]),
                stage="match",
                field=field,
                rule=rule,
                message=message,
                row_json=row_json,
            )
        )
    return rows


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
