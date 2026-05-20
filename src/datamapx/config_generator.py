"""Basic generate-config support for datamapx."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from datamapx.exceptions import ConfigError
from datamapx.naming import build_safe_field_names


@dataclass(frozen=True)
class GeneratedConfigResult:
    """Result of generating a basic migration YAML file."""

    config_path: Path
    input_headers: list[str]
    schema_fields: list[str]
    output_columns: list[str]


@dataclass(frozen=True)
class GeneratedOutputMapping:
    """Output column mapping selected by a wizard."""

    output_column: str
    schema_field: str


def generate_basic_config(
    input_path: str | Path,
    output_path: str | Path,
    config_path: str | Path,
    *,
    input_name: str = "input",
    output_name: str = "output",
    project_name: str = "generated_migration",
    encoding: str = "utf-8-sig",
    delimiter: str = ",",
    overwrite: bool = False,
    preserve_output_columns: bool = True,
    output_mappings: list[GeneratedOutputMapping] | None = None,
) -> GeneratedConfigResult:
    """Generate a minimal migration YAML from the input CSV headers."""

    input_path = Path(input_path).resolve()
    output_path = Path(output_path).resolve()
    config_path = Path(config_path)

    if config_path.exists() and not overwrite:
        raise ConfigError(
            f"{config_path}: config file already exists; use --overwrite to replace it"
        )

    headers = _read_csv_headers(input_path, encoding=encoding, delimiter=delimiter)
    schema_fields = _build_safe_field_names(headers)
    if output_mappings is None:
        output_columns = _build_output_columns(
            headers,
            schema_fields,
            preserve_output_columns=preserve_output_columns,
        )
        mapping_pairs = list(zip(output_columns, schema_fields, strict=True))
    else:
        if not output_mappings:
            raise ConfigError(f"{config_path}: output_mappings must not be empty")
        output_columns = [mapping.output_column for mapping in output_mappings]
        schema_field_set = set(schema_fields)
        for mapping in output_mappings:
            if mapping.schema_field not in schema_field_set:
                raise ConfigError(
                    f"{config_path}: unknown schema field in output_mappings: "
                    f"{mapping.schema_field}"
                )
        if len(set(output_columns)) != len(output_columns):
            raise ConfigError(f"{config_path}: output column names must be unique")
        mapping_pairs = [
            (mapping.output_column, mapping.schema_field)
            for mapping in output_mappings
        ]
    config_data = _build_config_data(
        input_path=str(input_path),
        output_path=str(output_path),
        input_name=input_name,
        output_name=output_name,
        project_name=project_name,
        encoding=encoding,
        delimiter=delimiter,
        headers=headers,
        schema_fields=schema_fields,
        output_columns=output_columns,
        mapping_pairs=mapping_pairs,
    )

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

    return GeneratedConfigResult(
        config_path=config_path,
        input_headers=headers,
        schema_fields=schema_fields,
        output_columns=output_columns,
    )


def _read_csv_headers(path: Path, *, encoding: str, delimiter: str) -> list[str]:
    try:
        with path.open("r", encoding=encoding, newline="") as file:
            reader = csv.reader(file, delimiter=delimiter)
            headers = next(reader, None)
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read input CSV: {exc}") from exc

    if headers is None:
        raise ConfigError(f"{path}: input CSV is empty")
    if not headers:
        raise ConfigError(f"{path}: input CSV header row is empty")
    return [str(header) for header in headers]


def _build_safe_field_names(headers: list[str]) -> list[str]:
    return build_safe_field_names(headers)


def _build_output_columns(
    headers: list[str],
    schema_fields: list[str],
    *,
    preserve_output_columns: bool,
) -> list[str]:
    if preserve_output_columns and _can_preserve_output_columns(headers):
        return list(headers)
    return list(schema_fields)


def _can_preserve_output_columns(headers: list[str]) -> bool:
    stripped = [header.strip() for header in headers]
    return all(stripped) and len(set(headers)) == len(headers)


def _build_config_data(
    *,
    input_path: str,
    output_path: str,
    input_name: str,
    output_name: str,
    project_name: str,
    encoding: str,
    delimiter: str,
    headers: list[str],
    schema_fields: list[str],
    output_columns: list[str],
    mapping_pairs: list[tuple[str, str]],
) -> dict[str, Any]:
    schema = {
        schema_field: {
            "source_columns": [header],
            "type": "string",
            "required": False,
            "normalize": ["trim"],
        }
        for schema_field, header in zip(schema_fields, headers, strict=True)
    }

    mappings = {
        output_name: {
            output_column: {"source": f"{input_name}.{schema_field}"}
            for output_column, schema_field in mapping_pairs
        }
    }

    return {
        "version": 1,
        "project": {
            "name": project_name,
            "description": "Generated migration from input CSV headers",
        },
        "inputs": {
            input_name: {
                "path": input_path,
                "encoding": encoding,
                "delimiter": delimiter,
                "header": True,
                "schema": schema,
            }
        },
        "outputs": {
            output_name: {
                "path": output_path,
                "encoding": encoding,
                "delimiter": delimiter,
                "header": True,
                "newline": "\n",
                "if_exists": "error",
                "columns": output_columns,
            }
        },
        "mappings": mappings,
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
