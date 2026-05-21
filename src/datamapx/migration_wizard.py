"""Interactive migration config generator."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from textwrap import fill
from typing import Any

import typer
import yaml

from datamapx.config import DatamapxConfig
from datamapx.config_generator import (
    GeneratedConfigResult,
    GeneratedOutputMapping,
    generate_basic_config,
)
from datamapx.exceptions import ConfigError
from datamapx.naming import build_safe_field_names, deduplicate_name

MAX_PROMPT_ATTEMPTS = 3
CSV_SAMPLE_LIMIT = 3


class MigrationWizardRestart(Exception):
    """Signal that the wizard should restart from output selection."""


@dataclass(frozen=True)
class ChoiceOption:
    """A numbered option shown to the user."""

    label: str
    value: Any


@dataclass(frozen=True)
class ColumnPreview:
    """Preview information for a CSV column."""

    index: int
    header: str
    safe_field: str
    samples: list[str]

    @property
    def sample_text(self) -> str:
        if not self.samples:
            return "(なし)"
        return " / ".join(self.samples)


@dataclass(frozen=True)
class ReferenceSpec:
    """Reference CSV metadata gathered by the wizard."""

    name: str
    path: Path
    columns: list[ColumnPreview]
    key: list[str]
    schema_overrides: list[SchemaOverrideSpec]


@dataclass(frozen=True)
class DerivedSpec:
    """Derived field definition gathered by the wizard."""

    name: str
    rule: dict[str, Any]


@dataclass(frozen=True)
class SchemaOverrideSpec:
    """Input schema override gathered by the wizard."""

    field: str
    values: dict[str, Any]


@dataclass(frozen=True)
class MappingSuggestion:
    """A natural-language rule suggestion."""

    label: str
    rule_type: str
    rule: dict[str, Any]


@dataclass(frozen=True)
class MigrationWizardResult:
    """Result of generating a migration YAML file."""

    config_path: Path
    project_name: str
    input_path: Path
    output_path: Path
    input_name: str
    output_name: str
    advanced_mode: bool
    reference_count: int
    reference_schema_override_count: int
    derived_count: int
    validation_count: int
    filter_count: int
    check_count: int
    schema_override_count: int
    output_if_exists: str
    output_newline: str
    error_handling_max_errors: int
    runtime_log_level: str
    generated: GeneratedConfigResult


def run_migration_wizard() -> MigrationWizardResult:
    """Interactively generate a basic migration YAML file."""

    typer.echo("migration-wizard は、単一CSVから migration.yml を対話式で作成します。")
    typer.echo(
        "CSV と出力先を指定し、input 列数とは独立に出力列数と列名を決めたあと "
        "rule を割り当てます。"
    )
    typer.echo("")

    project_name = _prompt_text("プロジェクト名", "generated_migration")
    input_path = Path(_prompt_text("入力CSVのパス", "./input/users.csv"))
    output_path = Path(_prompt_text("出力CSVのパス", "./output/users_out.csv"))
    config_path = Path(_prompt_text("migration.yml の保存先", "./migration.yml"))
    input_name = _prompt_text("入力名", "input")
    output_name = _prompt_text("出力名", "output")
    output_specs = _prompt_output_columns()
    advanced_mode = _prompt_number_choice(
        "詳細設定を行いますか？",
        [
            ChoiceOption(label="基本設定のまま進める", value=False),
            ChoiceOption(label="lookup / derived も設定する", value=True),
        ],
        default_index=1,
        help_text="まずは基本設定だけでも進められます。",
    )
    overwrite = False
    if config_path.exists():
        overwrite = typer.confirm(f"{config_path} exists. Overwrite?", default=False)
        if not overwrite:
            raise ConfigError(f"{config_path}: migration.yml が既に存在します")

    try:
        column_previews = _read_csv_preview(input_path)
        generated = None
        while True:
            scaffold_output_mappings = _build_wizard_output_mappings(
                output_specs,
                input_name=input_name,
                input_columns=column_previews,
            )

            if advanced_mode:
                try:
                    (
                        generated,
                        reference_count,
                        reference_schema_override_count,
                        derived_count,
                        validation_count,
                        filter_count,
                        check_count,
                        schema_override_count,
                        output_if_exists,
                        output_newline,
                        error_handling_max_errors,
                        runtime_log_level,
                    ) = _generate_wizard_config(
                        input_path=input_path,
                        output_path=output_path,
                        config_path=config_path,
                        input_name=input_name,
                        output_name=output_name,
                        project_name=project_name,
                        overwrite=overwrite,
                        advanced_mode=advanced_mode,
                        output_specs=output_specs,
                        scaffold_output_mappings=scaffold_output_mappings,
                        input_columns=column_previews,
                    )
                except MigrationWizardRestart:
                    typer.echo("出力列と rule をやり直します。")
                    continue
            else:
                (
                    generated,
                    reference_count,
                    reference_schema_override_count,
                    derived_count,
                    validation_count,
                    filter_count,
                    check_count,
                    schema_override_count,
                    output_if_exists,
                    output_newline,
                    error_handling_max_errors,
                    runtime_log_level,
                ) = _generate_wizard_config(
                    input_path=input_path,
                    output_path=output_path,
                    config_path=config_path,
                    input_name=input_name,
                    output_name=output_name,
                    project_name=project_name,
                    overwrite=overwrite,
                    advanced_mode=advanced_mode,
                    output_specs=output_specs,
                    scaffold_output_mappings=scaffold_output_mappings,
                    input_columns=column_previews,
                )
            break
    except ConfigError:
        raise

    return MigrationWizardResult(
        config_path=generated.config_path,
        project_name=project_name,
        input_path=input_path,
        output_path=output_path,
        input_name=input_name,
        output_name=output_name,
        advanced_mode=advanced_mode,
        reference_count=reference_count,
        reference_schema_override_count=reference_schema_override_count,
        derived_count=derived_count,
        validation_count=validation_count,
        filter_count=filter_count,
        check_count=check_count,
        schema_override_count=schema_override_count,
        output_if_exists=output_if_exists,
        output_newline=output_newline,
        error_handling_max_errors=error_handling_max_errors,
        runtime_log_level=runtime_log_level,
        generated=generated,
    )


def _prompt_text(message: str, default: str, *, attempts: int = MAX_PROMPT_ATTEMPTS) -> str:
    last_error: str | None = None
    for _ in range(attempts):
        value = str(typer.prompt(message, default=default)).strip()
        if value:
            return value
        last_error = f"{message}: 空では登録できません。値を入力してください"
        typer.echo(last_error)
    raise ConfigError(last_error or f"{message}: invalid input")


def _prompt_number_choice(
    message: str,
    options: list[ChoiceOption],
    default_index: int,
    help_text: str | None = None,
    *,
    attempts: int = MAX_PROMPT_ATTEMPTS,
) -> bool:
    if not options:
        raise ConfigError(f"{message}: 選択肢がありません")

    default_text = str(default_index)
    last_error: str | None = None
    for _ in range(attempts):
        typer.echo(message)
        if help_text:
            typer.echo(f"  {help_text}")
        for index, option in enumerate(options, start=1):
            typer.echo(f"  {index}. {option.label}")
        value = str(typer.prompt("番号を入力してください", default=default_text)).strip()
        if not value:
            last_error = f"{message}: 番号を入力してください"
            typer.echo(last_error)
            continue
        try:
            index = int(value)
        except ValueError:
            last_error = f"{message}: 数字で入力してください。例: 1"
            typer.echo(last_error)
            continue
        if index < 1 or index > len(options):
            last_error = f"{message}: 選べる番号は 1 から {len(options)} です。入力値: {index}"
            typer.echo(last_error)
            continue
        return options[index - 1].value
    raise ConfigError(last_error or f"{message}: invalid input")


def _read_csv_preview(path: Path, *, sample_limit: int = CSV_SAMPLE_LIMIT) -> list[ColumnPreview]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file, delimiter=",")
            headers = next(reader, None)
            if headers is None:
                raise ConfigError(f"{path}: input CSV is empty")
            rows = [row for _, row in zip(range(sample_limit), reader, strict=False)]
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read input CSV: {exc}") from exc

    safe_fields = build_safe_field_names([str(header) for header in headers])
    previews: list[ColumnPreview] = []
    for index, (header, safe_field) in enumerate(zip(headers, safe_fields, strict=True), start=1):
        samples = [
            str(row[index - 1]).strip()
            for row in rows
            if index - 1 < len(row) and str(row[index - 1]).strip()
        ]
        previews.append(
            ColumnPreview(
                index=index,
                header=str(header),
                safe_field=safe_field,
                samples=samples[:sample_limit],
            )
        )
    return previews


@dataclass(frozen=True)
class OutputColumnSpec:
    """An output column declared directly by the user."""

    name: str


def _prompt_output_columns() -> list[OutputColumnSpec]:
    output_count = _prompt_int("出力列をいくつ作成しますか？", 1)
    if output_count < 1:
        raise ConfigError("出力列は 1 つ以上必要です")
    output_specs: list[OutputColumnSpec] = []
    used_names: set[str] = set()

    typer.echo("")
    typer.echo("出力列名を入力してください。")
    for index in range(1, output_count + 1):
        default_name = deduplicate_name(f"output_{index}", used_names)
        name = _prompt_text(f"  出力列 {index} の名前", default_name)
        name = deduplicate_name(name, used_names)
        used_names.add(name)
        output_specs.append(OutputColumnSpec(name=name))
    typer.echo("")
    typer.echo("作成する出力列:")
    for spec in output_specs:
        typer.echo(f"- {spec.name}")
    typer.echo("")
    return output_specs


def _prompt_number_selection(
    message: str,
    *,
    default_indices: list[int],
    total: int,
    attempts: int = MAX_PROMPT_ATTEMPTS,
) -> list[int]:
    default_text = ",".join(str(index) for index in default_indices)
    last_error: str | None = None
    for _ in range(attempts):
        value = str(typer.prompt(f"{message} を入力してください", default=default_text)).strip()
        if not value:
            value = default_text
        try:
            indices = _parse_number_selection(value, total=total)
        except ConfigError as exc:
            last_error = str(exc)
            typer.echo(last_error)
            continue
        if not indices:
            last_error = f"{message}: 1つ以上の番号を選んでください"
            typer.echo(last_error)
            continue
        return indices
    raise ConfigError(last_error or f"{message}: invalid input")


def _parse_number_selection(value: str, *, total: int) -> list[int]:
    parts = [part for part in value.replace(" ", ",").split(",") if part]
    if not parts:
        raise ConfigError("番号を入力してください")

    selected: list[int] = []
    for part in parts:
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            try:
                start = int(start_text)
                end = int(end_text)
            except ValueError as exc:
                raise ConfigError("数字で入力してください。例: 1,3") from exc
            if start > end:
                raise ConfigError(
                    "範囲指定は小さい番号から大きい番号の順で入力してください: " + part
                )
            selected.extend(range(start, end + 1))
            continue
        try:
            selected.append(int(part))
        except ValueError as exc:
            raise ConfigError("数字で入力してください。例: 1,3") from exc

    unique_selected: list[int] = []
    seen: set[int] = set()
    for index in selected:
        if index < 1 or index > total:
            raise ConfigError(f"選べる番号は 1 から {total} です。入力値: {index}")
        if index not in seen:
            seen.add(index)
            unique_selected.append(index)
    return sorted(unique_selected)


def _build_wizard_output_mappings(
    output_specs: list[OutputColumnSpec],
    *,
    input_name: str,
    input_columns: list[ColumnPreview],
) -> list[GeneratedOutputMapping]:
    if not input_columns:
        raise ConfigError("入力CSVに列がありません")
    placeholder_field = input_columns[0].safe_field
    mappings: list[GeneratedOutputMapping] = []
    for spec in output_specs:
        mappings.append(
            GeneratedOutputMapping(
                output_column=spec.name,
                schema_field=placeholder_field,
            )
        )
    return mappings


def _generate_wizard_config(
    *,
    input_path: Path,
    output_path: Path,
    config_path: Path,
    input_name: str,
    output_name: str,
    project_name: str,
    overwrite: bool,
    advanced_mode: bool,
    output_specs: list[OutputColumnSpec],
    scaffold_output_mappings: list[GeneratedOutputMapping],
    input_columns: list[ColumnPreview],
) -> tuple[GeneratedConfigResult, int, int, int, int, int, int, str, str, int, str]:
    temp_config_path = config_path.with_suffix(config_path.suffix + ".wizard.tmp")
    if temp_config_path.exists():
        temp_config_path.unlink()

    generated = generate_basic_config(
        input_path,
        output_path,
        temp_config_path,
        input_name=input_name,
        output_name=output_name,
        project_name=project_name,
        overwrite=True,
        preserve_output_columns=False,
        output_mappings=scaffold_output_mappings,
    )

    try:
        config_data = yaml.safe_load(temp_config_path.read_text(encoding="utf-8"))
        if not isinstance(config_data, dict):
            raise ConfigError(f"{config_path}: generated config is invalid")

        reference_specs: list[ReferenceSpec] = []
        derived_specs: list[DerivedSpec] = []
        validations: dict[str, list[dict[str, Any]]] = {"input": [], "output": []}
        filters: dict[str, list[dict[str, Any]]] = {"include": [], "exclude": []}
        checks: list[dict[str, Any]] = []
        schema_overrides: list[SchemaOverrideSpec] = []
        output_settings = config_data["outputs"][output_name]
        error_handling_settings = config_data["error_handling"]
        runtime_settings = config_data["runtime"]
        if advanced_mode:
            reference_specs = _prompt_reference_specs()
            derived_specs = _prompt_derived_specs(
                input_name=input_name,
                input_columns=input_columns,
                reference_specs=reference_specs,
            )
            validations = _prompt_validations(
                input_name=input_name,
                input_columns=input_columns,
                output_columns=[spec.name for spec in output_specs],
            )
            filters = _prompt_filters(
                input_name=input_name,
                input_columns=input_columns,
                derived_specs=derived_specs,
            )
            checks = _prompt_checks(
                input_name=input_name,
                input_columns=input_columns,
                derived_specs=derived_specs,
            )
            schema_overrides = _prompt_input_schema_overrides(
                input_name=input_name,
                input_columns=input_columns,
            )
            output_settings = _prompt_output_settings(output_name=output_name)
            error_handling_settings = _prompt_error_handling_settings()
            runtime_settings = _prompt_runtime_settings()

        output_rules = _prompt_output_rules(
            output_specs=output_specs,
            input_name=input_name,
            input_columns=input_columns,
            reference_specs=reference_specs,
            derived_names=[spec.name for spec in derived_specs],
        )

        if reference_specs:
            config_data["references"] = _build_reference_section(reference_specs)
        if derived_specs:
            config_data["derived"] = {
                spec.name: spec.rule for spec in derived_specs
            }
        if validations["input"] or validations["output"]:
            config_data["validations"] = {
                key: value for key, value in validations.items() if value
            }
        if filters["include"] or filters["exclude"]:
            config_data["filters"] = {
                key: value for key, value in filters.items() if value
            }
        if checks:
            config_data["checks"] = checks
        if schema_overrides:
            input_schema = config_data["inputs"][input_name]["schema"]
            for spec in schema_overrides:
                input_schema[spec.field].update(spec.values)
        config_data["outputs"][output_name].update(output_settings)
        config_data["error_handling"].update(error_handling_settings)
        config_data["runtime"].update(runtime_settings)
        config_data["mappings"] = {
            output_name: output_rules,
        }
        DatamapxConfig.model_validate(config_data)
        review_text = _format_migration_review(
            project_name=project_name,
            input_name=input_name,
            output_name=output_name,
            output_columns=[spec.name for spec in output_specs],
            output_rules=output_rules,
            reference_specs=reference_specs,
            derived_specs=derived_specs,
            validations=validations,
            filters=filters,
            checks=checks,
            schema_overrides=schema_overrides,
            output_settings=output_settings,
            error_handling_settings=error_handling_settings,
            runtime_settings=runtime_settings,
        )
        typer.echo("")
        typer.echo("Review")
        typer.echo(review_text)
        review_action = _prompt_number_choice(
            "保存前の操作を番号で選択",
            [
                ChoiceOption(label="この内容で migration.yml を作成する", value="save"),
                ChoiceOption(label="出力列と rule をやり直す", value="redo"),
                ChoiceOption(label="中止する", value="cancel"),
            ],
            default_index=1,
            help_text="1=保存 / 2=出力列と rule をやり直す / 3=中止",
        )
        if review_action == "redo":
            raise MigrationWizardRestart
        if review_action == "cancel":
            raise ConfigError("migration-wizard を中止しました")
        config_text = yaml.safe_dump(
            config_data,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            indent=2,
            width=1000,
        )
        config_path.write_text(config_text, encoding="utf-8")
    finally:
        if temp_config_path.exists():
            temp_config_path.unlink()

    return (
        GeneratedConfigResult(
            config_path=config_path,
            input_headers=generated.input_headers,
            schema_fields=generated.schema_fields,
            output_columns=generated.output_columns,
        ),
        len(reference_specs),
        sum(len(spec.schema_overrides) for spec in reference_specs),
        len(derived_specs),
        len(validations["input"]) + len(validations["output"]),
        len(filters["include"]) + len(filters["exclude"]),
        len(checks),
        len(schema_overrides),
        output_settings["if_exists"],
        output_settings["newline"],
        error_handling_settings["max_errors"],
        runtime_settings["log_level"],
    )


def _format_migration_review(
    *,
    project_name: str,
    input_name: str,
    output_name: str,
    output_columns: list[str],
    output_rules: dict[str, dict[str, Any]],
    reference_specs: list[ReferenceSpec],
    derived_specs: list[DerivedSpec],
    validations: dict[str, list[dict[str, Any]]],
    filters: dict[str, list[dict[str, Any]]],
    checks: list[dict[str, Any]],
    schema_overrides: list[SchemaOverrideSpec],
    output_settings: dict[str, Any],
    error_handling_settings: dict[str, Any],
    runtime_settings: dict[str, Any],
) -> str:
    lines = [
        f"project: {project_name}",
        f"input: {input_name}",
        f"output: {output_name}",
        "",
        "出力列と rule:",
    ]
    for output_column in output_columns:
        rule = output_rules.get(output_column)
        lines.append(f"- {output_column}: {_summarize_rule(rule)}")
    if reference_specs:
        lines.append("")
        lines.append("reference CSV:")
        for spec in reference_specs:
            lines.append(
                f"- {spec.name}: {spec.path} (key: {', '.join(spec.key)})"
                + (
                    f", schema 変更 {len(spec.schema_overrides)} 件"
                    if spec.schema_overrides
                    else ""
                )
            )
    if derived_specs:
        lines.append("")
        lines.append("derived:")
        for spec in derived_specs:
            lines.append(f"- {spec.name}")
    if schema_overrides:
        lines.append("")
        lines.append("input schema 変更:")
        for spec in schema_overrides:
            lines.append(f"- {spec.field}")
    total_validations = len(validations["input"]) + len(validations["output"])
    total_filters = len(filters["include"]) + len(filters["exclude"])
    lines.extend(
        [
            "",
            f"validations: {total_validations}",
            f"filters: {total_filters}",
            f"checks: {len(checks)}",
            f"output.if_exists: {output_settings['if_exists']}",
            f"output.newline: {_format_newline(output_settings['newline'])}",
            f"error_handling.max_errors: {error_handling_settings['max_errors']}",
            f"runtime.log_level: {runtime_settings['log_level']}",
        ]
    )
    return "\n".join(lines)


def _summarize_rule(rule: dict[str, Any] | None) -> str:
    if not rule:
        return "(未設定)"
    if "source" in rule:
        return f"source: {rule['source']}"
    if "value" in rule:
        return f"value: {rule['value']}"
    if "expression" in rule:
        return f"expression: {rule['expression']}"
    if "lookup" in rule:
        lookup = rule["lookup"]
        if isinstance(lookup, dict):
            reference = lookup.get("reference", "(unknown)")
            value = lookup.get("value", "(unknown)")
            return f"lookup: {reference}.{value}"
        return "lookup"
    if "when" in rule:
        when_rules = rule["when"]
        if isinstance(when_rules, list):
            return f"when: {len(when_rules)} 条件"
        return "when"
    if "concat" in rule:
        concat = rule["concat"]
        if isinstance(concat, dict):
            values = concat.get("values", [])
            return f"concat: {len(values)} 要素"
        return "concat"
    if "map" in rule:
        map_rule = rule["map"]
        if isinstance(map_rule, dict):
            source = map_rule.get("source", "(unknown)")
            return f"map: {source}"
        return "map"
    if "suggest" in rule:
        return "suggest"
    return ", ".join(sorted(rule))


def _format_newline(value: str) -> str:
    return value.replace("\r", "\\r").replace("\n", "\\n")


def _build_reference_section(reference_specs: list[ReferenceSpec]) -> dict[str, Any]:
    section: dict[str, Any] = {}
    for spec in reference_specs:
        reference_section: dict[str, Any] = {
            "path": str(spec.path),
            "encoding": "utf-8-sig",
            "delimiter": ",",
            "header": True,
            "key": spec.key[0] if len(spec.key) == 1 else spec.key,
            "on_duplicate": "error",
        }
        if spec.schema_overrides:
            schema = {
                column.safe_field: _build_default_schema_field(column)
                for column in spec.columns
            }
            for override in spec.schema_overrides:
                schema[override.field].update(override.values)
            reference_section["schema"] = schema
        section[spec.name] = reference_section
    return section


def _prompt_reference_specs() -> list[ReferenceSpec]:
    reference_count = _prompt_int("参照CSVをいくつ追加しますか？", 0)
    references: list[ReferenceSpec] = []
    used_names: set[str] = set()
    for index in range(1, reference_count + 1):
        typer.echo("")
        typer.echo(f"参照CSV {index}")
        path = Path(_prompt_text("  CSVファイルのパス", f"./ref/reference_{index}.csv"))
        columns = _read_csv_preview(path)
        default_name = deduplicate_name(path.stem or f"reference_{index}", used_names)
        name = _prompt_text("  論理名", default_name)
        name = deduplicate_name(name, used_names)
        used_names.add(name)
        typer.echo(_format_column_preview_list(f"  {name} の列", columns))
        key_fields = _prompt_number_choices(
            f"  {name} のキー列を番号で選択",
            [
                ChoiceOption(
                    label=f"{column.index}. {column.header} ({column.safe_field})",
                    value=column.safe_field,
                )
                for column in columns
            ],
            default_indices=[1],
            help_text="複数キーは 1,2 のように入力できます。",
        )
        schema_overrides = _prompt_reference_schema_overrides(
            reference_name=name,
            columns=columns,
        )
        references.append(
            ReferenceSpec(
                name=name,
                path=path,
                columns=columns,
                key=key_fields,
                schema_overrides=schema_overrides,
            )
        )
    return references


def _prompt_reference_schema_overrides(
    *,
    reference_name: str,
    columns: list[ColumnPreview],
) -> list[SchemaOverrideSpec]:
    typer.echo("")
    typer.echo(f"  {reference_name} の reference schema を設定します。")
    override_count = _prompt_int("  schema を変更する列はいくつありますか？", 0)
    overrides: list[SchemaOverrideSpec] = []
    used_fields: set[str] = set()
    for index in range(1, override_count + 1):
        typer.echo("")
        typer.echo(f"  reference schema {index}")
        options = [
            ChoiceOption(
                label=fill(
                    f"{column.index}. {reference_name}.{column.safe_field} (CSV: {column.header})",
                    width=96,
                    subsequent_indent="    ",
                ),
                value=column,
            )
            for column in columns
            if column.safe_field not in used_fields
        ]
        if not options:
            raise ConfigError("reference schema を変更できる列がありません")
        selected = _prompt_number_choice(
            "    対象列を番号で選択",
            options,
            default_index=1,
            help_text="1件だけ選びます。",
        )
        used_fields.add(selected.safe_field)
        field_overrides = _prompt_schema_field_overrides(
            context=f"references.{reference_name}.schema.{selected.safe_field}",
        )
        overrides.append(SchemaOverrideSpec(field=selected.safe_field, values=field_overrides))
    return overrides


def _prompt_derived_specs(
    *,
    input_name: str,
    input_columns: list[ColumnPreview],
    reference_specs: list[ReferenceSpec],
) -> list[DerivedSpec]:
    derived_count = _prompt_int("derived をいくつ追加しますか？", 0)
    derived_specs: list[DerivedSpec] = []
    used_names: set[str] = set()
    for index in range(1, derived_count + 1):
        typer.echo("")
        typer.echo(f"derived {index}")
        default_name = deduplicate_name(f"derived_{index}", used_names)
        name = _prompt_text("  derived名", default_name)
        name = deduplicate_name(name, used_names)
        used_names.add(name)
        rule = _prompt_mapping_rule(
            context=f"derived.{name}",
            input_name=input_name,
            input_columns=input_columns,
            reference_specs=reference_specs,
            derived_names=[spec.name for spec in derived_specs],
            default_source=f"{input_name}.{input_columns[0].safe_field}" if input_columns else None,
        )
        derived_specs.append(DerivedSpec(name=name, rule=rule))
    return derived_specs


def _prompt_output_rules(
    *,
    output_specs: list[OutputColumnSpec],
    input_name: str,
    input_columns: list[ColumnPreview],
    reference_specs: list[ReferenceSpec],
    derived_names: list[str],
) -> dict[str, dict[str, Any]]:
    rules: dict[str, dict[str, Any]] = {}
    typer.echo("")
    typer.echo("出力列ごとに rule を選んでください。")
    for spec in output_specs:
        default_source = _default_source_for_output_column(
            spec.name,
            input_name=input_name,
            input_columns=input_columns,
            derived_names=derived_names,
        )
        typer.echo(fill(f"- {spec.name}", width=96, subsequent_indent="  "))
        rule_options = [
            ChoiceOption(label="source", value="source"),
            ChoiceOption(label="value", value="value"),
            ChoiceOption(label="concat", value="concat"),
            ChoiceOption(label="map", value="map"),
            ChoiceOption(label="when", value="when"),
            ChoiceOption(label="expression", value="expression"),
        ]
        if reference_specs:
            rule_options.insert(5, ChoiceOption(label="lookup", value="lookup"))
        rule_options.append(
            ChoiceOption(label="自然言語から提案を受ける", value="suggest"),
        )
        rule = _prompt_mapping_rule(
            context=f"mappings.output.{spec.name}",
            input_name=input_name,
            input_columns=input_columns,
            reference_specs=reference_specs,
            derived_names=derived_names,
            default_source=default_source,
            rule_options=rule_options,
        )
        rules[spec.name] = rule
    return rules


def _default_source_for_output_column(
    output_column: str,
    *,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
) -> str | None:
    if output_column in derived_names:
        return f"derived.{output_column}"
    for column in input_columns:
        if output_column == column.safe_field or output_column == column.header:
            return f"{input_name}.{column.safe_field}"
    if input_columns:
        return f"{input_name}.{input_columns[0].safe_field}"
    return None


def _prompt_mapping_rule(
    *,
    context: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    reference_specs: list[ReferenceSpec],
    derived_names: list[str],
    default_source: str | None,
    rule_options: list[ChoiceOption] | None = None,
) -> dict[str, Any]:
    rule_type = _prompt_number_choice(
        f"{context}: ルール種別を番号で選択",
        rule_options
        or [
            ChoiceOption(label="source", value="source"),
            ChoiceOption(label="value", value="value"),
            ChoiceOption(label="concat", value="concat"),
            ChoiceOption(label="map", value="map"),
            ChoiceOption(label="when", value="when"),
            ChoiceOption(label="lookup", value="lookup"),
            ChoiceOption(label="expression", value="expression"),
            ChoiceOption(label="自然言語から提案を受ける", value="suggest"),
        ],
        default_index=1,
        help_text="まずは source を選ぶと基本的なコピーになります。",
    )
    if rule_type == "suggest":
        return _prompt_suggested_mapping_rule(
            context=context,
            input_name=input_name,
            input_columns=input_columns,
            reference_specs=reference_specs,
            derived_names=derived_names,
        )
    return _build_mapping_rule_from_type(
        rule_type=rule_type,
        context=context,
        input_name=input_name,
        input_columns=input_columns,
        reference_specs=reference_specs,
        derived_names=derived_names,
        default_source=default_source,
    )


def _build_mapping_rule_from_type(
    *,
    rule_type: str,
    context: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    reference_specs: list[ReferenceSpec],
    derived_names: list[str],
    default_source: str | None,
) -> dict[str, Any]:
    if rule_type == "source":
        return {
            "source": _prompt_field_reference(
                message=f"{context}: source に使う列を番号で選択",
                input_name=input_name,
                input_columns=input_columns,
                derived_names=derived_names,
                default_source=default_source,
            )
        }
    if rule_type == "value":
        return {"value": _prompt_text(f"{context}: 固定値", "")}
    if rule_type == "concat":
        return {
            "concat": {
                "values": _prompt_concat_values(
                    context=context,
                    input_name=input_name,
                    input_columns=input_columns,
                    derived_names=derived_names,
                )
            }
        }
    if rule_type == "map":
        return {
            "map": _prompt_map_rule(
                context=context,
                input_name=input_name,
                input_columns=input_columns,
                derived_names=derived_names,
            )
        }
    if rule_type == "when":
        return {
            "when": _prompt_when_rules(
                context=context,
                input_name=input_name,
                input_columns=input_columns,
                derived_names=derived_names,
            )
        }
    if rule_type == "lookup":
        return {
            "lookup": _prompt_lookup_rule(
                context=context,
                input_name=input_name,
                input_columns=input_columns,
                reference_specs=reference_specs,
                derived_names=derived_names,
            )
        }
    if rule_type == "expression":
        return {
            "expression": _prompt_expression_rule(
                context=context,
                input_name=input_name,
                input_columns=input_columns,
                derived_names=derived_names,
            )
        }
    raise ConfigError(f"{context}: unsupported rule type: {rule_type}")


def _prompt_suggested_mapping_rule(
    *,
    context: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    reference_specs: list[ReferenceSpec],
    derived_names: list[str],
) -> dict[str, Any]:
    suggestion_text = _prompt_text(f"{context}: やりたいことを文章で入力", "")
    suggestions = _suggest_mapping_rules(
        suggestion_text,
        context=context,
        input_name=input_name,
        input_columns=input_columns,
        reference_specs=reference_specs,
        derived_names=derived_names,
    )
    if not suggestions:
        typer.echo("  提案できるルールがありませんでした。通常入力に戻ります。")
        return _build_mapping_rule_from_type(
            rule_type=_prompt_number_choice(
                f"{context}: ルール種別を番号で選択",
                [
                    ChoiceOption(label="source", value="source"),
                    ChoiceOption(label="value", value="value"),
                    ChoiceOption(label="concat", value="concat"),
                    ChoiceOption(label="map", value="map"),
                    ChoiceOption(label="when", value="when"),
                    ChoiceOption(label="expression", value="expression"),
                    *(
                        [ChoiceOption(label="lookup", value="lookup")]
                        if reference_specs
                        else []
                    ),
                ],
                default_index=1,
                help_text="提案が合わない場合は通常のルール選択に戻れます。",
            ),
            context=context,
            input_name=input_name,
            input_columns=input_columns,
            reference_specs=reference_specs,
            derived_names=derived_names,
            default_source=None,
        )

    typer.echo("提案されたルール:")
    for index, suggestion in enumerate(suggestions, start=1):
        typer.echo(f"  {index}. {suggestion.label}")
    selection = _prompt_number_choice(
        f"{context}: 提案を番号で選択",
        [ChoiceOption(label=suggestion.label, value=suggestion) for suggestion in suggestions],
        default_index=1,
        help_text="1件を選ぶとそのルールを使います。",
    )
    return selection.rule


def _prompt_expression_rule(
    *,
    context: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
) -> str:
    mode = _prompt_number_choice(
        f"{context}: expression の入力方法を選択",
        [
            ChoiceOption(label="ビルダーで作る", value="builder"),
            ChoiceOption(label="直接入力する", value="direct"),
            ChoiceOption(label="文章から提案を受ける", value="suggest"),
        ],
        default_index=1,
        help_text="非エンジニア向けはビルダーが基本です。",
    )
    if mode == "direct":
        return _prompt_text(f"{context}: expression", "")
    if mode == "suggest":
        suggestion_text = _prompt_text(f"{context}: やりたいことを文章で入力", "")
        suggestions = _suggest_expression_rules(
            suggestion_text,
            context=context,
            input_name=input_name,
            input_columns=input_columns,
            derived_names=derived_names,
        )
        if suggestions:
            typer.echo("提案された expression:")
            for index, suggestion in enumerate(suggestions, start=1):
                typer.echo(f"  {index}. {suggestion.label}")
            selection = _prompt_number_choice(
                f"{context}: 提案を番号で選択",
                [
                    ChoiceOption(label=suggestion.label, value=suggestion)
                    for suggestion in suggestions
                ],
                default_index=1,
            )
            return selection.rule["expression"]
        typer.echo("  提案できる expression がありませんでした。ビルダーを使います。")
    return _build_expression_rule(
        context=context,
        input_name=input_name,
        input_columns=input_columns,
        derived_names=derived_names,
    )


def _prompt_condition_rule(
    *,
    context: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
) -> str:
    mode = _prompt_number_choice(
        f"{context}: 条件の入力方法を選択",
        [
            ChoiceOption(label="ビルダーで作る", value="builder"),
            ChoiceOption(label="直接入力する", value="direct"),
        ],
        default_index=1,
        help_text="非エンジニア向けはビルダーが基本です。",
    )
    if mode == "direct":
        return _prompt_text(f"{context}: 条件式", "")
    return _build_condition_rule(
        context=context,
        input_name=input_name,
        input_columns=input_columns,
        derived_names=derived_names,
        allow_summary=False,
    )


def _prompt_check_rule(
    *,
    context: str,
) -> str:
    mode = _prompt_number_choice(
        f"{context}: rule の入力方法を選択",
        [
            ChoiceOption(label="ビルダーで作る", value="builder"),
            ChoiceOption(label="直接入力する", value="direct"),
        ],
        default_index=1,
        help_text="checks は summary 変数を使って作ることが多いです。",
    )
    if mode == "direct":
        return _prompt_text(f"{context}: rule", "")
    return _build_check_rule(context=context)


def _build_condition_rule(
    *,
    context: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
    allow_summary: bool,
) -> str:
    left = _prompt_condition_reference(
        context=f"{context}: 左辺",
        input_name=input_name,
        input_columns=input_columns,
        derived_names=derived_names,
        allow_summary=allow_summary,
    )
    operator = _prompt_number_choice(
        f"{context}: 比較演算子を選択",
        [
            ChoiceOption(label="==", value="=="),
            ChoiceOption(label="!=", value="!="),
            ChoiceOption(label=">", value=">"),
            ChoiceOption(label=">=", value=">="),
            ChoiceOption(label="<", value="<"),
            ChoiceOption(label="<=", value="<="),
            ChoiceOption(label="in", value="in"),
            ChoiceOption(label="not in", value="not in"),
        ],
        default_index=1,
    )
    literal = _prompt_condition_literal(
        context=f"{context}: 右辺",
        operator=operator,
        allow_summary=allow_summary,
        input_name=input_name,
        input_columns=input_columns,
        derived_names=derived_names,
    )
    return f"{left} {operator} {literal}"


def _build_check_rule(
    *,
    context: str,
) -> str:
    left = _prompt_check_operand(
        context=f"{context}: 左辺",
    )
    operator = _prompt_number_choice(
        f"{context}: 比較演算子を選択",
        [
            ChoiceOption(label="==", value="=="),
            ChoiceOption(label="!=", value="!="),
            ChoiceOption(label=">", value=">"),
            ChoiceOption(label=">=", value=">="),
            ChoiceOption(label="<", value="<"),
            ChoiceOption(label="<=", value="<="),
        ],
        default_index=1,
    )
    right = _prompt_check_operand(
        context=f"{context}: 右辺",
    )
    return f"{left} {operator} {right}"


def _build_expression_rule(
    *,
    context: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
) -> str:
    expression = _prompt_expression_operand(
        context=f"{context}: 最初の項",
        input_name=input_name,
        input_columns=input_columns,
        derived_names=derived_names,
    )
    while True:
        action = _prompt_number_choice(
            f"{context}: expression に追加する操作を選択",
            [
                ChoiceOption(label="演算子を追加", value="operator"),
                ChoiceOption(label="関数で包む", value="function"),
                ChoiceOption(label="終了", value="done"),
            ],
            default_index=1,
        )
        if action == "done":
            break
        if action == "operator":
            operator = _prompt_number_choice(
                f"{context}: 演算子を選択",
                [
                    ChoiceOption(label="+", value="+"),
                    ChoiceOption(label="-", value="-"),
                    ChoiceOption(label="*", value="*"),
                    ChoiceOption(label="/", value="/"),
                    ChoiceOption(label="//", value="//"),
                    ChoiceOption(label="%", value="%"),
                    ChoiceOption(label="**", value="**"),
                ],
                default_index=1,
            )
            next_operand = _prompt_expression_operand(
                context=f"{context}: 次の項",
                input_name=input_name,
                input_columns=input_columns,
                derived_names=derived_names,
            )
            expression = f"({expression} {operator} {next_operand})"
            continue
        function = _prompt_number_choice(
            f"{context}: 関数を選択",
            [
                ChoiceOption(label="round", value="round"),
                ChoiceOption(label="abs", value="abs"),
                ChoiceOption(label="min", value="min"),
                ChoiceOption(label="max", value="max"),
            ],
            default_index=1,
        )
        if function in {"round", "abs"}:
            expression = f"{function}({expression})"
            continue
        other_operand = _prompt_expression_operand(
            context=f"{context}: 関数のもう一方の項",
            input_name=input_name,
            input_columns=input_columns,
            derived_names=derived_names,
        )
        expression = f"{function}({expression}, {other_operand})"
    return expression


def _prompt_expression_operand(
    *,
    context: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
) -> str:
    operand_type = _prompt_number_choice(
        f"{context}: 項目の種類を選択",
        [
            ChoiceOption(label="列を使う", value="field"),
            ChoiceOption(label="数値を使う", value="number"),
            ChoiceOption(label="文字列を使う", value="string"),
        ],
        default_index=1,
    )
    if operand_type == "field":
        return _prompt_field_reference(
            message=f"{context}: 列を番号で選択",
            input_name=input_name,
            input_columns=input_columns,
            derived_names=derived_names,
            default_source=None,
        )
    if operand_type == "number":
        return _prompt_numeric_literal(f"{context}: 数値")
    return _prompt_quoted_literal(f"{context}: 文字列")


def _prompt_check_operand(
    *,
    context: str,
) -> str:
    operand_type = _prompt_number_choice(
        f"{context}: 項目の種類を選択",
        [
            ChoiceOption(
                label="input_rows / output_rows / error_rows / skipped_rows",
                value="summary",
            ),
            ChoiceOption(label="数値を使う", value="number"),
            ChoiceOption(label="文字列を使う", value="string"),
        ],
        default_index=1,
    )
    if operand_type == "summary":
        return _prompt_number_choice(
            f"{context}: summary 変数を選択",
            [
                ChoiceOption(label="input_rows", value="input_rows"),
                ChoiceOption(label="output_rows", value="output_rows"),
                ChoiceOption(label="error_rows", value="error_rows"),
                ChoiceOption(label="skipped_rows", value="skipped_rows"),
            ],
            default_index=1,
        )
    if operand_type == "number":
        return _prompt_numeric_literal(f"{context}: 数値")
    return _prompt_quoted_literal(f"{context}: 文字列")


def _prompt_condition_reference(
    *,
    context: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
    allow_summary: bool,
) -> str:
    options: list[ChoiceOption] = []
    for column in input_columns:
        options.append(
            ChoiceOption(
                label=f"{input_name}.{column.safe_field} (CSV: {column.header})",
                value=f"{input_name}.{column.safe_field}",
            )
        )
    for name in derived_names:
        options.append(ChoiceOption(label=f"derived.{name}", value=f"derived.{name}"))
    if allow_summary:
        for name in ("input_rows", "output_rows", "error_rows", "skipped_rows"):
            options.append(ChoiceOption(label=name, value=name))
    if not options:
        raise ConfigError(f"{context}: 選択できる列がありません")
    return _prompt_number_choice(
        context,
        options,
        default_index=1,
        help_text="番号で選びます。",
    )


def _prompt_condition_literal(
    *,
    context: str,
    operator: str,
    allow_summary: bool,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
) -> str:
    if operator in {"in", "not in"}:
        return _prompt_literal_list(context)
    literal_type = _prompt_number_choice(
        f"{context}: 値の種類を選択",
        [
            ChoiceOption(label="true", value="true"),
            ChoiceOption(label="false", value="false"),
            ChoiceOption(label="null", value="null"),
            ChoiceOption(label="数値", value="number"),
            ChoiceOption(label="文字列", value="string"),
        ],
        default_index=4,
    )
    if literal_type in {"true", "false", "null"}:
        return literal_type
    if literal_type == "number":
        return _prompt_numeric_literal(context)
    return _prompt_quoted_literal(context)


def _prompt_literal_list(message: str) -> str:
    items: list[str] = []
    count = _prompt_int(f"{message}: リストの件数", 2)
    for index in range(1, count + 1):
        item_mode = _prompt_number_choice(
            f"{message}: {index}件目の種類を選択",
            [
                ChoiceOption(label="数値", value="number"),
                ChoiceOption(label="文字列", value="string"),
                ChoiceOption(label="true", value="true"),
                ChoiceOption(label="false", value="false"),
                ChoiceOption(label="null", value="null"),
            ],
            default_index=2,
        )
        if item_mode == "number":
            items.append(_prompt_numeric_literal(f"{message}: {index}件目"))
        elif item_mode == "string":
            items.append(_prompt_quoted_literal(f"{message}: {index}件目"))
        else:
            items.append(item_mode)
    return json.dumps(items, ensure_ascii=False)


def _prompt_numeric_literal(message: str) -> str:
    while True:
        value = _prompt_text(message, "0")
        try:
            int(value)
            return value
        except ValueError:
            try:
                float(value)
                return value
            except ValueError:
                typer.echo(f"{message}: 数値で入力してください")


def _prompt_quoted_literal(message: str) -> str:
    value = _prompt_text(message, "")
    return json.dumps(value, ensure_ascii=False)


def _suggest_mapping_rules(
    text: str,
    *,
    context: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    reference_specs: list[ReferenceSpec],
    derived_names: list[str],
) -> list[MappingSuggestion]:
    normalized = text.lower()
    matched_columns = _rank_columns(normalized, input_columns)
    suggestions: list[MappingSuggestion] = []

    if ("参照" in text or "取得" in text or "引" in text) and reference_specs:
        reference_spec = reference_specs[0]
        key_field = (
            matched_columns[0].safe_field if matched_columns else input_columns[0].safe_field
        )
        value_field = _rank_columns(normalized, reference_spec.columns)
        selected_value = value_field[0].header if value_field else reference_spec.columns[0].header
        suggestions.append(
            MappingSuggestion(
                label=f"lookup: {reference_spec.name} から参照する",
                rule_type="lookup",
                rule={
                    "lookup": {
                        "reference": reference_spec.name,
                        "key": f"{input_name}.{key_field}",
                        "value": selected_value,
                        "on_missing": "error",
                    }
                },
            )
        )

    expression_rule = _suggest_expression_rule(text, input_name, input_columns, derived_names)
    if expression_rule is not None:
        suggestions.append(
            MappingSuggestion(
                label=expression_rule[0],
                rule_type="expression",
                rule={"expression": expression_rule[1]},
            )
        )

    if "固定" in text or "常に" in text:
        suggestions.append(
            MappingSuggestion(
                label="value: 固定値として使う",
                rule_type="value",
                rule={"value": _prompt_text(f"{context}: 固定値", "")},
            )
        )

    source_rule = _suggest_source_rule(text, input_name, input_columns, derived_names)
    if source_rule is not None:
        suggestions.append(source_rule)

    return suggestions


def _suggest_expression_rules(
    text: str,
    *,
    context: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
) -> list[MappingSuggestion]:
    expression_rule = _suggest_expression_rule(text, input_name, input_columns, derived_names)
    if expression_rule is None:
        return []
    return [
        MappingSuggestion(
            label=expression_rule[0],
            rule_type="expression",
            rule={"expression": expression_rule[1]},
        )
    ]


def _suggest_expression_rule(
    text: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
) -> tuple[str, str] | None:
    matched = _rank_columns(text.lower(), input_columns)
    field_a = (
        _field_reference_for_column(
            input_name,
            matched[0] if matched else input_columns[0],
        )
        if input_columns
        else None
    )
    field_b = _field_reference_for_column(input_name, matched[1]) if len(matched) > 1 else None
    if field_a is None:
        return None

    if "2倍" in text or "倍" in text:
        return ("expression: 2倍にする", f"({field_a} * 2)")
    if any(keyword in text for keyword in ("足", "合計", "加算", "和")) and field_b is not None:
        return ("expression: 2つの列を足す", f"({field_a} + {field_b})")
    if any(keyword in text for keyword in ("引", "差し引", "減算")) and field_b is not None:
        return ("expression: 2つの列を引く", f"({field_a} - {field_b})")
    if any(keyword in text for keyword in ("掛", "乗算")) and field_b is not None:
        return ("expression: 2つの列を掛ける", f"({field_a} * {field_b})")
    if any(keyword in text for keyword in ("割", "除算")) and field_b is not None:
        return ("expression: 2つの列で割る", f"({field_a} / {field_b})")
    if any(keyword in text for keyword in ("丸め", "round")):
        return ("expression: round を使う", f"round({field_a})")
    if any(keyword in text for keyword in ("絶対", "abs")):
        return ("expression: abs を使う", f"abs({field_a})")
    if any(keyword in text for keyword in ("最小", "min")) and field_b is not None:
        return ("expression: min を使う", f"min({field_a}, {field_b})")
    if any(keyword in text for keyword in ("最大", "max")) and field_b is not None:
        return ("expression: max を使う", f"max({field_a}, {field_b})")
    return None


def _suggest_source_rule(
    text: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
) -> MappingSuggestion | None:
    matched = _rank_columns(text.lower(), input_columns)
    if not matched and not derived_names:
        return None
    if any(keyword in text for keyword in ("そのまま", "コピー", "引用", "copy")):
        target = matched[0] if matched else input_columns[0]
        return MappingSuggestion(
            label=f"source: {target.header} をそのまま使う",
            rule_type="source",
            rule={"source": _field_reference_for_column(input_name, target)},
        )
    return None


def _field_reference_for_column(input_name: str, column: ColumnPreview) -> str:
    return f"{input_name}.{column.safe_field}"


def _rank_columns(text: str, columns: list[ColumnPreview]) -> list[ColumnPreview]:
    scored: list[tuple[int, int, ColumnPreview]] = []
    for index, column in enumerate(columns):
        score = 0
        header = column.header.lower()
        safe_field = column.safe_field.lower()
        if header and header in text:
            score += 10
        if safe_field and safe_field in text:
            score += 10
        for token in safe_field.split("_"):
            if token and token in text:
                score += 2
        for char in header:
            if char.strip() and char in text:
                score += 1
        scored.append((score, index, column))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [column for score, _, column in scored if score > 0]


def _prompt_field_reference(
    *,
    message: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
    default_source: str | None,
) -> str:
    options: list[ChoiceOption] = []
    for column in input_columns:
        options.append(
            ChoiceOption(
                label=f"{input_name}.{column.safe_field} (CSV: {column.header})",
                value=f"{input_name}.{column.safe_field}",
            )
        )
    for name in derived_names:
        options.append(ChoiceOption(label=f"derived.{name}", value=f"derived.{name}"))
    if not options:
        raise ConfigError(f"{message}: 選択できる列がありません")
    default_index = 1
    if default_source is not None:
        for index, option in enumerate(options, start=1):
            if option.value == default_source:
                default_index = index
                break
    return _prompt_number_choice(message, options, default_index=default_index)


def _prompt_field_references(
    *,
    message: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
    default_indices: list[int] | None = None,
) -> list[str]:
    options: list[ChoiceOption] = []
    for column in input_columns:
        options.append(
            ChoiceOption(
                label=f"{input_name}.{column.safe_field} (CSV: {column.header})",
                value=f"{input_name}.{column.safe_field}",
            )
        )
    for name in derived_names:
        options.append(ChoiceOption(label=f"derived.{name}", value=f"derived.{name}"))
    if not options:
        raise ConfigError(f"{message}: 選択できる列がありません")
    selected = _prompt_number_choices(
        message,
        options,
        default_indices=default_indices or [1],
        help_text="複数選択は 1,3 のように入力できます。",
    )
    return [str(value) for value in selected]


def _prompt_concat_values(
    *,
    context: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
) -> list[Any]:
    values: list[Any] = []
    while True:
        action = _prompt_number_choice(
            f"{context}: concat に追加する要素を選択",
            [
                ChoiceOption(label="列参照を追加", value="field"),
                ChoiceOption(label="固定文字列を追加", value="literal"),
                ChoiceOption(label="終了", value="done"),
            ],
            default_index=1,
        )
        if action == "done":
            break
        if action == "field":
            values.append(
                _prompt_field_reference(
                    message=f"{context}: 参照する列を番号で選択",
                    input_name=input_name,
                    input_columns=input_columns,
                    derived_names=derived_names,
                    default_source=None,
                )
            )
        else:
            values.append(_prompt_text(f"{context}: 固定文字列", ""))
    if not values:
        raise ConfigError(f"{context}: concat の要素がありません")
    return values


def _prompt_map_rule(
    *,
    context: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
) -> dict[str, Any]:
    source = _prompt_field_reference(
        message=f"{context}: map の元になる列を番号で選択",
        input_name=input_name,
        input_columns=input_columns,
        derived_names=derived_names,
        default_source=None,
    )
    value_count = _prompt_int(f"{context}: 変換表の件数", 2)
    values: dict[str, Any] = {}
    for index in range(1, value_count + 1):
        source_value = _prompt_text(f"{context}: 元の値 {index}", "")
        mapped_value = _prompt_text(f"{context}: 変換後の値 {index}", "")
        values[source_value] = mapped_value
    has_default = _prompt_number_choice(
        f"{context}: default を設定しますか？",
        [
            ChoiceOption(label="設定しない", value=False),
            ChoiceOption(label="設定する", value=True),
        ],
        default_index=1,
    )
    rule: dict[str, Any] = {"source": source, "values": values}
    if has_default:
        rule["default"] = _prompt_text(f"{context}: default 値", "")
    return rule


def _prompt_when_rules(
    *,
    context: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
) -> dict[str, Any]:
    item_count = _prompt_int(f"{context}: when 条件の件数", 1)
    rules: list[dict[str, Any]] = []
    for index in range(1, item_count + 1):
        condition = _prompt_condition_rule(
            context=f"{context}: 条件 {index}",
            input_name=input_name,
            input_columns=input_columns,
            derived_names=derived_names,
        )
        then_value = _prompt_text(f"{context}: then {index}", "")
        rules.append({"if": condition, "then": then_value})
    has_default = _prompt_number_choice(
        f"{context}: default を設定しますか？",
        [
            ChoiceOption(label="設定しない", value=False),
            ChoiceOption(label="設定する", value=True),
        ],
        default_index=1,
    )
    rule: dict[str, Any] = {"when": rules}
    if has_default:
        rule["default"] = _prompt_text(f"{context}: default 値", "")
    return rule


def _prompt_lookup_rule(
    *,
    context: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    reference_specs: list[ReferenceSpec],
    derived_names: list[str],
) -> dict[str, Any]:
    if not reference_specs:
        raise ConfigError(f"{context}: lookup を使うには reference CSV が必要です")
    reference_name = _prompt_number_choice(
        f"{context}: 参照CSVを番号で選択",
        [ChoiceOption(label=spec.name, value=spec.name) for spec in reference_specs],
        default_index=1,
    )
    reference_spec = next(spec for spec in reference_specs if spec.name == reference_name)
    key_refs = _prompt_field_references(
        message=f"{context}: lookup.key を番号で選択",
        input_name=input_name,
        input_columns=input_columns,
        derived_names=derived_names,
        default_indices=[1],
    )
    value_field = _prompt_number_choice(
        f"{context}: lookup.value を番号で選択",
        [
            ChoiceOption(label=f"{column.index}. {column.header}", value=column.header)
            for column in reference_spec.columns
        ],
        default_index=1,
    )
    on_missing = _prompt_number_choice(
        f"{context}: on_missing を選択",
        [
            ChoiceOption(label="error", value="error"),
            ChoiceOption(label="default", value="default"),
            ChoiceOption(label="empty", value="empty"),
            ChoiceOption(label="null", value="null"),
        ],
        default_index=1,
    )
    rule: dict[str, Any] = {
        "reference": reference_name,
        "key": key_refs[0] if len(key_refs) == 1 else key_refs,
        "value": value_field,
        "on_missing": on_missing,
    }
    if on_missing == "default":
        rule["default"] = _prompt_text(f"{context}: lookup.default", "")
    return rule


def _prompt_validations(
    *,
    input_name: str,
    input_columns: list[ColumnPreview],
    output_columns: list[str],
) -> dict[str, list[dict[str, Any]]]:
    typer.echo("")
    typer.echo("validations を設定します。")
    input_validations = _prompt_input_validations(
        input_name=input_name,
        input_columns=input_columns,
    )
    output_validations = _prompt_output_validations(output_columns=output_columns)
    return {"input": input_validations, "output": output_validations}


def _prompt_input_validations(
    *,
    input_name: str,
    input_columns: list[ColumnPreview],
) -> list[dict[str, Any]]:
    count = _prompt_int("validations.input をいくつ追加しますか？", 0)
    validations: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        typer.echo("")
        typer.echo(f"validations.input {index}")
        typer.echo("  入力列の validation を追加します。")
        options = []
        for column_index, column in enumerate(input_columns, start=1):
            options.append(
                ChoiceOption(
                    label=fill(
                        f"{column_index}. {input_name}.{column.safe_field} (CSV: {column.header})",
                        width=96,
                        subsequent_indent="    ",
                    ),
                    value=column,
                )
            )
        selected = _prompt_number_choice(
            "  対象列を番号で選択",
            options,
            default_index=1,
            help_text="1件だけ選びます。",
        )
        field = f"{input_name}.{selected.safe_field}"
        rule = _prompt_validation_rule(context=f"validations.input[{index}]")
        validations.append({"field": field, **rule})
    return validations


def _prompt_output_validations(*, output_columns: list[str]) -> list[dict[str, Any]]:
    count = _prompt_int("validations.output をいくつ追加しますか？", 0)
    validations: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        typer.echo("")
        typer.echo(f"validations.output {index}")
        typer.echo("  出力列の validation を追加します。")
        options = [
            ChoiceOption(
                label=fill(f"{column_index}. {column_name}", width=96, subsequent_indent="    "),
                value=column_name,
            )
            for column_index, column_name in enumerate(output_columns, start=1)
        ]
        selected = _prompt_number_choice(
            "  対象列を番号で選択",
            options,
            default_index=1,
            help_text="1件だけ選びます。",
        )
        rule = _prompt_validation_rule(context=f"validations.output[{index}]")
        validations.append({"field": selected, **rule})
    return validations


def _prompt_validation_rule(*, context: str) -> dict[str, Any]:
    rule_type = _prompt_number_choice(
        f"{context}: rule を選択",
        [
            ChoiceOption(label="required", value="required"),
            ChoiceOption(label="enum", value="enum"),
            ChoiceOption(label="min", value="min"),
            ChoiceOption(label="max", value="max"),
            ChoiceOption(label="regex", value="regex"),
            ChoiceOption(label="length", value="length"),
        ],
        default_index=1,
    )
    if rule_type == "required":
        return {"rule": rule_type}
    if rule_type == "enum":
        return {"rule": rule_type, "values": _prompt_value_list(f"{context}: enum の値")}
    if rule_type in {"min", "max"}:
        return {"rule": rule_type, "value": _prompt_required_int(f"{context}: {rule_type} の値")}
    if rule_type == "regex":
        return {"rule": rule_type, "pattern": _prompt_optional_text(f"{context}: pattern", "")}
    rule: dict[str, Any] = {"rule": rule_type}
    min_value = _prompt_optional_int(f"{context}: length の min")
    max_value = _prompt_optional_int(f"{context}: length の max")
    if min_value is not None:
        rule["min"] = min_value
    if max_value is not None:
        rule["max"] = max_value
    return rule


def _prompt_filters(
    *,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_specs: list[DerivedSpec],
) -> dict[str, list[dict[str, Any]]]:
    typer.echo("")
    typer.echo("filters を設定します。")
    derived_names = [spec.name for spec in derived_specs]
    include = _prompt_filter_entries(
        context="filters.include",
        input_name=input_name,
        input_columns=input_columns,
        derived_names=derived_names,
        label="include",
    )
    exclude = _prompt_filter_entries(
        context="filters.exclude",
        input_name=input_name,
        input_columns=input_columns,
        derived_names=derived_names,
        label="exclude",
    )
    return {"include": include, "exclude": exclude}


def _prompt_filter_entries(
    *,
    context: str,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
    label: str,
) -> list[dict[str, Any]]:
    count = _prompt_int(f"{context} をいくつ追加しますか？", 0)
    filters: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        typer.echo("")
        typer.echo(f"{context} {index}")
        typer.echo("  参照候補:")
        for line in _format_reference_candidates(input_name, input_columns, derived_names):
            typer.echo(f"  {line}")
        condition = _prompt_condition_rule(
            context=f"{label}.if",
            input_name=input_name,
            input_columns=input_columns,
            derived_names=derived_names,
        )
        reason = _prompt_optional_text(f"  {label}.reason", "")
        item: dict[str, Any] = {"if": condition}
        if reason:
            item["reason"] = reason
        filters.append(item)
    return filters


def _prompt_checks(
    *,
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_specs: list[DerivedSpec],
) -> list[dict[str, Any]]:
    typer.echo("")
    typer.echo("checks を設定します。")
    count = _prompt_int("checks をいくつ追加しますか？", 0)
    checks: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        typer.echo("")
        typer.echo(f"check {index}")
        name = _prompt_text("  check 名", f"check_{index}")
        typer.echo("  summary 変数: input_rows, output_rows, error_rows, skipped_rows")
        rule = _prompt_check_rule(
            context="  rule",
        )
        checks.append({"name": name, "rule": rule})
    return checks


def _prompt_input_schema_overrides(
    *,
    input_name: str,
    input_columns: list[ColumnPreview],
) -> list[SchemaOverrideSpec]:
    typer.echo("")
    typer.echo("input schema を設定します。")
    override_count = _prompt_int("schema を変更する列はいくつありますか？", 0)
    overrides: list[SchemaOverrideSpec] = []
    used_fields: set[str] = set()
    for index in range(1, override_count + 1):
        typer.echo("")
        typer.echo(f"schema {index}")
        options = [
            ChoiceOption(
                label=fill(
                    f"{column.index}. {input_name}.{column.safe_field} (CSV: {column.header})",
                    width=96,
                    subsequent_indent="    ",
                ),
                value=column,
            )
            for column in input_columns
            if column.safe_field not in used_fields
        ]
        if not options:
            raise ConfigError("schema を変更できる列がありません")
        selected = _prompt_number_choice(
            "  対象列を番号で選択",
            options,
            default_index=1,
            help_text="1件だけ選びます。",
        )
        used_fields.add(selected.safe_field)
        field_overrides = _prompt_schema_field_overrides(
            context=f"inputs.{input_name}.schema.{selected.safe_field}",
        )
        overrides.append(SchemaOverrideSpec(field=selected.safe_field, values=field_overrides))
    return overrides


def _build_default_schema_field(column: ColumnPreview) -> dict[str, Any]:
    return {
        "source_columns": [column.header],
        "type": "string",
        "required": False,
        "normalize": ["trim"],
    }


def _prompt_schema_field_overrides(*, context: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    values["type"] = _prompt_number_choice(
        f"{context}: type を選択",
        [
            ChoiceOption(label="string", value="string"),
            ChoiceOption(label="integer", value="integer"),
            ChoiceOption(label="decimal", value="decimal"),
            ChoiceOption(label="boolean", value="boolean"),
            ChoiceOption(label="date", value="date"),
        ],
        default_index=1,
    )
    values["required"] = _prompt_number_choice(
        f"{context}: required を選択",
        [
            ChoiceOption(label="false", value=False),
            ChoiceOption(label="true", value=True),
        ],
        default_index=1,
    )
    normalize_values = _prompt_number_choices(
        f"{context}: normalize を選択",
        [
            ChoiceOption(label="trim", value="trim"),
            ChoiceOption(label="remove_commas", value="remove_commas"),
            ChoiceOption(label="remove_currency_symbol", value="remove_currency_symbol"),
        ],
        default_indices=[1],
        help_text="複数選択は 1,2 のように入力できます。Enter で trim を使います。",
    )
    values["normalize"] = normalize_values
    if values["type"] == "boolean":
        true_values = _prompt_optional_value_list(f"{context}: true_values")
        false_values = _prompt_optional_value_list(f"{context}: false_values")
        if true_values:
            values["true_values"] = true_values
        if false_values:
            values["false_values"] = false_values
    return values


def _prompt_optional_value_list(message: str) -> list[Any]:
    count = _prompt_int(f"{message} の件数", 0)
    values: list[Any] = []
    for index in range(1, count + 1):
        values.append(_prompt_optional_text(f"{message} {index}", ""))
    return values


def _prompt_output_settings(*, output_name: str) -> dict[str, Any]:
    typer.echo("")
    typer.echo("output 設定を確認します。")
    if_exists = _prompt_number_choice(
        f"  {output_name}.if_exists を選択",
        [
            ChoiceOption(label="error", value="error"),
            ChoiceOption(label="overwrite", value="overwrite"),
        ],
        default_index=1,
    )
    newline = _prompt_number_choice(
        f"  {output_name}.newline を選択",
        [
            ChoiceOption(label="LF (\\n)", value="\n"),
            ChoiceOption(label="CRLF (\\r\\n)", value="\r\n"),
        ],
        default_index=1,
    )
    return {
        "if_exists": if_exists,
        "newline": newline,
    }


def _prompt_error_handling_settings() -> dict[str, Any]:
    typer.echo("")
    typer.echo("error_handling を設定します。")
    on_validation_error = _prompt_number_choice(
        "  on_validation_error を選択",
        [
            ChoiceOption(label="output_error", value="output_error"),
            ChoiceOption(label="stop", value="stop"),
        ],
        default_index=1,
    )
    on_lookup_missing = _prompt_number_choice(
        "  on_lookup_missing を選択",
        [
            ChoiceOption(label="output_error", value="output_error"),
            ChoiceOption(label="stop", value="stop"),
        ],
        default_index=1,
    )
    on_transform_error = _prompt_number_choice(
        "  on_transform_error を選択",
        [
            ChoiceOption(label="output_error", value="output_error"),
            ChoiceOption(label="stop", value="stop"),
        ],
        default_index=1,
    )
    max_errors = _prompt_int("  max_errors", 1000)
    error_output = _prompt_text("  error_output", "./reports/errors.csv")
    skipped_output = _prompt_text("  skipped_output", "./reports/skipped.csv")
    include_original_row = _prompt_number_choice(
        "  include_original_row を選択",
        [
            ChoiceOption(label="true", value=True),
            ChoiceOption(label="false", value=False),
        ],
        default_index=1,
    )
    return {
        "on_validation_error": on_validation_error,
        "on_lookup_missing": on_lookup_missing,
        "on_transform_error": on_transform_error,
        "max_errors": max_errors,
        "error_output": error_output,
        "skipped_output": skipped_output,
        "include_original_row": include_original_row,
    }


def _prompt_runtime_settings() -> dict[str, Any]:
    typer.echo("")
    typer.echo("runtime を設定します。")
    run_id = _prompt_text("  run_id", "auto")
    log_dir = _prompt_text("  log_dir", "./logs")
    log_level = _prompt_number_choice(
        "  log_level を選択",
        [
            ChoiceOption(label="DEBUG", value="DEBUG"),
            ChoiceOption(label="INFO", value="INFO"),
            ChoiceOption(label="WARNING", value="WARNING"),
            ChoiceOption(label="ERROR", value="ERROR"),
        ],
        default_index=2,
    )
    summary_output = _prompt_text("  summary_output", "./reports/summary.json")
    return {
        "run_id": run_id,
        "log_dir": log_dir,
        "log_level": log_level,
        "summary_output": summary_output,
    }


def _format_reference_candidates(
    input_name: str,
    input_columns: list[ColumnPreview],
    derived_names: list[str],
) -> list[str]:
    lines = [f"{input_name}.{column.safe_field} (CSV: {column.header})" for column in input_columns]
    lines.extend(f"derived.{name}" for name in derived_names)
    return lines


def _prompt_value_list(message: str) -> list[Any]:
    count = _prompt_int(f"{message} の件数", 2)
    values: list[Any] = []
    for index in range(1, count + 1):
        values.append(_prompt_optional_text(f"{message} {index}", ""))
    return values


def _prompt_required_int(message: str) -> int:
    value = _prompt_optional_text(message, "")
    if value == "":
        raise ConfigError(f"{message}: 数字を入力してください")
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{message}: 数字で入力してください") from exc


def _prompt_optional_int(message: str) -> int | None:
    value = _prompt_optional_text(message, "")
    if value == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{message}: 数字で入力してください") from exc


def _prompt_optional_text(message: str, default: str) -> str:
    value = str(typer.prompt(message, default=default)).strip()
    return value


def _prompt_int(message: str, default: int, *, attempts: int = MAX_PROMPT_ATTEMPTS) -> int:
    last_error: str | None = None
    for _ in range(attempts):
        value = str(typer.prompt(message, default=str(default))).strip()
        if not value:
            value = str(default)
        try:
            return int(value)
        except ValueError:
            last_error = f"{message}: 数字で入力してください。例: {default}"
            typer.echo(last_error)
    raise ConfigError(last_error or f"{message}: invalid input")


def _prompt_number_choices(
    message: str,
    options: list[ChoiceOption],
    default_indices: list[int],
    help_text: str | None = None,
    *,
    attempts: int = MAX_PROMPT_ATTEMPTS,
) -> list[Any]:
    if not options:
        raise ConfigError(f"{message}: 選択肢がありません")

    default_text = ",".join(str(index) for index in default_indices)
    last_error: str | None = None
    for _ in range(attempts):
        typer.echo(message)
        if help_text:
            typer.echo(f"  {help_text}")
        for index, option in enumerate(options, start=1):
            typer.echo(f"  {index}. {option.label}")
        value = str(typer.prompt("番号を入力してください", default=default_text)).strip()
        if not value:
            value = default_text
        try:
            selected_indices = _parse_number_selection(value, total=len(options))
        except ConfigError as exc:
            last_error = str(exc)
            typer.echo(last_error)
            continue
        return [options[index - 1].value for index in selected_indices]
    raise ConfigError(last_error or f"{message}: invalid input")


def _format_column_preview_list(title: str, columns: list[ColumnPreview]) -> str:
    lines = [title]
    for column in columns:
        sample = f" [sample: {column.sample_text}]" if column.sample_text != "(なし)" else ""
        lines.append(f"  {column.index}. {column.header} ({column.safe_field}){sample}")
    return "\n".join(lines)
