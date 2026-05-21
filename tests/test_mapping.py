from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from datamapx.config import MappingRule, load_config
from datamapx.io.csv_reader import read_input_csv, read_reference_csv
from datamapx.io.csv_writer import write_output_csv
from datamapx.io.errors import CsvWriteError
from datamapx.transform.errors import MappingError
from datamapx.transform.mapper import (
    apply_mapping_rule,
    build_output_dataframe,
    compute_derived_fields,
)

FIXTURES = Path(__file__).parent / "fixtures" / "mapping"


def _output_df(config_name: str = "mapping_config.yml") -> pd.DataFrame:
    config = load_config(FIXTURES / config_name)
    input_name, input_config = next(iter(config.inputs.items()))
    input_df = read_input_csv(input_name, input_config, FIXTURES)
    reference_dfs = {
        reference_name: read_reference_csv(reference_name, reference_config, FIXTURES)
        for reference_name, reference_config in config.references.items()
    }
    return build_output_dataframe(config, input_df, reference_dfs)


def test_source_mapping_creates_output_column() -> None:
    output_df = _output_df()

    assert output_df["id"].tolist() == ["u001", "u002", "u003"]


def test_value_mapping_creates_fixed_column() -> None:
    output_df = _output_df()

    assert output_df["source_system"].tolist() == ["CRM", "CRM", "CRM"]


def test_concat_mapping_joins_strings() -> None:
    output_df = _output_df()

    assert output_df["full_name"].tolist() == ["Yamada Taro", "Sato Hanako", "Suzuki Ichiro"]


def test_concat_mapping_treats_missing_as_empty_string() -> None:
    output_df = _output_df()

    assert output_df["optional_label"].tolist() == ["name:", "name:Hana", "name:"]


def test_map_mapping_converts_values() -> None:
    output_df = _output_df()

    assert output_df["status"].tolist()[:2] == ["active", "inactive"]


def test_map_mapping_applies_default() -> None:
    output_df = _output_df()

    assert output_df["status"].tolist()[2] == "unknown"


def test_map_mapping_without_default_fails_for_unmatched_values() -> None:
    config = load_config(FIXTURES / "mapping_config_map_missing_default.yml")
    input_name, input_config = next(iter(config.inputs.items()))
    input_df = read_input_csv(input_name, input_config, FIXTURES)

    with pytest.raises(MappingError, match="unmapped values without default"):
        build_output_dataframe(config, input_df)


def test_output_columns_order_is_preserved() -> None:
    output_df = _output_df()

    assert list(output_df.columns) == [
        "id",
        "source_system",
        "full_name",
        "optional_label",
        "status",
    ]


def test_when_mapping_true_condition_applies_then() -> None:
    output_df = _output_df("mapping_config_when.yml")

    assert output_df.loc[0, "active_label"] == "enabled"


def test_when_mapping_false_condition_applies_then() -> None:
    output_df = _output_df("mapping_config_when.yml")

    assert output_df.loc[1, "active_label"] == "disabled"


def test_when_mapping_default_applies_when_no_condition_matches() -> None:
    output_df = _output_df("mapping_config_when.yml")

    assert output_df["default_label"].tolist() == ["fallback", "fallback", "fallback"]


def test_when_mapping_field_references_in_then_and_default_work() -> None:
    output_df = _output_df("mapping_config_when_field_refs.yml")

    assert output_df["then_from_input"].tolist() == ["active", "fallback", "fallback"]
    assert output_df["then_from_derived"].tolist() == ["enabled", "fallback", "fallback"]
    assert output_df["default_from_input"].tolist() == ["u001", "u002", "u003"]
    assert output_df["default_from_derived"].tolist() == ["enabled", "disabled", "unknown"]
    assert output_df["derived_chain"].tolist() == ["enabled", "disabled", "unknown"]


def test_when_mapping_without_default_fails_when_no_condition_matches() -> None:
    with pytest.raises(MappingError, match="no when condition matched and default is missing"):
        _output_df("mapping_config_when_no_default.yml")


def test_when_mapping_not_equal_condition_works() -> None:
    output_df = _output_df("mapping_config_when.yml")

    assert output_df["not_active_label"].tolist() == ["true_value", "not_true", "true_value"]


