from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from datamapx.cli import app
from datamapx.config import load_config

FIXTURES = Path(__file__).parent / "fixtures" / "generate_config"


def _schema_answers(
    type_index: int = 1,
    required_index: int = 1,
    normalize: str = "1",
) -> list[str]:
    return [str(type_index), str(required_index), normalize]


def _schema_answers_for_columns(
    column_specs: list[tuple[int, int, str]],
) -> list[str]:
    answers: list[str] = []
    for type_index, required_index, normalize in column_specs:
        answers.extend(_schema_answers(type_index, required_index, normalize))
    return answers


def test_migration_wizard_command_generates_valid_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "migration.yml"
    responses = iter(
        [
            'migration_wizard_sample',
            str(FIXTURES / "input_japanese.csv"),
            str(tmp_path / "output" / "users_out.csv"),
            str(config_path),
            'users',
            'users_out',
            '2',
            '顧客ID',
            'total_amount',
            '1',
            '1',
            '1',
            '1',
            '4',
            '1',
        ]
    )
    monkeypatch.setattr(
        "datamapx.migration_wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )

    result = CliRunner().invoke(app, ["migration-wizard"])

    assert result.exit_code == 0
    assert "migration.yml を作成しました" in result.output
    assert "出力列数: 2" in result.output
    assert "設定モード: 基本設定のみ" in result.output
    assert config_path.exists()

    config = load_config(config_path)
    assert config.project.name == "migration_wizard_sample"
    assert list(config.inputs) == ["users"]
    assert list(config.outputs) == ["users_out"]
    assert list(config.inputs["users"].fields_schema) == [
        "id",
        "field_001",
        "field_002",
        "field_003",
    ]
    assert config.outputs["users_out"].columns == ["顧客ID", "total_amount"]
    assert config.mappings["users_out"]["顧客ID"].source == "users.id"
    assert config.mappings["users_out"]["total_amount"].source == "users.field_003"


def test_migration_wizard_keeps_selection_in_display_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "migration.yml"
    responses = iter(
        [
            'migration_wizard_sample',
            str(FIXTURES / "input_japanese.csv"),
            str(tmp_path / "output" / "users_out.csv"),
            str(config_path),
            'users',
            'users_out',
            '2',
            '顧客ID',
            '金額',
            '1',
            '1',
            '1',
            '1',
            '4',
            '1',
        ]
    )
    monkeypatch.setattr(
        "datamapx.migration_wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )

    result = CliRunner().invoke(app, ["migration-wizard"])

    assert result.exit_code == 0
    config = load_config(config_path)
    assert config.outputs["users_out"].columns == ["顧客ID", "金額"]
    assert config.mappings["users_out"]["顧客ID"].source == "users.id"
    assert config.mappings["users_out"]["金額"].source == "users.field_003"


def test_migration_wizard_advanced_mode_can_write_lookup_and_derived(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "migration.yml"
    reference_path = tmp_path / "departments.csv"
    reference_path.write_text("dept_code,dept_name\nA,Sales\n", encoding="utf-8")
    responses = iter(
        [
            'migration_wizard_sample',
            str(FIXTURES / "input_basic.csv"),
            str(tmp_path / "output" / "users_out.csv"),
            str(config_path),
            'users',
            'users_out',
            '1',
            'User ID',
            '2',
            '1',
            str(reference_path),
            'departments',
            '1',
            *_schema_answers_for_columns([(1, 1, '1'), (1, 1, '1')]),
            '1',
            'name_copy',
            '1',
            '1',
            '0',
            '0',
            '0',
            '0',
            '0',
            *_schema_answers_for_columns([(1, 1, '1'), (1, 1, '1'), (1, 1, '1')]),
            '1',
            '1',
            '1',
            '1',
            '1',
            '1000',
            './reports/errors.csv',
            './reports/skipped.csv',
            '1',
            'auto',
            './logs',
            '2',
            './reports/summary.json',
            '6',
            '1',
            '1',
            '2',
            '1',
            '1',
        ]
    )
    monkeypatch.setattr(
        "datamapx.migration_wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )

    result = CliRunner().invoke(app, ["migration-wizard"])

    assert result.exit_code == 0
    assert "設定モード: 詳細設定あり" in result.output
    config = load_config(config_path)
    assert list(config.references) == ["departments"]
    assert list(config.derived) == ["name_copy"]
    assert config.derived["name_copy"].source == "users.user_id"
    assert config.mappings["users_out"]["User ID"].lookup.reference == "departments"


def test_build_mapping_rule_when_is_not_double_nested(monkeypatch) -> None:
    from datamapx.migration_wizard import _build_mapping_rule_from_type

    monkeypatch.setattr(
        "datamapx.migration_wizard._prompt_when_rules",
        lambda **kwargs: {
            "when": [{"if": "users.status == \"A\"", "then": "Active"}],
            "default": "Inactive",
        },
    )

    rule = _build_mapping_rule_from_type(
        rule_type="when",
        context="mappings.output.status",
        input_name="users",
        input_columns=[],
        reference_specs=[],
        derived_names=[],
        default_source=None,
    )

    assert rule["when"] == [{"if": 'users.status == "A"', "then": "Active"}]
    assert rule["default"] == "Inactive"


def test_prompt_literal_list_writes_plain_string_items(monkeypatch) -> None:
    from datamapx.migration_wizard import _prompt_literal_list

    int_responses = iter([2])
    choice_responses = iter(["string", "string"])
    text_responses = iter(["現金", "クレジットカード"])

    monkeypatch.setattr(
        "datamapx.migration_wizard._prompt_int",
        lambda *args, **kwargs: next(int_responses),
    )
    monkeypatch.setattr(
        "datamapx.migration_wizard._prompt_number_choice",
        lambda *args, **kwargs: next(choice_responses),
    )
    monkeypatch.setattr(
        "datamapx.migration_wizard._prompt_text",
        lambda *args, **kwargs: next(text_responses),
    )

    result = _prompt_literal_list("when 条件")

    assert result == '["現金", "クレジットカード"]'


def test_migration_wizard_advanced_mode_can_write_reference_schema_overrides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "migration.yml"
    reference_path = tmp_path / "departments.csv"
    reference_path.write_text("dept_code,dept_name\nA,Sales\n", encoding="utf-8")
    responses = iter(
        [
            'migration_wizard_sample',
            str(FIXTURES / "input_basic.csv"),
            str(tmp_path / "output" / "users_out.csv"),
            str(config_path),
            'users',
            'users_out',
            '1',
            'User ID',
            '2',
            '1',
            str(reference_path),
            'departments',
            '1',
            *_schema_answers_for_columns([(1, 2, '1'), (1, 2, '1')]),
            '0',
            '0',
            '0',
            '0',
            '0',
            '0',
            *_schema_answers_for_columns([(1, 1, '1'), (1, 1, '1'), (1, 1, '1')]),
            '1',
            '1',
            '1',
            '1',
            '1',
            '1000',
            './reports/errors.csv',
            './reports/skipped.csv',
            '1',
            'auto',
            './logs',
            '2',
            './reports/summary.json',
            '1',
            '1',
            '1',
        ]
    )
    monkeypatch.setattr(
        "datamapx.migration_wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )

    result = CliRunner().invoke(app, ["migration-wizard"])

    assert result.exit_code == 0
    assert "reference 列設定数: 2" in result.output
    config = load_config(config_path)
    reference = config.references["departments"]
    assert set(reference.fields_schema) == {"dept_code", "dept_name"}
    assert reference.fields_schema["dept_code"].source_columns == ["dept_code"]
    assert reference.fields_schema["dept_name"].required is True


def test_migration_wizard_advanced_mode_can_write_validations_filters_and_checks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "migration.yml"
    responses = iter(
        [
            'migration_wizard_sample',
            str(FIXTURES / "input_basic.csv"),
            str(tmp_path / "output" / "users_out.csv"),
            str(config_path),
            'users',
            'users_out',
            '1',
            'User ID',
            '2',
            '0',
            '0',
            '1',
            '1',
            '1',
            '1',
            '1',
            '2',
            '2',
            'alpha',
            'beta',
            '1',
            '1',
            '3',
            '3',
            '4',
            '0',
            'keep positive rows',
            '1',
            '1',
            '3',
            '6',
            '4',
            '0',
            'drop zero rows',
            '1',
            'row_count_check',
            '2',
            'input_rows == output_rows + error_rows + skipped_rows',
            *_schema_answers_for_columns([(1, 1, '1'), (1, 1, '1'), (1, 1, '1')]),
            '1',
            '1',
            '1',
            '1',
            '1',
            '1000',
            './reports/errors.csv',
            './reports/skipped.csv',
            '1',
            'auto',
            './logs',
            '2',
            './reports/summary.json',
            '1',
            '1',
            '1',
        ]
    )
    monkeypatch.setattr(
        "datamapx.migration_wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )

    result = CliRunner().invoke(app, ["migration-wizard"])

    assert result.exit_code == 0
    assert "設定モード: 詳細設定あり" in result.output
    assert "validation 数: 2" in result.output
    assert "filter 数: 2" in result.output
    assert "check 数: 1" in result.output
    config = load_config(config_path)
    assert config.validations.input[0].field == "users.user_id"
    assert config.validations.input[0].rule == "required"
    assert config.validations.output[0].field == "User ID"
    assert config.validations.output[0].rule == "enum"
    assert config.validations.output[0].values == ["alpha", "beta"]
    assert len(config.filters.include) == 1
    assert config.filters.include[0].if_ == "users.amount > 0"
    assert config.filters.include[0].reason == "keep positive rows"
    assert len(config.filters.exclude) == 1
    assert config.filters.exclude[0].if_ == "users.amount <= 0"
    assert config.filters.exclude[0].reason == "drop zero rows"
    assert config.checks[0].name == "row_count_check"
    assert config.checks[0].rule == "input_rows == output_rows + error_rows + skipped_rows"


def test_migration_wizard_advanced_mode_can_write_output_error_handling_runtime_settings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "migration.yml"
    responses = iter(
        [
            'migration_wizard_sample',
            str(FIXTURES / "input_basic.csv"),
            str(tmp_path / "output" / "users_out.csv"),
            str(config_path),
            'users',
            'users_out',
            '1',
            'User ID',
            '2',
            '0',
            '0',
            '0',
            '0',
            '0',
            '0',
            '0',
            *_schema_answers_for_columns([(1, 1, '1'), (1, 1, '1'), (1, 1, '1')]),
            '2',
            '2',
            '2',
            '1',
            '2',
            '42',
            './reports/custom_errors.csv',
            './reports/custom_skipped.csv',
            '2',
            'job-001',
            './custom/logs',
            '1',
            './reports/custom_summary.json',
            '1',
            '1',
            '1',
        ]
    )
    monkeypatch.setattr(
        "datamapx.migration_wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )

    result = CliRunner().invoke(app, ["migration-wizard"])

    assert result.exit_code == 0
    assert "設定モード: 詳細設定あり" in result.output
    assert "output.if_exists: overwrite" in result.output
    assert "output.newline: \\r\\n" in result.output
    assert "error_handling.max_errors: 42" in result.output
    assert "runtime.log_level: DEBUG" in result.output
    config = load_config(config_path)
    assert config.outputs["users_out"].if_exists == "overwrite"
    assert config.outputs["users_out"].newline == "\r\n"
    assert config.error_handling.on_validation_error == "stop"
    assert config.error_handling.on_lookup_missing == "output_error"
    assert config.error_handling.on_transform_error == "stop"
    assert config.error_handling.max_errors == 42
    assert config.error_handling.error_output == "./reports/custom_errors.csv"
    assert config.error_handling.skipped_output == "./reports/custom_skipped.csv"
    assert config.error_handling.include_original_row is False
    assert config.runtime.run_id == "job-001"
    assert config.runtime.log_dir == "./custom/logs"
    assert config.runtime.log_level == "DEBUG"
    assert config.runtime.summary_output == "./reports/custom_summary.json"


def test_migration_wizard_advanced_mode_can_write_input_schema_overrides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "migration.yml"
    responses = iter(
        [
            'migration_wizard_sample',
            str(FIXTURES / "input_basic.csv"),
            str(tmp_path / "output" / "users_out.csv"),
            str(config_path),
            'users',
            'users_out',
            '1',
            'User ID',
            '2',
            '0',
            '0',
            '0',
            '0',
            '0',
            '0',
            '0',
            *_schema_answers_for_columns([(1, 1, '1'), (1, 1, '1'), (3, 2, '1,2,3')]),
            '1',
            '1',
            '1',
            '1',
            '1',
            '1000',
            './reports/errors.csv',
            './reports/skipped.csv',
            '1',
            'auto',
            './logs',
            '2',
            './reports/summary.json',
            '1',
            '1',
            '1',
        ]
    )
    monkeypatch.setattr(
        "datamapx.migration_wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )

    result = CliRunner().invoke(app, ["migration-wizard"])

    assert result.exit_code == 0
    assert "input 列設定数: 3" in result.output
    config = load_config(config_path)
    amount_schema = config.inputs["users"].fields_schema["amount"]
    assert amount_schema.type == "decimal"
    assert amount_schema.required is True
    assert amount_schema.normalize == [
        "trim",
        "remove_commas",
        "remove_currency_symbol",
    ]


def test_migration_wizard_can_build_filter_and_check_rules(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "migration.yml"
    responses = iter(
        [
            'migration_wizard_sample',
            str(FIXTURES / "input_basic.csv"),
            str(tmp_path / "output" / "users_out.csv"),
            str(config_path),
            'users',
            'users_out',
            '1',
            'User ID',
            '2',
            '0',
            '0',
            '0',
            '0',
            '1',
            '1',
            '3',
            '3',
            '4',
            '0',
            'keep positive rows',
            '1',
            '1',
            '3',
            '6',
            '4',
            '0',
            'drop zero rows',
            '1',
            'row_count_check',
            '2',
            'input_rows == output_rows + error_rows + skipped_rows',
            *_schema_answers_for_columns([(1, 1, '1'), (1, 1, '1'), (1, 1, '1')]),
            '1',
            '1',
            '1',
            '1',
            '1',
            '1000',
            './reports/errors.csv',
            './reports/skipped.csv',
            '1',
            'auto',
            './logs',
            '2',
            './reports/summary.json',
            '1',
            '1',
            '1',
        ]
    )
    monkeypatch.setattr(
        "datamapx.migration_wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )

    result = CliRunner().invoke(app, ["migration-wizard"])

    assert result.exit_code == 0
    config = load_config(config_path)
    assert len(config.filters.include) == 1
    assert config.filters.include[0].if_ == "users.amount > 0"
    assert config.filters.include[0].reason == "keep positive rows"
    assert len(config.filters.exclude) == 1
    assert config.filters.exclude[0].if_ == "users.amount <= 0"
    assert config.filters.exclude[0].reason == "drop zero rows"
    assert len(config.checks) == 1
    assert config.checks[0].name == "row_count_check"
    assert config.checks[0].rule == "input_rows == output_rows + error_rows + skipped_rows"


def test_migration_wizard_can_suggest_expression_from_natural_language(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "migration.yml"
    responses = iter(
        [
            'migration_wizard_sample',
            str(FIXTURES / "input_basic.csv"),
            str(tmp_path / "output" / "users_out.csv"),
            str(config_path),
            'users',
            'users_out',
            '1',
            'Amount',
            '2',
            '0',
            '0',
            '0',
            '0',
            '0',
            '0',
            '0',
            *_schema_answers_for_columns([(1, 1, '1'), (1, 1, '1'), (1, 1, '1')]),
            '1',
            '1',
            '1',
            '1',
            '1',
            '1000',
            './reports/errors.csv',
            './reports/skipped.csv',
            '1',
            'auto',
            './logs',
            '2',
            './reports/summary.json',
            '7',
            'Amount を 2倍したい',
            '1',
            '1',
        ]
    )
    monkeypatch.setattr(
        "datamapx.migration_wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )

    result = CliRunner().invoke(app, ["migration-wizard"])

    assert result.exit_code == 0
    config = load_config(config_path)
    assert config.mappings["users_out"]["Amount"].expression == "(users.amount * 2)"
