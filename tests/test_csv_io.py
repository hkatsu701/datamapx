from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from datamapx.config import load_config
from datamapx.io.csv_reader import profile_input_csv, read_input_csv, read_reference_csv
from datamapx.io.errors import CsvReadError

FIXTURES = Path(__file__).parent / "fixtures" / "csv_io"
DATE_FIXTURES = Path(__file__).parent / "fixtures" / "date_format"
ZENKAKU_FIXTURES = Path(__file__).parent / "fixtures" / "zenkaku"


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


def test_schema_defined_input_uses_pruned_usecols(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config()
    input_config = config.inputs["users"].model_copy(update={"path": "./input_users_alias.csv"})
    calls: list[dict[str, object]] = []
    original_read_csv = pd.read_csv

    def fake_read_csv(*args: object, **kwargs: object):
        calls.append(dict(kwargs))
        return original_read_csv(*args, **kwargs)

    monkeypatch.setattr("datamapx.io.csv_reader.pd.read_csv", fake_read_csv)

    read_input_csv("users", input_config, FIXTURES)

    assert calls[0]["usecols"] == [
        "顧客ID",
        "name",
        "age",
        "amount",
        "active",
        "joined",
        "department_code",
    ]


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


def test_zenkaku_to_hankaku_input_normalization() -> None:
    config = load_config(ZENKAKU_FIXTURES / "zenkaku_config.yml")

    df = read_input_csv("users", config.inputs["users"], ZENKAKU_FIXTURES)

    assert df.loc[0, "code"] == "ABC123"
    assert df.loc[0, "label"] == "山田"
    assert df.loc[0, "amount"] == 12345
    assert df.loc[0, "optional_text"] == "アイウ"
    assert pd.isna(df.loc[1, "optional_text"])


def test_zenkaku_to_hankaku_reference_normalization() -> None:
    config = load_config(ZENKAKU_FIXTURES / "zenkaku_config.yml")

    df = read_reference_csv("departments", config.references["departments"], ZENKAKU_FIXTURES)

    assert df.loc[0, "display_name"] == "営業部"
    assert df.loc[1, "display_name"] == "支援部"


def test_schema_free_reference_reads_all_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config()
    calls: list[dict[str, object]] = []
    original_read_csv = pd.read_csv

    def fake_read_csv(*args: object, **kwargs: object):
        calls.append(dict(kwargs))
        return original_read_csv(*args, **kwargs)

    monkeypatch.setattr("datamapx.io.csv_reader.pd.read_csv", fake_read_csv)

    df = read_reference_csv("departments", config.references["departments"], FIXTURES)

    assert calls[0].get("usecols") is None
    assert "region" in df.columns


def test_profile_input_chunk_size_matches_full_profile() -> None:
    config = load_config(FIXTURES / "csv_io_config.yml")

    full_profile = profile_input_csv("users", config.inputs["users"], FIXTURES)
    chunked_profile = profile_input_csv(
        "users",
        config.inputs["users"],
        FIXTURES,
        chunk_size=2,
    )

    assert chunked_profile.to_dict() == full_profile.to_dict()


def test_profile_input_chunk_size_uses_chunksize(monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_config(FIXTURES / "csv_io_config.yml")
    calls: list[dict[str, object]] = []
    expected_usecols = [
        "user_id",
        "name",
        "age",
        "amount",
        "active",
        "joined",
        "department_code",
    ]

    def fake_read_csv(*_args: object, **kwargs: object) -> object:
        calls.append(dict(kwargs))
        assert kwargs["chunksize"] == 2
        assert kwargs["dtype"] is object
        assert kwargs["usecols"] == expected_usecols
        return iter(
            [
                pd.DataFrame(
                    {
                        "user_id": ["u001", "u002"],
                        "name": ["Alice", "Bob"],
                        "nickname": [pd.NA, pd.NA],
                        "age": ["42", "35"],
                        "amount": ["1234.50", "2000"],
                        "active": ["true", "false"],
                        "joined": ["2024-01-01", "2024-01-02"],
                        "department_code": ["D001", "D002"],
                    }
                )
            ]
        )

    monkeypatch.setattr("datamapx.io.csv_reader.pd.read_csv", fake_read_csv)

    profile = profile_input_csv("users", config.inputs["users"], FIXTURES, chunk_size=2)

    assert calls
    assert profile.profiled_rows == 2
    assert profile.columns[0].sample_values == ["u001", "u002"]


def test_input_row_count_limit_allows_small_files(tmp_path: Path) -> None:
    input_path = tmp_path / "input_users.csv"
    _write_csv(
        input_path,
        [
            ["user_id", "name", "nickname", "age", "amount", "active", "joined", "department_code"],
            ["u001", "Alice", "", "42", "1234.50", "true", "2024-01-01", "D001"],
            ["u002", "Bob", "", "35", "2000", "false", "2024-01-02", "D002"],
        ],
    )
    config = _config()
    input_config = config.inputs["users"].model_copy(update={"path": str(input_path)})

    df = read_input_csv("users", input_config, tmp_path, max_rows=2)

    assert len(df) == 2


def test_input_row_count_limit_rejects_large_files(tmp_path: Path) -> None:
    input_path = tmp_path / "input_users.csv"
    _write_csv(
        input_path,
        [
            ["user_id", "name", "nickname", "age", "amount", "active", "joined", "department_code"],
            ["u001", "Alice", "", "42", "1234.50", "true", "2024-01-01", "D001"],
            ["u002", "Bob", "", "35", "2000", "false", "2024-01-02", "D002"],
            ["u003", "Carol", "", "29", "500", "true", "2024-01-03", "D003"],
        ],
    )
    config = _config()
    input_config = config.inputs["users"].model_copy(update={"path": str(input_path)})

    with pytest.raises(
        CsvReadError,
        match=r"inputs\.users: row count 3 exceeds runtime\.max_input_rows 2",
    ):
        read_input_csv("users", input_config, tmp_path, max_rows=2)


def test_reference_row_count_limit_allows_small_files(tmp_path: Path) -> None:
    reference_path = tmp_path / "ref_departments.csv"
    _write_csv(
        reference_path,
        [
            ["department_code", "department_name"],
            ["D001", "Sales"],
            ["D002", "Support"],
        ],
    )
    config = _config()
    reference_config = config.references["departments"].model_copy(
        update={"path": str(reference_path)}
    )

    df = read_reference_csv("departments", reference_config, tmp_path, max_rows=2)

    assert len(df) == 2


def test_reference_row_count_limit_rejects_large_files(tmp_path: Path) -> None:
    reference_path = tmp_path / "ref_departments.csv"
    _write_csv(
        reference_path,
        [
            ["department_code", "department_name"],
            ["D001", "Sales"],
            ["D002", "Support"],
            ["D003", "QA"],
        ],
    )
    config = _config()
    reference_config = config.references["departments"].model_copy(
        update={"path": str(reference_path)}
    )

    with pytest.raises(
        CsvReadError,
        match=r"references\.departments: row count 3 exceeds runtime\.max_reference_rows 2",
    ):
        read_reference_csv("departments", reference_config, tmp_path, max_rows=2)


@pytest.mark.parametrize(
    ("loader", "config_key", "path_name"),
    [
        (read_input_csv, "inputs", "users"),
        (read_reference_csv, "references", "departments"),
    ],
)
def test_row_count_limit_counts_empty_field_rows_as_data(
    tmp_path: Path,
    loader,
    config_key: str,
    path_name: str,
) -> None:
    csv_path = tmp_path / f"{path_name}.csv"
    csv_path.write_text(
        (
            "user_id,name,nickname,age,amount,active,joined,department_code\n"
            ",,,,,,,\n"
            ",,,,,,,\n"
            "u001,Alice,,42,1234.50,true,2024-01-01,D001\n"
        ),
        encoding="utf-8",
    )
    config = _config()
    config_obj = getattr(config, config_key)[path_name].model_copy(update={"path": str(csv_path)})

    with pytest.raises(
        CsvReadError,
        match=r"row count 3 exceeds runtime\.(max_input_rows|max_reference_rows) 2",
    ):
        loader(path_name, config_obj, tmp_path, max_rows=2)


@pytest.mark.parametrize(
    ("loader", "config_key", "path_name"),
    [
        (read_input_csv, "inputs", "users"),
        (read_reference_csv, "references", "departments"),
    ],
)
def test_header_false_is_reported_before_row_limit(
    tmp_path: Path,
    loader,
    config_key: str,
    path_name: str,
) -> None:
    csv_path = tmp_path / f"{path_name}.csv"
    csv_path.write_text("user_id,name\nu001,Alice\nu002,Bob\n", encoding="utf-8")
    config = _config()
    config_obj = getattr(config, config_key)[path_name].model_copy(
        update={"path": str(csv_path), "header": False}
    )

    with pytest.raises(
        CsvReadError,
        match="header: false is not supported in Phase 1 CSV reader",
    ):
        loader(path_name, config_obj, tmp_path, max_rows=1)


def _write_csv(path: Path, rows: list[list[str]]) -> None:
    content = "\n".join(",".join(row) for row in rows) + "\n"
    path.write_text(content, encoding="utf-8")
