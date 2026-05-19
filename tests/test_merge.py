from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from datamapx.cli import app
from datamapx.merge import load_merge_config, run_merge_pipeline

FIXTURES = Path(__file__).parent / "fixtures" / "merge"


def test_load_merge_config_success() -> None:
    config = load_merge_config(FIXTURES / "merge_config.yml")

    assert config.project.name == "merge_sample"
    assert config.merge.base == "users"
    assert config.merge.join_type == "left"
    assert list(config.inputs) == ["users", "accounts"]


def test_merge_pipeline_builds_staging_dataframe(tmp_path: Path) -> None:
    config_path = _copy_fixture_tree(tmp_path, "merge_config.yml")
    config = load_merge_config(config_path)

    result = run_merge_pipeline(config, config_path)

    assert result.status == "completed"
    assert result.output_rows == 3
    assert list(result.output_df.columns) == [
        "id",
        "primary_name",
        "fallback_name",
        "total_amount",
        "min_amount",
        "max_amount",
        "value_count",
        "department_name",
    ]
    assert result.output_df["primary_name"].tolist() == ["Alice", "Bob", "Carol"]
    assert result.output_df["fallback_name"].tolist() == ["Alice A", "Bob B", "Carol C"]
    assert result.output_df["total_amount"].tolist() == [110.0, 220.0, 330.0]


def test_merge_pipeline_reports_duplicate_key_errors(tmp_path: Path) -> None:
    config_path = _copy_fixture_tree(tmp_path, "merge_config_duplicate.yml")
    config = load_merge_config(config_path)

    result = run_merge_pipeline(config, config_path)

    assert result.status == "failed"
    assert result.error_count > 0
    assert any(row.rule == "duplicate_key" for row in result.error_rows)


def test_merge_pipeline_inner_join_skips_unmatched_rows(tmp_path: Path) -> None:
    config_path = _copy_fixture_tree(tmp_path, "merge_config_inner.yml")
    config = load_merge_config(config_path)

    result = run_merge_pipeline(config, config_path)

    assert result.status == "completed"
    assert result.output_rows == 2
    assert result.skipped_count == 1
    assert result.skipped_rows[0].reason == "No merge match in accounts"


def test_merge_cli_success_writes_output_and_reports(tmp_path: Path) -> None:
    config_path = _copy_fixture_tree(tmp_path, "merge_config.yml")

    result = CliRunner().invoke(app, ["merge", str(config_path)])

    assert result.exit_code == 0
    assert "Merge completed" in result.output
    assert "Reports:" in result.output
    assert (config_path.parent / "output" / "merged.csv").exists()
    assert (config_path.parent / "reports" / "errors.csv").exists()
    assert (config_path.parent / "reports" / "skipped.csv").exists()
    assert (config_path.parent / "reports" / "summary.json").exists()


def test_merge_cli_duplicate_key_fails(tmp_path: Path) -> None:
    config_path = _copy_fixture_tree(tmp_path, "merge_config_duplicate.yml")

    result = CliRunner().invoke(app, ["merge", str(config_path)])

    assert result.exit_code == 1
    assert "Merge failed" in result.output
    assert not (config_path.parent / "output" / "merged.csv").exists()
    errors_csv = config_path.parent / "reports" / "errors.csv"
    assert errors_csv.exists()
    assert "duplicate_key" in errors_csv.read_text(encoding="utf-8")


def test_merge_cli_reports_dir_override(tmp_path: Path) -> None:
    config_path = _copy_fixture_tree(tmp_path, "merge_config.yml")
    reports_dir = tmp_path / "custom_reports"

    result = CliRunner().invoke(
        app,
        ["merge", str(config_path), "--reports-dir", str(reports_dir)],
    )

    assert result.exit_code == 0
    assert (reports_dir / "errors.csv").exists()
    assert (reports_dir / "skipped.csv").exists()
    assert (reports_dir / "summary.json").exists()


def test_merge_summary_json_contains_counts(tmp_path: Path) -> None:
    config_path = _copy_fixture_tree(tmp_path, "merge_config.yml")
    result = CliRunner().invoke(app, ["merge", str(config_path)])

    assert result.exit_code == 0
    summary_path = config_path.parent / "reports" / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["counts"]["output_rows"] == 3


def _copy_fixture_tree(tmp_path: Path, name: str) -> Path:
    target_dir = tmp_path / "merge"
    shutil.copytree(FIXTURES, target_dir)
    return target_dir / name
