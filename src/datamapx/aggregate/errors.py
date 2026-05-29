"""Errors for aggregate pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


class AggregateError(Exception):
    """Raised for aggregate pipeline failures."""


@dataclass(frozen=True)
class AggregateErrorRow:
    """A row-level aggregate error."""

    input_name: str
    row_number: int
    stage: Literal["input_validation", "aggregate"]
    field: str
    rule: str
    message: str
    row_json: dict[str, Any]


@dataclass(frozen=True)
class AggregateSkippedRow:
    """A row skipped during aggregate."""

    row_number: int
    reason: str
    row_json: dict[str, Any]
