"""Errors for unpivot pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


class UnpivotError(Exception):
    """Raised for unpivot pipeline failures."""


@dataclass(frozen=True)
class UnpivotErrorRow:
    """A row-level unpivot error."""

    input_name: str
    row_number: int
    stage: Literal["input_validation", "unpivot"]
    field: str
    rule: str
    message: str
    row_json: dict[str, Any]


@dataclass(frozen=True)
class UnpivotSkippedRow:
    """A row skipped during unpivot."""

    row_number: int
    reason: str
    row_json: dict[str, Any]