def test_when_mapping_greater_than_condition_works() -> None:
    output_df = _output_df("mapping_config_when.yml")

    assert output_df["gt_label"].tolist() == ["gt", "other", "other"]


def test_when_mapping_greater_than_or_equal_condition_works() -> None:
    output_df = _output_df("mapping_config_when.yml")

    assert output_df["gte_label"].tolist() == ["gte", "gte", "other"]


def test_when_mapping_less_than_condition_works() -> None:
    output_df = _output_df("mapping_config_when.yml")

    assert output_df["lt_label"].tolist() == ["other", "other", "lt"]


def test_when_mapping_less_than_or_equal_condition_works() -> None:
    output_df = _output_df("mapping_config_when.yml")

    assert output_df["lte_label"].tolist() == ["other", "lte", "lte"]


def test_when_mapping_in_condition_works() -> None:
    output_df = _output_df("mapping_config_when.yml")

    assert output_df["in_label"].tolist() == ["included", "included", "excluded"]


def test_when_mapping_not_in_condition_works() -> None:
    output_df = _output_df("mapping_config_when.yml")

    assert output_df["not_in_label"].tolist() == ["allowed", "allowed", "blocked"]


def test_when_mapping_null_comparison_works() -> None:
    output_df = _output_df("mapping_config_when.yml")

    assert output_df["null_label"].tolist() == ["is_null", "not_null", "is_null"]


def test_when_mapping_unknown_field_fails() -> None:
    input_df = pd.DataFrame({"active": [True]})
    rule = MappingRule.model_construct(
        when=[{"if": "users.unknown == true", "then": "hit"}],
        default="fallback",
        _fields_set={"when", "default"},
    )

    with pytest.raises(MappingError, match="field is not defined"):
        apply_mapping_rule(rule, input_df, "users", "label", {}, {})


def test_when_mapping_bad_namespace_fails() -> None:
    input_df = pd.DataFrame({"active": [True]})
    rule = MappingRule.model_construct(
        when=[{"if": "customers.active == true", "then": "hit"}],
        default="fallback",
        _fields_set={"when", "default"},
    )

    with pytest.raises(MappingError, match="unknown input namespace"):
        apply_mapping_rule(rule, input_df, "users", "label", {}, {})


def test_when_mapping_unsupported_condition_fails() -> None:
    with pytest.raises(MappingError, match="Unsupported condition expression"):
        _output_df("mapping_config_when_invalid_condition.yml")


def test_when_mapping_non_list_fails() -> None:
    input_df = pd.DataFrame({"active": [True]})
    rule = MappingRule.model_construct(
        when={"if": "users.active == true", "then": "hit"},
        _fields_set={"when"},
    )

    with pytest.raises(MappingError, match="when must be a list"):
        apply_mapping_rule(rule, input_df, "users", "label", {}, {})


def test_when_mapping_missing_if_fails() -> None:
    input_df = pd.DataFrame({"active": [True]})
    rule = MappingRule.model_construct(
        when=[{"then": "hit"}],
        default="fallback",
        _fields_set={"when", "default"},
    )

    with pytest.raises(MappingError, match=r"when\[0\] is missing if"):
        apply_mapping_rule(rule, input_df, "users", "label", {}, {})


def test_when_mapping_missing_then_fails() -> None:
    input_df = pd.DataFrame({"active": [True]})
    rule = MappingRule.model_construct(
        when=[{"if": "users.active == true"}],
        default="fallback",
        _fields_set={"when", "default"},
    )

    with pytest.raises(MappingError, match=r"when\[0\] is missing then"):
        apply_mapping_rule(rule, input_df, "users", "label", {}, {})


def test_expression_mapping_multiplication_works() -> None:
    output_df = _output_df("mapping_config_expression.yml")

    assert output_df["multiply"].tolist() == [200.0, 200.0]


def test_expression_mapping_addition_works() -> None:
    output_df = _output_df("mapping_config_expression.yml")

    assert output_df["add"].tolist() == [110.0, 55.0]


def test_expression_mapping_subtraction_works() -> None:
    output_df = _output_df("mapping_config_expression.yml")

    assert output_df["subtract"].tolist() == [95.0, 40.0]


