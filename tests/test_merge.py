from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from datamapx.cli import app
from datamapx.merge import load_merge_config, run_merge_pipeline, run_merge_wizard

FIXTURES = Path(__file__).parent / "fixtures" / "merge"
EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


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


def test_merge_cli_html_report_writes_file(tmp_path: Path) -> None:
    config_path = _copy_fixture_tree(tmp_path, "merge_config.yml")
    reports_dir = tmp_path / "custom_reports"

    result = CliRunner().invoke(
        app,
        ["merge", str(config_path), "--reports-dir", str(reports_dir), "--html-report"],
    )

    assert result.exit_code == 0
    assert "- html:" in result.output
    assert (reports_dir / "report.html").exists()


def test_merge_summary_json_contains_counts(tmp_path: Path) -> None:
    config_path = _copy_fixture_tree(tmp_path, "merge_config.yml")
    result = CliRunner().invoke(app, ["merge", str(config_path)])

    assert result.exit_code == 0
    summary_path = config_path.parent / "reports" / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["counts"]["output_rows"] == 3


def test_example_05_merge_wizard_merge_config_loads() -> None:
    config = load_merge_config(EXAMPLES / "05_merge_wizard" / "merge.yml")

    assert config.project.name == "merge_wizard_example"
    assert config.merge.base == "users"
    assert config.merge.join_type == "left"
    assert list(config.merge.columns) == [
        "id",
        "display_name",
        "total_amount",
        "department_name",
    ]
    assert config.output.columns == [
        "id",
        "display_name",
        "total_amount",
        "department_name",
    ]


def test_example_05_merge_wizard_pipeline_matches_expected_output(
    tmp_path: Path,
) -> None:
    example_dir = _copy_example_tree(tmp_path, "05_merge_wizard")
    config_path = example_dir / "merge.yml"
    expected_path = example_dir / "expected" / "output" / "merged.csv"

    config = load_merge_config(config_path)
    result = run_merge_pipeline(config, config_path)

    expected_df = pd.read_csv(expected_path)
    pd.testing.assert_frame_equal(
        result.output_df.reset_index(drop=True),
        expected_df,
        check_dtype=False,
    )
    assert result.status == "completed"
    assert result.output_rows == 3


def test_merge_wizard_generates_valid_merge_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "merge.yml"
    output_path = tmp_path / "staging" / "merged.csv"
    responses = iter(
        [
            "1",
            "merge_wizard_sample",
            str(config_path),
            str(output_path),
            "2",
            "users",
            str(FIXTURES / "input_users.csv"),
            "1",
            "accounts",
            str(FIXTURES / "input_accounts.csv"),
            "1",
            "1",
            "1",
            "1,2,3",
            "total_amount",
            "4",
            "3,7",
            "1",
        ]
    )

    monkeypatch.setattr("typer.prompt", lambda *_args, **_kwargs: next(responses))
    confirm_responses = iter([True, False, False, False, False, True])
    monkeypatch.setattr("typer.confirm", lambda *_args, **_kwargs: next(confirm_responses))

    result = run_merge_wizard()
    captured = capsys.readouterr().out

    assert result.config_path == config_path
    assert result.project_name == "merge_wizard_sample"
    assert result.input_count == 2
    assert result.output_columns == ["id", "name", "amount", "total_amount"]
    assert config_path.exists()

    config = load_merge_config(config_path)
    assert config.project.name == "merge_wizard_sample"
    assert config.merge.base == "users"
    assert config.merge.join_type == "left"
    assert list(config.merge.columns) == ["id", "name", "amount", "total_amount"]
    assert config.output.path == str(output_path)
    assert "この設定で行うこと" in captured
    assert "users を基準にして" in captured
    assert "合計します" in captured
    assert config.merge.columns["name"].source == "users.name"
    assert config.merge.columns["total_amount"].sum == [
        "users.amount",
        "accounts.amount",
    ]


def test_merge_wizard_cli_generates_merge_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "merge.yml"
    output_path = tmp_path / "staging" / "merged.csv"
    responses = iter(
        [
            "1",
            "merge_wizard_sample",
            str(config_path),
            str(output_path),
            "2",
            "users",
            str(FIXTURES / "input_users.csv"),
            "1",
            "accounts",
            str(FIXTURES / "input_accounts.csv"),
            "1",
            "1",
            "1",
            "1,2",
            "1",
        ]
    )

    monkeypatch.setattr("typer.prompt", lambda *_args, **_kwargs: next(responses))
    confirm_responses = iter([False, False, False, True, True])
    monkeypatch.setattr("typer.confirm", lambda *_args, **_kwargs: next(confirm_responses))

    result = CliRunner().invoke(app, ["merge-wizard"])

    assert result.exit_code == 0
    assert "1/6. 最初にやりたいことを番号で選択" in result.output
    assert "入力1" in result.output
    assert "sample:" in result.output
    assert "出力したい列を番号で選択" in result.output
    assert "出力列名の確認" in result.output
    assert "推奨ルールを適用します。" in result.output
    assert "Review" in result.output
    assert "merge.yml を作成しました" in result.output
    assert config_path.exists()

    config = load_merge_config(config_path)
    assert config.output.columns == ["id", "name"]
    assert config.merge.columns["id"].source == "users.id"
    assert config.merge.columns["name"].source == "users.name"


def test_merge_wizard_review_can_redo_column_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "merge.yml"
    output_path = tmp_path / "staging" / "merged.csv"
    responses = iter(
        [
            "2",
            "merge_wizard_sample",
            str(config_path),
            str(output_path),
            "2",
            "users",
            str(FIXTURES / "input_users.csv"),
            "1",
            "accounts",
            str(FIXTURES / "input_accounts.csv"),
            "1",
            "1",
            "1",
            "1,6",
            "2",
            "1",
        ]
    )

    merge_columns_sequence = iter(
        [
            {
                "id": {"source": "users.id"},
                "department_name": {"source": "accounts.department_name"},
            },
            {
                "id": {"source": "users.id"},
                "department_name": {
                    "first": ["users.name", "accounts.department_name"],
                },
            },
        ]
    )

    monkeypatch.setattr("typer.prompt", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(
        "datamapx.merge.wizard._prompt_merge_column_rules",
        lambda *args, **kwargs: next(merge_columns_sequence),
    )
    confirm_responses = iter([False, False, False])
    monkeypatch.setattr("typer.confirm", lambda *_args, **_kwargs: next(confirm_responses))

    result = run_merge_wizard()
    captured = capsys.readouterr().out

    assert result.config_path == config_path
    assert config_path.exists()
    assert captured.count("Review") >= 2
    assert "この設定で行うこと" in captured
    assert "そのまま使います" in captured
    assert "先頭の値を使います" in captured

    config = load_merge_config(config_path)
    assert config.output.columns == ["id", "department_name"]
    assert config.merge.columns["id"].source == "users.id"
    assert config.merge.columns["department_name"].first == [
        "users.name",
        "accounts.department_name",
    ]


def _copy_fixture_tree(tmp_path: Path, name: str) -> Path:
    target_dir = tmp_path / "merge"
    shutil.copytree(FIXTURES, target_dir)
    return target_dir / name


def _copy_example_tree(tmp_path: Path, name: str) -> Path:
    target_dir = tmp_path / "examples"
    shutil.copytree(EXAMPLES, target_dir)
    return target_dir / name
