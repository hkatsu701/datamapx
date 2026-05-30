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


def _when_field_ref_data() -> dict:
    with (
        FIXTURES / "mapping" / "mapping_config_when_field_refs.yml"
    ).open("r", encoding="utf-8") as file:
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


def test_generate_id_mapping_loads() -> None:
    config = load_config(FIXTURES / "mapping" / "mapping_config_generate_id.yml")

    rule = config.mappings["users_out"]["id"].generate_id

    assert rule is not None
    assert rule.fields == ["users.user_id", "users.department_code"]
    assert rule.prefix == "UID-"
    assert rule.separator == "::"
    assert rule.length == 20


def test_generate_id_derived_loads() -> None:
    config = load_config(FIXTURES / "mapping" / "mapping_config_generate_id_derived.yml")

    rule = config.derived["stable_id"].generate_id

    assert rule is not None
    assert rule.fields == ["users.user_id", "users.department_code"]
    assert rule.prefix == "DID-"
    assert rule.separator == "-"
    assert rule.length == 24


def test_version_other_than_1_fails() -> None:
    data = _valid_data()
    data["version"] = 2

    _assert_invalid(data, "Input should be 1")


def test_multiple_inputs_fail() -> None:
    data = _valid_data()
    data["inputs"]["contacts"] = deepcopy(data["inputs"]["users"])

    _assert_invalid(data, "Phase 1 supports exactly one input")


def test_multiple_outputs_pass() -> None:
    config = load_config(FIXTURES / "run" / "run_config_multi_output.yml")

    assert list(config.outputs) == ["users_out", "users_out_copy"]


def test_output_validation_requires_output_when_multiple_outputs_exist() -> None:
    data = _valid_data()
    data["outputs"]["other_out"] = deepcopy(data["outputs"]["users_out"])
    data["mappings"]["other_out"] = deepcopy(data["mappings"]["users_out"])
    data["validations"]["output"] = [
        {"field": "id", "rule": "required"},
    ]

    _assert_invalid(
        data,
        "output validation requires output when multiple outputs are configured",
    )


def test_output_validation_unknown_output_fails() -> None:
    data = _valid_data()
    data["validations"]["output"][0]["output"] = "unknown_out"

    _assert_invalid(data, "unknown output 'unknown_out'")


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


def test_runtime_row_limits_load() -> None:
    data = _valid_data()
    data["runtime"] = {
        "run_id": "auto",
        "log_dir": "./logs",
        "log_level": "INFO",
        "max_input_rows": 100,
        "max_reference_rows": 200,
        "max_output_rows": 300,
    }

    config = DatamapxConfig.model_validate(data)

    assert config.runtime.max_input_rows == 100
    assert config.runtime.max_reference_rows == 200
    assert config.runtime.max_output_rows == 300


@pytest.mark.parametrize("field", ["max_input_rows", "max_reference_rows", "max_output_rows"])
def test_runtime_row_limits_must_be_positive(field: str) -> None:
    data = _valid_data()
    data["runtime"] = {
        "run_id": "auto",
        "log_dir": "./logs",
        "log_level": "INFO",
        field: 0,
    }

    _assert_invalid(data, "must be a positive integer")


def test_generate_id_fields_must_not_be_empty() -> None:
    data = _valid_data()
    data["mappings"]["users_out"]["id"] = {
        "generate_id": {
            "fields": [],
        }
    }

    _assert_invalid(data, "generate_id requires at least one field")


@pytest.mark.parametrize("length", [7, 65])
def test_generate_id_length_must_be_within_range(length: int) -> None:
    data = _valid_data()
    data["mappings"]["users_out"]["id"] = {
        "generate_id": {
            "fields": ["users.user_id"],
            "length": length,
        }
    }

    _assert_invalid(data, "length must be between 8 and 64")


def test_generate_id_unknown_field_reference_fails() -> None:
    data = _valid_data()
    data["mappings"]["users_out"]["id"] = {
        "generate_id": {
            "fields": ["users.unknown_code"],
        }
    }

    _assert_invalid(data, "unknown input field 'users.unknown_code'")


def test_zenkaku_to_hankaku_normalize_loads() -> None:
    config = load_config(FIXTURES / "zenkaku" / "zenkaku_config.yml")

    assert config.inputs["users"].fields_schema["code"].normalize == ["zenkaku_to_hankaku"]
    assert config.inputs["users"].fields_schema["label"].normalize == [
        "zenkaku_to_hankaku",
        "trim",
    ]


def test_invalid_output_if_exists_fails() -> None:
    data = _valid_data()
    data["outputs"]["users_out"]["if_exists"] = "append"

    _assert_invalid(data, "Input should be 'error' or 'overwrite'")


def test_date_format_requires_date_type() -> None:
    data = _valid_data()
    data["inputs"]["users"]["schema"]["user_id"]["date_format"] = "%Y%m%d"

    _assert_invalid(data, "date_format is only supported when type is date")


def test_date_format_loads_for_date_type() -> None:
    config = load_config(FIXTURES / "date_format" / "date_format_config.yml")

    assert config.inputs["users"].fields_schema["date_compact"].date_format == "%Y%m%d"
    assert config.references["events"].fields_schema["effective_on"].date_format == "%Y%m%d"


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


def test_when_logical_condition_unknown_input_field_fails() -> None:
    data = _valid_data()
    data["mappings"]["users_out"]["status"]["when"][0]["if"] = (
        'users.active or users.unknown_active == true'
    )

    _assert_invalid(data, "unknown input field 'users.unknown_active'")


def test_when_parenthesized_logical_condition_unknown_input_field_fails() -> None:
    data = _valid_data()
    data["mappings"]["users_out"]["status"]["when"][0]["if"] = (
        '(users.active or users.unknown_active == true) and users.amount > 100'
    )

    _assert_invalid(data, "unknown input field 'users.unknown_active'")


def test_when_logical_condition_unknown_derived_field_fails() -> None:
    data = _valid_data()
    data["mappings"]["users_out"]["status"]["when"][0]["if"] = (
        "users.active and derived.unknown_total > 0"
    )

    _assert_invalid(data, "unknown derived field 'derived.unknown_total'")


def test_when_then_unknown_input_field_fails() -> None:
    data = _when_field_ref_data()
    data["mappings"]["users_out"]["then_from_input"]["when"][0]["then"] = (
        "users.unknown_status"
    )

    _assert_invalid(data, "unknown input field 'users.unknown_status'")


def test_when_default_unknown_derived_field_fails() -> None:
    data = _when_field_ref_data()
    data["mappings"]["users_out"]["default_from_derived"]["default"] = (
        "derived.unknown_state"
    )

    _assert_invalid(data, "unknown derived field 'derived.unknown_state'")


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
        data,
        "output validation field is not defined in output columns of users_out: unknown_column",
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

    _assert_invalid(data, "field references are not supported in checks")


def test_checks_unknown_summary_variable_fails() -> None:
    data = _valid_data()
    data["checks"] = [{"name": "amount_check", "rule": "total_rows > 0"}]

    _assert_invalid(data, "unknown check variable 'total_rows'")
