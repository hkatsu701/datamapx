from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd

from datamapx.config import CheckConfig, ErrorHandlingConfig, load_config
from datamapx.report.writers import (
    write_dry_run_reports,
    write_errors_csv,
    write_skipped_csv,
)
from datamapx.runner import (
    DryRunResult,
    LoadPhaseResult,
    OutputExecutionResult,
    ReferenceLoadSummary,
    run_dry_run,
)
from datamapx.transform.checks import CheckResult
from datamapx.transform.filters import SkippedRow
from datamapx.validation.errors import ValidationErrorRow

FIXTURES = Path(__file__).parent / "fixtures"


def test_errors_csv_is_written(tmp_path: Path) -> None:
    config = load_config(FIXTURES / "validation" / "validation_config_output_errors.yml")
    result = run_dry_run(config, FIXTURES / "validation")

    report_paths = write_dry_run_reports(result, config, FIXTURES / "validation", tmp_path)

    errors_csv = report_paths.errors_csv
    assert errors_csv.exists()
    rows = list(csv.DictReader(errors_csv.open("r", encoding="utf-8")))
    assert rows[0]["run_id"] == result.run_id
    assert rows[0]["output_name"] == "users_out"
    assert rows[0]["stage"] == "output_validation"


def test_errors_csv_header_only_when_no_rows(tmp_path: Path) -> None:
    config = _config_with_tmp_reports(
        load_config(FIXTURES / "validation" / "validation_config.yml"),
        tmp_path,
    )
    result = run_dry_run(config, FIXTURES / "validation")

    errors_csv = write_errors_csv(tmp_path / "errors.csv", result)
    content = errors_csv.read_text(encoding="utf-8").splitlines()

    assert content == ["run_id,row_number,stage,output_name,field,rule,message,row_json"]


def test_skipped_csv_is_written(tmp_path: Path) -> None:
    config = load_config(FIXTURES / "filters" / "filters_config_exclude.yml")
    result = run_dry_run(config, FIXTURES / "filters")

    report_paths = write_dry_run_reports(result, config, FIXTURES / "filters", tmp_path)

    skipped_csv = report_paths.skipped_csv
    assert skipped_csv.exists()
    rows = list(csv.DictReader(skipped_csv.open("r", encoding="utf-8")))
    assert rows[0]["reason"] == "zero amount is excluded"


def test_skipped_csv_header_only_when_no_rows(tmp_path: Path) -> None:
    config = _config_with_tmp_reports(
        load_config(FIXTURES / "validation" / "validation_config.yml"),
        tmp_path,
    )
    result = run_dry_run(config, FIXTURES / "validation")

    skipped_csv = write_skipped_csv(tmp_path / "skipped.csv", result)
    content = skipped_csv.read_text(encoding="utf-8").splitlines()

    assert content == ["run_id,row_number,reason,row_json"]


def test_summary_json_is_written(tmp_path: Path) -> None:
    config = load_config(FIXTURES / "validation" / "validation_config_output_errors.yml")
    result = run_dry_run(config, FIXTURES / "validation")

    report_paths = write_dry_run_reports(result, config, FIXTURES / "validation", tmp_path)

    summary = json.loads(report_paths.summary_json.read_text(encoding="utf-8"))
    assert summary["run_id"] == result.run_id
    assert summary["counts"]["error_rows"] == result.total_error_count
    assert summary["counts"]["check_failures"] == 0
    assert summary["counts"]["validation_errors"] == result.total_error_count
    assert summary["counts"]["mapping_errors"] == 0
    assert summary["counts"]["lookup_missing_errors"] == 0
    assert summary["counts"]["transform_errors"] == 0
    assert summary["checks"] == []


def test_summary_json_includes_dry_run_flags(tmp_path: Path) -> None:
    config = load_config(FIXTURES / "validation" / "validation_config.yml")
    result = run_dry_run(config, FIXTURES / "validation")

    report_paths = write_dry_run_reports(result, config, FIXTURES / "validation", tmp_path)

    summary = json.loads(report_paths.summary_json.read_text(encoding="utf-8"))
    assert summary["notes"]["dry_run"] is True
    assert summary["notes"]["output_file_written"] is False
    assert summary["notes"]["checks_passed"] is True
    assert summary["notes"]["fatal_error"] is False
    assert summary["notes"]["completed_with_row_errors"] is False
    assert summary["notes"]["final_outcome"] == "success"
    assert summary["error_handling"]["max_errors"] == config.error_handling.max_errors


