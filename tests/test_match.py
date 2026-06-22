from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from datamapx.cli import app
from datamapx.exceptions import ConfigError
from datamapx.io.errors import CsvWriteError
from datamapx.match import load_match_config, run_match_pipeline
from datamapx.match.reports import write_match_reports

FIXTURES = Path(__file__).parent / "fixtures" / "match"


def test_load_match_config_success() -> None:
    config = load_match_config(FIXTURES / "match_config.yml")

    assert config.project.name == "match_sample"
    assert config.match.keys == ["key_1", "key_2", "key_3", "key_4"]
    assert config.match.output_column == "MATCH_NO"


def test_load_match_config_rejects_output_column_collision(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "match_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["match"]["output_column"] = "record_id"
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="must not collide"):
        load_match_config(config_path)


def test_match_pipeline_assigns_ids(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "match_config.yml"
    config = load_match_config(config_path)

    result = run_match_pipeline(config, config_path)

    expected = pd.DataFrame(
        [
            ["1", "A", "X", "2024", "T1", 100.0, "Alice", "GROUP000001"],
            ["2", "A", "X", "2024", "T1", 200.0, "Alice", "GROUP000001"],
            ["3", "B", "Y", "2024", "T2", 150.0, "Bob", "GROUP000002"],
        ],
        columns=config.output.columns,
    )
    pd.testing.assert_frame_equal(
        result.output_df.reset_index(drop=True),
        expected,
        check_dtype=False,
    )
    assert result.status == "completed"


def test_match_pipeline_missing_key_fails(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "match_config.yml"
    input_path = config_path.parent / "input_match.csv"
    input_path.write_text(
        "record_id,key_1,key_2,key_3,key_4,amount,person\n1,A,X,2024,T1,100,Alice\n2,,X,2024,T1,200,Alice\n",
        encoding="utf-8",
    )
    config = load_match_config(config_path)

    result = run_match_pipeline(config, config_path)

    assert result.status == "failed"
    assert result.error_count == 1
    assert result.stop_reason == "missing_match_key"


def test_match_cli_success_writes_output_and_reports(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "match_config.yml"

    result = CliRunner().invoke(app, ["match", str(config_path)])

    assert result.exit_code == 0
    assert "Match completed" in result.output
    assert (config_path.parent / "output" / "matched.csv").exists()
    summary = json.loads(
        (config_path.parent / "reports" / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["notes"]["match"] is True
    assert summary["counts"]["output_rows"] == 3


def test_match_cli_reports_dir_override(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "match_config.yml"
    reports_dir = tmp_path / "custom_reports"

    result = CliRunner().invoke(
        app,
        ["match", str(config_path), "--reports-dir", str(reports_dir)],
    )

    assert result.exit_code == 0
    assert (reports_dir / "errors.csv").exists()
    assert (reports_dir / "skipped.csv").exists()
    assert (reports_dir / "summary.json").exists()


def test_write_match_reports_errors_when_directory_is_file(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "match_config.yml"
    config = load_match_config(config_path)
    result = run_match_pipeline(config, config_path)
    reports_dir = tmp_path / "reports_target"
    reports_dir.write_text("not a directory", encoding="utf-8")

    with pytest.raises(CsvWriteError):
        write_match_reports(result, config, config_path, reports_dir=reports_dir)


def _copy_tree(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    return destination
