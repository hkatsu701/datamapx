from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest
import yaml
from openpyxl import load_workbook
from typer.testing import CliRunner

from datamapx.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
PROFILE_FIXTURES = FIXTURES / "profile_input"


def test_validate_config_success() -> None:
    result = CliRunner().invoke(app, ["validate-config", str(FIXTURES / "valid_config.yml")])

    assert result.exit_code == 0
    assert "Config is valid" in result.output


def test_generate_config_success(tmp_path: Path) -> None:
    config_path = tmp_path / "generated_migration.yml"
    output_path = tmp_path / "output" / "users_out.csv"

    result = CliRunner().invoke(
        app,
        [
            "generate-config",
            "--input",
            str(FIXTURES / "generate_config" / "input_basic.csv"),
            "--output",
            str(output_path),
            "--config",
            str(config_path),
            "--input-name",
            "users",
            "--output-name",
            "users_out",
        ],
    )

    assert result.exit_code == 0
    assert "Config generated:" in result.output
    assert "Next steps:" in result.output
    assert config_path.exists()


def test_generate_config_output_validates(tmp_path: Path) -> None:
    config_path = tmp_path / "generated_migration.yml"
    output_path = tmp_path / "output" / "users_out.csv"

    result = CliRunner().invoke(
        app,
        [
            "generate-config",
            "--input",
            str(FIXTURES / "generate_config" / "input_basic.csv"),
            "--output",
            str(output_path),
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0

    validate_result = CliRunner().invoke(app, ["validate-config", str(config_path)])
    assert validate_result.exit_code == 0


def test_generate_config_overwrite_controls_existing_file(tmp_path: Path) -> None:
    config_path = tmp_path / "generated_migration.yml"
    output_path = tmp_path / "output" / "users_out.csv"
    config_path.write_text("existing", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "generate-config",
            "--input",
            str(FIXTURES / "generate_config" / "input_basic.csv"),
            "--output",
            str(output_path),
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 1
    assert "config file already exists" in result.output

    overwrite_result = CliRunner().invoke(
        app,
        [
            "generate-config",
            "--input",
            str(FIXTURES / "generate_config" / "input_basic.csv"),
            "--output",
            str(output_path),
            "--config",
            str(config_path),
            "--overwrite",
        ],
    )

    assert overwrite_result.exit_code == 0
    assert "Config generated:" in overwrite_result.output


def test_validate_config_failure() -> None:
    result = CliRunner().invoke(app, ["validate-config", str(FIXTURES / "invalid_config.yml")])

    assert result.exit_code == 1
    assert "missing mappings for output columns" in result.output


def test_validate_design_success() -> None:
    result = CliRunner().invoke(
        app,
        ["validate-design", str(EXAMPLES / "08_excel_design" / "datamapx_design_template.xlsx")],
    )

    assert result.exit_code == 0
    assert "Design is valid:" in result.output
    assert "Project: invoice_migration" in result.output
    assert "Sheets: 16" in result.output
    assert "Jobs: 2" in result.output
    assert "Enabled jobs: 2" in result.output


def test_validate_design_writes_summary_and_errors_csv(tmp_path: Path) -> None:
    design_path = _prepare_design_fixture(tmp_path)
    workbook = load_workbook(design_path)
    workbook.remove(workbook["runtime"])
    workbook.save(design_path)
    summary_path = tmp_path / "design-summary.json"
    errors_path = tmp_path / "design-errors.csv"

    result = CliRunner().invoke(
        app,
        [
            "validate-design",
            str(design_path),
            "--summary-json",
            str(summary_path),
            "--errors-csv",
            str(errors_path),
        ],
    )

    assert result.exit_code == 1
    assert "Design is invalid:" in result.output
    assert summary_path.exists()
    assert errors_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["valid"] is False
    assert summary["error_count"] >= 1
    with errors_path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert rows
    assert rows[0]["sheet"] == "runtime"


def test_inspect_success() -> None:
    result = CliRunner().invoke(app, ["inspect", str(FIXTURES / "valid_config.yml")])

    assert result.exit_code == 0
    assert "Project name: test_migration" in result.output
    assert "Input names: users" in result.output
    assert "Reference names: departments" in result.output
    assert "Output names: users_out" in result.output
    assert "Error output path: ./output/errors.csv" in result.output


def test_run_success(tmp_path: Path) -> None:
    config_path = _prepare_run_fixture(tmp_path, "run_config.yml")

    result = CliRunner().invoke(app, ["run", str(config_path)])

    assert result.exit_code == 0
    assert "Run completed" in result.output
    assert "Output:" in result.output
    assert "Reports:" in result.output
    assert "Counts:" in result.output


def test_run_inspect_displays_runtime_row_limits(tmp_path: Path) -> None:
    config_path = _prepare_run_fixture(tmp_path, "run_config.yml")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["runtime"]["max_input_rows"] = 100
    data["runtime"]["max_reference_rows"] = 200
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["inspect", str(config_path)])

    assert result.exit_code == 0
    assert "Runtime max input rows: 100" in result.output
    assert "Runtime max reference rows: 200" in result.output


def test_run_with_validation_errors_still_succeeds(tmp_path: Path) -> None:
    config_path = _prepare_run_fixture(tmp_path, "run_config_with_errors.yml")

    result = CliRunner().invoke(app, ["run", str(config_path)])

    assert result.exit_code == 0
    assert "Run completed" in result.output
    assert "error rows:" in result.output


def test_dry_run_success() -> None:
    result = CliRunner().invoke(
        app,
        ["dry-run", str(FIXTURES / "runner" / "runner_config.yml")],
    )

    assert result.exit_code == 0
    assert "Dry run completed" in result.output
    assert "Status: dry_run_completed" in result.output


def test_dry_run_limit_displays_limited_rows() -> None:
    result = CliRunner().invoke(
        app,
        ["dry-run", str(FIXTURES / "runner" / "runner_config.yml"), "--limit", "2"],
    )

    assert result.exit_code == 0
    assert "- rows loaded: 2" in result.output
    assert "Limit: 2" in result.output


def test_dry_run_reference_duplicate_fails() -> None:
    result = CliRunner().invoke(
        app,
        ["dry-run", str(FIXTURES / "runner" / "runner_config_bad_ref_duplicate.yml")],
    )

    assert result.exit_code == 1
    assert "duplicate key values" in result.output


def test_dry_run_output_preview_is_displayed() -> None:
    result = CliRunner().invoke(
        app,
        ["dry-run", str(FIXTURES / "runner" / "runner_config.yml"), "--limit", "2"],
    )

    assert result.exit_code == 0
    assert "Output preview:" in result.output
    assert "- name: users_out" in result.output
    assert "id,name,system_code,status" in result.output


def test_dry_run_multi_output_previews_are_displayed() -> None:
    result = CliRunner().invoke(
        app,
        ["dry-run", str(FIXTURES / "run" / "run_config_multi_output.yml"), "--limit", "2"],
    )

    assert result.exit_code == 0
    assert "Output previews:" in result.output
    assert "- name: users_out" in result.output
    assert "- name: users_out_copy" in result.output


def test_dry_run_notes_output_file_is_not_written() -> None:
    result = CliRunner().invoke(
        app,
        ["dry-run", str(FIXTURES / "runner" / "runner_config.yml"), "--limit", "2"],
    )

    assert result.exit_code == 0
    assert "output file is not written in dry-run" in result.output


def test_dry_run_write_reports_writes_files(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    result = CliRunner().invoke(
        app,
        [
            "dry-run",
            str(FIXTURES / "validation" / "validation_config_filter_and_errors.yml"),
            "--limit",
            "10",
            "--write-reports",
            "--reports-dir",
            str(reports_dir),
        ],
    )

    assert result.exit_code == 0
    assert "Reports written:" in result.output
    assert (reports_dir / "errors.csv").exists()
    assert (reports_dir / "skipped.csv").exists()
    assert (reports_dir / "summary.json").exists()


def test_dry_run_html_report_requires_write_reports() -> None:
    result = CliRunner().invoke(
        app,
        [
            "dry-run",
            str(FIXTURES / "validation" / "validation_config_filter_and_errors.yml"),
            "--html-report",
        ],
    )

    assert result.exit_code == 2
    assert "--html-report requires --write-reports" in result.output


def test_dry_run_write_reports_html_report_writes_files(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    result = CliRunner().invoke(
        app,
        [
            "dry-run",
            str(FIXTURES / "validation" / "validation_config_filter_and_errors.yml"),
            "--limit",
            "10",
            "--write-reports",
            "--reports-dir",
            str(reports_dir),
            "--html-report",
        ],
    )

    assert result.exit_code == 0
    assert "Reports written:" in result.output
    assert "- html:" in result.output
    assert (reports_dir / "report.html").exists()


def test_dry_run_rejects_input_row_limit_exceeded(tmp_path: Path) -> None:
    config_path = _prepare_run_fixture(tmp_path, "run_config.yml")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["runtime"]["max_input_rows"] = 1
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["dry-run", str(config_path)])

    assert result.exit_code == 1
    assert "inputs.users: row count 3 exceeds runtime.max_input_rows 1" in result.output


def test_dry_run_rejects_reference_row_limit_exceeded(tmp_path: Path) -> None:
    config_path = _prepare_run_fixture(tmp_path, "run_config.yml")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["runtime"]["max_reference_rows"] = 1
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["dry-run", str(config_path)])

    assert result.exit_code == 1
    assert (
        "references.departments: row count 3 exceeds runtime.max_reference_rows 1"
        in result.output
    )


def test_dry_run_check_failure_exits_nonzero(tmp_path: Path) -> None:
    config_path = _prepare_run_fixture(tmp_path, "run_config.yml")
    _set_checks(config_path, [{"name": "row_count_check", "rule": "input_rows == 0"}])
    reports_dir = tmp_path / "reports"

    result = CliRunner().invoke(
        app,
        [
            "dry-run",
            str(config_path),
            "--write-reports",
            "--reports-dir",
            str(reports_dir),
        ],
    )

    assert result.exit_code == 1
    assert "One or more checks failed." in result.output
    summary = json.loads((reports_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["counts"]["check_failures"] == 1
    assert summary["notes"]["checks_passed"] is False
    assert summary["checks"][0]["passed"] is False


def test_migration_wizard_example_validates() -> None:
    result = CliRunner().invoke(
        app,
        ["validate-config", str(EXAMPLES / "06_migration_wizard" / "migration.yml")],
    )

    assert result.exit_code == 0
    assert "Config is valid" in result.output


def test_migration_wizard_example_dry_run() -> None:
    result = CliRunner().invoke(
        app,
        [
            "dry-run",
            str(EXAMPLES / "06_migration_wizard" / "migration.yml"),
            "--limit",
            "5",
        ],
    )

    assert result.exit_code == 0
    assert "Dry run completed" in result.output
    assert "Output preview:" in result.output


def test_practical_migration_example_validates() -> None:
    result = CliRunner().invoke(
        app,
        ["validate-config", str(EXAMPLES / "07_practical_migration" / "migration.yml")],
    )

    assert result.exit_code == 0
    assert "Config is valid" in result.output


def test_practical_migration_example_dry_run(tmp_path: Path) -> None:
    config_path = _prepare_example_fixture(tmp_path, "07_practical_migration")
    reports_dir = tmp_path / "reports"

    result = CliRunner().invoke(
        app,
        [
            "dry-run",
            str(config_path / "migration.yml"),
            "--write-reports",
            "--reports-dir",
            str(reports_dir),
        ],
    )

    assert result.exit_code == 0
    assert "Dry run completed" in result.output
    assert "Output preview:" in result.output
    assert "Skipped preview:" in result.output
    assert "Error preview:" in result.output
    assert "Reports written:" in result.output
    summary = json.loads((reports_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["counts"]["input_rows"] == 5
    assert summary["counts"]["output_rows"] == 2
    assert summary["counts"]["error_rows"] == 2
    assert summary["counts"]["validation_errors"] == 1
    assert summary["counts"]["mapping_errors"] == 1
    assert summary["counts"]["lookup_missing_errors"] == 1
    assert summary["counts"]["transform_errors"] == 0
    assert summary["counts"]["skipped_rows"] == 1
    assert summary["counts"]["check_failures"] == 0
    assert summary["notes"]["completed_with_row_errors"] is True
    assert summary["notes"]["final_outcome"] == "completed_with_row_errors"


def test_practical_migration_example_run(tmp_path: Path) -> None:
    config_path = _prepare_example_fixture(tmp_path, "07_practical_migration")
    reports_dir = tmp_path / "reports"

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(config_path / "migration.yml"),
            "--reports-dir",
            str(reports_dir),
        ],
    )

    assert result.exit_code == 0
    assert "Run completed" in result.output
    output_csv = config_path / "output" / "invoices_out.csv"
    rows = list(csv.DictReader(output_csv.open("r", encoding="utf-8-sig")))
    assert [row["invoice_no"] for row in rows] == ["INV001", "INV005"]
    assert rows[0]["customer_id"] == "CU001"
    assert rows[0]["account_code"] == "AR-100"
    assert rows[0]["outstanding_amount"] == "800"
    assert rows[0]["payment_state"] == "partial"
    assert rows[0]["invoice_category"] == "retail"
    assert rows[1]["customer_id"] == "CU002"
    assert rows[1]["account_code"] == "AR-200"
    assert rows[1]["outstanding_amount"] == "0"
    assert rows[1]["payment_state"] == "settled"
    assert rows[1]["invoice_category"] == "wholesale"
    summary = json.loads((reports_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["counts"]["input_rows"] == 5
    assert summary["counts"]["output_rows"] == 2
    assert summary["counts"]["error_rows"] == 2
    assert summary["counts"]["skipped_rows"] == 1
    assert summary["counts"]["check_failures"] == 0
    assert summary["notes"]["final_outcome"] == "completed_with_row_errors"
    assert summary["notes"]["fatal_error"] is False


def test_run_html_report_writes_file(tmp_path: Path) -> None:
    config_path = _prepare_run_fixture(tmp_path, "run_config.yml")
    reports_dir = tmp_path / "reports"

    result = CliRunner().invoke(
        app,
        ["run", str(config_path), "--reports-dir", str(reports_dir), "--html-report"],
    )

    assert result.exit_code == 0
    assert "Reports:" in result.output
    assert "- html:" in result.output
    assert (reports_dir / "report.html").exists()


def test_run_all_runs_jobs_sequentially(tmp_path: Path) -> None:
    config_path = _prepare_run_all_config(
        tmp_path,
        merge_fixture_name="merge_config.yml",
    )

    result = CliRunner().invoke(
        app,
        [
            "run-all",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    assert "Run-all job 1/3: migration [run]" in result.output
    assert "Run-all job 2/3: merge_stage [merge]" in result.output
    assert "Run-all job 3/3: union_stage [union]" in result.output
    assert "Run-all completed" in result.output
    assert (tmp_path / "run" / "output" / "users_out.csv").exists()
    assert (tmp_path / "merge" / "output" / "merged.csv").exists()
    assert (tmp_path / "union" / "output" / "unioned.csv").exists()
    assert (tmp_path / "run_reports" / "report.html").exists()
    assert (tmp_path / "merge_reports" / "errors.csv").exists()
    assert (tmp_path / "union_reports" / "summary.json").exists()


def test_run_all_stops_after_first_failure(tmp_path: Path) -> None:
    config_path = _prepare_run_all_config(
        tmp_path,
        merge_fixture_name="merge_config_duplicate.yml",
    )

    result = CliRunner().invoke(
        app,
        [
            "run-all",
            str(config_path),
        ],
    )

    assert result.exit_code == 1
    assert "Run-all job 1/3: migration [run]" in result.output
    assert "Run-all job 2/3: merge_stage [merge]" in result.output
    assert "Run-all job 3/3: union_stage [union]" not in result.output
    assert (tmp_path / "run" / "output" / "users_out.csv").exists()
    assert not (tmp_path / "merge" / "output" / "merged.csv").exists()
    assert not (tmp_path / "union" / "output" / "unioned.csv").exists()
    assert (tmp_path / "run_reports" / "report.html").exists()


def test_run_rejects_input_row_limit_exceeded(tmp_path: Path) -> None:
    config_path = _prepare_run_fixture(tmp_path, "run_config.yml")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["runtime"]["max_input_rows"] = 1
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["run", str(config_path)])

    assert result.exit_code == 1
    assert "inputs.users: row count 3 exceeds runtime.max_input_rows 1" in result.output


def test_run_rejects_reference_row_limit_exceeded(tmp_path: Path) -> None:
    config_path = _prepare_run_fixture(tmp_path, "run_config.yml")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["runtime"]["max_reference_rows"] = 1
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["run", str(config_path)])

    assert result.exit_code == 1
    assert (
        "references.departments: row count 3 exceeds runtime.max_reference_rows 1"
        in result.output
    )


def test_dry_run_without_write_reports_does_not_write_files(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    result = CliRunner().invoke(
        app,
        [
            "dry-run",
            str(FIXTURES / "validation" / "validation_config_filter_and_errors.yml"),
            "--limit",
            "10",
        ],
    )

    assert result.exit_code == 0
    assert not reports_dir.exists()


def test_reports_dir_without_write_reports_fails(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "dry-run",
            str(FIXTURES / "validation" / "validation_config_filter_and_errors.yml"),
            "--reports-dir",
            str(tmp_path / "reports"),
        ],
    )

    assert result.exit_code == 2
    assert "--reports-dir requires --write-reports" in result.output


def test_dry_run_lookup_output_preview_is_displayed() -> None:
    result = CliRunner().invoke(
        app,
        ["dry-run", str(FIXTURES / "mapping" / "mapping_config_lookup.yml"), "--limit", "3"],
    )

    assert result.exit_code == 0
    assert "Sales" in result.output
    assert "Support" in result.output
    assert "Unknown" in result.output


def test_dry_run_lookup_missing_becomes_row_error() -> None:
    result = CliRunner().invoke(
        app,
        ["dry-run", str(FIXTURES / "mapping" / "mapping_config_lookup_missing_error.yml")],
    )

    assert result.exit_code == 0
    assert "Error preview:" in result.output
    assert "lookup missing" in result.output


def test_dry_run_lookup_missing_stop_fails(tmp_path: Path) -> None:
    fixture_dir = FIXTURES / "mapping"
    for path in fixture_dir.iterdir():
        target = tmp_path / path.name
        if path.is_dir():
            shutil.copytree(path, target)
        else:
            shutil.copy2(path, target)

    config_path = tmp_path / "lookup_stop.yml"
    data = yaml.safe_load(
        (tmp_path / "mapping_config_lookup_missing_error.yml").read_text(
            encoding="utf-8"
        )
    )
    data["error_handling"] = {
        "error_output": "./output/errors.csv",
        "skipped_output": "./output/skipped.csv",
        "on_lookup_missing": "stop",
    }
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["dry-run", str(config_path)])

    assert result.exit_code == 1
    assert "Output preview:" in result.output
    assert "u001" in result.output
    assert "u002" in result.output
    assert "Execution stopped (lookup_missing)" in result.output


def test_dry_run_transform_error_becomes_row_error() -> None:
    result = CliRunner().invoke(
        app,
        ["dry-run", str(FIXTURES / "mapping" / "mapping_config_expression_missing_value.yml")],
    )

    assert result.exit_code == 0
    assert "Error preview:" in result.output
    assert "transform_error" in result.output


def test_dry_run_expression_error_details_are_displayed(tmp_path: Path) -> None:
    config_path = _prepare_expression_error_fixture(tmp_path)

    result = CliRunner().invoke(app, ["dry-run", str(config_path)])

    assert result.exit_code == 0
    assert "Error details:" in result.output
    assert "row 1" in result.output
    assert "billingitemamount_c1='1000' (str)" in result.output
    assert "servicereception_r_isunpaid_c1='true' (str)" in result.output
    assert "TypeError" in result.output


def test_run_expression_error_details_are_displayed(tmp_path: Path) -> None:
    config_path = _prepare_expression_error_fixture(tmp_path)

    result = CliRunner().invoke(app, ["run", str(config_path)])

    assert result.exit_code == 0
    assert "Error details:" in result.output
    assert "row 1" in result.output
    assert "billingitemamount_c1='1000' (str)" in result.output
    assert "servicereception_r_isunpaid_c1='true' (str)" in result.output
    assert "TypeError" in result.output


def test_dry_run_when_output_preview_is_displayed() -> None:
    result = CliRunner().invoke(
        app,
        ["dry-run", str(FIXTURES / "mapping" / "mapping_config_when.yml"), "--limit", "3"],
    )

    assert result.exit_code == 0
    assert "Output preview:" in result.output
    assert "enabled" in result.output
    assert "disabled" in result.output
    assert "fallback" in result.output


def test_dry_run_expression_output_preview_is_displayed() -> None:
    result = CliRunner().invoke(
        app,
        ["dry-run", str(FIXTURES / "mapping" / "mapping_config_expression.yml"), "--limit", "2"],
    )

    assert result.exit_code == 0
    assert "Output preview:" in result.output
    assert "multiply" in result.output
    assert "u001,200,110,95,50.0" in result.output
    assert "u002,200,55,40,12.5" in result.output


def test_dry_run_derived_output_preview_is_displayed() -> None:
    result = CliRunner().invoke(
        app,
        ["dry-run", str(FIXTURES / "mapping" / "mapping_config_derived.yml"), "--limit", "2"],
    )

    assert result.exit_code == 0
    assert "Output preview:" in result.output
    assert "Yamada Taro" in result.output
    assert "Sato Hanako" in result.output
    assert "Sales" in result.output


def test_dry_run_filter_summary_is_displayed() -> None:
    result = CliRunner().invoke(
        app,
        ["dry-run", str(FIXTURES / "filters" / "filters_config_exclude.yml"), "--limit", "10"],
    )

    assert result.exit_code == 0
    assert "Filter:" in result.output
    assert "- rows before filter: 4" in result.output
    assert "- rows after filter: 2" in result.output
    assert "- skipped rows: 2" in result.output


def test_dry_run_skipped_preview_is_displayed() -> None:
    result = CliRunner().invoke(
        app,
        ["dry-run", str(FIXTURES / "filters" / "filters_config_exclude.yml"), "--limit", "10"],
    )

    assert result.exit_code == 0
    assert "Skipped preview:" in result.output
    assert "row_number,reason" in result.output
    assert "2,zero amount is excluded" in result.output


def test_dry_run_output_preview_uses_filtered_rows() -> None:
    result = CliRunner().invoke(
        app,
        ["dry-run", str(FIXTURES / "filters" / "filters_config_exclude.yml"), "--limit", "10"],
    )

    assert result.exit_code == 0
    assert "u001,100" in result.output
    assert "u003,25" in result.output
    assert "u002,0" not in result.output
    assert "u004,0" not in result.output


def test_dry_run_validation_summary_is_displayed() -> None:
    result = CliRunner().invoke(
        app,
        [
            "dry-run",
            str(FIXTURES / "validation" / "validation_config_output_errors.yml"),
            "--limit",
            "10",
        ],
    )

    assert result.exit_code == 0
    assert "Validation:" in result.output
    assert "- output validation errors:" in result.output
    assert "- total error rows:" in result.output


def test_dry_run_error_preview_is_displayed() -> None:
    result = CliRunner().invoke(
        app,
        [
            "dry-run",
            str(FIXTURES / "validation" / "validation_config_output_errors.yml"),
            "--limit",
            "10",
        ],
    )

    assert result.exit_code == 0
    assert "Error preview:" in result.output
    assert "row_number,stage,field,rule,message" in result.output
    assert "output_validation" in result.output


def test_dry_run_output_preview_is_filtered_by_validation() -> None:
    result = CliRunner().invoke(
        app,
        [
            "dry-run",
            str(FIXTURES / "validation" / "validation_config_output_errors.yml"),
            "--limit",
            "10",
        ],
    )

    assert result.exit_code == 0
    assert "u001" in result.output
    assert "u002" not in result.output
    assert "u003" not in result.output
    assert "u004" not in result.output


def test_profile_input_success() -> None:
    result = CliRunner().invoke(
        app,
        ["profile-input", str(FIXTURES / "csv_io" / "csv_io_config.yml")],
    )

    assert result.exit_code == 0
    assert "datamapx input profile" in result.output
    assert "Input name: users" in result.output
    assert "Rows: 2" in result.output


def test_profile_input_limit_displays_profiled_rows() -> None:
    result = CliRunner().invoke(
        app,
        [
            "profile-input",
            str(PROFILE_FIXTURES / "profile_input_config.yml"),
            "--limit",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert "Profiled rows: 1" in result.output
    assert "Limit: 1" in result.output
    assert "Note: metrics are based on the limited sample." in result.output


def test_profile_input_json_output_is_valid() -> None:
    result = CliRunner().invoke(
        app,
        [
            "profile-input",
            str(PROFILE_FIXTURES / "profile_input_config.yml"),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["input_name"] == "users"
    assert payload["profiled_rows"] == 3
    assert payload["limit"] is None
    assert payload["columns"][0]["name"] == "user_id"
    assert payload["columns"][0]["schema_type"] == "string"
    assert payload["columns"][0]["sample_values"] == ["u001", "u002", "u001"]


def test_profile_input_json_limit_reports_limit_and_metrics() -> None:
    result = CliRunner().invoke(
        app,
        [
            "profile-input",
            str(PROFILE_FIXTURES / "profile_input_config.yml"),
            "--limit",
            "1",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["profiled_rows"] == 1
    assert payload["limit"] == 1
    assert payload["columns"][0]["missing_count"] == 0


def test_profile_input_metrics_are_reported() -> None:
    result = CliRunner().invoke(
        app,
        [
            "profile-input",
            str(PROFILE_FIXTURES / "profile_input_config.yml"),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    columns = {column["name"]: column for column in payload["columns"]}

    assert columns["user_id"]["missing_count"] == 0
    assert columns["user_id"]["non_null_count"] == 3
    assert columns["user_id"]["unique_count"] == 2
    assert columns["user_id"]["duplicate_count"] == 1
    assert columns["user_id"]["top_values"][0] == {"value": "u001", "count": 2}
    assert columns["name"]["min_length"] == 2
    assert columns["name"]["max_length"] == 5
    assert columns["age"]["min"] == 7
    assert columns["age"]["max"] == 42
    assert columns["age"]["mean"] == pytest.approx(24.5)
    assert columns["amount"]["min"] == 500
    assert columns["amount"]["max"] == 2000
    assert columns["amount"]["mean"] == pytest.approx(1244.8333333333333)


def test_profile_input_invalid_limit_exits_2() -> None:
    result = CliRunner().invoke(
        app,
        [
            "profile-input",
            str(FIXTURES / "csv_io" / "csv_io_config.yml"),
            "--limit",
            "0",
        ],
    )

    assert result.exit_code == 2
    assert "--limit must be a positive integer" in result.output


def test_profile_input_negative_limit_exits_2() -> None:
    result = CliRunner().invoke(
        app,
        [
            "profile-input",
            str(FIXTURES / "csv_io" / "csv_io_config.yml"),
            "--limit",
            "-1",
        ],
    )

    assert result.exit_code == 2
    assert "--limit must be a positive integer" in result.output


def test_profile_input_invalid_format_exits_2() -> None:
    result = CliRunner().invoke(
        app,
        [
            "profile-input",
            str(FIXTURES / "csv_io" / "csv_io_config.yml"),
            "--format",
            "xml",
        ],
    )

    assert result.exit_code == 2
    assert "--format must be 'text' or 'json'" in result.output


def _prepare_run_fixture(tmp_path: Path, fixture_name: str) -> Path:
    fixture_dir = FIXTURES / "run"
    for path in fixture_dir.iterdir():
        target = tmp_path / path.name
        if path.is_dir():
            shutil.copytree(path, target)
        else:
            shutil.copy2(path, target)
    return tmp_path / fixture_name


def _prepare_run_all_config(
    tmp_path: Path,
    *,
    merge_fixture_name: str,
) -> Path:
    for fixture_name in ("run", "merge", "union"):
        shutil.copytree(FIXTURES / fixture_name, tmp_path / fixture_name)

    config_path = tmp_path / "run-all.yml"
    config = {
        "version": 1,
        "project": {"name": "run_all_sample"},
        "jobs": [
            {
                "name": "migration",
                "type": "run",
                "config": "./run/run_config.yml",
                "reports_dir": "./run_reports",
                "html_report": True,
            },
            {
                "name": "merge_stage",
                "type": "merge",
                "config": f"./merge/{merge_fixture_name}",
                "reports_dir": "./merge_reports",
                "html_report": False,
            },
            {
                "name": "union_stage",
                "type": "union",
                "config": "./union/union_config.yml",
                "reports_dir": "./union_reports",
                "html_report": False,
            },
        ],
    }
    rendered = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
    config_path.write_text(rendered, encoding="utf-8")
    return config_path


def _prepare_design_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "design.xlsx"
    shutil.copy2(EXAMPLES / "08_excel_design" / "datamapx_design_template.xlsx", target)
    return target


def _prepare_example_fixture(tmp_path: Path, example_name: str) -> Path:
    example_dir = EXAMPLES / example_name
    target_dir = tmp_path / example_name
    shutil.copytree(example_dir, target_dir)
    return target_dir


def _set_checks(config_path: Path, checks: list[dict[str, object]]) -> None:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["checks"] = checks
    rendered = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    config_path.write_text(rendered, encoding="utf-8")


def _prepare_expression_error_fixture(tmp_path: Path) -> Path:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "expression_error.csv").write_text(
        "user_id,billingitemamount_c1,servicereception_r_isunpaid_c1\n"
        "u001,1000,true\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "expression_error.yml"
    config = {
        "version": 1,
        "project": {"name": "expression_error"},
        "inputs": {
            "users": {
                "path": "./input/expression_error.csv",
                "schema": {
                    "user_id": {"type": "string"},
                    "billingitemamount_c1": {"type": "string"},
                    "servicereception_r_isunpaid_c1": {"type": "string"},
                },
            }
        },
        "outputs": {
            "users_out": {
                "path": "./output/users_out.csv",
                "columns": ["id", "result"],
            }
        },
        "mappings": {
            "users_out": {
                "id": {"source": "users.user_id"},
                "result": {
                    "expression": (
                        "users.billingitemamount_c1 * "
                        "users.servicereception_r_isunpaid_c1"
                    )
                },
            }
        },
        "error_handling": {
            "error_output": "./output/errors.csv",
            "skipped_output": "./output/skipped.csv",
        },
    }
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return config_path
