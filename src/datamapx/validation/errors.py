"""Validation error structures for row-level validation failures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


class ValidationError(Exception):
    """Raised when validation rules cannot be evaluated safely."""


@dataclass(frozen=True)
class ValidationErrorRow:
    """A single row-level validation failure."""

    row_number: Any
    stage: Literal["input_validation", "output_validation", "mapping"]
    field: str
    rule: str
    message: str
    output_name: str | None = None
    normalized_row: dict[str, Any] | None = None
    output_row: dict[str, Any] | None = None
