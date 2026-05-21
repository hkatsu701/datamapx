from __future__ import annotations

from datamapx.config import ErrorHandlingConfig
from datamapx.transform.error_policy import (
    classify_mapping_error,
    evaluate_max_errors,
    evaluate_validation_stop_policy,
    mapping_error_policy,
)
from datamapx.transform.errors import MappingError
from datamapx.validation.errors import ValidationErrorRow


def test_evaluate_validation_stop_policy_returns_stop_for_validation_rows() -> None:
    config = ErrorHandlingConfig(
        error_output="./errors.csv",
        skipped_output="./skipped.csv",
        on_validation_error="stop",
    )

    result = evaluate_validation_stop_policy(
        config,
        [
            ValidationErrorRow(
                row_number=1,
                stage="input_validation",
                field="users.amount",
                rule="required",
                message="required validation failed",
                normalized_row={"amount": ""},
            )
        ],
    )

    assert result is not None
    assert result.reason == "validation_error"


def test_evaluate_max_errors_only_stops_above_threshold() -> None:
    config = ErrorHandlingConfig(
        error_output="./errors.csv",
        skipped_output="./skipped.csv",
        max_errors=1,
    )

    assert evaluate_max_errors(config, 1) is None
    assert evaluate_max_errors(config, 2) is not None


def test_classify_mapping_error_detects_lookup_missing() -> None:
    result = classify_mapping_error(MappingError("department_name: lookup missing: D999"))

    assert result.reason == "lookup_missing"
    assert result.message is not None
    assert "lookup missing" in result.message


def test_mapping_error_policy_matches_configured_mode() -> None:
    config = ErrorHandlingConfig(
        error_output="./errors.csv",
        skipped_output="./skipped.csv",
        on_lookup_missing="stop",
        on_transform_error="output_error",
    )

    assert (
        mapping_error_policy(
            config,
            classify_mapping_error(MappingError("field: lookup missing: x")),
        )
        == "stop"
    )
    assert (
        mapping_error_policy(
            config,
            classify_mapping_error(MappingError("field: expression evaluation failed")),
        )
        == "output_error"
    )
