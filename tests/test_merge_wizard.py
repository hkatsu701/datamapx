from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from datamapx.cli import app
from datamapx.merge import load_merge_config

FIXTURES = Path(__file__).parent / "fixtures" / "merge"


def test_merge_wizard_command_generates_valid_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "merge.yml"
    staging_path = tmp_path / "staging.csv"
    responses = iter(
        [
            "wizard_merge",
            str(config_path),
            str(staging_path),
            "2",
            "users",
            str(FIXTURES / "input_users.csv"),
            "id",
            "accounts",
            str(FIXTURES / "input_accounts.csv"),
            "id",
            "users",
            "left",
            "id,primary_name,total_amount,department_name",
            "source",
            "users.id",
            "first",
            "users.name,accounts.account_name",
            "sum",
            "users.amount,accounts.amount",
            "first",
            "accounts.department_name",
        ]
    )

    monkeypatch.setattr(
        "datamapx.merge.wizard.typer.prompt",
        lambda *args, **kwargs: next(responses),
    )
    monkeypatch.setattr("datamapx.merge.wizard.typer.confirm", lambda *args, **kwargs: True)

    result = CliRunner().invoke(app, ["merge-wizard"])

    assert result.exit_code == 0
    assert "Merge config generated" in result.output
    assert "Next steps:" in result.output
    assert config_path.exists()

    config = load_merge_config(config_path)
    assert config.project.name == "wizard_merge"
    assert config.merge.base == "users"
    assert config.merge.join_type == "left"
    assert config.output.columns == [
        "id",
        "primary_name",
        "total_amount",
        "department_name",
    ]
    assert config.merge.columns["id"].source == "users.id"
    assert config.merge.columns["primary_name"].first == [
        "users.name",
        "accounts.account_name",
    ]
    assert config.merge.columns["total_amount"].sum == [
        "users.amount",
        "accounts.amount",
    ]


def test_merge_wizard_command_rejects_overwrite(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "merge.yml"
    config_path.write_text("existing", encoding="utf-8")
    responses = iter(
        [
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
    assert "merge config file already exists" in result.output