def test_summary_json_includes_check_results(tmp_path: Path) -> None:
    config = load_config(FIXTURES / "runner" / "runner_config.yml")
    config = config.model_copy(
        update={
            "checks": [
                CheckConfig(
                    name="row_count_check",
                    rule="input_rows == output_rows + error_rows + skipped_rows",
                )
            ]
        }
    )
    result = run_dry_run(config, FIXTURES / "runner")

    report_paths = write_dry_run_reports(result, config, FIXTURES / "runner", tmp_path)

    summary = json.loads(report_paths.summary_json.read_text(encoding="utf-8"))
    assert summary["counts"]["check_failures"] == 0
    assert summary["checks"][0]["name"] == "row_count_check"
    assert summary["checks"][0]["passed"] is True
    assert summary["notes"]["checks_passed"] is True
    assert summary["notes"]["final_outcome"] == "success"


def test_summary_json_counts_error_categories(tmp_path: Path) -> None:
    result = _make_result(
        error_rows=[
            ValidationErrorRow(
                row_number=1,
                stage="input_validation",
                field="users.name",
                rule="required",
                message="required validation failed",
                normalized_row={"name": "山田太郎"},
            ),
            ValidationErrorRow(
                row_number=2,
                stage="mapping",
                field="department_name",
                rule="lookup_missing",
                message="lookup missing",
                normalized_row={"department_code": "D999"},
            ),
            ValidationErrorRow(
                row_number=3,
                stage="mapping",
                field="total_amount",
                rule="transform_error",
                message="transform error",
                normalized_row={"amount": "abc"},
            ),
            ValidationErrorRow(
                row_number=4,
                stage="output_validation",
                field="id",
                rule="required",
                message="required validation failed",
                output_row={"id": ""},
            ),
        ]
    )

    summary = _summary_from_result(tmp_path, result)

    assert summary["counts"]["error_rows"] == 4
    assert summary["counts"]["validation_errors"] == 2
    assert summary["counts"]["mapping_errors"] == 2
    assert summary["counts"]["lookup_missing_errors"] == 1
    assert summary["counts"]["transform_errors"] == 1
    assert summary["notes"]["completed_with_row_errors"] is True
    assert summary["notes"]["final_outcome"] == "completed_with_row_errors"


def test_summary_json_marks_check_failures_as_final_outcome(tmp_path: Path) -> None:
    result = _make_result(
        error_rows=[],
        check_results=[
            CheckResult(
                name="row_count_check",
                rule="input_rows == output_rows",
                passed=False,
                evaluated_value=False,
                message="expected row counts to match",
            )
        ],
    )

    summary = _summary_from_result(tmp_path, result)

    assert summary["notes"]["checks_passed"] is False
    assert summary["notes"]["final_outcome"] == "completed_with_check_failures"
    assert summary["notes"]["completed_with_row_errors"] is False


def test_summary_json_marks_fatal_failure_as_final_outcome(tmp_path: Path) -> None:
    result = replace(
        _make_result(error_rows=[]),
        fatal_error=True,
        stop_reason="validation_error",
        stop_message="Execution stopped (validation_error)",
        status="failed",
    )

    summary = _summary_from_result(tmp_path, result)

    assert summary["notes"]["fatal_error"] is True
    assert summary["notes"]["final_outcome"] == "failed"
    assert summary["notes"]["completed_with_row_errors"] is False


def test_row_json_preserves_japanese(tmp_path: Path) -> None:
    result = _make_result(
        error_rows=[
            ValidationErrorRow(
                row_number=1,
                stage="input_validation",
                field="users.name",
                rule="required",
                message="required validation failed",
                normalized_row={"name": "山田太郎"},
            )
        ]
    )

    errors_csv = write_errors_csv(tmp_path / "errors.csv", result)
    content = errors_csv.read_text(encoding="utf-8")

    assert "山田太郎" in content


