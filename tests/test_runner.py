from __future__ import annotations

from pathlib import Path

import pytest

from datamapx.config import ValidationRule, load_config
from datamapx.io.errors import CsvReadError
from datamapx.runner import run_dry_run, run_load_phase, run_pipeline

FIXTURES = Path(__file__).parent / "fixtures" / "runner"
MAPPING_FIXTURES = Path(__file__).parent / "fixtures" / "mapping"


def test_run_load_phase_reads_input_csv() -> None:
    config = load_config(FIXTURES / "runner_config.yml")

    result = run_load_phase(config, FIXTURES)

    assert result.input_name == "users"
    assert result.input_rows == 3
    assert result.input_columns == ["user_id", "name", "status_code", "amount", "department_code"]


def test_run_load_phase_reads_reference_csv() -> None:
    config = load_config(FIXTURES / "runner_config.yml")

    result = run_load_phase(config, FIXTURES)

    assert result.references[0].name == "departments"
    assert result.references[0].rows == 3
    assert result.references[0].key == "department_code"


def test_run_load_phase_limits_input_rows() -> None:
    config = load_config(FIXTURES / "runner_config.yml")

    result = run_load_phase(config, FIXTURES, limit=2)

    assert result.input_rows == 2
    assert result.limit == 2


def test_references_are_not_limited() -> None:
    config = load_config(FIXTURES / "runner_config.yml")

    result = run_load_phase(config, FIXTURES, limit=2)

    assert result.references[0].rows == 3


def test_run_pipeline_limits_input_rows_without_limiting_references() -> None:
    config = load_config(FIXTURES / "runner_config.yml")

    result = run_pipeline(config, FIXTURES, limit=2)

    assert result.load_result.limit == 2
    assert result.output_rows == 2
    assert result.input_rows_before_validation == 2
    assert result.load_result.references[0].rows == 3


def test_reference_duplicate_key_fails() -> None:
    config = load_config(FIXTURES / "runner_config_bad_ref_duplicate.yml")

    with pytest.raises(CsvReadError, match="duplicate key values"):
        run_load_phase(config, FIXTURES)


def test_input_type_conversion_error_fails() -> None:
    config = load_config(FIXTURES / "runner_config_bad_input_type.yml")

    with pytest.raises(CsvReadError, match="decimal conversion failed"):
        run_load_phase(config, FIXTURES)


def test_dry_run_builds_output_preview_dataframe() -> None:
    config = load_config(FIXTURES / "runner_config.yml")

    result = run_dry_run(config, FIXTURES)

    assert result.output_name == "users_out"
    assert result.output_rows == 3
    assert result.output_columns == ["id", "name", "system_code", "status"]
    assert result.output_preview_df["status"].tolist() == ["active", "inactive", "unknown"]


def test_dry_run_builds_multiple_output_previews() -> None:
    run_fixtures = Path(__file__).parent / "fixtures" / "run"
    config = load_config(run_fixtures / "run_config_multi_output.yml")

    result = run_dry_run(config, run_fixtures)

    assert [output.name for output in result.output_results] == ["users_out", "users_out_copy"]
    assert result.output_rows == 3
    assert result.output_results[0].rows == 3
    assert result.output_results[1].rows == 3
    assert result.output_preview_df["status"].tolist() == ["active", "inactive", "pending"]


def test_dry_run_limit_also_limits_output_preview_rows() -> None:
    config = load_config(FIXTURES / "runner_config.yml")

    result = run_dry_run(config, FIXTURES, limit=2)

    assert result.load_result.input_rows == 2
    assert result.output_rows == 2
    assert len(result.output_preview_df) == 2


def test_dry_run_max_output_rows_stops_execution() -> None:
    config = load_config(FIXTURES / "runner_config.yml")
    config = config.model_copy(
        update={"runtime": config.runtime.model_copy(update={"max_output_rows": 2})}
    )

    result = run_dry_run(config, FIXTURES)

    assert result.fatal_error is True
    assert result.stop_reason == "max_output_rows_exceeded"
    assert (
        result.stop_message
        == "outputs.users_out: output row count 3 exceeded runtime.max_output_rows 2"
    )
    assert result.output_rows == 3