def test_expression_mapping_division_works() -> None:
    output_df = _output_df("mapping_config_expression.yml")

    assert output_df["divide"].tolist() == [50.0, 12.5]


def test_expression_mapping_floor_division_works() -> None:
    output_df = _output_df("mapping_config_expression.yml")

    assert output_df["floor_divide"].tolist() == [50.0, 12.0]


def test_expression_mapping_modulo_works() -> None:
    output_df = _output_df("mapping_config_expression.yml")

    assert output_df["modulo"].tolist() == [0.0, 2.0]


def test_expression_mapping_power_works() -> None:
    output_df = _output_df("mapping_config_expression.yml")

    assert output_df["power"].tolist() == [10000.0, 2500.0]


def test_expression_mapping_parentheses_work() -> None:
    output_df = _output_df("mapping_config_expression.yml")

    assert output_df["parenthesized"].tolist() == [220.0, 220.0]


def test_expression_mapping_round_function_works() -> None:
    output_df = _output_df("mapping_config_expression.yml")

    assert output_df["rounded"].tolist() == [50, 12]


def test_expression_mapping_abs_function_works() -> None:
    output_df = _output_df("mapping_config_expression.yml")

    assert output_df["absolute"].tolist() == [20.0, 15.0]


def test_expression_mapping_min_function_works() -> None:
    output_df = _output_df("mapping_config_expression.yml")

    assert output_df["minimum"].tolist() == [3.0, 2.0]


def test_expression_mapping_max_function_works() -> None:
    output_df = _output_df("mapping_config_expression.yml")

    assert output_df["maximum"].tolist() == [7.0, 8.0]


def test_expression_mapping_unknown_field_fails() -> None:
    input_df = pd.DataFrame({"price": [100]})
    rule = MappingRule.model_construct(
        expression="users.unknown * 2",
        _fields_set={"expression"},
    )

    with pytest.raises(MappingError, match="field is not defined"):
        apply_mapping_rule(rule, input_df, "users", "result", {}, {})


def test_expression_mapping_bad_namespace_fails() -> None:
    input_df = pd.DataFrame({"price": [100]})
    rule = MappingRule.model_construct(
        expression="customers.price * 2",
        _fields_set={"expression"},
    )

    with pytest.raises(MappingError, match="unknown input namespace"):
        apply_mapping_rule(rule, input_df, "users", "result", {}, {})


def test_expression_mapping_derived_reference_fails() -> None:
    input_df = pd.DataFrame({"price": [100]})
    rule = MappingRule.model_construct(
        expression="derived.total_amount * 2",
        _fields_set={"expression"},
    )

    with pytest.raises(MappingError, match="derived field is not defined"):
        apply_mapping_rule(rule, input_df, "users", "result", {}, {})


def test_expression_mapping_missing_value_fails() -> None:
    with pytest.raises(MappingError, match="expression field has missing value"):
        _output_df("mapping_config_expression_missing_value.yml")


def test_expression_mapping_disallowed_function_fails() -> None:
    with pytest.raises(MappingError, match="function is not allowed"):
        _output_df("mapping_config_expression_bad_function.yml")


def test_expression_mapping_invalid_syntax_fails() -> None:
    with pytest.raises(MappingError, match="invalid syntax"):
        _output_df("mapping_config_expression_invalid_syntax.yml")


def test_expression_mapping_non_string_fails() -> None:
    input_df = pd.DataFrame({"price": [100]})
    rule = MappingRule.model_construct(
        expression=100,
        _fields_set={"expression"},
    )

    with pytest.raises(MappingError, match="expression must be a string"):
        apply_mapping_rule(rule, input_df, "users", "result", {}, {})


def test_derived_concat_can_be_referenced_by_output_source() -> None:
    output_df = _output_df("mapping_config_derived.yml")

    assert output_df["name"].tolist() == ["Yamada Taro", "Sato Hanako"]


def test_derived_expression_can_be_referenced_by_output_source() -> None:
    output_df = _output_df("mapping_config_derived.yml")

    assert output_df["amount"].tolist() == [200.0, 50.0]


def test_output_concat_can_reference_derived() -> None:
    output_df = _output_df("mapping_config_derived.yml")

    assert output_df["label"].tolist() == ["Yamada Taro / D001", "Sato Hanako / D002"]


