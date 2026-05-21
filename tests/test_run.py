from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import yaml
from typer.testing import CliRunner

from datamapx.cli import app

FIXTURES = Path(__file__).parent / "fixtures" / "run"


def test_run_writes_main_output_and_reports(tmp_path: Path) -> None:
    config_path = _prepare_fixture(tmp_path, "run_config.yml")

    result = CliRunner().invoke(app, ["run", str(config_path)])

    assert result.exit_code == 0
    assert "Run completed" in result.output
    assert "Output:" in result.output
    assert "Reports:" in result.output
    assert "Counts:" in result.output

    output_csv = tmp_path / "output" / "users_out.csv"
    assert output_csv.exists()
    rows = list(csv.DictReader(output_csv.open("r", encoding="utf-8-sig")))
    assert rows[0]["id"] == "u001"
    assert list(rows[0].keys()) == [
        "id",
        "name",
        "system_code",
        "status",
        "department_name",
        "total_amount",
    ]

    report_dir = tmp_path / "reports"
    assert (report_dir / "errors.csv").exists()
    assert (report_dir / "skipped.csv").exists()
    assert (report_dir / "summary.json").exists()

    summary = json.loads((report_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["notes"]["dry_run"] is False
    assert summary["notes"]["output_file_written"] is True
    assert summary["counts"]["output_rows"] == 3


def test_run_omits_invalid_and_skipped_rows_from_output(tmp_path: Path) -> None:
    config_path = _prepare_fixture(tmp_path, "run_config_with_errors.yml")

    result = CliRunner().invoke(app, ["run", str(config_path)])

    assert result.exit_code == 0

    output_csv = tmp_path / "output" / "users_out.csv"
    rows = list(csv.DictReader(output_csv.open("r", encoding="utf-8-sig")))
    assert [row["id"] for row in rows] == ["u001"]

    summary = json.loads((tmp_path / "reports" / "summary.json").read_text(encoding="utf-8"))
    assert summary["counts"]["skipped_rows"] == 1
    assert summary["counts"]["error_rows"] >= 1


def test_run_check_failure_exits_nonzero(tmp_path: Path) -> None:
    config_path = _prepare_fixture(tmp_path, "run_config.yml")
    _set_checks(config_path, [{"name": "row_count_check", "rule": "input_rows == 0"}])

    result = CliRunner().invoke(app, ["run", str(config_path)])

    assert result.exit_code == 1
    assert "One or more checks failed." in result.output

    summary = json.loads((tmp_path / "reports" / "summary.json").read_text(encoding="utf-8"))
    assert summary["counts"]["check_failures"] == 1
    assert summary["notes"]["checks_passed"] is False
    assert summary["checks"][0]["passed"] is False
    assert (tmp_path / "output" / "users_out.csv").exists()


def test_run_validation_stop_exits_nonzero_and_skips_output(tmp_path: Path) -> None:
    config_path = _prepare_fixture(tmp_path, "run_config_with_errors.yml")
    _set_error_handling(config_path, {"on_validation_error": "stop"})

    result = CliRunner().invoke(app, ["run", str(config_path)])

    assert result.exit_code == 1
    assert "Execution stopped (validation_error)" in result.output
    assert not (tmp_path / "output" / "users_out.csv").exists()

    summary = json.loads((tmp_path / "reports" / "summary.json").read_text(encoding="utf-8"))
    assert summary["notes"]["fatal_error"] is True
    assert summary["notes"]["stop_reason"] == "validation_error"


def test_run_lookup_missing_stop_exits_nonzero_and_keeps_preview_counts(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "mapping"
    for path in fixture_dir.iterdir():
        target = tmp_path / path.name
        if path.is_dir():
            shutil.copytree(path, target)
        else:
            shutil.copy2(path, target)

    config_path = tmp_path / "mapping_config_lookup_missing_error.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["error_handling"]["on_lookup_missing"] = "stop"
    rendered = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    config_path.write_text(rendered, encoding="utf-8")

    result = CliRunner().invoke(app, ["run", str(config_path)])

    assert result.exit_code == 1
    assert "Execution stopped (lookup_missing)" in result.output
    assert not (tmp_path / "output" / "users.csv").exists()

    summary = json.loads((tmp_path / "output" / "summary.json").read_text(encoding="utf-8"))
    assert summary["counts"]["output_rows"] == 2
    assert summary["notes"]["fatal_error"] is True
    assert summary["notes"]["stop_reason"] == "lookup_missing"


def test_run_max_errors_stop_exits_nonzero(tmp_path: Path) -> None:
    config_path = _prepare_fixture(tmp_path, "run_config_with_errors.yml")
    _set_error_handling(config_path, {"max_errors": 0})

    result = CliRunner().invoke(app, ["run", str(config_path)])

    assert result.exit_code == 1
    assert "Execution stopped (max_errors_exceeded)" in result.output

    summary = json.loads((tmp_path / "reports" / "summary.json").read_text(encoding="utf-8"))
    assert summary["notes"]["fatal_error"] is True
    assert summary["notes"]["stop_reason"] == "max_errors_exceeded"
    assert summary["notes"]["max_errors_exceeded"] is True


def test_run_reports_dir_writes_reports_to_override_directory(tmp_path: Path) -> None:
    config_path = _prepare_fixture(tmp_path, "run_config_with_errors.yml")
    reports_dir = tmp_path / "custom_reports"

    result = CliRunner().invoke(
        app,
        ["run", str(config_path), "--reports-dir", str(reports_dir)],
    )

    assert result.exit_code == 0
    assert (reports_dir / "errors.csv").exists()
    assert (reports_dir / "skipped.csv").exists()
    assert (reports_dir / "summary.json").exists()
    assert (tmp_path / "output" / "users_out.csv").exists()


def test_run_if_exists_error_fails_when_output_exists(tmp_path: Path) -> None:
    config_path = _prepare_fixture(tmp_path, "run_config_if_exists_error.yml")
    output_path = tmp_path / "output" / "users_out.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("old content", encoding="utf-8")

    result = CliRunner().invoke(app, ["run", str(config_path)])

    assert result.exit_code == 1
    assert "output file already exists" in result.output
    assert output_path.read_text(encoding="utf-8") == "old content"


def test_run_if_exists_overwrite_replaces_existing_output(tmp_path: Path) -> None:
    config_path = _prepare_fixture(tmp_path, "run_config_if_exists_overwrite.yml")
    output_path = tmp_path / "output" / "users_out.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("old content", encoding="utf-8")

    result = CliRunner().invoke(app, ["run", str(config_path)])

    assert result.exit_code == 0
    content = output_path.read_text(encoding="utf-8-sig")
    assert "old content" not in content
    assert "id,name" in content


def _prepare_fixture(tmp_path: Path, fixture_name: str) -> Path:
    fixture_dir = FIXTURES
    for path in fixture_dir.iterdir():
        target = tmp_path / path.name
        if path.is_dir():
            shutil.copytree(path, target)
        else:
            shutil.copy2(path, target)
    return tmp_path / fixture_name


def _set_checks(config_path: Path, checks: list[dict[str, object]]) -> None:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["checks"] = checks
    rendered = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    config_path.write_text(rendered, encoding="utf-8")


def _set_error_handling(config_path: Path, updates: dict[str, object]) -> None:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["error_handling"].update(updates)
    rendered = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    config_path.write_text(rendered, encoding="utf-8")
