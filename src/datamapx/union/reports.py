"""Report writers for union execution."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from datamapx.io.errors import CsvWriteError
from datamapx.report.atomic import atomic_write
from datamapx.report.html import write_html_report
from datamapx.report.summary import ReportPaths
from datamapx.union.config import UnionConfig
from datamapx.union.errors import UnionErrorRow, UnionSkippedRow
from datamapx.union.runner import UnionResult


def resolve_union_report_paths(
    config: UnionConfig,
    config_path: Path,
    reports_dir: Path | None = None,
    *,
    html_report: bool = False,
) -> ReportPaths:
    """Resolve union report output paths."""

    if reports_dir is not None:
        return ReportPaths(
            errors_csv=reports_dir / "errors.csv",
            skipped_csv=reports_dir / "skipped.csv",
            summary_json=reports_dir / "summary.json",
            html_report=reports_dir / "report.html" if html_report else None,
        )

    base_path = config_path.parent
    errors_csv = _resolve_path(config.error_handling.error_output, base_path)
    skipped_csv = _resolve_path(config.error_handling.skipped_output, base_path)
    summary_json = (
        _resolve_path(config.runtime.summary_output, base_path)
        if config.runtime.summary_output
        else errors_csv.with_name("summary.json")
    )
    return ReportPaths(
        errors_csv=errors_csv,
        skipped_csv=skipped_csv,
        summary_json=summary_json,
        html_report=summary_json.with_name("report.html") if html_report else None,
    )


def write_union_reports(
    result: UnionResult,
    config: UnionConfig,
    config_path: Path,
    reports_dir: Path | None = None,
    *,
    html_report: bool = False,
) -> ReportPaths:
    """Write union error/skipped/summary reports."""

    report_paths = resolve_union_report_paths(
        config,
        config_path,
        reports_dir,
        html_report=html_report,
    )
    try:
        if reports_dir is not None:
            reports_dir.mkdir(parents=True, exist_ok=True)
        else:
            report_paths.errors_csv.parent.mkdir(parents=True, exist_ok=True)
            report_paths.skipped_csv.parent.mkdir(parents=True, exist_ok=True)
            report_paths.summary_json.parent.mkdir(parents=True, exist_ok=True)
            if report_paths.html_report is not None:
                report_paths.html_report.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CsvWriteError(
            f"{reports_dir or config_path}: cannot create report directory: {exc}"
        ) from exc

    _write_errors_csv(report_paths.errors_csv, result.error_rows, result.run_id)
    _write_skipped_csv(report_paths.skipped_csv, result.skipped_rows, result.run_id)
    payload = _build_summary_payload(result, config, config_path, report_paths)
    _write_summary_json(report_paths.summary_json, payload)
    if report_paths.html_report is not None:
        html_payload = dict(payload)
        reports = dict(html_payload.get("reports", {}))
        reports["html_report"] = str(report_paths.html_report)
        html_payload["reports"] = reports
        write_html_report(
            report_paths.html_report,
            html_payload,
            error_rows=[_error_row_payload(row, result.run_id) for row in result.error_rows],
            skipped_rows=[_skipped_row_payload(row, result.run_id) for row in result.skipped_rows],
        )
    return report_paths


def _write_errors_csv(path: Path, error_rows: list[UnionErrorRow], run_id: str) -> None:
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


def _write_skipped_csv(path: Path, skipped_rows: list[UnionSkippedRow], run_id: str) -> None:
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


def _build_summary_payload(
    result: UnionResult,
    config: UnionConfig,
    config_path: Path,
    report_paths: ReportPaths,
) -> dict[str, Any]:
    return {
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
            "union": True,
            "output_file_written": result.output_file_written,
        },
    }


def _write_summary_json(path: Path, payload: dict[str, Any]) -> None:
    try:
        atomic_write(
            path,
            lambda temp_path: temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            ),
        )
    except OSError as exc:
        raise CsvWriteError(f"{path}: cannot write summary.json: {exc}") from exc


def _error_row_payload(row: UnionErrorRow, run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "input_name": row.input_name,
        "row_number": row.row_number,
        "stage": row.stage,
        "field": row.field,
        "rule": row.rule,
        "message": row.message,
        "row_json": _json_dumps(row.row_json),
    }


def _skipped_row_payload(row: UnionSkippedRow, run_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "row_number": row.row_number,
        "reason": row.reason,
        "row_json": _json_dumps(row.row_json),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    try:
        atomic_write(
            path,
            lambda temp_path: pd.DataFrame(rows, columns=columns).to_csv(
                temp_path,
                index=False,
                encoding="utf-8",
                quoting=csv.QUOTE_MINIMAL,
            ),
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
