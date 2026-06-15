"""Unpivot pipeline for datamapx."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from datamapx.io.csv_reader import apply_schema, read_csv_frame
from datamapx.io.csv_writer import resolve_output_path
from datamapx.io.errors import CsvReadError
from datamapx.transform.errors import MappingError
from datamapx.transform.filters import apply_filters
from datamapx.unpivot.config import UnpivotConfig
from datamapx.unpivot.errors import UnpivotError, UnpivotErrorRow, UnpivotSkippedRow


@dataclass(frozen=True)
class UnpivotInputSummary:
    """Summary for the unpivot input."""

    name: str
    path: str
    rows_loaded: int


@dataclass(frozen=True)
class UnpivotResult:
    """Unpivot execution result."""

    run_id: str
    project_name: str
    status: str
    started_at: str
    finished_at: str
    config_path: str
    output_name: str
    output_path: str
    output_df: pd.DataFrame
    inputs: list[UnpivotInputSummary]
    error_rows: list[UnpivotErrorRow]
    skipped_rows: list[UnpivotSkippedRow]
    input_rows: int
    output_rows: int
    error_count: int
    skipped_count: int
    output_file_written: bool = False
    stop_reason: str | None = None
    stop_message: str | None = None


def run_unpivot_pipeline(
    config: UnpivotConfig,
    config_path: Path,
) -> UnpivotResult:
    """Run the unpivot pipeline and return the expanded dataframe and reports."""

    started_at = _utc_now()
    run_id = _resolve_run_id(config.runtime.run_id)
    input_name = "input"
    input_df = _load_unpivot_input(
        input_name,
        config,
        config_path.parent,
    )
    input_summary = UnpivotInputSummary(
        name=input_name,
        path=config.input_.path,
        rows_loaded=len(input_df),
    )
    try:
        filter_result = apply_filters(
            config,
            input_df,
            input_name,
            {},
        )
    except MappingError as exc:
        raise UnpivotError(str(exc)) from exc
    input_df = filter_result.input_df

    output_records: list[dict[str, Any]] = []
    skipped_rows = [
        UnpivotSkippedRow(
            row_number=int(row.row_number),
            reason=row.reason,
            row_json=row.normalized_row,
        )
        for row in filter_result.skipped_rows
    ]
    error_rows: list[UnpivotErrorRow] = []
    id_columns = list(config.unpivot.id_columns)
    variable_column = config.unpivot.variable_column
    value_column = config.unpivot.value_column

    for _, row in input_df.iterrows():
        base_row = {column: row[column] for column in id_columns}
        for source_column, variable_value in config.unpivot.value_columns.items():
            value = row[source_column]
            if config.unpivot.drop_null_values and _is_nullish(value):
                continue
            output_records.append(
                {
                    **base_row,
                    variable_column: variable_value,
                    value_column: value,
                }
            )

    output_columns = config.output.columns
    output_df = pd.DataFrame(output_records, columns=output_columns)
    output_written = False
    status = "completed"
    stop_reason: str | None = None
    stop_message: str | None = None
    if (
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
    return UnpivotResult(
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
        input_rows=input_summary.rows_loaded,
        output_rows=len(output_df),
        error_count=len(error_rows),
        skipped_count=len(skipped_rows),
        output_file_written=output_written,
        stop_reason=stop_reason,
        stop_message=stop_message,
    )


def _load_unpivot_input(
    input_name: str,
    config: UnpivotConfig,
    base_path: Path,
) -> pd.DataFrame:
    input_config = config.input_
    if not input_config.header:
        raise CsvReadError("input.header: false is not supported in unpivot")
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


def _is_nullish(value: Any) -> bool:
    if pd.isna(value):
        return True
    return isinstance(value, str) and value.strip() == ""


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