def test_reports_dir_override_writes_all_files(tmp_path: Path) -> None:
    config = load_config(FIXTURES / "validation" / "validation_config_filter_and_errors.yml")
    result = run_dry_run(config, FIXTURES / "validation")

    report_paths = write_dry_run_reports(
        result,
        config,
        FIXTURES / "validation",
        tmp_path / "reports",
    )

    assert report_paths.errors_csv.parent == tmp_path / "reports"
    assert report_paths.skipped_csv.parent == tmp_path / "reports"
    assert report_paths.summary_json.parent == tmp_path / "reports"
    assert report_paths.errors_csv.exists()
    assert report_paths.skipped_csv.exists()
    assert report_paths.summary_json.exists()


def _config_with_tmp_reports(config, tmp_path: Path):
    return config.model_copy(
        update={
            "error_handling": config.error_handling.model_copy(
                update={
                    "error_output": str(tmp_path / "errors.csv"),
                    "skipped_output": str(tmp_path / "skipped.csv"),
                }
            )
        }
    )


def _make_result(
    error_rows: list[ValidationErrorRow],
    *,
    check_results: list[CheckResult] | None = None,
    fatal_error: bool = False,
    stop_reason: str | None = None,
    stop_message: str | None = None,
    status: str = "dry_run_completed",
) -> DryRunResult:
    load_result = LoadPhaseResult(
        project_name="demo",
        input_name="users",
        input_path="./input/users.csv",
        input_rows=1,
        input_columns=["name"],
        references=[ReferenceLoadSummary(name="departments", path="./ref.csv", rows=0, key="code")],
        limit=None,
        status="load_phase_completed",
        input_df=pd.DataFrame([{"__row_number": 1, "name": "山田太郎"}]),
        reference_dfs={},
    )
    return DryRunResult(
        run_id="20240515_120000",
        started_at="2024-05-15T12:00:00",
        finished_at="2024-05-15T12:00:01",
        dry_run=True,
        output_file_written=False,
        load_result=load_result,
        output_results=[
            OutputExecutionResult(
                name="users_out",
                path="./output/users_out.csv",
                file_written=False,
                rows=1,
                columns=["name"],
                preview_df=pd.DataFrame([{"name": "山田太郎"}]),
                validation_error_rows=[],
            )
        ],
        output_name="users_out",
        output_path="./output/users_out.csv",
        output_rows=1,
        output_columns=["name"],
        output_preview_df=pd.DataFrame([{"name": "山田太郎"}]),
        input_rows_before_validation=1,
        input_rows_after_validation=1,
        input_rows_before_filter=1,
        input_rows_after_filter=1,
        skipped_rows=[
            SkippedRow(
                row_number=1,
                reason="理由",
                normalized_row={"name": "山田太郎"},
            )
        ],
        error_rows=error_rows,
        check_results=check_results
        if check_results is not None
        else [
            CheckResult(
                name="row_count_check",
                rule="input_rows == output_rows + error_rows + skipped_rows",
                passed=True,
                evaluated_value=True,
            )
        ],
        error_handling=ErrorHandlingConfig(
            error_output="./errors.csv",
            skipped_output="./skipped.csv",
        ),
        stop_reason=stop_reason,
        stop_message=stop_message,
        max_errors_exceeded=False,
        fatal_error=fatal_error,
        status=status,
    )


def _summary_from_result(tmp_path: Path, result: DryRunResult) -> dict[str, object]:
    config = load_config(FIXTURES / "validation" / "validation_config.yml")
    report_paths = write_dry_run_reports(result, config, FIXTURES / "validation", tmp_path)
    return json.loads(report_paths.summary_json.read_text(encoding="utf-8"))


def test_summary_json_includes_multiple_outputs(tmp_path: Path) -> None:
    config = load_config(FIXTURES / "run" / "run_config_multi_output.yml")
    result = run_dry_run(config, FIXTURES / "run")

    report_paths = write_dry_run_reports(result, config, FIXTURES / "run", tmp_path)

    summary = json.loads(report_paths.summary_json.read_text(encoding="utf-8"))
    assert len(summary["outputs"]) == 2
    assert summary["outputs"][0]["name"] == "users_out"
    assert summary["outputs"][0]["file_written"] is False
    assert summary["outputs"][1]["name"] == "users_out_copy"
