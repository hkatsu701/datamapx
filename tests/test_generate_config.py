from __future__ import annotations

from pathlib import Path

import pytest

from datamapx.config import load_config
from datamapx.config_generator import GeneratedOutputMapping, generate_basic_config
from datamapx.exceptions import ConfigError

FIXTURES = Path(__file__).parent / "fixtures" / "generate_config"


def test_generate_basic_config_from_ascii_headers(tmp_path: Path) -> None:
    config_path = tmp_path / "migration.yml"

    result = generate_basic_config(
        FIXTURES / "input_basic.csv",
        tmp_path / "output" / "users_out.csv",
        config_path,
        input_name="users",
        output_name="users_out",
    )

    content = config_path.read_text(encoding="utf-8")
    assert "source_columns:" in content
    assert "User ID" in content
    assert "outputs:" in content
    assert "columns:" in content
    assert "User ID" in content
    assert result.schema_fields == ["user_id", "name", "amount"]
    assert result.output_columns == ["User ID", "Name", "Amount"]

    config = load_config(config_path)
    assert list(config.inputs) == ["users"]
    assert list(config.outputs) == ["users_out"]
    assert config.inputs["users"].fields_schema["user_id"].source_columns == ["User ID"]
    assert config.outputs["users_out"].columns == ["User ID", "Name", "Amount"]
    assert config.mappings["users_out"]["User ID"].source == "users.user_id"


def test_generate_config_loads_and_validates(tmp_path: Path) -> None:
    config_path = tmp_path / "migration.yml"
    generate_basic_config(
        FIXTURES / "input_basic.csv",
        tmp_path / "output" / "users_out.csv",
        config_path,
    )

    config = load_config(config_path)

    assert config.version == 1
    assert config.error_handling.error_output == "./reports/errors.csv"
    assert config.runtime.summary_output == "./reports/summary.json"


def test_generate_japanese_headers_use_safe_schema_names(tmp_path: Path) -> None:
    config_path = tmp_path / "migration.yml"

    result = generate_basic_config(
        FIXTURES / "input_japanese.csv",
        tmp_path / "output" / "users_out.csv",
        config_path,
        input_name="users",
        output_name="users_out",
    )

    assert result.schema_fields == ["id", "field_001", "field_002", "field_003"]
    assert result.output_columns == ["顧客ID", "姓", "名", "金額"]

    config = load_config(config_path)
    assert list(config.inputs["users"].fields_schema) == [
        "id",
        "field_001",
        "field_002",
        "field_003",
    ]
    assert config.inputs["users"].fields_schema["id"].source_columns == ["顧客ID"]
    assert config.outputs["users_out"].columns == ["顧客ID", "姓", "名", "金額"]


def test_generate_basic_config_accepts_selected_output_mappings(tmp_path: Path) -> None:
    config_path = tmp_path / "migration.yml"

    result = generate_basic_config(
        FIXTURES / "input_basic.csv",
        tmp_path / "output" / "users_out.csv",
        config_path,
        input_name="users",
        output_name="users_out",
        output_mappings=[
            GeneratedOutputMapping(output_column="customer_code", schema_field="user_id"),
            GeneratedOutputMapping(output_column="amount", schema_field="amount"),
        ],
    )

    assert result.output_columns == ["customer_code", "amount"]

    config = load_config(config_path)
    assert config.outputs["users_out"].columns == ["customer_code", "amount"]
    assert config.mappings["users_out"]["customer_code"].source == "users.user_id"
    assert config.mappings["users_out"]["amount"].source == "users.amount"


def test_generate_duplicate_headers_get_suffixes_when_safe_output_columns(tmp_path: Path) -> None:
    config_path = tmp_path / "migration.yml"

    result = generate_basic_config(
        FIXTURES / "input_duplicate_headers.csv",
        tmp_path / "output" / "users_out.csv",
        config_path,
        output_name="users_out",
        preserve_output_columns=False,
    )

    assert result.schema_fields == ["name", "name_2", "amount"]
    assert result.output_columns == ["name", "name_2", "amount"]

    config = load_config(config_path)
    assert list(config.outputs["users_out"].columns) == ["name", "name_2", "amount"]
    assert config.mappings["users_out"]["name_2"].source == "input.name_2"


def test_generate_numeric_and_blank_headers_get_safe_names(tmp_path: Path) -> None:
    config_path = tmp_path / "migration.yml"

    result = generate_basic_config(
        FIXTURES / "input_numeric_and_blank.csv",
        tmp_path / "output" / "users_out.csv",
        config_path,
        preserve_output_columns=False,
    )

    assert result.schema_fields[0] == "field_2026_amount"
    assert result.schema_fields[1] == "field_001"
    assert result.schema_fields[2] == "user_id"


def test_generate_semicolon_delimiter_is_reflected(tmp_path: Path) -> None:
    config_path = tmp_path / "migration.yml"

    result = generate_basic_config(
        FIXTURES / "input_semicolon.csv",
        tmp_path / "output" / "users_out.csv",
        config_path,
        delimiter=";",
    )

    config = load_config(config_path)
    assert result.output_columns == ["User ID", "Name", "Amount"]
    assert config.inputs["input"].delimiter == ";"
    assert config.outputs["output"].delimiter == ";"


def test_generate_overwrite_requires_flag(tmp_path: Path) -> None:
    config_path = tmp_path / "migration.yml"
    config_path.write_text("existing", encoding="utf-8")

    with pytest.raises(ConfigError, match="config file already exists"):
        generate_basic_config(
            FIXTURES / "input_basic.csv",
            tmp_path / "output" / "users_out.csv",
            config_path,
        )


def test_generate_overwrite_replaces_existing_file(tmp_path: Path) -> None:
    config_path = tmp_path / "migration.yml"
    config_path.write_text("existing", encoding="utf-8")

    result = generate_basic_config(
        FIXTURES / "input_basic.csv",
        tmp_path / "output" / "users_out.csv",
        config_path,
        overwrite=True,
    )

    assert result.config_path == config_path
    assert "existing" not in config_path.read_text(encoding="utf-8")
