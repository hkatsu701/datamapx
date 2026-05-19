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

MERGE_RULE_TYPES = ["source", "first", "last", "sum", "min", "max", "count"]


@dataclass(frozen=True)
class MergeWizardResult:
    """Result of generating a merge YAML file."""

    config_path: Path
    project_name: str
    input_count: int
    output_columns: list[str]


def run_merge_wizard() -> MergeWizardResult:
    """Interactively build and write a merge config YAML file."""

    project_name = _prompt_text("Project name", "generated_merge")
    config_path = Path(_prompt_text("Merge config path", "./merge.yml"))
    output_path = _prompt_text("Staging CSV output path", "./output/merged.csv")

    if config_path.exists():
        if not typer.confirm(f"{config_path} exists. Overwrite?", default=False):
            raise ConfigError(f"{config_path}: merge config file already exists")

    input_count = _prompt_int("How many input CSV files?", 2)
    if input_count < 2:
        raise ConfigError("merge wizard requires at least two input CSV files")

    input_specs: list[dict[str, Any]] = []
    input_fields: dict[str, dict[str, str]] = {}
    input_summaries: list[str] = []

    for index in range(1, input_count + 1):
        input_name = _prompt_text(f"Input {index} name", f"input_{index}")
        input_csv_path = _prompt_text(f"Input {index} CSV path", f"./input/{input_name}.csv")
        headers = _read_csv_headers(Path(input_csv_path))
        safe_fields = _build_safe_field_names(headers)
        field_map = dict(zip(headers, safe_fields, strict=True))
        raw_map = _build_raw_header_map(headers, safe_fields)
        input_fields[input_name] = {
            "safe": {field_name: field_name for field_name in safe_fields},
            "raw": raw_map,
        }
        input_summaries.append(_format_field_map(input_name, headers, safe_fields))

        key_text = _prompt_text(
            f"{input_name} key column(s) (comma-separated)",
            safe_fields[0],
        )
        key_fields = _normalize_key_fields(key_text, input_name, input_fields)
        input_specs.append(
            {
                "name": input_name,
                "path": input_csv_path,
                "headers": headers,
                "safe_fields": safe_fields,
                "field_map": field_map,
                "key": key_fields,
            }
        )

    base_input = _prompt_choice(
        "Base input name",
        [spec["name"] for spec in input_specs],
        input_specs[0]["name"],
    )
    join_type = _prompt_choice("Join type", ["left", "inner"], "left")

    base_spec = next(spec for spec in input_specs if spec["name"] == base_input)
    default_output_columns = ",".join(base_spec["safe_fields"])
    output_columns = _prompt_list("Output columns (comma-separated)", default_output_columns)
    if not output_columns:
        raise ConfigError("merge wizard requires at least one output column")

    merge_columns: dict[str, dict[str, Any]] = {}
    for output_column in output_columns:
        rule_type = _prompt_choice(
            f"Rule for {output_column}",
            MERGE_RULE_TYPES,
            "source",
        )
        if rule_type == "source":
            reference = _prompt_text(
                f"Reference for {output_column} (input.field)",
                f"{base_input}.{base_spec['safe_fields'][0]}",
            )
            merge_columns[output_column] = {
                "source": _normalize_single_reference(reference, input_fields)
            }
            continue

        default_refs = _default_merge_references(input_specs, base_input)
        refs_text = _prompt_list(
            f"References for {output_column} (comma-separated input.field)",
            ",".join(default_refs),
        )
        if not refs_text:
            raise ConfigError(f"{output_column}: merge rule requires at least one reference")
        merge_columns[output_column] = {
            rule_type: _normalize_merge_references(refs_text, input_fields)
        }

    config_data = {
        "version": 1,
        "project": {
            "name": project_name,
            "description": "Generated merge config from interactive wizard",
        },
        "inputs": {
            spec["name"]: {
                "path": spec["path"],
                "encoding": "utf-8-sig",
                "delimiter": ",",
                "header": True,
                "schema": {
                    safe_field: {
                        "source_columns": [header],
                        "type": "string",
                        "required": False,
                        "normalize": ["trim"],
                    }
                    for header, safe_field in zip(spec["headers"], spec["safe_fields"], strict=True)
                },
                "key": spec["key"][0] if len(spec["key"]) == 1 else spec["key"],
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
        raise ConfigError(f"{config_path}: cannot write merge config: {exc}") from exc

    for summary in input_summaries:
        typer.echo(summary)

    return MergeWizardResult(
        config_path=config_path,
        project_name=project_name,
        input_count=input_count,
        output_columns=output_columns,
    )


def _prompt_text(message: str, default: str) -> str:
    return str(typer.prompt(message, default=default))


def _prompt_int(message: str, default: int) -> int:
    value = typer.prompt(message, default=default)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{message}: integer value required") from exc


def _prompt_choice(message: str, options: list[str], default: str) -> str:
    choice = str(typer.prompt(f"{message} ({', '.join(options)})", default=default)).strip()
    if choice not in options:
        raise ConfigError(f"{message}: must be one of {', '.join(options)}")
    return choice


def _prompt_list(message: str, default: str) -> list[str]:
    value = str(typer.prompt(message, default=default)).strip()
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _read_csv_headers(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file, delimiter=",")
            headers = next(reader, None)
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read input CSV: {exc}") from exc

    if headers is None:
        raise ConfigError(f"{path}: input CSV is empty")
    if not headers:
        raise ConfigError(f"{path}: input CSV header row is empty")
    return [str(header) for header in headers]


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


def _build_raw_header_map(headers: list[str], safe_fields: list[str]) -> dict[str, list[str]]:
    raw_map: dict[str, list[str]] = {}
    for header, safe_field in zip(headers, safe_fields, strict=True):
        raw_map.setdefault(header, []).append(safe_field)
    return raw_map


def _format_field_map(input_name: str, headers: list[str], safe_fields: list[str]) -> str:
    lines = [f"{input_name} fields:"]
    for header, safe_field in zip(headers, safe_fields, strict=True):
        lines.append(f"- {header} -> {safe_field}")
    return "\n".join(lines)


def _normalize_single_reference(reference: str, input_fields: dict[str, dict[str, Any]]) -> str:
    normalized = _normalize_reference_text(reference)
    if "." not in normalized:
        raise ConfigError(f"{reference}: merge reference must use '<input>.<field>'")
    namespace, field_name = normalized.split(".", 1)
    if namespace not in input_fields:
        raise ConfigError(f"{reference}: unknown input namespace '{namespace}'")
    return f"{namespace}.{_resolve_field_name(namespace, field_name, input_fields)}"


def _normalize_merge_references(
    refs_text: list[str],
    input_fields: dict[str, dict[str, Any]],
) -> list[str]:
    return [_normalize_single_reference(reference, input_fields) for reference in refs_text]


def _normalize_key_fields(
    key_text: str,
    input_name: str,
    input_fields: dict[str, dict[str, Any]],
) -> list[str]:
    values = [item.strip() for item in key_text.split(",") if item.strip()]
    if not values:
        raise ConfigError(f"{input_name}: merge key requires at least one field")
    return [_resolve_field_name(input_name, field_name, input_fields) for field_name in values]


def _normalize_reference_text(reference: str) -> str:
    return reference.strip()


def _resolve_field_name(
    input_name: str,
    field_name: str,
    input_fields: dict[str, dict[str, Any]],
) -> str:
    field_maps = input_fields[input_name]
    safe_map = field_maps["safe"]
    raw_map = field_maps["raw"]
    if field_name in safe_map:
        return field_name
    if field_name in raw_map:
        safe_names = raw_map[field_name]
        if len(safe_names) == 1:
            return safe_names[0]
        raise ConfigError(
            f"{input_name}.{field_name}: raw header is ambiguous; use the generated safe field name"
        )
    raise ConfigError(f"{input_name}.{field_name}: unknown field")


def _default_merge_references(input_specs: list[dict[str, Any]], base_input: str) -> list[str]:
    base_spec = next(spec for spec in input_specs if spec["name"] == base_input)
    return [f"{base_input}.{field_name}" for field_name in base_spec["safe_fields"][:1]]


def _format_validation_error(config_path: Path, exc: ValidationError) -> str:
    lines = [f"{config_path}: invalid merge configuration"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        lines.append(f"- {location}: {error['msg']}")
    return "\n".join(lines)
