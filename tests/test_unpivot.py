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
from datamapx.unpivot import load_unpivot_config, run_unpivot_pipeline
from datamapx.unpivot.reports import write_unpivot_reports

FIXTURES = Path(__file__).parent / "fixtures" / "unpivot"


def test_load_unpivot_config_success() -> None:
    config = load_unpivot_config(FIXTURES / "unpivot_config.yml")

    assert config.project.name == "unpivot_sample"
    assert config.input_.path == "./input_payments_wide.csv"
    assert config.unpivot.id_columns == ["customer_id"]
    assert config.output.columns == ["customer_id", "year", "amount"]


def test_load_unpivot_config_rejects_missing_required_sections(tmp_path: Path) -> None:
    config_path = tmp_path / "unpivot.yml"
    config_path.write_text(
        yaml.safe_dump({"version": 1, "project": {"name": "x"}}, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_unpivot_config(config_path)


def test_load_unpivot_config_rejects_output_column_mismatch(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "unpivot_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["output"]["columns"] = ["customer_id", "amount", "year"]
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="must match unpivot output columns exactly"):
        load_unpivot_config(config_path)


def test_load_unpivot_config_rejects_unknown_schema_columns(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "unpivot_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["unpivot"]["id_columns"] = ["missing_id"]
    data["unpivot"]["value_columns"] = {"missing_amount": "2025"}
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="unknown input schema fields"):
        load_unpivot_config(config_path)


def test_load_unpivot_config_rejects_unknown_filter_field(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "unpivot_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["filters"] = {
        "exclude": [
            {
                "if": "input.unknown_field is null",
                "reason": "invalid row",
            }
        ]
    }
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="unknown input field"):
        load_unpivot_config(config_path)


def test_unpivot_pipeline_expands_rows(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "unpivot_config.yml"
    config = load_unpivot_config(config_path)

    result = run_unpivot_pipeline(config, config_path)

    expected = pd.DataFrame(
        [
            {"customer_id": "C001", "year": "2023", "amount": 1000.0},
            {"customer_id": "C001", "year": "2024", "amount": 1200.0},
            {"customer_id": "C002", "year": "2023", "amount": 1500.0},
        ],
        columns=["customer_id", "year", "amount"],
    )

    pd.testing.assert_frame_equal(
        result.output_df.reset_index(drop=True),
        expected,
        check_dtype=False,
    )
    assert result.status == "completed"
    assert result.output_rows == 3
    assert result.skipped_count == 0
    assert result.skipped_rows == []


def test_unpivot_pipeline_applies_filters_before_expanding_rows(tmp_path: Path) -> None:
    fixture = _copy_tree(FIXTURES, tmp_path / "fixture")
    input_path = fixture / "input_payments_wide.csv"
    input_path.write_text(
        input_path.read_text(encoding="utf-8") + "C003,,\n",
        encoding="utf-8",
    )
    config_path = fixture / "unpivot_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["filters"] = {
        "exclude": [
            {
                "if": "input.amount_2023 is null and input.amount_2024 is null",
                "reason": "All amount columns are blank",
            }
        ]
    }
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    config = load_unpivot_config(config_path)

    result = run_unpivot_pipeline(config, config_path)

    assert result.output_rows == 3
    assert result.skipped_count == 1
    assert any(
        row.row_number == 3 and row.reason == "All amount columns are blank"
        for row in result.skipped_rows
    )


def test_unpivot_pipeline_keeps_null_values_when_configured(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "unpivot_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["unpivot"]["drop_null_values"] = False
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    config = load_unpivot_config(config_path)

    result = run_unpivot_pipeline(config, config_path)

    assert result.status == "completed"
    assert result.output_rows == 4
    assert pd.isna(result.output_df.iloc[3]["amount"])


def test_unpivot_pipeline_uses_pruned_usecols(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "unpivot_config.yml"
    config = load_unpivot_config(config_path)
    calls: list[dict[str, object]] = []
    original_read_csv = pd.read_csv

    def fake_read_csv(*args: object, **kwargs: object):
        calls.append(dict(kwargs))
        return original_read_csv(*args, **kwargs)

    monkeypatch.setattr("datamapx.io.csv_reader.pd.read_csv", fake_read_csv)

    result = run_unpivot_pipeline(config, config_path)

    assert result.status == "completed"
    assert calls
    assert calls[0]["usecols"] == ["customer_id", "amount_2023", "amount_2024"]


def test_unpivot_cli_success_writes_output_and_reports(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "unpivot_config.yml"

    result = CliRunner().invoke(app, ["unpivot", str(config_path)])

    assert result.exit_code == 0
    assert "Unpivot completed" in result.output
    assert (config_path.parent / "output" / "payments_long.csv").exists()
    assert (config_path.parent / "reports" / "errors.csv").exists()
    assert (config_path.parent / "reports" / "skipped.csv").exists()
    summary = json.loads(
        (config_path.parent / "reports" / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["notes"]["unpivot"] is True
    assert summary["counts"]["output_rows"] == 3


def test_unpivot_cli_filters_rows_and_reports_skip_reason(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "unpivot_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["filters"] = {
        "exclude": [
            {
                "if": "input.customer_id == 'C002'",
                "reason": "Customer excluded before unpivot",
            }
        ]
    }
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["unpivot", str(config_path)])

    assert result.exit_code == 0
    output_df = pd.read_csv(
        config_path.parent / "output" / "payments_long.csv",
        dtype="string",
    )
    assert output_df["customer_id"].tolist() == ["C001", "C001"]
    skipped_df = pd.read_csv(
        config_path.parent / "reports" / "skipped.csv",
        dtype="string",
    )
    assert "Customer excluded before unpivot" in skipped_df["reason"].tolist()


def test_unpivot_cli_reports_dir_override(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "unpivot_config.yml"
    reports_dir = tmp_path / "custom_reports"

    result = CliRunner().invoke(
        app,
        ["unpivot", str(config_path), "--reports-dir", str(reports_dir)],
    )

    assert result.exit_code == 0
    assert (reports_dir / "errors.csv").exists()
    assert (reports_dir / "skipped.csv").exists()
    assert (reports_dir / "summary.json").exists()


def test_unpivot_cli_html_report_writes_file(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "unpivot_config.yml"
    reports_dir = tmp_path / "custom_reports"

    result = CliRunner().invoke(
        app,
        ["unpivot", str(config_path), "--reports-dir", str(reports_dir), "--html-report"],
    )

    assert result.exit_code == 0
    assert "- html:" in result.output
    assert (reports_dir / "report.html").exists()


def test_unpivot_cli_max_output_rows_skips_output(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "unpivot_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["runtime"]["max_output_rows"] = 2
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["unpivot", str(config_path)])

    assert result.exit_code == 1
    assert "Unpivot failed" in result.output
    assert "Stop:" in result.output
    assert "output row count 3 exceeded runtime.max_output_rows 2" in result.output
    assert not (config_path.parent / "output" / "payments_long.csv").exists()
    summary = json.loads(
        (config_path.parent / "reports" / "summary.json").read_text(encoding="utf-8")
    )
    assert summary["status"] == "failed"
    assert summary["notes"]["output_file_written"] is False


def test_unpivot_cli_if_exists_error_does_not_overwrite(tmp_path: Path) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "unpivot_config.yml"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["output"]["if_exists"] = "error"
    config_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    output_path = config_path.parent / "output" / "payments_long.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("old content\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["unpivot", str(config_path)])

    assert result.exit_code == 1
    assert output_path.read_text(encoding="utf-8") == "old content\n"


def test_unpivot_reports_are_atomic_on_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _copy_tree(FIXTURES, tmp_path / "fixture") / "unpivot_config.yml"
    config = load_unpivot_config(config_path)
    result = run_unpivot_pipeline(config, config_path)
    errors_csv = config_path.parent / "reports" / "errors.csv"
    errors_csv.parent.mkdir(parents=True, exist_ok=True)
    errors_csv.write_text("old errors\n", encoding="utf-8")

    monkeypatch.setattr("datamapx.report.atomic.os.replace", _raise_os_error)

    with pytest.raises(CsvWriteError, match="cannot write report CSV"):
        write_unpivot_reports(result, config, config_path)

    assert errors_csv.read_text(encoding="utf-8") == "old errors\n"
    assert not list(errors_csv.parent.glob(".errors.csv.*.tmp"))


def _copy_tree(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    return destination


def _raise_os_error(*_args, **_kwargs) -> None:
    raise OSError("boom")
