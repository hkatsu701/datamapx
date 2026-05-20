from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from datamapx.cli import app
from datamapx.merge import load_merge_config
from datamapx.merge.wizard import (
    ChoiceOption,
    ColumnPreview,
    _build_safe_field_names,
    _format_input_preview,
    _format_numbered_options,
    _prioritize_columns,
    _prompt_int,
    _prompt_number_choice,
    _prompt_number_choices,
    _prompt_text,
)

FIXTURES = Path(__file__).parent / "fixtures" / "merge"


def test_merge_wizard_command_generates_valid_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "merge.yml"
    staging_path = tmp_path / "staging.csv"
    responses = iter(
        [
            "2",
            "wizard_merge",
            str(config_path),
            str(staging_path),
            "2",
            "users",
            str(FIXTURES / "input_users.csv"),
            "1",
            "accounts",
            str(FIXTURES / "input_accounts.csv"),
            "1",
            "1",
            "1",
            "1,5",
            "primary_account_name",
            "1",
        ]
    )

    monkeypatch.setattr(
        "datamapx.merge.wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )
    confirm_responses = iter([False, False, True, True, True])
    monkeypatch.setattr(
        "datamapx.merge.wizard.typer.confirm",
        lambda *args, **kwargs: next(confirm_responses),
    )

    result = CliRunner().invoke(app, ["merge-wizard"])

    assert result.exit_code == 0
    assert "1/6. 最初にやりたいことを番号で選択" in result.output
    assert "2/6. Project and paths" in result.output
    assert "6/6. Column rules" in result.output
    assert "CSV:" in result.output
    assert "sample:" in result.output
    assert "出力したい列を番号で選択" in result.output
    assert "出力列名の確認" in result.output
    assert "推奨ルールを適用します。" in result.output
    assert "Review" in result.output
    assert "この設定で行うこと" in result.output
    assert "を基準にして" in result.output
    assert "そのまま使います" in result.output
    assert "merge.yml を作成しました" in result.output
    assert "次にやること:" in result.output
    assert config_path.exists()

    config = load_merge_config(config_path)
    assert config.project.name == "wizard_merge"
    assert config.merge.base == "users"
    assert config.merge.join_type == "left"
    assert config.output.columns == [
        "id",
        "primary_account_name",
    ]
    assert config.merge.columns["id"].source == "users.id"
    assert config.merge.columns["primary_account_name"].first == [
        "accounts.account_name",
    ]


def test_merge_wizard_command_rejects_overwrite(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "merge.yml"
    config_path.write_text("existing", encoding="utf-8")
    responses = iter(
        [
            "1",
            "wizard_merge",
            str(config_path),
            str(tmp_path / "staging.csv"),
        ]
    )

    monkeypatch.setattr(
        "datamapx.merge.wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )
    monkeypatch.setattr("datamapx.merge.wizard.typer.confirm", lambda *args, **kwargs: False)

    result = CliRunner().invoke(app, ["merge-wizard"])

    assert result.exit_code == 1
    assert "merge.yml が既に存在します" in result.output


def test_prompt_number_choice_retries_on_non_numeric_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    responses = iter(["abc", "2"])
    monkeypatch.setattr(
        "datamapx.merge.wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )

    result = _prompt_number_choice(
        "基準にする入力を番号で選択",
        [
            ChoiceOption(label="users", value="users"),
            ChoiceOption(label="accounts", value="accounts"),
        ],
        default_index=1,
    )

    captured = capsys.readouterr().out
    assert result == "accounts"
    assert "数字で入力してください。例: 1 または 1,3" in captured


def test_prompt_number_choices_retries_on_out_of_range_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    responses = iter(["9", "2"])
    monkeypatch.setattr(
        "datamapx.merge.wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )

    result = _prompt_number_choices(
        "出力したい列を番号で選択",
        [
            ChoiceOption(label="id", value="users.id"),
            ChoiceOption(label="name", value="users.name"),
        ],
        default_indices=[1],
    )

    captured = capsys.readouterr().out
    assert result == ["users.name"]
    assert "選べる番号は 1 から 2 です。入力値: 9" in captured


def test_prompt_number_choice_retries_when_multiple_numbers_are_entered(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    responses = iter(["1,2", "2"])
    monkeypatch.setattr(
        "datamapx.merge.wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )

    result = _prompt_number_choice(
        "結合方法を番号で選択",
        [
            ChoiceOption(label="left", value="left"),
            ChoiceOption(label="inner", value="inner"),
        ],
        default_index=1,
    )

    captured = capsys.readouterr().out
    assert result == "inner"
    assert "1つだけ選択してください。例: 1" in captured


def test_prompt_int_reports_japanese_retry_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    responses = iter(["abc", "3"])
    monkeypatch.setattr(
        "datamapx.merge.wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )

    result = _prompt_int("入力CSVファイルはいくつありますか？", 2)

    captured = capsys.readouterr().out
    assert result == 3
    assert "整数で入力してください。例: 2" in captured


def test_prompt_text_reports_japanese_retry_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    responses = iter(["", "wizard_merge"])
    monkeypatch.setattr(
        "datamapx.merge.wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )

    result = _prompt_text("プロジェクト名", "generated_merge")

    captured = capsys.readouterr().out
    assert result == "wizard_merge"
    assert "空では登録できません。値を入力してください" in captured


def test_build_safe_field_names_replaces_dots_with_underscores() -> None:
    assert _build_safe_field_names(["update.records.csv", "update records.csv"]) == [
        "update_records_csv",
        "update_records_csv_2",
    ]


def test_format_input_preview_uses_prioritized_order() -> None:
    ordered = _prioritize_columns(
        [
            ColumnPreview(header="amount", safe_field="amount", samples=["100"]),
            ColumnPreview(header="id", safe_field="id", samples=["A001"]),
            ColumnPreview(header="name", safe_field="name", samples=["Alice"]),
        ],
    )
    preview = _format_input_preview("sample", ordered)

    assert ordered[0].safe_field == "id"
    assert ordered[1].safe_field == "name"
    assert ordered[2].safe_field == "amount"
    assert preview.index("  1. id") < preview.index("  2. name")
    assert preview.index("  2. name") < preview.index("  3. amount")


def test_format_numbered_options_wraps_long_labels() -> None:
    lines = _format_numbered_options(
        [
            ChoiceOption(
                label="this is a very long option label that should wrap across multiple lines",
                value="value",
            )
        ]
    )

    assert len(lines) >= 2
    assert lines[0].startswith("  1. ")
    assert lines[1].startswith(" " * 4)
