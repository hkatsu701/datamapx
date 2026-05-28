"""Union-specific errors and row records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


class UnionError(Exception):
    """Raised for union pipeline failures."""


@dataclass(frozen=True)
class UnionErrorRow:
    """A row-level union error."""

    input_name: str
    row_number: int
    stage: Literal["input_validation", "union"]
    field: str
    rule: str
    message: str
    row_json: dict[str, Any]


@dataclass(frozen=True)
class UnionSkippedRow:
    """A row skipped during union."""

    row_number: int
    reason: str
    row_json: dict[str, Any]
