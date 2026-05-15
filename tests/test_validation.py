from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from datamapx.config import DatamapxConfig, load_config
from datamapx.exceptions import ConfigError
from datamapx.runner import run_dry_run

FIXTURES = Path(__file__).parent / "fixtures" / "validation"


def _load_data() -> dict:
    with (FIXTURES / "validation_config.yml").open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def test_input_required_success() -> None:
    config = load_config(FIXTURES / "validation_config.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.input_validation_error_count == 0


def test_input_required_missing_row_becomes_error_row() -> None:
    config = load_config(FIXTURES / "validation_config_input_errors.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.input_validation_error_count == 1
    assert any(
        row.stage == "input_validation" and row.rule == "required"
        for row in result.error_rows
    )
    assert result.output_preview_df["id"].tolist() == ["u001", "u003", "u004"]


def test_output_required_missing_row_becomes_error_row() -> None:
    config = load_config(FIXTURES / "validation_config_output_errors.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.output_validation_error_count >= 1
    assert any(
        row.stage == "output_validation" and row.rule == "required"
        for row in result.error_rows
    )
    assert result.output_preview_df["id"].tolist() == ["u001"]


def test_enum_success() -> None:
    config = load_config(FIXTURES / "validation_config.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.output_validation_error_count == 0


def test_enum_mismatch_becomes_error_row() -> None:
    config = load_config(FIXTURES / "validation_config_output_errors.yml")

    result = run_dry_run(config, FIXTURES)

    assert any(row.rule == "enum" for row in result.error_rows)


def test_enum_allows_missing_when_not_required() -> None:
    config = load_config(FIXTURES / "validation_config.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.output_preview_df["id"].tolist() == ["u001", "u002", "u003", "u004"]
    assert result.output_validation_error_count == 0


def test_min_success() -> None:
    config = load_config(FIXTURES / "validation_config.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.output_validation_error_count == 0


def test_min_violation_becomes_error_row() -> None:
    config = load_config(FIXTURES / "validation_config_output_errors.yml")

    result = run_dry_run(config, FIXTURES)

    assert any(row.rule == "min" for row in result.error_rows)


def test_max_success() -> None:
    config = load_config(FIXTURES / "validation_config.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.output_validation_error_count == 0


def test_max_violation_becomes_error_row() -> None:
    config = load_config(FIXTURES / "validation_config_output_errors.yml")

    result = run_dry_run(config, FIXTURES)

    assert any(row.rule == "max" for row in result.error_rows)


def test_regex_success() -> None:
    config = load_config(FIXTURES / "validation_config.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.output_validation_error_count == 0


def test_regex_mismatch_becomes_error_row() -> None:
    config = load_config(FIXTURES / "validation_config_output_errors.yml")

    result = run_dry_run(config, FIXTURES)

    assert any(row.rule == "regex" for row in result.error_rows)


def test_length_min_success() -> None:
    config = load_config(FIXTURES / "validation_config.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.output_validation_error_count == 0


def test_length_min_violation_becomes_error_row() -> None:
    config = load_config(FIXTURES / "validation_config_output_errors.yml")

    result = run_dry_run(config, FIXTURES)

    assert any(row.field == "short_text" and row.rule == "length" for row in result.error_rows)


def test_length_max_success() -> None:
    config = load_config(FIXTURES / "validation_config.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.output_validation_error_count == 0


def test_length_max_violation_becomes_error_row() -> None:
    config = load_config(FIXTURES / "validation_config_output_errors.yml")

    result = run_dry_run(config, FIXTURES)

    assert any(row.field == "long_text" and row.rule == "length" for row in result.error_rows)


def test_unsupported_rule_fails() -> None:
    with pytest.raises(ConfigError, match="Input should be"):
        load_config(FIXTURES / "validation_config_bad_rule.yml")


def test_enum_values_missing_fails() -> None:
    data = _load_data()
    data["validations"]["output"][1]["values"] = []

    with pytest.raises(ValueError, match="enum validation requires values"):
        DatamapxConfig.model_validate(data)


def test_regex_pattern_missing_fails() -> None:
    data = _load_data()
    data["validations"]["output"][4]["pattern"] = None

    with pytest.raises(ValueError, match="regex validation requires pattern"):
        DatamapxConfig.model_validate(data)


def test_length_min_max_missing_fails() -> None:
    data = _load_data()
    data["validations"]["output"][5].pop("min", None)
    data["validations"]["output"][5].pop("max", None)

    with pytest.raises(ValueError, match="length validation requires min or max"):
        DatamapxConfig.model_validate(data)


def test_filter_and_validation_errors_are_separate() -> None:
    config = load_config(FIXTURES / "validation_config_filter_and_errors.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.skipped_count == 1
    assert result.input_validation_error_count == 1
    assert result.output_validation_error_count == 0
    assert [row.stage for row in result.error_rows] == ["input_validation"]
