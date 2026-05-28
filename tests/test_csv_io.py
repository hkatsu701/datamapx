from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from datamapx.config import load_config
from datamapx.io.csv_reader import read_input_csv, read_reference_csv
from datamapx.io.errors import CsvReadError

FIXTURES = Path(__file__).parent / "fixtures" / "csv_io"
DATE_FIXTURES = Path(__file__).parent / "fixtures" / "date_format"


def _config():
    return load_config(FIXTURES / "csv_io_config.yml")


def test_input_csv_is_converted_to_schema_field_names() -> None:
    config = _config()
    df = read_input_csv("users", config.inputs["users"], FIXTURES)

    assert list(df.columns) == [
        "__row_number",
        "user_id",
        "name",
        "nickname",
        "age",
        "amount",
        "active",
        "joined",
        "department_code",
    ]


def test_source_columns_alias_is_converted_to_schema_field_name() -> None:
    config = _config()
    input_config = config.inputs["users"].model_copy(update={"path": "./input_users_alias.csv"})

    df = read_input_csv("users", input_config, FIXTURES)

    assert df.loc[0, "user_id"] == "A001"


def test_missing_required_column_fails() -> None:
    config = _config()
    input_config = config.inputs["users"].model_copy(
        update={"path": "./input_missing_required.csv"}
    )

    with pytest.raises(CsvReadError, match="required column not found"):
        read_input_csv("users", input_config, FIXTURES)


def test_missing_optional_column_is_created_as_na() -> None:
    config = _config()
    df = read_input_csv("users", config.inputs["users"], FIXTURES)

    assert "nickname" in df.columns
    assert df["nickname"].isna().all()


def test_trim_is_applied() -> None:
    config = _config()
    df = read_input_csv("users", config.inputs["users"], FIXTURES)

    assert df.loc[0, "user_id"] == "u001"


def test_remove_commas_is_applied() -> None:
    config = _config()
    df = read_input_csv("users", config.inputs["users"], FIXTURES)

    assert df.loc[1, "amount"] == 2000


def test_remove_currency_symbol_is_applied() -> None:
    config = _config()
    df = read_input_csv("users", config.inputs["users"], FIXTURES)

    assert df.loc[0, "amount"] == 1234.50


def test_integer_conversion() -> None:
    config = _config()
    df = read_input_csv("users", config.inputs["users"], FIXTURES)

    assert str(df["age"].dtype) == "Int64"
    assert df.loc[0, "age"] == 42


def test_decimal_conversion() -> None:
    config = _config()
    df = read_input_csv("users", config.inputs["users"], FIXTURES)

    assert pd.api.types.is_numeric_dtype(df["amount"])
    assert df.loc[0, "amount"] == 1234.50


def test_boolean_conversion() -> None:
    config = _config()
    df = read_input_csv("users", config.inputs["users"], FIXTURES)

    assert bool(df.loc[0, "active"]) is True
    assert bool(df.loc[1, "active"]) is False


def test_bad_boolean_fails() -> None:
    config = _config()
    input_config = config.inputs["users"].model_copy(update={"path": "./input_bad_boolean.csv"})

    with pytest.raises(CsvReadError, match="boolean conversion failed"):
        read_input_csv("users", input_config, FIXTURES)


def test_date_conversion() -> None:
    config = _config()
    df = read_input_csv("users", config.inputs["users"], FIXTURES)

    assert pd.api.types.is_datetime64_any_dtype(df["joined"])


def test_bad_date_fails() -> None:
    config = _config()
    input_config = config.inputs["users"].model_copy(update={"path": "./input_bad_date.csv"})

    with pytest.raises(CsvReadError, match="date conversion failed"):
        read_input_csv("users", input_config, FIXTURES)


def test_reference_duplicate_key_fails() -> None:
    config = _config()
    reference_config = config.references["departments"].model_copy(
        update={"path": "./ref_departments_duplicate.csv"}
    )

    with pytest.raises(CsvReadError, match="duplicate key values"):
        read_reference_csv("departments", reference_config, FIXTURES)


def test_reference_composite_duplicate_key_fails() -> None:
    config = _config()
    reference_config = config.references["departments"].model_copy(
        update={
            "path": "./ref_departments_composite_duplicate.csv",
            "key": ["department_code", "region"],
        }
    )

    with pytest.raises(CsvReadError, match="duplicate key values"):
        read_reference_csv("departments", reference_config, FIXTURES)


def test_date_format_input_conversion() -> None:
    config = load_config(DATE_FIXTURES / "date_format_config.yml")

    df = read_input_csv("users", config.inputs["users"], DATE_FIXTURES)

    assert pd.api.types.is_datetime64_any_dtype(df["date_compact"])
    assert pd.api.types.is_datetime64_any_dtype(df["date_dash"])
    assert pd.api.types.is_datetime64_any_dtype(df["date_slash"])
    assert pd.isna(df.loc[0, "date_blank"])
    assert pd.isna(df.loc[1, "date_blank"])


def test_date_format_input_mismatch_fails() -> None:
    config = load_config(DATE_FIXTURES / "date_format_config.yml")
    input_config = config.inputs["users"].model_copy(update={"path": "./input_dates_bad.csv"})

    with pytest.raises(CsvReadError, match="date conversion failed"):
        read_input_csv("users", input_config, DATE_FIXTURES)


def test_date_format_reference_conversion() -> None:
    config = load_config(DATE_FIXTURES / "date_format_config.yml")

    df = read_reference_csv(
        "events",
        config.references["events"],
        DATE_FIXTURES,
    )

    assert pd.api.types.is_datetime64_any_dtype(df["effective_on"])
