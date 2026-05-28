from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from datamapx.cli import app
from datamapx.exceptions import ConfigError
from datamapx.io.errors import CsvReadError
from datamapx.union import load_union_config, run_union_pipeline

FIXTURES = Path(__file__).parent / "fixtures" / "union"
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_load_union_config_success() -> None:
    config = load_union_config(FIXTURES / "union_config.yml")

    assert config.project.name == "union_sample"
    assert list(config.inputs) == ["file_a", "file_b"]
    assert config.union.columns == ["id", "name", "amount"]
    assert config.output.columns == ["id", "name", "amount"]


def test_union_pipeline_builds_union_dataframe(tmp_path: Path) -> None:
    example_dir = _copy_tree(EXAMPLES / "09_union", tmp_path / "example")
    config_path = example_dir / "union.yml"
    expected_path = example_dir / "expected" / "output" / "unioned.csv"

    config = load_union_config(config_path)
    result = run_union_pipeline(config, config_path)

    expected_df = pd.read_csv(expected_path)
    pd.testing.assert_frame_equal(
        result.output_df.reset_index(drop=True),
        expected_df,
        check_dtype=False,
    )
    assert result.status == "completed"
    assert result.output_rows == 4
    assert [summary.name for summary in result.inputs] == ["file_a", "file_b"]


def test_union_pipeline_reports_duplicate_key_errors_within_input(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "union_config_duplicate_within.yml"
    config = load_union_config(config_path)

    result = run_union_pipeline(config, config_path)

    assert result.status == "failed"
    assert result.error_count == 2
    assert all(row.rule == "duplicate_key" for row in result.error_rows)


def test_union_pipeline_reports_duplicate_key_errors_across_inputs(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "union_config_duplicate_across.yml"
    config = load_union_config(config_path)

    result = run_union_pipeline(config, config_path)

    assert result.status == "failed"
    assert result.error_count == 2
    assert any(row.input_name == "file_a" for row in result.error_rows)
    assert any(row.input_name == "file_b" for row in result.error_rows)


def test_union_pipeline_reports_missing_key_errors(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "union_config_missing_key.yml"
    config = load_union_config(config_path)

    result = run_union_pipeline(config, config_path)

    assert result.status == "failed"
    assert result.error_count == 1
    assert result.error_rows[0].rule == "missing_key"


def test_union_config_column_mismatch_fails(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "union_config_mismatch.yml"

    with pytest.raises(ConfigError, match="must match output.columns exactly"):
        load_union_config(config_path)


def test_union_pipeline_fails_when_required_schema_column_missing(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "union_config_missing_required.yml"
    config = load_union_config(config_path)

    with pytest.raises(CsvReadError, match="required column not found"):
        run_union_pipeline(config, config_path)


def test_union_cli_success_writes_output_and_reports(tmp_path: Path) -> None:
    example_dir = _copy_tree(EXAMPLES / "09_union", tmp_path / "example")
    config_path = example_dir / "union.yml"

    result = CliRunner().invoke(app, ["union", str(config_path)])

    assert result.exit_code == 0
    assert "Union completed" in result.output
    assert (example_dir / "output" / "unioned.csv").exists()
    assert (example_dir / "reports" / "errors.csv").exists()
    assert (example_dir / "reports" / "skipped.csv").exists()
    summary = json.loads((example_dir / "reports" / "summary.json").read_text(encoding="utf-8"))
    assert summary["notes"]["union"] is True
    assert summary["counts"]["output_rows"] == 4


def test_union_cli_reports_dir_override(tmp_path: Path) -> None:
    example_dir = _copy_tree(EXAMPLES / "09_union", tmp_path / "example")
    config_path = example_dir / "union.yml"
    reports_dir = tmp_path / "custom_reports"

    result = CliRunner().invoke(
        app,
        ["union", str(config_path), "--reports-dir", str(reports_dir)],
    )

    assert result.exit_code == 0
    assert (reports_dir / "errors.csv").exists()
    assert (reports_dir / "skipped.csv").exists()
    assert (reports_dir / "summary.json").exists()


def test_union_cli_html_report_writes_file(tmp_path: Path) -> None:
    example_dir = _copy_tree(EXAMPLES / "09_union", tmp_path / "example")
    config_path = example_dir / "union.yml"
    reports_dir = tmp_path / "custom_reports"

    result = CliRunner().invoke(
        app,
        ["union", str(config_path), "--reports-dir", str(reports_dir), "--html-report"],
    )

    assert result.exit_code == 0
    assert "- html:" in result.output
    assert (reports_dir / "report.html").exists()


def test_union_cli_duplicate_key_fails(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "union_config_duplicate_within.yml"

    result = CliRunner().invoke(app, ["union", str(config_path)])

    assert result.exit_code == 1
    assert "Union failed" in result.output
    assert not (config_path.parent / "output" / "unioned.csv").exists()
    errors_csv = config_path.parent / "reports" / "errors.csv"
    assert errors_csv.exists()
    assert "duplicate_key" in errors_csv.read_text(encoding="utf-8")


def test_union_cli_if_exists_error_does_not_overwrite(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "union_config_if_exists_error.yml"
    output_path = config_path.parent / "output" / "unioned.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("old content\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["union", str(config_path)])

    assert result.exit_code == 1
    assert output_path.read_text(encoding="utf-8") == "old content\n"


def _copy_tree(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    return destination
