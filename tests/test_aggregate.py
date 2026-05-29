from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from datamapx.aggregate import load_aggregate_config, run_aggregate_pipeline
from datamapx.aggregate.reports import write_aggregate_reports
from datamapx.cli import app
from datamapx.exceptions import ConfigError
from datamapx.io.errors import CsvWriteError

FIXTURES = Path(__file__).parent / "fixtures" / "aggregate"


def test_load_aggregate_config_success() -> None:
    config = load_aggregate_config(FIXTURES / "aggregate_config.yml")

    assert config.project.name == "aggregate_sample"
    assert config.input_.path == "./input_payment_lines.csv"
    assert config.aggregate.group_by == ["customer_id"]
    assert list(config.aggregate.columns) == [
        "customer_id",
        "total_amount",
        "payment_count",
        "first_paid_on",
        "last_paid_on",
        "first_note",
        "last_note",
    ]


def test_load_aggregate_config_rejects_missing_required_sections(tmp_path: Path) -> None:
    config_path = tmp_path / "aggregate.yml"
    config_path.write_text(
        yaml.safe_dump({"version": 1, "project": {"name": "x"}}, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_aggregate_config(config_path)


def test_load_aggregate_config_rejects_output_column_mismatch(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "aggregate_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["output"]["columns"] = ["customer_id", "total_amount"]
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="must match aggregate output columns exactly"):
        load_aggregate_config(config_path)


def test_load_aggregate_config_rejects_unknown_schema_columns(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "aggregate_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["aggregate"]["group_by"] = ["missing_group"]
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="unknown input schema fields"):
        load_aggregate_config(config_path)


def test_aggregate_pipeline_groups_rows(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "aggregate_config.yml"
    config = load_aggregate_config(config_path)

    result = run_aggregate_pipeline(config, config_path)

    expected = pd.DataFrame(
        [
            {
                "customer_id": "C001",
                "total_amount": 250.0,
                "payment_count": 2,
                "first_paid_on": pd.Timestamp("2024-01-01"),
                "last_paid_on": pd.Timestamp("2024-01-05"),
                "first_note": "first",
                "last_note": "beta",
            },
            {
                "customer_id": "C002",
                "total_amount": 200.0,
                "payment_count": 1,
                "first_paid_on": pd.Timestamp("2024-01-03"),
                "last_paid_on": pd.Timestamp("2024-01-03"),
                "first_note": "alpha",
                "last_note": "alpha",
            },
            {
                "customer_id": "C003",
                "total_amount": 50.0,
                "payment_count": 1,
                "first_paid_on": pd.Timestamp("2024-01-04"),
                "last_paid_on": pd.Timestamp("2024-01-04"),
                "first_note": "gamma",
                "last_note": "gamma",
            },
        ],
        columns=list(config.output.columns),
    )

    pd.testing.assert_frame_equal(
        result.output_df.reset_index(drop=True),
        expected,
        check_dtype=False,
    )
    assert result.status == "completed"
    assert result.output_rows == 3


def test_aggregate_pipeline_preserves_group_order(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "aggregate_config.yml"
    config = load_aggregate_config(config_path)

    result = run_aggregate_pipeline(config, config_path)

    assert list(result.output_df["customer_id"]) == ["C001", "C002", "C003"]


def test_aggregate_pipeline_uses_pruned_usecols(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "aggregate_config.yml"
    config = load_aggregate_config(config_path)
    calls: list[dict[str, object]] = []
    original_read_csv = pd.read_csv

    def fake_read_csv(*args: object, **kwargs: object):
        calls.append(dict(kwargs))
        return original_read_csv(*args, **kwargs)

    monkeypatch.setattr("datamapx.io.csv_reader.pd.read_csv", fake_read_csv)

    result = run_aggregate_pipeline(config, config_path)

    assert result.status == "completed"
    assert calls
    assert calls[0]["usecols"] == ["customer_id", "amount", "paid_on", "note"]


def test_aggregate_cli_success_writes_output_and_reports(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "aggregate_config.yml"

    result = CliRunner().invoke(app, ["aggregate", str(config_path)])

    assert result.exit_code == 0
    assert "Aggregate completed" in result.output
    assert (config_path.parent / "output" / "payment_summary.csv").exists()
    assert (config_path.parent / "reports" / "errors.csv").exists()
    assert (config_path.parent / "reports" / "skipped.csv").exists()
    summary = json.loads(
        (config_path.parent / "reports" / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["notes"]["aggregate"] is True
    assert summary["counts"]["output_rows"] == 3


def test_aggregate_cli_reports_dir_override(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "aggregate_config.yml"
    reports_dir = tmp_path / "custom_reports"

    result = CliRunner().invoke(
        app,
        ["aggregate", str(config_path), "--reports-dir", str(reports_dir)],
    )

    assert result.exit_code == 0
    assert (reports_dir / "errors.csv").exists()
    assert (reports_dir / "skipped.csv").exists()
    assert (reports_dir / "summary.json").exists()


def test_aggregate_cli_html_report_writes_file(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "aggregate_config.yml"
    reports_dir = tmp_path / "custom_reports"

    result = CliRunner().invoke(
        app,
        ["aggregate", str(config_path), "--reports-dir", str(reports_dir), "--html-report"],
    )

    assert result.exit_code == 0
    assert "- html:" in result.output
    assert (reports_dir / "report.html").exists()


def test_aggregate_cli_max_output_rows_skips_output(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "aggregate_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data.setdefault("runtime", {})
    data["runtime"]["max_output_rows"] = 2
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["aggregate", str(config_path)])

    assert result.exit_code == 1
    assert "Aggregate failed" in result.output
    assert "Stop:" in result.output
    assert "output row count 3 exceeded runtime.max_output_rows 2" in result.output
    assert not (config_path.parent / "output" / "payment_summary.csv").exists()
    summary = json.loads(
        (config_path.parent / "reports" / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["status"] == "failed"
    assert summary["notes"]["output_file_written"] is False


def test_aggregate_cli_group_key_missing_fails(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "aggregate_config.yml"
    input_path = config_path.parent / "input_payment_lines.csv"
    input_path.write_text(
        "customer_id,amount,paid_on,note\nC001,100,2024-01-05,first\n,200,2024-01-03,alpha\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["aggregate", str(config_path)])

    assert result.exit_code == 1
    assert "missing group key values" in result.output
    assert not (config_path.parent / "output" / "payment_summary.csv").exists()


def test_aggregate_cli_numeric_conversion_failure(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "aggregate_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["input"]["schema"]["amount"]["type"] = "string"
    data["input"]["schema"]["amount"]["normalize"] = ["trim"]
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    input_path = config_path.parent / "input_payment_lines.csv"
    input_path.write_text(
        "customer_id,amount,paid_on,note\nC001,abc,2024-01-05,first\nC001,150,2024-01-01,beta\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["aggregate", str(config_path)])

    assert result.exit_code == 1
    assert "numeric conversion failed" in result.output
    assert not (config_path.parent / "output" / "payment_summary.csv").exists()


def test_aggregate_cli_if_exists_error_does_not_overwrite(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "aggregate_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["output"]["if_exists"] = "error"
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    output_path = config_path.parent / "output" / "payment_summary.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("old content\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["aggregate", str(config_path)])

    assert result.exit_code == 1
    assert output_path.read_text(encoding="utf-8") == "old content\n"


def test_aggregate_reports_are_atomic_on_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "aggregate_config.yml"
    config = load_aggregate_config(config_path)
    result = run_aggregate_pipeline(config, config_path)
    errors_csv = config_path.parent / "reports" / "errors.csv"
    errors_csv.parent.mkdir(parents=True, exist_ok=True)
    errors_csv.write_text("old errors\n", encoding="utf-8")

    monkeypatch.setattr("datamapx.report.atomic.os.replace", _raise_os_error)

    with pytest.raises(CsvWriteError, match="cannot write report CSV"):
        write_aggregate_reports(result, config, config_path)

    assert errors_csv.read_text(encoding="utf-8") == "old errors\n"
    assert not list(errors_csv.parent.glob(".errors.csv.*.tmp"))


def _copy_tree(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    return destination


def _raise_os_error(*_args, **_kwargs) -> None:
    raise OSError("boom")
