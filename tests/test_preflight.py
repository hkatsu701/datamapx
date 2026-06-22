from __future__ import annotations

import shutil
from pathlib import Path

import yaml
from typer.testing import CliRunner

from datamapx.cli import app

FIXTURES = Path(__file__).parent / "fixtures"


def test_preflight_migration_success_and_no_side_effects(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES / "runner", tmp_path / "runner") / "runner_config.yml"

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 0
    assert "Preflight completed: migration" in result.output
    assert "- inputs.users: header readable" in result.output
    assert "- references.departments: header readable" in result.output
    assert "- outputs.users_out: output directory is available" in result.output
    assert not (config_path.parent / "output").exists()
    assert not (config_path.parent / "reports").exists()
    assert not (config_path.parent / "logs").exists()


def test_preflight_migration_missing_input_path_fails(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES / "runner", tmp_path / "runner") / "runner_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["inputs"]["users"]["path"] = "./missing.csv"
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 1
    assert "inputs.users: CSV file not found" in result.output


def test_preflight_migration_required_column_missing_fails(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES / "runner", tmp_path / "runner") / "runner_config.yml"
    input_path = config_path.parent / "input_users.csv"
    input_path.write_text(
        "name,status_code,amount,department_code\nAlice,A,100,engineering\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 1
    assert "inputs.users.user_id: required raw column not found" in result.output


def test_preflight_migration_reference_path_missing_fails(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES / "runner", tmp_path / "runner") / "runner_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["references"]["departments"]["path"] = "./missing_ref.csv"
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 1
    assert "references.departments: CSV file not found" in result.output


def test_preflight_migration_output_conflict_fails(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES / "runner", tmp_path / "runner") / "runner_config.yml"
    output_path = config_path.parent / "output" / "users.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("existing output\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 1
    assert "outputs.users_out: output file already exists" in result.output
    assert output_path.read_text(encoding="utf-8") == "existing output\n"


def test_preflight_migration_row_guardrails_fail(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES / "runner", tmp_path / "runner") / "runner_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data.setdefault("runtime", {})
    data["runtime"]["max_input_rows"] = 1
    data["runtime"]["max_reference_rows"] = 1
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 1
    assert "inputs.users: row count 3 exceeds runtime.max_input_rows 1" in result.output


def test_preflight_migration_referential_integrity_success(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES / "runner", tmp_path / "runner") / "runner_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data.setdefault("validations", {})
    data["validations"]["input"] = [
        {
            "field": "users.department_code",
            "rule": "referential_integrity",
            "reference": "departments",
            "reference_key": "department_code",
        }
    ]
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 0
    assert "Preflight completed: migration" in result.output
    assert "- validations.input[0]: referential_integrity reference_key resolved" in result.output


def test_preflight_migration_referential_integrity_reference_key_missing_fails(
    tmp_path: Path,
) -> None:
    config_path = _copy_tree(FIXTURES / "runner", tmp_path / "runner") / "runner_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data.setdefault("validations", {})
    data["validations"]["input"] = [
        {
            "field": "users.department_code",
            "rule": "referential_integrity",
            "reference": "departments",
            "reference_key": "missing_department_code",
        }
    ]
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 1
    assert (
        "validations.input[0]: missing reference column 'missing_department_code'"
        in result.output
    )


def test_preflight_merge_success(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES / "merge", tmp_path / "merge") / "merge_config.yml"

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 0
    assert "Preflight completed: merge" in result.output
    assert "- inputs.users: key columns resolved" in result.output
    assert "- outputs:" not in result.output
    assert not (config_path.parent / "output").exists()
    assert not (config_path.parent / "reports").exists()
    assert not (config_path.parent / "logs").exists()


def test_preflight_merge_key_column_missing_fails(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES / "merge", tmp_path / "merge") / "merge_config.yml"
    input_path = config_path.parent / "input_users.csv"
    input_path.write_text(
        "name,amount\nAlice,100\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 1
    assert "inputs.users.key: missing key column 'id'" in result.output


def test_preflight_union_success(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES / "union", tmp_path / "union") / "union_config.yml"

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 0
    assert "Preflight completed: union" in result.output
    assert "- inputs.file_a: key columns resolved" in result.output
    assert not (config_path.parent / "output").exists()
    assert not (config_path.parent / "reports").exists()
    assert not (config_path.parent / "logs").exists()


def test_preflight_union_key_column_missing_fails(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES / "union", tmp_path / "union") / "union_config.yml"
    input_path = config_path.parent / "input_union_a.csv"
    input_path.write_text(
        "name,amount\nAlpha,10\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 1
    assert "inputs.file_a.key: missing key column 'id'" in result.output


def test_preflight_unpivot_success(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES / "unpivot", tmp_path / "unpivot") / "unpivot_config.yml"

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 0
    assert "Preflight completed: unpivot" in result.output
    assert "- input: header readable" in result.output
    assert "- output: output directory is available" in result.output
    assert not (config_path.parent / "output").exists()
    assert not (config_path.parent / "reports").exists()
    assert not (config_path.parent / "logs").exists()


def test_preflight_aggregate_success(tmp_path: Path) -> None:
    config_path = (
        _copy_tree(FIXTURES / "aggregate", tmp_path / "aggregate") / "aggregate_config.yml"
    )

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 0
    assert "Preflight completed: aggregate" in result.output
    assert "- input: header readable" in result.output
    assert "- output: output directory is available" in result.output
    assert not (config_path.parent / "output").exists()
    assert not (config_path.parent / "reports").exists()
    assert not (config_path.parent / "logs").exists()


def test_preflight_match_success(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES / "match", tmp_path / "match") / "match_config.yml"

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 0
    assert "Preflight completed: match" in result.output
    assert "- input: header readable" in result.output
    assert "- output: output directory is available" in result.output
    assert not (config_path.parent / "output").exists()
    assert not (config_path.parent / "reports").exists()


def test_preflight_consolidate_success(tmp_path: Path) -> None:
    config_path = (
        _copy_tree(FIXTURES / "consolidate", tmp_path / "consolidate")
        / "consolidate_config.yml"
    )

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 0
    assert "Preflight completed: consolidate" in result.output
    assert "- input: header readable" in result.output
    assert "- consolidate.parent.output: output directory is available" in result.output
    assert "- consolidate.children[0].output: output directory is available" in result.output
    assert not (config_path.parent / "output").exists()
    assert not (config_path.parent / "reports").exists()


def test_preflight_run_all_success(tmp_path: Path) -> None:
    run_config = _copy_tree(FIXTURES / "run", tmp_path / "run")
    merge_config = _copy_tree(FIXTURES / "merge", tmp_path / "merge")
    union_config = _copy_tree(FIXTURES / "union", tmp_path / "union")
    aggregate_config = _copy_tree(FIXTURES / "aggregate", tmp_path / "aggregate")
    match_config = _copy_tree(FIXTURES / "match", tmp_path / "match")
    consolidate_config = _copy_tree(FIXTURES / "consolidate", tmp_path / "consolidate")
    config_path = tmp_path / "run-all.yml"
    _write_run_all_config(
        config_path,
        jobs=[
            {
                "name": "migration",
                "type": "run",
                "config": "./run/run_config.yml",
                "html_report": True,
            },
            {
                "name": "merge_stage",
                "type": "merge",
                "config": "./merge/merge_config.yml",
                "reports_dir": "./merge_reports",
            },
            {
                "name": "union_stage",
                "type": "union",
                "config": "./union/union_config.yml",
                "reports_dir": "./union_reports",
            },
            {
                "name": "aggregate_stage",
                "type": "aggregate",
                "config": "./aggregate/aggregate_config.yml",
                "reports_dir": "./aggregate_reports",
            },
            {
                "name": "match_stage",
                "type": "match",
                "config": "./match/match_config.yml",
            },
            {
                "name": "consolidate_stage",
                "type": "consolidate",
                "config": "./consolidate/consolidate_config.yml",
            },
        ],
    )

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 0
    assert "Preflight completed: run-all" in result.output
    assert "job 1/6: migration [run]" in result.output
    assert "job 2/6: merge_stage [merge]" in result.output
    assert "job 3/6: union_stage [union]" in result.output
    assert "job 4/6: aggregate_stage [aggregate]" in result.output
    assert "job 5/6: match_stage [match]" in result.output
    assert "job 6/6: consolidate_stage [consolidate]" in result.output
    assert not (run_config / "output").exists()
    assert not (merge_config / "output").exists()
    assert not (union_config / "output").exists()
    assert not (aggregate_config / "output").exists()
    assert not (match_config / "output").exists()
    assert not (consolidate_config / "output").exists()
    assert not (tmp_path / "merge_reports").exists()
    assert not (tmp_path / "union_reports").exists()
    assert not (tmp_path / "aggregate_reports").exists()


def test_preflight_run_all_stops_after_first_failure(tmp_path: Path) -> None:
    _copy_tree(FIXTURES / "run", tmp_path / "run")
    _copy_tree(FIXTURES / "merge", tmp_path / "merge")
    config_path = tmp_path / "run-all.yml"
    _write_run_all_config(
        config_path,
        jobs=[
            {
                "name": "migration",
                "type": "run",
                "config": "./run/run_config.yml",
            },
            {
                "name": "merge_stage",
                "type": "merge",
                "config": "./missing_merge.yml",
            },
        ],
    )

    data = yaml.safe_load((tmp_path / "run" / "run_config.yml").read_text(encoding="utf-8"))
    data["inputs"]["users"]["path"] = "./missing.csv"
    (tmp_path / "run" / "run_config.yml").write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["preflight", str(config_path)])

    assert result.exit_code == 1
    assert "run-all job 1/2: migration [run]" in result.output
    assert "job 2/2: merge_stage [merge]" not in result.output
    assert "inputs.users: CSV file not found" in result.output
    assert not (tmp_path / "run" / "output").exists()
    assert not (tmp_path / "merge" / "output").exists()


def _copy_tree(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    return destination


def _write_run_all_config(config_path: Path, *, jobs: list[dict[str, object]]) -> None:
    config = {
        "version": 1,
        "project": {"name": "run_all_preflight_sample"},
        "jobs": jobs,
    }
    rendered = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
    config_path.write_text(rendered, encoding="utf-8")
