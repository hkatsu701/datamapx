from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from datamapx.cli import app
from datamapx.consolidate import load_consolidate_config, run_consolidate_pipeline
from datamapx.exceptions import ConfigError

FIXTURES = Path(__file__).parent / "fixtures" / "consolidate"


def test_load_consolidate_config_success() -> None:
    config = load_consolidate_config(FIXTURES / "consolidate_config.yml")

    assert config.project.name == "consolidate_sample"
    assert config.consolidate.group_by == ["MATCH_NO"]
    assert config.consolidate.children[0].name == "kojin"


def test_load_consolidate_config_rejects_unknown_parent_reference(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "consolidate_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["consolidate"]["children"][0]["columns"]["reception_id"]["parent_value"] = "missing_parent"
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="unknown parent output column"):
        load_consolidate_config(config_path)


def test_consolidate_pipeline_builds_parent_and_child_outputs(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "consolidate_config.yml"
    config = load_consolidate_config(config_path)

    result = run_consolidate_pipeline(config, config_path)

    parent_df = result.outputs[0].df.reset_index(drop=True)
    child_df = result.outputs[1].df.reset_index(drop=True)
    expected_parent = pd.DataFrame(
        [
            ["1", "GROUP000001", "2024-01-01", "Alice", 300.0, 2, "last note"],
            ["3", "GROUP000002", "2024-01-02", "Bob", 150.0, 1, "solo note"],
        ],
        columns=config.consolidate.parent.output.columns,
    )
    expected_child = pd.DataFrame(
        [
            ["1", "12345", "GROUP000001"],
            ["1", "12346", "GROUP000001"],
            ["3", "12347", "GROUP000002"],
        ],
        columns=config.consolidate.children[0].output.columns,
    )
    pd.testing.assert_frame_equal(parent_df, expected_parent, check_dtype=False)
    pd.testing.assert_frame_equal(child_df, expected_child, check_dtype=False)
    assert result.status == "completed"


def test_consolidate_pipeline_require_same_conflict_fails(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "consolidate_config.yml"
    input_path = config_path.parent / "input_consolidate.csv"
    input_path.write_text(
        "uketsuke_id,MATCH_NO,uketsuke_date,uketsukesha,kingaku,kcode,biko\n"
        "1,GROUP000001,2024-01-01,Alice,100,12345,first note\n"
        "2,GROUP000001,2024-01-03,Alice,200,12346,last note\n",
        encoding="utf-8",
    )
    config = load_consolidate_config(config_path)

    result = run_consolidate_pipeline(config, config_path)

    assert result.status == "failed"
    assert result.stop_reason == "require_same_conflict"


def test_consolidate_pipeline_last_ignores_nulls_and_count_counts_non_nulls(
    tmp_path: Path,
) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "consolidate_config.yml"
    input_path = config_path.parent / "input_consolidate.csv"
    input_path.write_text(
        "uketsuke_id,MATCH_NO,uketsuke_date,uketsukesha,kingaku,kcode,biko\n"
        "1,GROUP000001,2024-01-01,Alice,100,12345,first note\n"
        "2,GROUP000001,2024-01-01,Alice,200,12346,\n"
        "3,GROUP000001,2024-01-01,Alice,300,12347,last note\n"
        "4,GROUP000002,2024-01-02,Bob,150,12348,\n",
        encoding="utf-8",
    )
    config = load_consolidate_config(config_path)

    result = run_consolidate_pipeline(config, config_path)

    parent_df = result.outputs[0].df.reset_index(drop=True)
    assert result.status == "completed"
    assert parent_df.loc[0, "merged_count"] == 3
    assert parent_df.loc[0, "last_biko"] == "last note"
    assert parent_df.loc[1, "merged_count"] == 1
    assert pd.isna(parent_df.loc[1, "last_biko"])


def test_load_consolidate_config_accepts_last_and_count_rules(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "consolidate_config.yml"

    config = load_consolidate_config(config_path)

    assert config.consolidate.parent.columns["merged_count"].rule_name() == "count"
    assert config.consolidate.parent.columns["last_biko"].rule_name() == "last"


def test_consolidate_cli_success_writes_outputs_and_reports(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "consolidate_config.yml"

    result = CliRunner().invoke(app, ["consolidate", str(config_path)])

    assert result.exit_code == 0
    assert "Consolidate completed" in result.output
    assert (config_path.parent / "output" / "Reception.csv").exists()
    assert (config_path.parent / "output" / "kojin.csv").exists()
    summary = json.loads(
        (config_path.parent / "reports" / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["notes"]["consolidate"] is True
    assert len(summary["outputs"]) == 2


def _copy_tree(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    return destination
