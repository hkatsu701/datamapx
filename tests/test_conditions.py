from __future__ import annotations

import pandas as pd
import pytest

from datamapx.transform.conditions import evaluate_condition
from datamapx.transform.errors import MappingError


def test_logical_and_or_precedence_works() -> None:
    input_df = pd.DataFrame(
        {
            "active": [True, False, False],
            "amount": [50, 150, 50],
            "status": ["other", "pending", "pending"],
        }
    )

    result = evaluate_condition(
        'users.active or users.status == "pending" and users.amount > 100',
        input_df,
        "users",
    )

    assert result.tolist() == [True, True, False]


def test_boolean_field_shorthand_works() -> None:
    input_df = pd.DataFrame({"active": [True, False, None]})

    result = evaluate_condition("users.active", input_df, "users")

    assert result.tolist() == [True, False, False]


def test_null_comparisons_work() -> None:
    input_df = pd.DataFrame({"deleted_at": [pd.NaT, pd.Timestamp("2024-01-01"), None]})

    is_null = evaluate_condition("users.deleted_at is null", input_df, "users")
    is_not_null = evaluate_condition("users.deleted_at is not null", input_df, "users")

    assert is_null.tolist() == [True, False, True]
    assert is_not_null.tolist() == [False, True, False]


def test_parentheses_are_unsupported() -> None:
    input_df = pd.DataFrame({"active": [True]})

    with pytest.raises(MappingError, match="Unsupported condition expression"):
        evaluate_condition("(users.active)", input_df, "users")
