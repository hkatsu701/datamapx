from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from datamapx.config import DatamapxConfig, load_config
from datamapx.exceptions import ConfigError
from datamapx.runner import run_dry_run
from datamapx.validation import validate_input_rows, validate_output_rows

FIXTURES = Path(__file__).parent / "fixtures" / "validation"
MIGRATION_FIXTURES = Path(__file__).parent / "fixtures"


def _load_data() -> dict:
    with (FIXTURES / "validation_config.yml").open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def _load_migration_data() -> dict:
    with (MIGRATION_FIXTURES / "valid_config.yml").open("r", encoding="utf-8") as file:
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


def test_referential_integrity_input_validation_ignores_missing_values() -> None:
    data = _load_migration_data()
    data["validations"]["input"] = [
        {
            "field": "users.department_code",
            "rule": "referential_integrity",
            "reference": "departments",
            "reference_key": "department_code",
        }
    ]
    config = DatamapxConfig.model_validate(data)
    input_df = pd.DataFrame(
        {
            "department_code": ["D001", pd.NA, "", "D999"],
        }
    )
    reference_dfs = {
        "departments": pd.DataFrame({"department_code": ["D001", "D002"]}),
    }

    result = validate_input_rows(config, input_df, "users", reference_dfs)

    assert result.error_count == 1
    assert result.error_rows[0].rule == "referential_integrity"
    assert result.dataframe["department_code"].tolist()[0] == "D001"
    assert pd.isna(result.dataframe["department_code"].iloc[1])
    assert result.dataframe["department_code"].iloc[2] == ""


def test_referential_integrity_input_validation_is_order_independent() -> None:
    data = _load_migration_data()
    data["validations"]["input"] = [
        {
            "field": "users.department_code",
            "rule": "referential_integrity",
            "reference": "departments",
            "reference_key": "department_code",
        },
        {
            "field": "users.user_id",
            "rule": "required",
        },
    ]
    config = DatamapxConfig.model_validate(data)
    input_df = pd.DataFrame(
        {
            "department_code": ["D001", "D999"],
            "user_id": ["U001", "U002"],
        }
    )
    reference_dfs = {
        "departments": pd.DataFrame({"department_code": ["D001", "D002"]}),
    }

    result = validate_input_rows(config, input_df, "users", reference_dfs)

    assert result.error_count == 1
    assert result.error_rows[0].rule == "referential_integrity"
    assert result.dataframe["department_code"].tolist() == ["D001"]


def test_referential_integrity_output_validation_ignores_missing_values() -> None:
    data = _load_migration_data()
    data["outputs"]["users_out"]["columns"] = ["department_name"]
    data["mappings"]["users_out"] = {
        "department_name": {"source": "users.department_code"}
    }
    data["validations"]["output"] = [
        {
            "field": "department_name",
            "rule": "referential_integrity",
            "reference": "departments",
            "reference_key": "department_name",
        }
    ]
    config = DatamapxConfig.model_validate(data)
    output_df = pd.DataFrame(
        {
            "department_name": ["Sales", pd.NA, "", "Unknown"],
        }
    )
    row_numbers = pd.Series([1, 2, 3, 4], dtype="object")
    reference_dfs = {
        "departments": pd.DataFrame({"department_name": ["Sales", "Support"]}),
    }

    result = validate_output_rows(config, output_df, row_numbers, "users_out", reference_dfs)

    assert result.error_count == 1
    assert result.error_rows[0].rule == "referential_integrity"
    assert result.dataframe["department_name"].tolist()[0] == "Sales"
    assert pd.isna(result.dataframe["department_name"].iloc[1])
    assert result.dataframe["department_name"].iloc[2] == ""


def test_referential_integrity_output_validation_is_order_independent() -> None:
    data = _load_migration_data()
    data["validations"]["output"] = [
        {
            "field": "department_name",
            "rule": "referential_integrity",
            "reference": "departments",
            "reference_key": "department_name",
        },
        {
            "field": "status",
            "rule": "required",
        },
    ]
    config = DatamapxConfig.model_validate(data)
    output_df = pd.DataFrame(
        {
            "department_name": ["Sales", "Unknown"],
            "status": ["active", "inactive"],
        }
    )
    row_numbers = pd.Series([1, 2], dtype="object")
    reference_dfs = {
        "departments": pd.DataFrame({"department_name": ["Sales", "Support"]}),
    }

    result = validate_output_rows(config, output_df, row_numbers, "users_out", reference_dfs)

    assert result.error_count == 1
    assert result.error_rows[0].rule == "referential_integrity"
    assert result.dataframe["department_name"].tolist() == ["Sales"]


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
