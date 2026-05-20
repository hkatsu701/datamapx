from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from datamapx.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


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


def test_dry_run_lookup_missing_fails() -> None:
    result = CliRunner().invoke(
        app,
        ["dry-run", str(FIXTURES / "mapping" / "mapping_config_lookup_missing_error.yml")],
    )

    assert result.exit_code == 1
    assert "lookup missing" in result.output


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


def _prepare_run_fixture(tmp_path: Path, fixture_name: str) -> Path:
    fixture_dir = FIXTURES / "run"
    for path in fixture_dir.iterdir():
        target = tmp_path / path.name
        if path.is_dir():
            shutil.copytree(path, target)
        else:
            shutil.copy2(path, target)
    return tmp_path / fixture_name