def test_output_expression_can_reference_derived() -> None:
    output_df = _output_df("mapping_config_derived.yml")

    assert output_df["amount_with_tax"].tolist() == [220.00000000000003, 55.00000000000001]


def test_derived_can_reference_another_derived() -> None:
    config = load_config(FIXTURES / "mapping_config_derived.yml")
    input_name, input_config = next(iter(config.inputs.items()))
    input_df = read_input_csv(input_name, input_config, FIXTURES)
    reference_dfs = {
        reference_name: read_reference_csv(reference_name, reference_config, FIXTURES)
        for reference_name, reference_config in config.references.items()
    }

    derived_values = compute_derived_fields(config, input_df, reference_dfs)

    assert derived_values["amount_with_tax"].tolist() == [220.00000000000003, 55.00000000000001]


def test_derived_dependency_order_is_resolved() -> None:
    output_df = _output_df("mapping_config_derived.yml")

    assert output_df["amount_with_tax"].tolist() == [220.00000000000003, 55.00000000000001]


def test_derived_cycle_fails() -> None:
    config = load_config(FIXTURES / "mapping_config_derived_cycle.yml")
    input_name, input_config = next(iter(config.inputs.items()))
    input_df = read_input_csv(input_name, input_config, FIXTURES)

    with pytest.raises(MappingError, match="derived field cycle detected"):
        build_output_dataframe(config, input_df)


def test_derived_unknown_field_reference_fails() -> None:
    input_df = pd.DataFrame({"user_id": ["u001"]})
    rule = MappingRule.model_construct(
        source="derived.unknown_field",
        _fields_set={"source"},
    )

    with pytest.raises(MappingError, match="source field is not defined"):
        apply_mapping_rule(rule, input_df, "users", "id", {}, {}, {})


def test_derived_source_rule_works() -> None:
    output_df = _output_df("mapping_config_derived.yml")

    assert output_df["id"].tolist() == ["u001", "u002"]


def test_derived_value_rule_works() -> None:
    output_df = _output_df("mapping_config_derived.yml")

    assert output_df["source_system"].tolist() == ["CRM", "CRM"]


def test_derived_concat_rule_works() -> None:
    output_df = _output_df("mapping_config_derived.yml")

    assert output_df["name"].tolist() == ["Yamada Taro", "Sato Hanako"]


def test_derived_map_rule_works() -> None:
    output_df = _output_df("mapping_config_derived.yml")

    assert output_df["status"].tolist() == ["active", "inactive"]


def test_derived_lookup_rule_works() -> None:
    output_df = _output_df("mapping_config_derived.yml")

    assert output_df["department_name"].tolist() == ["Sales", "Support"]


def test_derived_when_rule_works() -> None:
    output_df = _output_df("mapping_config_derived.yml")

    assert output_df["active_label"].tolist() == ["enabled", "disabled"]


def test_derived_expression_rule_works() -> None:
    output_df = _output_df("mapping_config_derived.yml")

    assert output_df["amount"].tolist() == [200.0, 50.0]


def test_when_condition_can_reference_derived() -> None:
    output_df = _output_df("mapping_config_derived.yml")

    assert output_df["amount_status"].tolist() == ["large", "normal"]


def test_when_condition_unknown_derived_reference_fails() -> None:
    input_df = pd.DataFrame({"price": [100]})
    rule = MappingRule.model_construct(
        when=[{"if": "derived.unknown_field >= 100", "then": "large"}],
        default="normal",
        _fields_set={"when", "default"},
    )

    with pytest.raises(MappingError, match="field is not defined"):
        apply_mapping_rule(rule, input_df, "users", "status", {}, {}, {})


def test_lookup_mapping_gets_value_by_single_key() -> None:
    output_df = _output_df("mapping_config_lookup.yml")

    assert output_df["department_name"].tolist() == ["Sales", "Support", "Unknown"]


def test_lookup_mapping_gets_value_by_composite_key() -> None:
    output_df = _output_df("mapping_config_lookup_composite.yml")

    assert output_df["department_name"].tolist() == ["Japan Sales", "US Support", "Unknown"]


