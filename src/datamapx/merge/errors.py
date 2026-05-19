"""Merge-specific errors and row records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


class MergeError(Exception):
    """Raised for merge pipeline failures."""


@dataclass(frozen=True)
class MergeErrorRow:
    """A row-level merge error."""

    input_name: str
    row_number: int
    stage: Literal["input_validation", "merge"]
    field: str
    rule: str
    message: str
    row_json: dict[str, Any]


@dataclass(frozen=True)
class MergeSkippedRow:
    """A row skipped during merge."""

    row_number: int
    reason: str
    row_json: dict[str, Any]
