"""Lightweight execution runner for datamapx."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from datamapx.config import DatamapxConfig, ErrorHandlingConfig
from datamapx.io.csv_reader import read_input_csv, read_reference_csv
from datamapx.io.csv_writer import resolve_output_path
from datamapx.transform.checks import CheckResult, evaluate_checks
from datamapx.transform.error_policy import (
    StopInfo,
    evaluate_max_errors,
    evaluate_validation_stop_policy,
)
from datamapx.transform.filters import SkippedRow
from datamapx.transform.row_executor import (
    build_output_from_prepared_rows,
    prepare_rowwise_inputs,
)
from datamapx.validation import (
    ValidationErrorRow,
    ValidationResult,
    validate_input_rows,
    validate_output_rows,
)


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
class OutputExecutionResult:
    """Result for one configured output."""

    name: str
    path: str
    file_written: bool
    rows: int
    columns: list[str]
    preview_df: pd.DataFrame
    validation_error_rows: list[ValidationErrorRow]


@dataclass(frozen=True)
class DryRunResult:
    """Result of dry-run through output dataframe construction."""

    run_id: str
    started_at: str
    finished_at: str
    dry_run: bool
    output_file_written: bool
    load_result: LoadPhaseResult
    output_results: list[OutputExecutionResult]
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
    check_results: list[CheckResult]
    error_handling: ErrorHandlingConfig
    stop_reason: str | None
    stop_message: str | None
    max_errors_exceeded: bool
    fatal_error: bool
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

    @property
    def check_failure_count(self) -> int:
        return sum(1 for check in self.check_results if not check.passed)

    @property
    def check_success_count(self) -> int:
        return sum(1 for check in self.check_results if check.passed)

    @property
    def has_check_failures(self) -> bool:
        return self.check_failure_count > 0


@dataclass(frozen=True)
class RunResult:
    """Result of a full run including file writes."""

    run_id: str
    started_at: str
    finished_at: str
    dry_run: bool
    output_file_written: bool
    load_result: LoadPhaseResult
    output_results: list[OutputExecutionResult]
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
    check_results: list[CheckResult]
    error_handling: ErrorHandlingConfig
    stop_reason: str | None
    stop_message: str | None
    max_errors_exceeded: bool
    fatal_error: bool
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

    @property
    def check_failure_count(self) -> int:
        return sum(1 for check in self.check_results if not check.passed)

    @property
    def check_success_count(self) -> int:
        return sum(1 for check in self.check_results if check.passed)

    @property
    def has_check_failures(self) -> bool:
        return self.check_failure_count > 0


def run_load_phase(
    config: DatamapxConfig,
    base_path: Path | None = None,
    limit: int | None = None,
) -> LoadPhaseResult:
    """Load input and reference CSVs, applying schema and key checks only."""

    input_name, input_config = next(iter(config.inputs.items()))
    input_df = read_input_csv(
        input_name,
        input_config,
        base_path,
        limit=limit,
        max_rows=config.runtime.max_input_rows,
    )

    reference_summaries: list[ReferenceLoadSummary] = []
    reference_dfs: dict[str, pd.DataFrame] = {}
    for reference_name, reference_config in config.references.items():
        reference_df = read_reference_csv(
            reference_name,
            reference_config,
            base_path,
            max_rows=config.runtime.max_reference_rows,
        )
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
        output_results=execution.output_results,
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
        check_results=execution.check_results,
        error_handling=execution.error_handling,
        stop_reason=execution.stop_reason,
        stop_message=execution.stop_message,
        max_errors_exceeded=execution.max_errors_exceeded,
        fatal_error=execution.fatal_error,
        status=(
            "dry_run_completed_with_check_failures"
            if any(not check.passed for check in execution.check_results)
            else "failed"
            if execution.fatal_error
            else "dry_run_completed"
        ),
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
        output_results=execution.output_results,
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
        check_results=execution.check_results,
        error_handling=execution.error_handling,
        stop_reason=execution.stop_reason,
        stop_message=execution.stop_message,
        max_errors_exceeded=execution.max_errors_exceeded,
        fatal_error=execution.fatal_error,
        status=(
            "completed_with_check_failures"
            if any(not check.passed for check in execution.check_results)
            else "failed"
            if execution.fatal_error
            else "completed"
        ),
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
    output_results: list[OutputExecutionResult]
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
    check_results: list[CheckResult]
    error_handling: ErrorHandlingConfig
    stop_reason: str | None
    stop_message: str | None
    max_errors_exceeded: bool
    fatal_error: bool
    status: str


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
    primary_output_name = next(iter(config.outputs))
    input_validation_result = validate_input_rows(
        config,
        load_result.input_df,
        input_name,
    )
    validation_stop = evaluate_validation_stop_policy(
        config.error_handling,
        input_validation_result.error_rows,
    )
    if validation_stop is not None:
        finished_at = _timestamp(datetime.now())
        return _build_failed_execution_result(
            config=config,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            load_result=load_result,
            output_results=[],
            input_validation_result=input_validation_result,
            input_rows_before_filter=input_validation_result.rows_after_validation,
            input_rows_after_filter=input_validation_result.rows_after_validation,
            skipped_rows=[],
            output_rows=0,
            output_name=primary_output_name,
            output_preview_df=pd.DataFrame(),
            base_path=base_path,
            stop_info=validation_stop,
            check_results=[],
        )

    row_preparation = prepare_rowwise_inputs(
        config=config,
        input_df=input_validation_result.dataframe,
        input_name=input_name,
        reference_dfs=load_result.reference_dfs,
        base_error_count=len(input_validation_result.error_rows),
    )
    if row_preparation.stop_info is not None:
        finished_at = _timestamp(datetime.now())
        return _build_failed_execution_result(
            config=config,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            load_result=load_result,
            output_results=[],
            input_validation_result=input_validation_result,
            input_rows_before_filter=row_preparation.input_rows_before_filter,
            input_rows_after_filter=row_preparation.input_rows_after_filter,
            skipped_rows=row_preparation.skipped_rows,
            output_rows=0,
            output_name=primary_output_name,
            output_preview_df=pd.DataFrame(),
            base_path=base_path,
            stop_info=row_preparation.stop_info,
            check_results=[],
            mapping_error_rows=row_preparation.mapping_error_rows,
        )

    output_results: list[OutputExecutionResult] = []
    output_error_rows: list[ValidationErrorRow] = []
    output_validation_error_rows: list[ValidationErrorRow] = []
    last_output_preview_df = pd.DataFrame()
    last_output_name = primary_output_name

    for output_name, output_config in config.outputs.items():
        output_build_result = build_output_from_prepared_rows(
            config=config,
            prepared_rows=row_preparation.prepared_rows,
            output_columns=output_config.columns,
            reference_dfs=load_result.reference_dfs,
            output_name=output_name,
            base_error_count=len(input_validation_result.error_rows)
            + len(row_preparation.mapping_error_rows)
            + len(output_error_rows),
        )
        if output_build_result.stop_info is not None:
            output_error_rows = output_error_rows + output_build_result.mapping_error_rows
            finished_at = _timestamp(datetime.now())
            preview_df = output_build_result.output_df
            failed_output_rows = output_results[0].rows if output_results else len(preview_df)
            return _build_failed_execution_result(
                config=config,
                run_id=run_id,
                started_at=started_at,
                finished_at=finished_at,
                load_result=load_result,
                output_results=output_results,
                input_validation_result=input_validation_result,
                input_rows_before_filter=row_preparation.input_rows_before_filter,
                input_rows_after_filter=row_preparation.input_rows_after_filter,
                skipped_rows=row_preparation.skipped_rows,
                output_rows=failed_output_rows,
                output_name=output_name,
                output_preview_df=preview_df,
                base_path=base_path,
                stop_info=output_build_result.stop_info,
                check_results=[],
                mapping_error_rows=row_preparation.mapping_error_rows
                + output_error_rows,
                output_validation_result=None,
            )

        output_validation_result = validate_output_rows(
            config,
            output_build_result.output_df,
            output_build_result.output_row_numbers,
            output_name,
        )
        output_error_rows = output_error_rows + output_build_result.mapping_error_rows
        output_error_rows = output_error_rows + output_validation_result.error_rows
        output_validation_error_rows = (
            output_validation_error_rows + output_validation_result.error_rows
        )
        output_result = OutputExecutionResult(
            name=output_name,
            path=str(resolve_output_path(output_config.path, base_path)),
            file_written=False,
            rows=len(output_validation_result.dataframe),
            columns=list(output_validation_result.dataframe.columns),
            preview_df=output_validation_result.dataframe,
            validation_error_rows=output_validation_result.error_rows,
        )
        output_results.append(output_result)
        last_output_preview_df = output_validation_result.dataframe
        last_output_name = output_name

        error_rows = (
            input_validation_result.error_rows
            + row_preparation.mapping_error_rows
            + output_error_rows
        )
        max_errors_stop = evaluate_max_errors(config.error_handling, len(error_rows))
        if max_errors_stop is not None:
            finished_at = _timestamp(datetime.now())
            return _build_failed_execution_result(
                config=config,
                run_id=run_id,
                started_at=started_at,
                finished_at=finished_at,
                load_result=load_result,
                output_results=output_results,
                input_validation_result=input_validation_result,
                input_rows_before_filter=row_preparation.input_rows_before_filter,
                input_rows_after_filter=row_preparation.input_rows_after_filter,
                skipped_rows=row_preparation.skipped_rows,
                output_rows=output_results[0].rows if output_results else 0,
                output_name=last_output_name,
                output_preview_df=last_output_preview_df,
                base_path=base_path,
                stop_info=max_errors_stop,
                check_results=[],
                mapping_error_rows=row_preparation.mapping_error_rows + output_error_rows,
                output_validation_result=output_validation_result,
            )

        validation_error_rows = (
            input_validation_result.error_rows + output_validation_error_rows
        )
        validation_stop = evaluate_validation_stop_policy(
            config.error_handling,
            validation_error_rows,
        )
        if validation_stop is not None:
            finished_at = _timestamp(datetime.now())
            return _build_failed_execution_result(
                config=config,
                run_id=run_id,
                started_at=started_at,
                finished_at=finished_at,
                load_result=load_result,
                output_results=output_results,
                input_validation_result=input_validation_result,
                input_rows_before_filter=row_preparation.input_rows_before_filter,
                input_rows_after_filter=row_preparation.input_rows_after_filter,
                skipped_rows=row_preparation.skipped_rows,
                output_rows=output_results[0].rows if output_results else 0,
                output_name=last_output_name,
                output_preview_df=last_output_preview_df,
                base_path=base_path,
                stop_info=validation_stop,
                check_results=[],
                mapping_error_rows=row_preparation.mapping_error_rows + output_error_rows,
                output_validation_result=output_validation_result,
            )

    primary_output_rows = output_results[0].rows if output_results else 0
    total_error_rows = (
        len(input_validation_result.error_rows)
        + len(row_preparation.mapping_error_rows)
        + len(output_error_rows)
    )
    check_context = {
        "input_rows": load_result.input_rows,
        "output_rows": primary_output_rows,
        "error_rows": total_error_rows,
        "skipped_rows": len(row_preparation.skipped_rows),
    }
    check_results = evaluate_checks(config.checks, check_context)
    status = (
        "completed_with_check_failures"
        if any(not check.passed for check in check_results)
        else "completed"
    )
    finished_at = _timestamp(datetime.now())
    primary_output = output_results[0] if output_results else OutputExecutionResult(
        name=primary_output_name,
        path=str(resolve_output_path(config.outputs[primary_output_name].path, base_path)),
        file_written=False,
        rows=0,
        columns=list(config.outputs[primary_output_name].columns),
        preview_df=pd.DataFrame(columns=config.outputs[primary_output_name].columns),
        validation_error_rows=[],
    )
    return ExecutionResult(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        load_result=load_result,
        output_results=output_results,
        output_name=primary_output.name,
        output_path=primary_output.path,
        output_rows=primary_output_rows,
        output_columns=primary_output.columns,
        output_preview_df=primary_output.preview_df,
        input_rows_before_validation=load_result.input_rows,
        input_rows_after_validation=input_validation_result.rows_after_validation,
        input_rows_before_filter=row_preparation.input_rows_before_filter,
        input_rows_after_filter=row_preparation.input_rows_after_filter,
        skipped_rows=row_preparation.skipped_rows,
        error_rows=input_validation_result.error_rows
        + row_preparation.mapping_error_rows
        + output_error_rows,
        check_results=check_results,
        error_handling=config.error_handling,
        stop_reason=None,
        stop_message=None,
        max_errors_exceeded=False,
        fatal_error=False,
        status=status,
    )


def _build_failed_execution_result(
    *,
    config: DatamapxConfig,
    run_id: str,
    started_at: str,
    finished_at: str,
    load_result: LoadPhaseResult,
    output_results: list[OutputExecutionResult],
    input_validation_result: ValidationResult,
    input_rows_before_filter: int,
    input_rows_after_filter: int,
    skipped_rows: list[SkippedRow],
    output_rows: int,
    output_name: str,
    output_preview_df: pd.DataFrame,
    base_path: Path | None,
    stop_info: StopInfo,
    check_results: list[CheckResult],
    mapping_error_rows: list[ValidationErrorRow] | None = None,
    output_validation_result: ValidationResult | None = None,
) -> ExecutionResult:
    error_rows = input_validation_result.error_rows
    if mapping_error_rows:
        error_rows = error_rows + mapping_error_rows
    if output_validation_result is not None:
        error_rows = error_rows + output_validation_result.error_rows
    output_columns = list(output_preview_df.columns)
    return ExecutionResult(
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        load_result=load_result,
        output_results=output_results,
        output_name=output_name,
        output_path=str(resolve_output_path(config.outputs[output_name].path, base_path)),
        output_rows=output_rows,
        output_columns=output_columns,
        output_preview_df=output_preview_df,
        input_rows_before_validation=load_result.input_rows,
        input_rows_after_validation=input_validation_result.rows_after_validation,
        input_rows_before_filter=input_rows_before_filter,
        input_rows_after_filter=input_rows_after_filter,
        skipped_rows=skipped_rows,
        error_rows=error_rows,
        check_results=check_results,
        error_handling=config.error_handling,
        stop_reason=stop_info.reason,
        stop_message=stop_info.message,
        max_errors_exceeded=stop_info.max_errors_exceeded,
        fatal_error=True,
        status="failed",
    )