def test_dry_run_max_output_rows_checks_each_output() -> None:
    run_fixtures = Path(__file__).parent / "fixtures" / "run"
    config = load_config(run_fixtures / "run_config_multi_output.yml")
    config = config.model_copy(
        update={
            "runtime": config.runtime.model_copy(update={"max_output_rows": 2}),
            "validations": config.validations.model_copy(
                update={
                    "output": [
                        ValidationRule(
                            field="status",
                            output="users_out",
                            rule="enum",
                            values=["active", "inactive"],
                        )
                    ]
                }
            ),
        }
    )

    result = run_dry_run(config, run_fixtures)

    assert result.fatal_error is True
    assert result.stop_reason == "max_output_rows_exceeded"
    assert (
        result.stop_message
        == "outputs.users_out_copy: output row count 3 exceeded runtime.max_output_rows 2"
    )
    assert [output.name for output in result.output_results] == ["users_out", "users_out_copy"]
    assert result.output_results[0].rows == 2
    assert result.output_results[1].rows == 3


def test_dry_run_builds_lookup_output_preview_dataframe() -> None:
    config = load_config(MAPPING_FIXTURES / "mapping_config_lookup.yml")

    result = run_dry_run(config, MAPPING_FIXTURES)

    assert result.output_preview_df["department_name"].tolist() == [
        "Sales",
        "Support",
        "Unknown",
    ]


def test_dry_run_builds_composite_lookup_output_preview_dataframe() -> None:
    config = load_config(MAPPING_FIXTURES / "mapping_config_lookup_composite.yml")

    result = run_dry_run(config, MAPPING_FIXTURES)

    assert result.output_preview_df["department_name"].tolist() == [
        "Japan Sales",
        "US Support",
        "Unknown",
    ]


def test_dry_run_lookup_missing_becomes_row_error() -> None:
    config = load_config(MAPPING_FIXTURES / "mapping_config_lookup_missing_error.yml")

    result = run_dry_run(config, MAPPING_FIXTURES)

    assert result.fatal_error is False
    assert result.output_rows == 2
    assert result.total_error_count == 1
    assert result.error_rows[0].stage == "mapping"
    assert result.error_rows[0].rule == "lookup_missing"


def test_dry_run_lookup_missing_respects_validation_stop_policy() -> None:
    config = load_config(MAPPING_FIXTURES / "mapping_config_lookup_missing_error.yml")
    config = config.model_copy(
        update={
            "error_handling": config.error_handling.model_copy(
                update={"on_validation_error": "stop"}
            )
        }
    )

    result = run_dry_run(config, MAPPING_FIXTURES)

    assert result.fatal_error is False
    assert result.stop_reason is None
    assert result.output_rows == 2
    assert result.output_preview_df["id"].tolist() == ["u001", "u002"]


def test_dry_run_lookup_missing_stop_marks_failure() -> None:
    config = load_config(MAPPING_FIXTURES / "mapping_config_lookup_missing_error.yml")
    config = config.model_copy(
        update={
            "error_handling": config.error_handling.model_copy(
                update={"on_lookup_missing": "stop"}
            )
        }
    )

    result = run_dry_run(config, MAPPING_FIXTURES)

    assert result.fatal_error is True
    assert result.stop_reason == "lookup_missing"
    assert result.output_rows == 2
    assert result.output_preview_df["id"].tolist() == ["u001", "u002"]


def test_dry_run_transform_error_becomes_row_error() -> None:
    config = load_config(MAPPING_FIXTURES / "mapping_config_expression_missing_value.yml")

    result = run_dry_run(config, MAPPING_FIXTURES)

    assert result.fatal_error is False
    assert result.total_error_count == 1
    assert result.error_rows[0].stage == "mapping"
    assert result.error_rows[0].rule == "transform_error"


