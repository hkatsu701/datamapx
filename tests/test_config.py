from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from datamapx.config import DatamapxConfig, load_config
from datamapx.exceptions import ConfigError

FIXTURES = Path(__file__).parent / "fixtures"


def _valid_data() -> dict:
    with (FIXTURES / "valid_config.yml").open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def _assert_invalid(data: dict, expected: str) -> None:
    with pytest.raises(ValueError, match=expected):
        DatamapxConfig.model_validate(data)


def test_load_valid_config() -> None:
    config = load_config(FIXTURES / "valid_config.yml")

    assert config.version == 1
    assert config.project.name == "test_migration"
    assert list(config.inputs) == ["users"]
    assert list(config.outputs) == ["users_out"]


def test_version_other_than_1_fails() -> None:
    data = _valid_data()
    data["version"] = 2

    _assert_invalid(data, "Input should be 1")


def test_multiple_inputs_fail() -> None:
    data = _valid_data()
    data["inputs"]["contacts"] = deepcopy(data["inputs"]["users"])

    _assert_invalid(data, "Phase 1 supports exactly one input")


def test_multiple_outputs_fail() -> None:
    data = _valid_data()
    data["outputs"]["other_out"] = deepcopy(data["outputs"]["users_out"])
    data["mappings"]["other_out"] = deepcopy(data["mappings"]["users_out"])

    _assert_invalid(data, "Phase 1 supports exactly one output")


def test_output_columns_and_mappings_must_match() -> None:
    with pytest.raises(ConfigError, match="missing mappings for output columns"):
        load_config(FIXTURES / "invalid_config.yml")


def test_lookup_reference_must_exist() -> None:
    data = _valid_data()
    data["mappings"]["users_out"]["department_name"]["lookup"]["reference"] = "unknown_ref"

    _assert_invalid(data, "unknown reference 'unknown_ref'")


def test_reference_on_duplicate_first_or_last_fails() -> None:
    data = _valid_data()
    data["references"]["departments"]["on_duplicate"] = "first"

    _assert_invalid(data, "Input should be 'error'")


def test_zenkaku_to_hankaku_normalize_fails() -> None:
    data = _valid_data()
    data["inputs"]["users"]["schema"]["user_id"]["normalize"] = ["zenkaku_to_hankaku"]

    _assert_invalid(data, "Input should be 'trim', 'remove_commas' or 'remove_currency_symbol'")


def test_invalid_output_if_exists_fails() -> None:
    data = _valid_data()
    data["outputs"]["users_out"]["if_exists"] = "append"

    _assert_invalid(data, "Input should be 'error' or 'overwrite'")


def test_expression_unknown_input_field_fails() -> None:
    data = _valid_data()
    data["mappings"]["users_out"]["total_amount"] = {
        "expression": "users.unknown_price * users.quantity"
    }

    _assert_invalid(data, "unknown input field 'users.unknown_price'")


def test_when_if_unknown_field_fails() -> None:
    data = _valid_data()
    data["mappings"]["users_out"]["status"]["when"][0]["if"] = (
        "users.unknown_active == true"
    )

    _assert_invalid(data, "unknown input field 'users.unknown_active'")


def test_concat_values_unknown_field_fails() -> None:
    data = _valid_data()
    data["mappings"]["users_out"]["source_system"] = {
        "concat": {"values": ["users.unknown_last_name", " literal"]}
    }

    _assert_invalid(data, "unknown input field 'users.unknown_last_name'")


def test_map_source_unknown_field_fails() -> None:
    data = _valid_data()
    data["mappings"]["users_out"]["status"] = {
        "map": {
            "source": "users.unknown_status",
            "values": {"A": "active"},
            "default": "unknown",
        }
    }

    _assert_invalid(data, "unknown input field 'users.unknown_status'")


def test_lookup_key_unknown_field_fails() -> None:
    data = _valid_data()
    data["mappings"]["users_out"]["department_name"]["lookup"]["key"] = (
        "users.unknown_department_code"
    )

    _assert_invalid(data, "unknown input field 'users.unknown_department_code'")


def test_derived_expression_unknown_field_fails() -> None:
    data = _valid_data()
    data["derived"]["total_amount"]["expression"] = "users.price * users.unknown_quantity"

    _assert_invalid(data, "unknown input field 'users.unknown_quantity'")


def test_input_validation_field_cannot_reference_derived() -> None:
    data = _valid_data()
    data["validations"]["input"][0]["field"] = "derived.total_amount"

    _assert_invalid(data, "input validation field must reference the single input namespace")


def test_output_validation_field_must_exist_in_output_columns() -> None:
    data = _valid_data()
    data["validations"]["output"][0]["field"] = "unknown_column"

    _assert_invalid(
        data, "output validation field is not defined in output columns: unknown_column"
    )


def test_checks_reserved_row_count_names_are_valid() -> None:
    data = _valid_data()
    data["checks"] = [
        {"name": "row_count_check", "rule": "input_rows == output_rows + error_rows + skipped_rows"}
    ]

    config = DatamapxConfig.model_validate(data)

    assert config.checks[0].name == "row_count_check"


def test_checks_unknown_field_reference_fails() -> None:
    data = _valid_data()
    data["checks"] = [{"name": "amount_check", "rule": "users.unknown_amount > 0"}]

    _assert_invalid(data, "unknown input field 'users.unknown_amount'")
