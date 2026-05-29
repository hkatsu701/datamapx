from __future__ import annotations

from pathlib import Path

import pytest

from datamapx.config import FilterRule, load_config
from datamapx.exceptions import ConfigError
from datamapx.runner import run_dry_run, run_load_phase
from datamapx.transform.errors import MappingError
from datamapx.transform.filters import EXCLUDE_DEFAULT_REASON, apply_filters
from datamapx.transform.mapper import compute_derived_fields

FIXTURES = Path(__file__).parent / "fixtures" / "filters"


def test_exclude_matching_rows_are_removed() -> None:
    config = load_config(FIXTURES / "filters_config_exclude.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.output_preview_df["id"].tolist() == ["u001", "u003"]
    assert result.input_rows_before_filter == 4
    assert result.input_rows_after_filter == 2
    assert result.skipped_count == 2


def test_exclude_reason_is_retained() -> None:
    config = load_config(FIXTURES / "filters_config_exclude.yml")

    result = run_dry_run(config, FIXTURES)

    assert [row.reason for row in result.skipped_rows] == [
        "zero amount is excluded",
        "zero amount is excluded",
    ]


def test_exclude_default_reason_is_used_when_reason_is_missing() -> None:
    config = load_config(FIXTURES / "filters_config_exclude_default_reason.yml")

    result = run_dry_run(config, FIXTURES)

    assert [row.reason for row in result.skipped_rows] == [
        EXCLUDE_DEFAULT_REASON,
        EXCLUDE_DEFAULT_REASON,
    ]


def test_include_keeps_only_matching_rows() -> None:
    config = load_config(FIXTURES / "filters_config_include.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.output_preview_df["id"].tolist() == ["u001", "u003", "u004"]


def test_include_unmatched_rows_are_skipped() -> None:
    config = load_config(FIXTURES / "filters_config_include.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.skipped_count == 1
    assert result.skipped_rows[0].row_number == 2
    assert result.skipped_rows[0].reason == "No include condition matched"


def test_include_then_exclude_order_is_applied() -> None:
    config = load_config(FIXTURES / "filters_config_include_exclude.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.output_preview_df["id"].tolist() == ["u001", "u003"]
    assert [(row.row_number, row.reason) for row in result.skipped_rows] == [
        (2, "No include condition matched"),
        (4, "zero amount is excluded"),
    ]


def test_include_parenthesized_logical_conditions_work() -> None:
    config = load_config(FIXTURES / "filters_config_include.yml")
    config.filters.include = [
        {
            "if": '(users.active == true or users.status == "pending") and users.amount > 0',
            "reason": "active or pending with amount",
        }
    ]

    result = run_dry_run(config, FIXTURES)

    assert result.output_preview_df["id"].tolist() == ["u001", "u003"]
    assert [row.reason for row in result.skipped_rows] == [
        "No include condition matched",
        "No include condition matched",
    ]


def test_filter_condition_can_reference_derived() -> None:
    config = load_config(FIXTURES / "filters_config_derived.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.output_preview_df["id"].tolist() == ["u001", "u003"]
    assert result.output_preview_df["total_amount"].tolist() == [100.0, 25.0]
    assert [row.reason for row in result.skipped_rows] == [
        "zero total amount",
        "zero total amount",
    ]


def test_filter_logical_conditions_with_derived_work() -> None:
    config = load_config(FIXTURES / "filters_config_derived.yml")
    config.filters.exclude = [
        {
            "if": (
                '(derived.total_amount > 80 and users.active == true) '
                'or users.status == "pending"'
            ),
            "reason": "high and active",
        }
    ]

    result = run_dry_run(config, FIXTURES)

    assert result.output_preview_df["id"].tolist() == ["u002", "u004"]
    assert [row.reason for row in result.skipped_rows] == ["high and active", "high and active"]


def test_filtered_output_dataframe_row_count_is_correct() -> None:
    config = load_config(FIXTURES / "filters_config_exclude.yml")

    result = run_dry_run(config, FIXTURES)

    assert len(result.output_preview_df) == 2
    assert result.output_rows == 2


def test_skipped_rows_keep_original_row_number() -> None:
    config = load_config(FIXTURES / "filters_config_exclude.yml")

    result = run_dry_run(config, FIXTURES)

    assert [row.row_number for row in result.skipped_rows] == [2, 4]


def test_filter_unknown_field_fails() -> None:
    with pytest.raises(ConfigError, match="unknown input field"):
        load_config(FIXTURES / "filters_config_bad_field.yml")


def test_filter_bad_namespace_fails() -> None:
    with pytest.raises(ConfigError, match="unknown field namespace"):
        load_config(FIXTURES / "filters_config_bad_namespace.yml")


def test_filters_include_not_list_fails() -> None:
    with pytest.raises(ConfigError):
        load_config(FIXTURES / "filters_config_include_not_list.yml")


def test_filter_item_missing_if_fails() -> None:
    with pytest.raises(ConfigError):
        load_config(FIXTURES / "filters_config_missing_if.yml")


def test_apply_filters_defensively_rejects_non_list_include() -> None:
    config = load_config(FIXTURES / "filters_config_exclude.yml")
    load_result = run_load_phase(config, FIXTURES)
    derived_values = compute_derived_fields(config, load_result.input_df, load_result.reference_dfs)
    config.filters.include = {"if": "users.active == true"}  # type: ignore[assignment]

    with pytest.raises(MappingError, match="filters.include must be a list"):
        apply_filters(config, load_result.input_df, "users", derived_values)


def test_apply_filters_defensively_rejects_missing_if() -> None:
    config = load_config(FIXTURES / "filters_config_exclude.yml")
    load_result = run_load_phase(config, FIXTURES)
    derived_values = compute_derived_fields(config, load_result.input_df, load_result.reference_dfs)
    config.filters.exclude = [FilterRule.model_construct(reason="missing")]

    with pytest.raises(MappingError, match="filter item is missing if"):
        apply_filters(config, load_result.input_df, "users", derived_values)
