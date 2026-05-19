"""Report writers for merge execution."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from datamapx.io.errors import CsvWriteError
from datamapx.merge.config import MergeConfig
from datamapx.merge.errors import MergeErrorRow, MergeSkippedRow
from datamapx.merge.runner import MergeResult
from datamapx.report.summary import ReportPaths


def resolve_merge_report_paths(
    config: MergeConfig,
    config_path: Path,
    reports_dir: Path | None = None,
) -> ReportPaths:
    """Resolve merge report output paths."""

    if reports_dir is not None:
        return ReportPaths(
            errors_csv=reports_dir / "errors.csv",
            skipped_csv=reports_dir / "skipped.csv",
            summary_json=reports_dir / "summary.json",
        )

    base_path = config_path.parent
    errors_csv = _resolve_path(config.error_handling.error_output, base_path)
    skipped_csv = _resolve_path(config.error_handling.skipped_output, base_path)
    summary_json = (
        _resolve_path(config.runtime.summary_output, base_path)
        if config.runtime.summary_output
        else errors_csv.with_name("summary.json")
    )
    return ReportPaths(errors_csv=errors_csv, skipped_csv=skipped_csv, summary_json=summary_json)


def write_merge_reports(
    result: MergeResult,
    config: MergeConfig,
    config_path: Path,
    reports_dir: Path | None = None,
) -> ReportPaths:
    """Write merge error/skipped/summary reports."""

    report_paths = resolve_merge_report_paths(config, config_path, reports_dir)
    try:
        if reports_dir is not None:
            reports_dir.mkdir(parents=True, exist_ok=True)
        else:
            report_paths.errors_csv.parent.mkdir(parents=True, exist_ok=True)
            report_paths.skipped_csv.parent.mkdir(parents=True, exist_ok=True)
            report_paths.summary_json.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CsvWriteError(
            f"{reports_dir or config_path}: cannot create report directory: {exc}"
        ) from exc

    _write_errors_csv(report_paths.errors_csv, result.error_rows, result.run_id)
    _write_skipped_csv(report_paths.skipped_csv, result.skipped_rows, result.run_id)
    _write_summary_json(report_paths.summary_json, result, config, config_path, report_paths)
    return report_paths


def _write_errors_csv(path: Path, error_rows: list[MergeErrorRow], run_id: str) -> None:
    rows = [
        {
            "run_id": run_id,
            "input_name": row.input_name,
            "row_number": row.row_number,
            "stage": row.stage,
            "field": row.field,
            "rule": row.rule,
            "message": row.message,
            "row_json": _json_dumps(row.row_json),
        }
        for row in error_rows
    ]
    _write_csv(
        path,
        rows,
        ["run_id", "input_name", "row_number", "stage", "field", "rule", "message", "row_json"],
    )


def _write_skipped_csv(path: Path, skipped_rows: list[MergeSkippedRow], run_id: str) -> None:
    rows = [
        {
            "run_id": run_id,
            "row_number": row.row_number,
            "reason": row.reason,
            "row_json": _json_dumps(row.row_json),
        }
        for row in skipped_rows
    ]
    _write_csv(path, rows, ["run_id", "row_number", "reason", "row_json"])


def _write_summary_json(
    path: Path,
    result: MergeResult,
    config: MergeConfig,
    config_path: Path,
    report_paths: ReportPaths,
) -> None:
    payload = {
        "run_id": result.run_id,
        "project_name": result.project_name,
        "status": result.status,
        "config_path": str(config_path),
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "inputs": [asdict(input_summary) for input_summary in result.inputs],
        "output": {
            "name": result.output_name,
            "path": result.output_path,
            "columns": config.output.columns,
            "rows_written": result.output_rows,
        },
        "counts": {
            "input_rows": result.input_rows,
            "output_rows": result.output_rows,
            "skipped_rows": result.skipped_count,
            "error_rows": result.error_count,
        },
        "reports": {
            "errors_csv": str(report_paths.errors_csv),
            "skipped_csv": str(report_paths.skipped_csv),
            "summary_json": str(report_paths.summary_json),
        },
        "notes": {
            "merge": True,
            "output_file_written": result.output_file_written,
        },
    }
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        raise CsvWriteError(f"{path}: cannot write summary.json: {exc}") from exc


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows, columns=columns).to_csv(
            path,
            index=False,
            encoding="utf-8",
            quoting=csv.QUOTE_MINIMAL,
        )
    except OSError as exc:
        raise CsvWriteError(f"{path}: cannot write report CSV: {exc}") from exc


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _resolve_path(path: str, base_path: Path) -> Path:
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return base_path / resolved