def test_dry_run_validation_stop_marks_failure() -> None:
    fixtures = Path(__file__).parent / "fixtures" / "validation"
    config = load_config(fixtures / "validation_config_output_errors.yml")
    config = config.model_copy(
        update={
            "error_handling": config.error_handling.model_copy(
                update={"on_validation_error": "stop"}
            )
        }
    )

    result = run_dry_run(config, fixtures)

    assert result.fatal_error is True
    assert result.stop_reason == "validation_error"
    assert result.total_error_count >= 1


def test_dry_run_max_errors_stop_marks_failure() -> None:
    fixtures = Path(__file__).parent / "fixtures" / "validation"
    config = load_config(fixtures / "validation_config_output_errors.yml")
    config = config.model_copy(
        update={"error_handling": config.error_handling.model_copy(update={"max_errors": 0})}
    )

    result = run_dry_run(config, fixtures)

    assert result.fatal_error is True
    assert result.stop_reason == "max_errors_exceeded"
    assert result.max_errors_exceeded is True


def test_dry_run_builds_when_output_preview_dataframe() -> None:
    config = load_config(MAPPING_FIXTURES / "mapping_config_when.yml")

    result = run_dry_run(config, MAPPING_FIXTURES)

    assert result.output_preview_df["active_label"].tolist() == [
        "enabled",
        "disabled",
        "unknown",
    ]


def test_dry_run_builds_expression_output_preview_dataframe() -> None:
    config = load_config(MAPPING_FIXTURES / "mapping_config_expression.yml")

    result = run_dry_run(config, MAPPING_FIXTURES)

    assert result.output_preview_df["multiply"].tolist() == [200.0, 200.0]
    assert result.output_preview_df["rounded"].tolist() == [50, 12]


def test_dry_run_builds_derived_output_preview_dataframe() -> None:
    config = load_config(MAPPING_FIXTURES / "mapping_config_derived.yml")

    result = run_dry_run(config, MAPPING_FIXTURES)

    assert result.output_preview_df["name"].tolist() == ["Yamada Taro", "Sato Hanako"]
    assert result.output_preview_df["amount"].tolist() == [200.0, 50.0]


def test_input_validation_errors_remove_rows_from_mapping() -> None:
    fixtures = Path(__file__).parent / "fixtures" / "validation"
    config = load_config(fixtures / "validation_config_input_errors.yml")

    result = run_dry_run(config, fixtures)

    assert result.input_validation_error_count == 1
    assert result.output_preview_df["id"].tolist() == ["u001", "u003", "u004"]


def test_output_validation_errors_remove_rows_from_preview() -> None:
    fixtures = Path(__file__).parent / "fixtures" / "validation"
    config = load_config(fixtures / "validation_config_output_errors.yml")

    result = run_dry_run(config, fixtures)

    assert result.output_validation_error_count >= 1
    assert result.output_preview_df["id"].tolist() == ["u001"]


def test_filter_skipped_rows_and_validation_error_rows_are_separate() -> None:
    fixtures = Path(__file__).parent / "fixtures" / "validation"
    config = load_config(fixtures / "validation_config_filter_and_errors.yml")

    result = run_dry_run(config, fixtures)

    assert result.skipped_count == 1
    assert result.input_validation_error_count == 1
    assert result.output_validation_error_count == 0
    assert [row.stage for row in result.error_rows] == ["input_validation"]


def test_dry_run_retains_validation_error_rows() -> None:
    fixtures = Path(__file__).parent / "fixtures" / "validation"
    config = load_config(fixtures / "validation_config_output_errors.yml")

    result = run_dry_run(config, fixtures)

    assert result.total_error_count == len(result.error_rows)
    assert result.run_id
    assert result.started_at
    assert result.finished_at
    assert result.skipped_count == 0
