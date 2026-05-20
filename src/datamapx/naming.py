"""Shared helpers for safe field names derived from CSV headers."""

from __future__ import annotations

import re

SAFE_HEADER_RE = re.compile(r"^[A-Za-z0-9 _.-]+$")
DEFAULT_FALLBACK_PREFIX = "field"


def build_safe_field_names(
    headers: list[str],
    *,
    fallback_prefix: str = DEFAULT_FALLBACK_PREFIX,
) -> list[str]:
    """Build unique safe field names for a header list."""

    safe_names: list[str] = []
    used: set[str] = set()
    generated_index = 1
    for header in headers:
        safe_name = safe_field_name_from_header(header)
        if safe_name is None:
            safe_name = f"{fallback_prefix}_{generated_index:03d}"
            generated_index += 1
        safe_name = deduplicate_name(safe_name, used)
        used.add(safe_name)
        safe_names.append(safe_name)
    return safe_names


def safe_field_name_from_header(header: str) -> str | None:
    """Convert a CSV header into a safe field name when possible."""

    candidate = header.strip().lower()
    if not candidate:
        return None
    candidate = re.sub(r"[^0-9a-z]+", "_", candidate)
    candidate = re.sub(r"_+", "_", candidate).strip("_")
    if not candidate:
        return None
    if candidate[0].isdigit():
        candidate = f"field_{candidate}"
    return candidate


def deduplicate_name(name: str, used: set[str]) -> str:
    """Add suffixes until the name is unique."""

    if name not in used:
        return name
    suffix = 2
    while f"{name}_{suffix}" in used:
        suffix += 1
    return f"{name}_{suffix}"

