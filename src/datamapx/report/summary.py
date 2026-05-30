"""Report path and payload helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datamapx.config import DatamapxConfig
from datamapx.runner import DryRunResult


@dataclass(frozen=True)
class ReportPaths:
    """Resolved report file paths."""

    errors_csv: Path
    skipped_csv: Path
    summary_json: Path
    html_report: Path | None = None


def resolve_report_paths(
    config: DatamapxConfig,
    config_path: Path,
    reports_dir: Path | None = None,
    *,
    html_report: bool = False,
) -> ReportPaths:
    """Resolve report output paths for dry-run report writing."""

    if reports_dir is not None:
        html_path = reports_dir / "report.html" if html_report else None
        return ReportPaths(
            errors_csv=reports_dir / "errors.csv",
            skipped_csv=reports_dir / "skipped.csv",
            summary_json=reports_dir / "summary.json",
            html_report=html_path,
        )

    base_path = config_path.parent
    errors_csv = _resolve_path(config.error_handling.error_output, base_path)
    skipped_csv = _resolve_path(config.error_handling.skipped_output, base_path)
    summary_json = (
        _resolve_path(config.runtime.summary_output, base_path)
        if config.runtime.summary_output
        else errors_csv.with_name("summary.json")
    )
    html_path = summary_json.with_name("report.html") if html_report else None
    return ReportPaths(
        errors_csv=errors_csv,
        skipped_csv=skipped_csv,
        summary_json=summary_json,
        html_report=html_path,
    )


def build_summary_payload(
    result: DryRunResult,
    config: DatamapxConfig,
    config_path: Path,
    report_paths: ReportPaths,
) -> dict[str, Any]:
    """Build the JSON payload for summary.json."""

    load_result = result.load_result
    primary_output = result.output_results[0] if result.output_results else None
    output_name = result.output_name
    output_config = config.outputs[output_name]
    reference_rows = [
        {
            "name": reference.name,
            "path": reference.path,
            "rows_loaded": reference.rows,
            "key": reference.key,
        }
        for reference in load_result.references
    ]
    outputs = [
        {
            "name": output_result.name,
            "path": output_result.path,
            "file_written": output_result.file_written,
            "columns": output_result.columns,
            "rows_previewed": output_result.rows,
        }
        for output_result in result.output_results
    ]
    limit = load_result.limit
    notes: dict[str, Any] = {
        "dry_run": result.dry_run,
        "output_file_written": result.output_file_written,
        "checks_passed": not result.has_check_failures,
        "completed_with_row_errors": result.total_error_count > 0 and not result.fatal_error,
        "final_outcome": _final_outcome(result),
        "fatal_error": getattr(result, "fatal_error", False),
        "stop_reason": getattr(result, "stop_reason", None),
        "stop_message": getattr(result, "stop_message", None),
        "max_errors_exceeded": getattr(result, "max_errors_exceeded", False),
    }
    if limit is not None:
        notes["limited_run"] = True
        notes["limit"] = limit
    return {
        "run_id": result.run_id,
        "project_name": load_result.project_name,
        "status": result.status,
        "config_path": str(config_path),
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "error_handling": config.error_handling.model_dump(mode="python"),
        "input": {
            "name": load_result.input_name,
            "path": load_result.input_path,
            "rows_loaded": load_result.input_rows,
            "rows_after_input_validation": result.input_rows_after_validation,
            "rows_after_filter": result.input_rows_after_filter,
        },
        "references": reference_rows,
        "output": {
            "name": output_name,
            "path": result.output_path,
            "columns": output_config.columns,
            "rows_previewed": (
                primary_output.rows if primary_output is not None else result.output_rows
            ),
        },
        "outputs": outputs,
        "counts": {
            "input_rows": result.input_rows_before_validation,
            "skipped_rows": result.skipped_count,
            "error_rows": result.total_error_count,
            "validation_errors": _count_error_rows(
                result.error_rows,
                stages={"input_validation", "output_validation"},
            ),
            "mapping_errors": _count_error_rows(result.error_rows, stages={"mapping"}),
            "lookup_missing_errors": _count_error_rows(
                result.error_rows,
                stages={"mapping"},
                rules={"lookup_missing"},
            ),
            "transform_errors": _count_error_rows(
                result.error_rows,
                stages={"mapping"},
                rules={"transform_error"},
            ),
            "input_validation_errors": result.input_validation_error_count,
            "output_validation_errors": result.output_validation_error_count,
            "check_failures": result.check_failure_count,
            "check_successes": result.check_success_count,
            "output_rows": result.output_rows,
        },
        "checks": [
            {
                "name": check.name,
                "rule": check.rule,
                "passed": check.passed,
                "evaluated_value": check.evaluated_value,
                "message": check.message,
            }
            for check in result.check_results
        ],
        "reports": {
            "errors_csv": str(report_paths.errors_csv),
            "skipped_csv": str(report_paths.skipped_csv),
            "summary_json": str(report_paths.summary_json),
        },
        "notes": notes,
    }


def _resolve_path(path: str, base_path: Path) -> Path:
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return base_path / resolved


def _count_error_rows(
    error_rows: list[Any],
    *,
    stages: set[str] | None = None,
    rules: set[str] | None = None,
) -> int:
    count = 0
    for row in error_rows:
        if stages is not None and row.stage not in stages:
            continue
        if rules is not None and row.rule not in rules:
            continue
        count += 1
    return count


def _final_outcome(result: DryRunResult) -> str:
    if getattr(result, "fatal_error", False):
        return "failed"
    if result.has_check_failures:
        return "completed_with_check_failures"
    if result.total_error_count > 0:
        return "completed_with_row_errors"
    return "success"
