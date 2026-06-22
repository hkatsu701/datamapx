"""Errors for consolidate pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


class ConsolidateError(Exception):
    """Raised for consolidate pipeline failures."""


@dataclass(frozen=True)
class ConsolidateErrorRow:
    """A row-level consolidate error."""

    input_name: str
    row_number: int
    stage: Literal["input_validation", "consolidate"]
    field: str
    rule: str
    message: str
    row_json: dict[str, Any]


@dataclass(frozen=True)
class ConsolidateSkippedRow:
    """A row skipped during consolidate."""

    row_number: int
    reason: str
    row_json: dict[str, Any]
