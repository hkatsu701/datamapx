"""Errors for match pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


class MatchError(Exception):
    """Raised for match pipeline failures."""


@dataclass(frozen=True)
class MatchErrorRow:
    """A row-level match error."""

    input_name: str
    row_number: int
    stage: Literal["input_validation", "match"]
    field: str
    rule: str
    message: str
    row_json: dict[str, Any]


@dataclass(frozen=True)
class MatchSkippedRow:
    """A row skipped during match."""

    row_number: int
    reason: str
    row_json: dict[str, Any]