def test_lookup_missing_error_fails() -> None:
    with pytest.raises(MappingError, match="lookup missing: reference=departments key=D999"):
        _output_df("mapping_config_lookup_missing_error.yml")


def test_lookup_missing_default_uses_default() -> None:
    output_df = _output_df("mapping_config_lookup_missing_default.yml")

    assert output_df["department_name"].tolist() == ["Sales", "Support", "Missing"]


def test_lookup_missing_empty_uses_empty_string() -> None:
    output_df = _output_df("mapping_config_lookup_missing_empty.yml")

    assert output_df["department_name"].tolist() == ["Sales", "Support", ""]


def test_lookup_missing_null_uses_na() -> None:
    output_df = _output_df("mapping_config_lookup_missing_null.yml")

    assert pd.isna(output_df.loc[2, "department_name"])


def test_lookup_default_without_default_value_fails() -> None:
    with pytest.raises(MappingError, match="requires default value"):
        _output_df("mapping_config_lookup_default_missing_default.yml")


def test_lookup_value_column_missing_fails() -> None:
    with pytest.raises(MappingError, match="lookup value column is not defined"):
        _output_df("mapping_config_lookup_bad_value.yml")


def test_lookup_key_input_field_missing_fails() -> None:
    config = load_config(FIXTURES / "mapping_config_lookup_bad_key.yml")
    input_name, input_config = next(iter(config.inputs.items()))
    input_df = read_input_csv(input_name, input_config, FIXTURES).drop(
        columns=["missing_department_code"]
    )
    reference_dfs = {
        reference_name: read_reference_csv(reference_name, reference_config, FIXTURES)
        for reference_name, reference_config in config.references.items()
    }

    with pytest.raises(MappingError, match="lookup key field is not defined"):
        build_output_dataframe(config, input_df, reference_dfs)


def test_lookup_reference_missing_fails() -> None:
    config = load_config(FIXTURES / "mapping_config_lookup_bad_reference_runtime.yml")
    input_name, input_config = next(iter(config.inputs.items()))
    input_df = read_input_csv(input_name, input_config, FIXTURES)

    with pytest.raises(MappingError, match="lookup reference is not loaded"):
        build_output_dataframe(config, input_df, reference_dfs={})


def test_lookup_string_key_against_composite_reference_key_fails() -> None:
    with pytest.raises(MappingError, match="lookup.key is string but reference.key is composite"):
        _output_df("mapping_config_lookup_string_to_composite.yml")


def test_lookup_composite_key_against_string_reference_key_fails() -> None:
    with pytest.raises(MappingError, match="lookup.key is composite but reference.key is string"):
        _output_df("mapping_config_lookup_composite_to_string.yml")


def test_lookup_composite_key_length_mismatch_fails() -> None:
    with pytest.raises(MappingError, match="lookup.key count does not match"):
        _output_df("mapping_config_lookup_composite_length_mismatch.yml")


def test_unknown_source_field_fails() -> None:
    config = load_config(FIXTURES / "mapping_config_unknown_source.yml")
    input_name, input_config = next(iter(config.inputs.items()))
    input_df = read_input_csv(input_name, input_config, FIXTURES)
    input_df = input_df.drop(columns=["unknown_source"])

    with pytest.raises(MappingError, match="source field is not defined"):
        build_output_dataframe(config, input_df)


def test_output_csv_writer_writes_file(tmp_path: Path) -> None:
    config = load_config(FIXTURES / "mapping_config.yml")
    output_name, output_config = next(iter(config.outputs.items()))
    output_df = _output_df()

    written_path = write_output_csv(output_df, output_config, tmp_path)

    assert output_name == "users_out"
    assert written_path.exists()
    assert written_path.read_text(encoding="utf-8-sig").startswith("id,source_system")


def test_output_csv_writer_if_exists_error(tmp_path: Path) -> None:
    config = load_config(FIXTURES / "mapping_config.yml")
    _, output_config = next(iter(config.outputs.items()))
    output_path = tmp_path / output_config.path
    output_path.parent.mkdir(parents=True)
    output_path.write_text("existing", encoding="utf-8")

    with pytest.raises(CsvWriteError, match="already exists"):
        write_output_csv(
            _output_df(),
            output_config.model_copy(update={"if_exists": "error"}),
            tmp_path,
        )
