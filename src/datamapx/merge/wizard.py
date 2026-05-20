"""Interactive merge config generator."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
import yaml
from pydantic import ValidationError

from datamapx.exceptions import ConfigError
from datamapx.merge.config import MergeConfig

SAFE_HEADER_RE = re.compile(r"^[A-Za-z0-9 _-]+$")
MAX_PROMPT_ATTEMPTS = 3
DEFAULT_SAMPLE_LIMIT = 3

MERGE_RULE_TYPES = ["source", "first", "last", "sum", "min", "max", "count"]
MERGE_RULE_HELP = {
    "source": "1つの入力列をそのまま使う",
    "first": "候補の先頭にある値を使う",
    "last": "候補の最後にある値を使う",
    "sum": "数値を合計する",
    "min": "最小値を使う",
    "max": "最大値を使う",
    "count": "件数を数える",
}
MERGE_PURPOSES = [
    ("横に結合したい", "source"),
    ("列を補完したい", "first"),
    ("数値を合算したい", "sum"),
]

PURPOSE_GUIDANCE = {
    "source": "そのまま使う列を中心に、横に並べたいときに向いています。",
    "first": "候補の先頭から値を採用したいときに向いています。",
    "sum": "数値を合算したいときに向いています。",
}


@dataclass(frozen=True)
class MergeWizardResult:
    """Result of generating a merge YAML file."""

    config_path: Path
    project_name: str
    input_count: int
    output_columns: list[str]


@dataclass(frozen=True)
class ColumnPreview:
    """A column shown in the wizard."""

    header: str
    safe_field: str
    samples: list[str]

    @property
    def sample_text(self) -> str:
        if not self.samples:
            return "(sampleなし)"
        return ", ".join(self.samples)


@dataclass(frozen=True)
class MergeInputSpec:
    """Input CSV metadata gathered by the wizard."""

    name: str
    path: str
    columns: list[ColumnPreview]
    key: list[str]

    @property
    def headers(self) -> list[str]:
        return [column.header for column in self.columns]

    @property
    def safe_fields(self) -> list[str]:
        return [column.safe_field for column in self.columns]


@dataclass(frozen=True)
class ChoiceOption:
    """A numbered option shown to the user."""

    label: str
    value: str


@dataclass(frozen=True)
class OutputColumnSpec:
    """An output column selected or added in the wizard."""

    name: str
    references: list[str]
    is_manual: bool = False


def run_merge_wizard() -> MergeWizardResult:
    """Interactively build and write a merge config YAML file."""

    typer.echo(
        "merge-wizard は、複数CSVをまとめるための merge.yml を対話式で作成します。"
    )
    typer.echo("CSVを先に用意しておくと、列名とサンプル値を見ながら選べます。")
    typer.echo("選択は番号で行い、YAMLを知らなくても進められるようにしています。")
    typer.echo("最後にレビューを確認してから保存します。")
    typer.echo("")

    default_rule_type = _prompt_number_choice(
        "1/6. 最初にやりたいことを番号で選択",
        [ChoiceOption(label=label, value=value) for label, value in MERGE_PURPOSES],
        default_index=1,
        help_text=(
            "横に結合したい / 列を補完したい / 数値を合算したい の3つから選びます。"
        ),
    )
    purpose_label = next(
        label for label, value in MERGE_PURPOSES if value == default_rule_type
    )
    purpose_text = PURPOSE_GUIDANCE[default_rule_type]

    typer.echo("")
    typer.echo("2/6. Project and paths")
    project_name = _prompt_text("プロジェクト名", "generated_merge")
    config_path = Path(_prompt_text("merge.yml の保存先", "./merge.yml"))
    output_path = _prompt_text("結合後CSV(staging) の出力先", "./output/merged.csv")

    if config_path.exists():
        if not typer.confirm(f"{config_path} exists. Overwrite?", default=False):
            raise ConfigError(f"{config_path}: merge.yml が既に存在します")

    typer.echo("")
    typer.echo("3/6. Inputs")
    input_count = _prompt_int("入力CSVファイルはいくつありますか？", 2)
    if input_count < 2:
        raise ConfigError("merge-wizard では入力CSVが2つ以上必要です")

    input_specs: list[MergeInputSpec] = []
    for index in range(1, input_count + 1):
        typer.echo("")
        typer.echo(f"入力{index}")
        input_name = _prompt_text("  論理名", f"input_{index}")
        input_csv_path = _prompt_text(
            "  CSVファイルパス",
            f"./input/{input_name}.csv",
        )
        columns = _read_csv_preview(Path(input_csv_path))
        typer.echo(_format_input_preview(input_name, columns))
        key_fields = _prompt_number_choices(
            f"  {input_name} のキー列を番号で選択 (カンマ区切り)",
            [
                ChoiceOption(
                    label=_format_column_option(input_name, column),
                    value=column.safe_field,
                )
                for column in _prioritize_columns(columns)
            ],
            default_indices=[1],
            help_text="列番号を 1,2 のように入力してください",
        )
        input_specs.append(
            MergeInputSpec(
                name=input_name,
                path=input_csv_path,
                columns=columns,
                key=key_fields,
            )
        )

    typer.echo("")
    typer.echo("4/6. Merge policy")
    base_input = _prompt_number_choice(
        "基準にする入力を番号で選択",
        [ChoiceOption(label=spec.name, value=spec.name) for spec in input_specs],
        default_index=1,
        help_text="基準にするCSVを選びます。",
    )
    join_type = _prompt_number_choice(
        "結合方法を番号で選択",
        [
            ChoiceOption(label="left", value="left"),
            ChoiceOption(label="inner", value="inner"),
        ],
        default_index=1,
        help_text="left = 基準CSVを残す / inner = 両方にある行だけ残す",
    )

    reference_candidates = _build_reference_candidates(input_specs)
    base_default_references = _default_merge_references(input_specs, base_input)

    typer.echo("")
    typer.echo("5/6. Output columns")
    typer.echo("出力列は番号で選びます。基準CSVの列が最初から選ばれています。")
    typer.echo("候補:")
    for index, option in enumerate(reference_candidates, start=1):
        typer.echo(
            f"  {index}. {option.label}"
        )

    output_specs = _prompt_output_columns(
        reference_candidates,
        base_default_references,
    )
    output_specs = _prompt_output_column_renames(
        output_specs,
        reference_candidates,
    )
    if not output_specs:
        raise ConfigError("merge-wizard では出力列が1つ以上必要です")

    output_columns = [spec.name for spec in output_specs]
    output_defaults = {spec.name: spec.references for spec in output_specs}
    merge_columns: dict[str, dict[str, Any]] = {}
    while True:
        merge_columns = _prompt_merge_column_rules(
            output_specs,
            output_defaults,
            reference_candidates,
            base_input,
            default_rule_type,
        )

        config_data = {
            "version": 1,
            "project": {
                "name": project_name,
                "description": "merge-wizard で生成した merge.yml",
            },
            "inputs": {
                spec.name: {
                    "path": spec.path,
                    "encoding": "utf-8-sig",
                    "delimiter": ",",
                    "header": True,
                    "schema": {
                        column.safe_field: {
                            "source_columns": [column.header],
                            "type": "string",
                            "required": False,
                            "normalize": ["trim"],
                        }
                        for column in spec.columns
                    },
                    "key": spec.key[0] if len(spec.key) == 1 else spec.key,
                }
                for spec in input_specs
            },
            "merge": {
                "base": base_input,
                "join_type": join_type,
                "columns": merge_columns,
            },
            "output": {
                "path": output_path,
                "encoding": "utf-8-sig",
                "delimiter": ",",
                "header": True,
                "newline": "\n",
                "if_exists": "overwrite",
                "columns": output_columns,
            },
            "error_handling": {
                "on_validation_error": "output_error",
                "on_lookup_missing": "output_error",
                "on_transform_error": "output_error",
                "max_errors": 1000,
                "error_output": "./reports/errors.csv",
                "skipped_output": "./reports/skipped.csv",
                "include_original_row": True,
            },
            "runtime": {
                "run_id": "auto",
                "log_dir": "./logs",
                "log_level": "INFO",
                "summary_output": "./reports/summary.json",
            },
        }

        try:
            MergeConfig.model_validate(config_data)
        except ValidationError as exc:
            raise ConfigError(_format_validation_error(config_path, exc)) from exc

        review_text = _format_review(
            purpose_label,
            purpose_text,
            project_name,
            base_input,
            join_type,
            input_specs,
            output_columns,
            merge_columns,
        )
        typer.echo("")
        typer.echo("Review")
        typer.echo(review_text)
        review_action = _prompt_number_choice(
            "保存前の操作を番号で選択",
            [
                ChoiceOption(
                    label="この内容で merge.yml を作成する",
                    value="save",
                ),
                ChoiceOption(
                    label="列ルールだけやり直す",
                    value="redo",
                ),
                ChoiceOption(label="中止する", value="cancel"),
            ],
            default_index=1,
            help_text="1=保存 / 2=列ルールだけやり直す / 3=中止",
        )
        if review_action == "redo":
            typer.echo("列ルールをやり直します。")
            continue
        if review_action == "cancel":
            raise ConfigError("merge-wizard を中止しました")
        break

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_text = yaml.safe_dump(
            config_data,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            indent=2,
            width=1000,
        )
        config_path.write_text(config_text, encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"{config_path}: merge.yml を書き込めません: {exc}") from exc

    typer.echo("")
    typer.echo("YAML を保存しました。")
    typer.echo(f"保存先: {config_path}")
    typer.echo(f"プロジェクト名: {project_name}")
    typer.echo(f"入力CSV数: {input_count}")
    typer.echo(f"出力列: {', '.join(output_columns)}")

    return MergeWizardResult(
        config_path=config_path,
        project_name=project_name,
        input_count=input_count,
        output_columns=output_columns,
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


def _prompt_int(message: str, default: int, *, attempts: int = MAX_PROMPT_ATTEMPTS) -> int:
    last_error: str | None = None
    for _ in range(attempts):
        value = typer.prompt(message, default=default)
        try:
            return int(value)
        except (TypeError, ValueError):
            last_error = f"{message}: 整数で入力してください。例: 2"
            typer.echo(last_error)
    raise ConfigError(last_error or f"{message}: 整数で入力してください。例: 2")


def _prompt_number_choice(
    message: str,
    options: list[ChoiceOption],
    default_index: int,
    help_text: str | None = None,
    *,
    attempts: int = MAX_PROMPT_ATTEMPTS,
) -> str:
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
        parsed, error_message = _parse_number_selection(value, len(options), message)
        if parsed is None:
            last_error = error_message
            typer.echo(last_error)
            continue
        if len(parsed) != 1:
            last_error = f"{message}: 1つだけ選択してください。例: {default_index}"
            typer.echo(last_error)
            continue
        return options[parsed[0] - 1].value
    raise ConfigError(last_error or f"{message}: 1つだけ選択してください。例: {default_index}")


def _prompt_number_choices(
    message: str,
    options: list[ChoiceOption],
    default_indices: list[int] | None = None,
    help_text: str | None = None,
    *,
    attempts: int = MAX_PROMPT_ATTEMPTS,
) -> list[str]:
    if not options:
        raise ConfigError(f"{message}: 選択肢がありません")

    default_text = None
    if default_indices:
        default_text = ",".join(str(index) for index in default_indices)
    prompt_default = default_text or "1"

    last_error: str | None = None
    for _ in range(attempts):
        typer.echo(message)
        if help_text:
            typer.echo(f"  {help_text}")
        for index, option in enumerate(options, start=1):
            typer.echo(f"  {index}. {option.label}")
        value = str(typer.prompt("番号を入力してください", default=prompt_default)).strip()
        parsed, error_message = _parse_number_selection(value, len(options), message)
        if parsed is not None:
            return [options[index - 1].value for index in parsed]
        last_error = error_message
        typer.echo(last_error)
    raise ConfigError(
        last_error
        or f"{message}: 1 から {len(options)} の範囲で番号を入力してください"
    )


def _parse_number_selection(
    value: str,
    option_count: int,
    message: str,
) -> tuple[list[int] | None, str | None]:
    if not value:
        return None, f"{message}: 番号を入力してください。既定値を使う場合は Enter を押してください"
    indices: list[int] = []
    seen: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            index = int(item)
        except ValueError:
            return None, f"{message}: 数字で入力してください。例: 1 または 1,3"
        if index < 1 or index > option_count:
            return (
                None,
                f"{message}: 選べる番号は 1 から {option_count} です。入力値: {index}",
            )
        if index not in seen:
            indices.append(index)
            seen.add(index)
    if not indices:
        return None, f"{message}: 番号を入力してください。既定値を使う場合は Enter を押してください"
    return indices, None


def _prompt_list(message: str, default: str, *, attempts: int = MAX_PROMPT_ATTEMPTS) -> list[str]:
    last_error: str | None = None
    for _ in range(attempts):
        value = str(typer.prompt(message, default=default)).strip()
        if value:
            return [item.strip() for item in value.split(",") if item.strip()]
        last_error = f"{message}: 空では登録できません。値を入力してください"
        typer.echo(last_error)
    raise ConfigError(last_error or f"{message}: 空では登録できません。値を入力してください")


def _prompt_optional_list(
    message: str,
    default: str = "",
    *,
    attempts: int = MAX_PROMPT_ATTEMPTS,
) -> list[str]:
    value = str(typer.prompt(message, default=default)).strip()
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _read_csv_preview(path: Path, sample_limit: int = DEFAULT_SAMPLE_LIMIT) -> list[ColumnPreview]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file, delimiter=",")
            headers = next(reader, None)
            if headers is None:
                raise ConfigError(f"{path}: input CSV is empty")
            if not headers:
                raise ConfigError(f"{path}: input CSV header row is empty")
            safe_fields = _build_safe_field_names([str(header) for header in headers])
            previews = [
                ColumnPreview(header=str(header), safe_field=safe_field, samples=[])
                for header, safe_field in zip(headers, safe_fields, strict=True)
            ]
            for row in reader:
                for index, preview in enumerate(previews):
                    if len(preview.samples) >= sample_limit:
                        continue
                    if index >= len(row):
                        continue
                    value = str(row[index]).strip()
                    if value:
                        preview.samples.append(value)
                if all(len(preview.samples) >= sample_limit for preview in previews):
                    break
            return previews
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read input CSV: {exc}") from exc


def _build_safe_field_names(headers: list[str]) -> list[str]:
    safe_names: list[str] = []
    used: set[str] = set()
    generated_index = 1
    for header in headers:
        safe_name = _safe_field_name_from_header(header)
        if safe_name is None:
            safe_name = f"col_{generated_index:03d}"
            generated_index += 1
        safe_name = _deduplicate_name(safe_name, used)
        used.add(safe_name)
        safe_names.append(safe_name)
    return safe_names


def _safe_field_name_from_header(header: str) -> str | None:
    candidate = header.strip()
    if not candidate:
        return None
    if not SAFE_HEADER_RE.fullmatch(candidate):
        return None
    candidate = candidate.lower()
    candidate = re.sub(r"[\s\-]+", "_", candidate)
    candidate = re.sub(r"[^0-9a-z_]+", "", candidate)
    candidate = re.sub(r"_+", "_", candidate).strip("_")
    if not candidate:
        return None
    if candidate[0].isdigit():
        candidate = f"col_{candidate}"
    return candidate


def _deduplicate_name(name: str, used: set[str]) -> str:
    if name not in used:
        return name
    suffix = 2
    while f"{name}_{suffix}" in used:
        suffix += 1
    return f"{name}_{suffix}"


def _prioritize_columns(columns: list[ColumnPreview]) -> list[ColumnPreview]:
    def sort_key(column: ColumnPreview) -> tuple[int, int, str]:
        text = f"{column.header} {column.safe_field}".lower()
        score = 0
        if any(token in text for token in ("id", "code", "no", "number", "番号", "コード")):
            score -= 10
        if any(token in text for token in ("name", "name__r", "name__c", "名")):
            score -= 5
        if any(token in text for token in ("amount", "price", "total", "金額", "合計")):
            score -= 4
        return (score, len(column.header), column.safe_field)

    return sorted(columns, key=sort_key)


def _build_reference_candidates(input_specs: list[MergeInputSpec]) -> list[ChoiceOption]:
    return [
        ChoiceOption(
            label=_format_reference_option(
                ChoiceOption(
                    label=_format_column_option(spec.name, column),
                    value=f"{spec.name}.{column.safe_field}",
                )
            ),
            value=f"{spec.name}.{column.safe_field}",
        )
        for spec in input_specs
        for column in _prioritize_columns(spec.columns)
    ]


def _prompt_output_columns(
    reference_candidates: list[ChoiceOption],
    base_default_references: list[str],
) -> list[OutputColumnSpec]:
    default_indices = _reference_indices(reference_candidates, base_default_references)
    selected_refs = _prompt_number_choices(
        "出力したい列を番号で選択 (カンマ区切り)",
        reference_candidates,
        default_indices=default_indices,
        help_text="基準CSVの列が既定で選ばれています。必要なら他の入力CSVの列も選べます。",
    )
    if not selected_refs:
        raise ConfigError("merge-wizard では出力列が1つ以上必要です")

    output_specs: list[OutputColumnSpec] = []
    used_names: set[str] = set()
    for reference in selected_refs:
        output_name = _derive_output_column_name(reference, used_names)
        output_specs.append(
            OutputColumnSpec(
                name=output_name,
                references=[reference],
                is_manual=False,
            )
        )
        used_names.add(output_name)

    if typer.confirm("番号で選べない出力列名を追加しますか？", default=False):
        extra_output_columns = _prompt_optional_list(
            "追加したい出力列名 (カンマ区切り)",
            "",
        )
        for output_name in extra_output_columns:
            resolved_name = _deduplicate_name(output_name, used_names)
            output_specs.append(
                OutputColumnSpec(
                    name=resolved_name,
                    references=base_default_references,
                    is_manual=True,
                )
            )
            used_names.add(resolved_name)

    return output_specs


def _prompt_output_column_renames(
    output_specs: list[OutputColumnSpec],
    reference_candidates: list[ChoiceOption],
) -> list[OutputColumnSpec]:
    renamed_output_specs: list[OutputColumnSpec] = []
    used_names: set[str] = set()

    for output_spec in output_specs:
        references = output_spec.references
        reference_text = _format_reference_summary(reference_candidates, references)
        typer.echo("  出力列名の確認")
        typer.echo(f"  元列: {reference_text}")
        typer.echo(f"  現在の出力列名: {output_spec.name}")
        if typer.confirm("  この列名を変更しますか？", default=False):
            new_name = _prompt_text("  新しい出力列名", output_spec.name)
        else:
            new_name = output_spec.name
        resolved_name = _deduplicate_name(new_name, used_names)
        if resolved_name != new_name:
            typer.echo(f"  同じ列名があるため {resolved_name} に変更します")
        renamed_output_specs.append(
            OutputColumnSpec(
                name=resolved_name,
                references=references,
                is_manual=output_spec.is_manual,
            )
        )
        used_names.add(resolved_name)

    return renamed_output_specs


def _prompt_merge_column_rules(
    output_specs: list[OutputColumnSpec],
    output_defaults: dict[str, list[str]],
    reference_candidates: list[ChoiceOption],
    base_input: str,
    default_rule_type: str,
) -> dict[str, dict[str, Any]]:
    typer.echo("")
    typer.echo("6/6. Column rules")
    typer.echo("各出力列について、どの入力列を使うかを番号で選びます。")
    merge_columns: dict[str, dict[str, Any]] = {}
    manual_output_columns = {spec.name for spec in output_specs if spec.is_manual}
    use_template = typer.confirm(
        "推奨ルールをまとめて使いますか？",
        default=not manual_output_columns,
    )
    if use_template:
        typer.echo("推奨ルールを適用します。")
        if manual_output_columns:
            typer.echo("手入力した出力列は個別に設定します。")
        merge_columns.update(
            _build_template_merge_columns(
                output_specs,
                base_input,
                default_rule_type,
            )
        )

    for output_column in [spec.name for spec in output_specs]:
        if output_column in merge_columns:
            continue
        rule_type = _prompt_number_choice(
            f"{output_column} の作り方を番号で選択",
            [
                ChoiceOption(label=MERGE_RULE_HELP[rule], value=rule)
                for rule in MERGE_RULE_TYPES
            ],
            default_index=_default_rule_index(default_rule_type),
            help_text=(
                "source=そのまま使う / first=先頭 / last=最後 / "
                "sum=合計 / min=最小 / max=最大 / count=件数"
            ),
        )
        default_refs = output_defaults.get(output_column, [])
        default_indices = _reference_indices(reference_candidates, default_refs)
        if rule_type == "source":
            reference = _prompt_number_choice(
                f"{output_column} に使う元列を番号で選択",
                [
                    ChoiceOption(
                        label=_format_reference_option(option),
                        value=option.value,
                    )
                    for option in reference_candidates
                ],
                default_index=default_indices[0] if default_indices else 1,
                help_text="source は 1つの列をそのまま使います",
            )
            merge_columns[output_column] = {"source": reference}
            continue

        refs_text = _prompt_number_choices(
            f"{output_column} に使う元列を番号で選択 (カンマ区切り)",
            [
                ChoiceOption(
                    label=_format_reference_option(option),
                    value=option.value,
                )
                for option in reference_candidates
            ],
            default_indices=default_indices,
            help_text=(
                "first/last/sum/min/max/count は複数列をまとめて選べます。"
                " 例: 1,3,5"
            ),
        )
        if not refs_text:
            raise ConfigError(f"{output_column}: 少なくとも1つの参照列が必要です")
        merge_columns[output_column] = {rule_type: refs_text}

    return merge_columns


def _build_template_merge_columns(
    output_specs: list[OutputColumnSpec],
    base_input: str,
    purpose: str,
) -> dict[str, dict[str, Any]]:
    merge_columns: dict[str, dict[str, Any]] = {}
    for spec in output_specs:
        if spec.is_manual:
            continue
        merge_columns[spec.name] = _build_template_rule(
            spec.references,
            base_input,
            purpose,
        )
    return merge_columns


def _build_template_rule(
    references: list[str],
    base_input: str,
    purpose: str,
) -> dict[str, Any]:
    if not references:
        raise ConfigError("template requires at least one reference")
    first_reference = references[0]
    if purpose == "source":
        return {"source": first_reference}
    if purpose == "first":
        if first_reference.split(".", 1)[0] == base_input:
            return {"source": first_reference}
        return {"first": references}
    if purpose == "sum":
        return {"sum": references}
    return {"source": first_reference}


def _format_column_option(input_name: str, column: ColumnPreview) -> str:
    return (
        f"{input_name}.{column.safe_field} "
        f"(CSV: {column.header}, sample: {column.sample_text})"
    )


def _format_reference_option(option: ChoiceOption) -> str:
    return option.label


def _format_reference_summary(
    reference_candidates: list[ChoiceOption],
    references: list[str],
) -> str:
    if not references:
        return "(referenceなし)"
    labels: list[str] = []
    for reference in references:
        label = reference
        for option in reference_candidates:
            if option.value == reference:
                label = option.label
                break
        labels.append(label)
    return ", ".join(labels)


def _derive_output_column_name(reference: str, used_names: set[str]) -> str:
    input_name, field_name = reference.split(".", 1)
    candidate = field_name
    if candidate in used_names:
        candidate = f"{input_name}_{field_name}"
    return _deduplicate_name(candidate, used_names)


def _format_input_preview(input_name: str, columns: list[ColumnPreview]) -> str:
    lines = [f"{input_name} fields:"]
    for index, column in enumerate(columns, start=1):
        lines.append(
            f"- {index}. {column.safe_field} (CSV: {column.header}, sample: {column.sample_text})"
        )
    return "\n".join(lines)


def _default_merge_references(input_specs: list[MergeInputSpec], base_input: str) -> list[str]:
    base_spec = next(spec for spec in input_specs if spec.name == base_input)
    return [f"{base_input}.{field_name}" for field_name in base_spec.safe_fields[:1]]


def _reference_indices(
    reference_candidates: list[ChoiceOption],
    references: list[str],
) -> list[int]:
    indices: list[int] = []
    for reference in references:
        for index, option in enumerate(reference_candidates, start=1):
            if option.value == reference:
                indices.append(index)
                break
    return indices


def _format_review(
    purpose_label: str,
    purpose_text: str,
    project_name: str,
    base_input: str,
    join_type: str,
    input_specs: list[MergeInputSpec],
    output_columns: list[str],
    merge_columns: dict[str, dict[str, Any]],
) -> str:
    return _format_natural_review(
        purpose_label,
        purpose_text,
        project_name,
        base_input,
        join_type,
        input_specs,
        output_columns,
        merge_columns,
    )


def _default_rule_index(default_rule_type: str) -> int:
    try:
        return MERGE_RULE_TYPES.index(default_rule_type) + 1
    except ValueError:
        return 1


def _format_natural_review(
    purpose_label: str,
    purpose_text: str,
    project_name: str,
    base_input: str,
    join_type: str,
    input_specs: list[MergeInputSpec],
    output_columns: list[str],
    merge_columns: dict[str, dict[str, Any]],
) -> str:
    reference_labels = {
        f"{spec.name}.{column.safe_field}": (
            f"{spec.name}.{column.safe_field} (CSV: {column.header})"
        )
        for spec in input_specs
        for column in spec.columns
    }
    lines = [
        "この設定で行うこと",
        f"- {project_name} では {purpose_label} を行います。",
        f"- {purpose_text}",
        f"- {base_input} を基準にして、{_join_type_to_japanese(join_type)}結合します。",
        "",
        "使用するCSV",
    ]
    for spec in input_specs:
        lines.append(
            f"- {spec.name}: キーは {', '.join(spec.key)} です。"
            f" ファイルは {spec.path} です。"
        )
    lines.extend(
        [
            "",
            "出力する列",
        ]
    )
    for output_column in output_columns:
        lines.append(
            f"- {output_column}: "
            f"{_format_natural_rule(merge_columns[output_column], reference_labels)}"
        )
    return "\n".join(lines)


def _format_natural_rule(
    rule: dict[str, Any],
    reference_labels: dict[str, str],
) -> str:
    rule_name = next(iter(rule))
    references = rule[rule_name]
    if isinstance(references, list):
        reference_text = " と ".join(
            _format_natural_reference(reference, reference_labels) for reference in references
        )
    else:
        reference_text = _format_natural_reference(str(references), reference_labels)

    return {
        "source": f"{reference_text} をそのまま使います。",
        "first": f"{reference_text} の先頭の値を使います。",
        "last": f"{reference_text} の最後の値を使います。",
        "sum": f"{reference_text} を合計します。",
        "min": f"{reference_text} の最小値を使います。",
        "max": f"{reference_text} の最大値を使います。",
        "count": f"{reference_text} の件数を数えます。",
    }.get(rule_name, f"{rule_name} -> {reference_text}")


def _format_natural_reference(reference: str, reference_labels: dict[str, str]) -> str:
    return reference_labels.get(reference, reference)


def _join_type_to_japanese(join_type: str) -> str:
    return {
        "left": "left join で",
        "inner": "inner join で",
    }.get(join_type, f"{join_type} で")


def _format_validation_error(config_path: Path, exc: ValidationError) -> str:
    lines = [f"{config_path}: invalid merge configuration"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        lines.append(f"- {location}: {error['msg']}")
    return "\n".join(lines)
