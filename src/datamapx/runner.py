"""Lightweight execution runner for datamapx."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from datamapx.config import DatamapxConfig
from datamapx.io.csv_reader import read_input_csv, read_reference_csv
from datamapx.io.csv_writer import resolve_output_path
from datamapx.transform.filters import SkippedRow, apply_filters
from datamapx.transform.mapper import build_output_dataframe, compute_derived_fields
from datamapx.validation import ValidationErrorRow, validate_input_rows, validate_output_rows


@dataclass(frozen=True)
class ReferenceLoadSummary:
    """Summary for one loaded reference CSV."""

    name: str
    path: str
    rows: int
    key: str | list[str]


@dataclass(frozen=True)
class LoadPhaseResult:
    """Result of the dry-run load phase."""

    project_name: str
    input_name: str
    input_path: str
    input_rows: int
    input_columns: list[str]
    references: list[ReferenceLoadSummary]
    limit: int | None
    status: str
    input_df: pd.DataFrame
    reference_dfs: dict[str, pd.DataFrame]


@dataclass(frozen=True)
class DryRunResult:
    """Result of dry-run through output dataframe construction."""

    run_id: str
    started_at: str
    finished_at: str
    dry_run: bool
    output_file_written: bool
    load_result: LoadPhaseResult
    output_name: str
    output_path: str
    output_rows: int
    output_columns: list[str]
    output_preview_df: pd.DataFrame
    input_rows_before_validation: int
    input_rows_after_validation: int
    input_rows_before_filter: int
    input_rows_after_filter: int
    skipped_rows: list[SkippedRow]
    error_rows: list[ValidationErrorRow]
    status: str

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_rows)

    @property
    def input_validation_error_count(self) -> int:
        return sum(1 for row in self.error_rows if row.stage == "input_validation")

    @property
    def output_validation_error_count(self) -> int:
        return sum(1 for row in self.error_rows if row.stage == "output_validation")

    @property
    def total_error_count(self) -> int:
        return len(self.error_rows)


@dataclass(frozen=True)
class RunResult:
    """Result of a full run including file writes."""

    run_id: str
    started_at: str
    finished_at: str
    dry_run: bool
    output_file_written: bool
    load_result: LoadPhaseResult
    output_name: str
    output_path: str
    output_rows: int
    output_columns: list[str]
    output_preview_df: pd.DataFrame
    input_rows_before_validation: int
    input_rows_after_validation: int
    input_rows_before_filter: int
    input_rows_after_filter: int
    skipped_rows: list[SkippedRow]
    error_rows: list[ValidationErrorRow]
    status: str

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_rows)

    @property
    def input_validation_error_count(self) -> int:
        return sum(1 for row in self.error_rows if row.stage == "input_validation")

    @property
    def output_validation_error_count(self) -> int:
        return sum(1 for row in self.error_rows if row.stage == "output_validation")

    @property
    def total_error_count(self) -> int:
        return len(self.error_rows)


def run_load_phase(
    config: DatamapxConfig,
    base_path: Path | None = None,
    limit: int | None = None,
) -> LoadPhaseResult:
    """Load input and reference CSVs, applying schema and key checks only."""

    input_name, input_config = next(iter(config.inputs.items()))
    input_df = read_input_csv(input_name, input_config, base_path, limit=limit)

    reference_summaries: list[ReferenceLoadSummary] = []
    reference_dfs: dict[str, pd.DataFrame] = {}
    for reference_name, reference_config in config.references.items():
        reference_df = read_reference_csv(reference_name, reference_config, base_path)
        reference_dfs[reference_name] = reference_df
        reference_summaries.append(
            ReferenceLoadSummary(
                name=reference_name,
                path=reference_config.path,
                rows=len(reference_df),
                key=reference_config.key,
            )
        )

    return LoadPhaseResult(
        project_name=config.project.name,
        input_name=input_name,
        input_path=input_config.path,
        input_rows=len(input_df),
        input_columns=[
            column for column in input_df.columns if column != "__row_number"
        ],
        references=reference_summaries,
        limit=limit,
        status="load_phase_completed",
        input_df=input_df,
        reference_dfs=reference_dfs,
    )


def run_dry_run(
    config: DatamapxConfig,
    base_path: Path | None = None,
    limit: int | None = None,
) -> DryRunResult:
    """Run load phase and supported mappings without writing output files."""

    execution = _execute_pipeline(config, base_path, limit)
    return DryRunResult(
        run_id=execution.run_id,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        dry_run=True,
        output_file_written=False,
        load_result=execution.load_result,
        output_name=execution.output_name,
        output_path=execution.output_path,
        output_rows=execution.output_rows,
        output_columns=execution.output_columns,
        output_preview_df=execution.output_preview_df,
        input_rows_before_validation=execution.input_rows_before_validation,
        input_rows_after_validation=execution.input_rows_after_validation,
        input_rows_before_filter=execution.input_rows_before_filter,
        input_rows_after_filter=execution.input_rows_after_filter,
        skipped_rows=execution.skipped_rows,
        error_rows=execution.error_rows,
        status="dry_run_completed",
    )


def run_pipeline(
    config: DatamapxConfig,
    base_path: Path | None = None,
) -> RunResult:
    """Run the full pipeline and write no files by itself."""

    execution = _execute_pipeline(config, base_path, limit=None)
    return RunResult(
        run_id=execution.run_id,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        dry_run=False,
        output_file_written=False,
        load_result=execution.load_result,
        output_name=execution.output_name,
        output_path=execution.output_path,
        output_rows=execution.output_rows,
        output_columns=execution.output_columns,
        output_preview_df=execution.output_preview_df,
        input_rows_before_validation=execution.input_rows_before_validation,
        input_rows_after_validation=execution.input_rows_after_validation,
        input_rows_before_filter=execution.input_rows_before_filter,
        input_rows_after_filter=execution.input_rows_after_filter,
        skipped_rows=execution.skipped_rows,
        error_rows=execution.error_rows,
        status="completed",
    )


def _resolve_run_id(config_run_id: str, started_at: datetime) -> str:
    if config_run_id != "auto":
        return config_run_id
    return started_at.strftime("%Y%m%d_%H%M%S")


def _timestamp(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


@dataclass(frozen=True)
class ExecutionResult:
    """Internal shared pipeline result."""

    run_id: str
    started_at: str
    finished_at: str
    load_result: LoadPhaseResult
    output_name: str
    output_path: str
    output_rows: int
    output_columns: list[str]
    output_preview_df: pd.DataFrame
    input_rows_before_validation: int
    input_rows_after_validation: int
    input_rows_before_filter: int
    input_rows_after_filter: int
    skipped_rows: list[SkippedRow]
    error_rows: list[ValidationErrorRow]


def _execute_pipeline(
    config: DatamapxConfig,
    base_path: Path | None,
    limit: int | None,
) -> ExecutionResult:
    started_at_dt = datetime.now()
    started_at = _timestamp(started_at_dt)
    run_id = _resolve_run_id(config.runtime.run_id, started_at_dt)
    load_result = run_load_phase(config, base_path, limit)
    input_name = next(iter(config.inputs))
    output_name = next(iter(config.outputs))
    input_validation_result = validate_input_rows(
        config,
        load_result.input_df,
        input_name,
    )
    derived_values = compute_derived_fields(
        config,
        input_validation_result.dataframe,
        load_result.reference_dfs,
    )
    filter_result = apply_filters(
        config,
        input_validation_result.dataframe,
        input_name,
        derived_values,
    )
    output_df_before_validation = build_output_dataframe(
        config,
        filter_result.input_df,
        reference_dfs=load_result.reference_dfs,
        derived_values=filter_result.derived_values,
    )
    output_row_numbers = filter_result.input_df["__row_number"].reset_index(drop=True)
    output_validation_result = validate_output_rows(
        config,
        output_df_before_validation,
        output_row_numbers,
        output_name,
    )
    finished_at = _timestamp(datetime.now())
    output_path = str(resolve_output_path(config.outputs[output_name].path, base_path))
    return ExecutionResult(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        load_result=load_result,
        output_name=output_name,
        output_path=output_path,
        output_rows=len(output_validation_result.dataframe),
        output_columns=list(output_validation_result.dataframe.columns),
        output_preview_df=output_validation_result.dataframe,
        input_rows_before_validation=load_result.input_rows,
        input_rows_after_validation=input_validation_result.rows_after_validation,
        input_rows_before_filter=filter_result.rows_before_filter,
        input_rows_after_filter=filter_result.rows_after_filter,
        skipped_rows=filter_result.skipped_rows,
        error_rows=input_validation_result.error_rows + output_validation_result.error_rows,
    )
