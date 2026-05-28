"""Report file writers for dry-run execution."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd

from datamapx.config import DatamapxConfig
from datamapx.report.errors import ReportWriteError
from datamapx.report.html import write_html_report
from datamapx.report.summary import (
    ReportPaths,
    build_summary_payload,
    resolve_report_paths,
)
from datamapx.runner import DryRunResult


def write_errors_csv(path: Path, result: DryRunResult) -> Path:
    """Write validation error rows to errors.csv."""

    rows = [
        {
            "run_id": result.run_id,
            "row_number": row.row_number,
            "stage": row.stage,
            "output_name": row.output_name,
            "field": row.field,
            "rule": row.rule,
            "message": row.message,
            "row_json": _json_dumps(row.output_row or row.normalized_row or {}),
        }
        for row in result.error_rows
    ]
    _write_csv(
        path,
        rows,
        [
            "run_id",
            "row_number",
            "stage",
            "output_name",
            "field",
            "rule",
            "message",
            "row_json",
        ],
    )
    return path


def write_skipped_csv(path: Path, result: DryRunResult) -> Path:
    """Write skipped rows to skipped.csv."""

    rows = [
        {
            "run_id": result.run_id,
            "row_number": row.row_number,
            "reason": row.reason,
            "row_json": _json_dumps(row.normalized_row),
        }
        for row in result.skipped_rows
    ]
    _write_csv(path, rows, ["run_id", "row_number", "reason", "row_json"])
    return path


def write_summary_json(
    path: Path,
    result: DryRunResult,
    config: DatamapxConfig,
    config_path: Path,
    report_paths: ReportPaths,
) -> Path:
    """Write summary.json for a dry-run."""

    payload = build_summary_payload(result, config, config_path, report_paths)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        raise ReportWriteError(f"{path}: cannot write summary.json: {exc}") from exc
    return path


def write_dry_run_reports(
    result: DryRunResult,
    config: DatamapxConfig,
    config_path: Path,
    reports_dir: Path | None = None,
    *,
    html_report: bool = False,
) -> ReportPaths:
    """Write report files for a dry-run."""

    report_paths = resolve_report_paths(
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
        raise ReportWriteError(
            f"{reports_dir or config_path}: cannot create report directory: {exc}"
        ) from exc

    write_errors_csv(report_paths.errors_csv, result)
    write_skipped_csv(report_paths.skipped_csv, result)
    write_summary_json(report_paths.summary_json, result, config, config_path, report_paths)
    if report_paths.html_report is not None:
        html_payload = dict(build_summary_payload(result, config, config_path, report_paths))
        reports = dict(html_payload.get("reports", {}))
        reports["html_report"] = str(report_paths.html_report)
        html_payload["reports"] = reports
        write_html_report(
            report_paths.html_report,
            html_payload,
            error_rows=[
                {
                    "run_id": result.run_id,
                    "row_number": row.row_number,
                    "stage": row.stage,
                    "output_name": row.output_name,
                    "field": row.field,
                    "rule": row.rule,
                    "message": row.message,
                    "row_json": _json_dumps(row.output_row or row.normalized_row or {}),
                }
                for row in result.error_rows
            ],
            skipped_rows=[
                {
                    "run_id": result.run_id,
                    "row_number": row.row_number,
                    "reason": row.reason,
                    "row_json": _json_dumps(row.normalized_row),
                }
                for row in result.skipped_rows
            ],
        )
    return report_paths


def write_run_reports(
    result: DryRunResult,
    config: DatamapxConfig,
    config_path: Path,
    reports_dir: Path | None = None,
    *,
    html_report: bool = False,
) -> ReportPaths:
    """Write report files for a run."""

    return write_dry_run_reports(
        result,
        config,
        config_path,
        reports_dir,
        html_report=html_report,
    )


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
        raise ReportWriteError(f"{path}: cannot write report CSV: {exc}") from exc


def _json_dumps(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "item"):
        try:
            item = value.item()
        except Exception:  # pragma: no cover - defensive
            return str(value)
        return _json_safe(item)
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # pragma: no cover - defensive
            return str(value)
    return str(value)
