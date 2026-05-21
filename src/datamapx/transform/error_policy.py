"""Row-level and run-level stop policy helpers."""

from __future__ import annotations

from dataclasses import dataclass

from datamapx.config import ErrorHandlingConfig
from datamapx.transform.errors import MappingError
from datamapx.validation.errors import ValidationErrorRow


@dataclass(frozen=True)
class StopInfo:
    """Fatal pipeline stop metadata."""

    reason: str
    message: str | None
    max_errors_exceeded: bool = False


def evaluate_validation_stop_policy(
    error_handling: ErrorHandlingConfig,
    error_rows: list[ValidationErrorRow],
) -> StopInfo | None:
    """Return a stop reason when validation errors must stop execution."""

    if error_rows and error_handling.on_validation_error == "stop":
        return StopInfo(
            reason="validation_error",
            message=f"validation error count: {len(error_rows)}",
        )
    return None


def evaluate_max_errors(
    error_handling: ErrorHandlingConfig,
    total_error_count: int,
) -> StopInfo | None:
    """Return a stop reason when the configured max error threshold is exceeded."""

    if total_error_count > error_handling.max_errors:
        return StopInfo(
            reason="max_errors_exceeded",
            message=(
                f"error count {total_error_count} exceeded max_errors {error_handling.max_errors}"
            ),
            max_errors_exceeded=True,
        )
    return None


def classify_mapping_error(exc: MappingError) -> StopInfo:
    """Classify a mapping exception into lookup or transform failure."""

    message = str(exc)
    if "lookup missing:" in message:
        return StopInfo(reason="lookup_missing", message=message)
    return StopInfo(reason="transform_error", message=message)


def mapping_error_policy(
    error_handling: ErrorHandlingConfig,
    stop_info: StopInfo,
) -> str:
    """Return the configured policy for a classified mapping error."""

    if stop_info.reason == "lookup_missing":
        return error_handling.on_lookup_missing
    return error_handling.on_transform_error
