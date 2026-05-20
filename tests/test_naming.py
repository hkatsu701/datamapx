from __future__ import annotations

from datamapx.naming import build_safe_field_names, safe_field_name_from_header


def test_safe_field_name_from_header_replaces_punctuation() -> None:
    assert safe_field_name_from_header("update.records.csv") == "update_records_csv"
    assert safe_field_name_from_header(" update records csv ") == "update_records_csv"


def test_build_safe_field_names_uses_field_prefix_for_unsafe_headers() -> None:
    assert build_safe_field_names(["顧客ID", "注文日", "", "2026 Amount"]) == [
        "id",
        "field_001",
        "field_002",
        "field_2026_amount",
    ]
