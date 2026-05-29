"""Lightweight preflight checks for datamapx configs."""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from datamapx.config import DatamapxConfig, OutputConfig, SchemaFieldConfig, load_config
from datamapx.exceptions import ConfigError
from datamapx.io.errors import CsvReadError, CsvWriteError
from datamapx.merge.config import MergeConfig, load_merge_config
from datamapx.run_all import RunAllConfig, load_run_all_config, resolve_run_all_path
from datamapx.union.config import UnionConfig, load_union_config
from datamapx.unpivot.config import UnpivotConfig, load_unpivot_config

PreflightKind = Literal["migration", "merge", "union", "unpivot", "run-all"]


@dataclass(frozen=True)
class PreflightReport:
    """Human-readable result for a successful preflight run."""

    config_type: PreflightKind
    config_path: Path
    lines: list[str]


def run_preflight(config_path: str | Path) -> PreflightReport:
    """Run a lightweight, read-only preflight on a datamapx config file."""

    path = Path(config_path)
    kind = _detect_config_kind(path)
    if kind == "run-all":
        config = load_run_all_config(path)
        lines = _preflight_run_all(config, path)
        return PreflightReport(config_type=kind, config_path=path, lines=lines)
    if kind == "merge":
        config = load_merge_config(path)
        lines = _preflight_merge(config, path)
        return PreflightReport(config_type=kind, config_path=path, lines=lines)
    if kind == "union":
        config = load_union_config(path)
        lines = _preflight_union(config, path)
        return PreflightReport(config_type=kind, config_path=path, lines=lines)
    if kind == "unpivot":
        config = load_unpivot_config(path)
        lines = _preflight_unpivot(config, path)
        return PreflightReport(config_type=kind, config_path=path, lines=lines)

    config = load_config(path)
    lines = _preflight_migration(config, path)
    return PreflightReport(config_type=kind, config_path=path, lines=lines)


def format_preflight_report(report: PreflightReport) -> str:
    """Return a human-readable preflight summary."""

    lines = [
        f"Preflight completed: {report.config_type}",
        f"Config: {report.config_path}",
    ]
    lines.extend(report.lines)
    return "\n".join(lines)


def _preflight_migration(config: DatamapxConfig, config_path: Path) -> list[str]:
    base_path = config_path.parent
    lines = ["Checks:", "- config validation: ok"]

    for input_name, input_config in config.inputs.items():
        lines.extend(
            _preflight_csv_resource(
                target=f"inputs.{input_name}",
                path=input_config.path,
                encoding=input_config.encoding,
                delimiter=input_config.delimiter,
                header=input_config.header,
                base_path=base_path,
                schema=input_config.fields_schema,
                key_fields=None,
                row_limit=config.runtime.max_input_rows,
                row_limit_name="runtime.max_input_rows",
            )
        )

    for reference_name, reference_config in config.references.items():
        lines.extend(
            _preflight_csv_resource(
                target=f"references.{reference_name}",
                path=reference_config.path,
                encoding=reference_config.encoding,
                delimiter=reference_config.delimiter,
                header=reference_config.header,
                base_path=base_path,
                schema=reference_config.fields_schema,
                key_fields=_key_fields(reference_config.key),
                row_limit=config.runtime.max_reference_rows,
                row_limit_name="runtime.max_reference_rows",
            )
        )

    for output_name, output_config in config.outputs.items():
        lines.extend(
            _preflight_output_resource(
                target=f"outputs.{output_name}",
                output_config=output_config,
                base_path=base_path,
            )
        )

    return lines


def _preflight_merge(config: MergeConfig, config_path: Path) -> list[str]:
    base_path = config_path.parent
    lines = ["Checks:", "- config validation: ok"]

    for input_name, input_config in config.inputs.items():
        lines.extend(
            _preflight_csv_resource(
                target=f"inputs.{input_name}",
                path=input_config.path,
                encoding=input_config.encoding,
                delimiter=input_config.delimiter,
                header=input_config.header,
                base_path=base_path,
                schema=input_config.fields_schema,
                key_fields=_key_fields(input_config.key),
                row_limit=config.runtime.max_input_rows,
                row_limit_name="runtime.max_input_rows",
            )
        )

    lines.extend(
        _preflight_output_resource(
            target="output",
            output_config=config.output,
            base_path=base_path,
        )
    )
    return lines


def _preflight_union(config: UnionConfig, config_path: Path) -> list[str]:
    base_path = config_path.parent
    lines = ["Checks:", "- config validation: ok"]

    for input_name, input_config in config.inputs.items():
        lines.extend(
            _preflight_csv_resource(
                target=f"inputs.{input_name}",
                path=input_config.path,
                encoding=input_config.encoding,
                delimiter=input_config.delimiter,
                header=input_config.header,
                base_path=base_path,
                schema=input_config.fields_schema,
                key_fields=_key_fields(input_config.key),
                row_limit=config.runtime.max_input_rows,
                row_limit_name="runtime.max_input_rows",
            )
        )

    lines.extend(
        _preflight_output_resource(
            target="output",
            output_config=config.output,
            base_path=base_path,
        )
    )
    return lines


def _preflight_unpivot(config: UnpivotConfig, config_path: Path) -> list[str]:
    base_path = config_path.parent
    lines = ["Checks:", "- config validation: ok"]

    lines.extend(
        _preflight_csv_resource(
            target="input",
            path=config.input_.path,
            encoding=config.input_.encoding,
            delimiter=config.input_.delimiter,
            header=config.input_.header,
            base_path=base_path,
            schema=config.input_.fields_schema,
            key_fields=None,
            row_limit=config.runtime.max_input_rows,
            row_limit_name="runtime.max_input_rows",
        )
    )
    lines.extend(
        _preflight_output_resource(
            target="output",
            output_config=config.output,
            base_path=base_path,
        )
    )
    return lines


def _preflight_run_all(config: RunAllConfig, config_path: Path) -> list[str]:
    base_path = config_path.parent
    total_jobs = len(config.jobs)
    lines = ["Jobs:"]

    for index, job in enumerate(config.jobs, start=1):
        job_config_path = resolve_run_all_path(job.config, base_path)
        lines.append(
            f"- job {index}/{total_jobs}: {job.name} [{job.type}] ({job_config_path})"
        )
        try:
            job_report = run_preflight(job_config_path)
        except (ConfigError, CsvReadError, CsvWriteError) as exc:
            message = (
                f"run-all job {index}/{total_jobs}: {job.name} [{job.type}] "
                f"({job_config_path}): {exc}"
            )
            raise exc.__class__(message) from exc
        for line in job_report.lines:
            lines.append(f"  {line}")

    return lines


def _preflight_csv_resource(
    *,
    target: str,
    path: str,
    encoding: str,
    delimiter: str,
    header: bool,
    base_path: Path,
    schema: dict[str, SchemaFieldConfig],
    key_fields: list[str] | None,
    row_limit: int | None,
    row_limit_name: str,
) -> list[str]:
    csv_path = _resolve_path(path, base_path)
    if not header:
        raise CsvReadError(f"{target}: header: false is not supported in preflight")
    if not csv_path.exists():
        raise CsvReadError(f"{target}: CSV file not found: {csv_path}")

    header_row = _read_csv_header(csv_path, encoding, delimiter)
    header_set = set(header_row)
    lines = [f"- {target}: header readable ({len(header_row)} columns)"]

    if key_fields is not None:
        _validate_key_header_resolution(target, key_fields, schema, header_set)
        lines.append(f"- {target}: key columns resolved")

    if schema:
        _validate_schema_header_resolution(target, schema, header_set)
        lines.append(f"- {target}: schema columns resolved")

    if row_limit is not None:
        row_count = _count_csv_data_rows(csv_path, encoding, delimiter)
        if row_count > row_limit:
            raise CsvReadError(
                f"{target}: row count {row_count} exceeds {row_limit_name} {row_limit}"
            )
        lines.append(
            f"- {target}: row count {row_count} within {row_limit_name} {row_limit}"
        )

    return lines


def _preflight_output_resource(
    *,
    target: str,
    output_config: OutputConfig,
    base_path: Path,
) -> list[str]:
    output_path = _resolve_path(output_config.path, base_path)
    parent = output_path.parent

    if output_config.if_exists == "error" and output_path.exists():
        raise CsvWriteError(f"{target}: output file already exists: {output_path}")

    _ensure_directory_creatable(parent, target)
    lines = [f"- {target}: output directory is available ({parent})"]
    if output_config.if_exists == "error":
        lines.append(f"- {target}: output file does not exist")
    else:
        lines.append(f"- {target}: if_exists=overwrite")
    return lines


def _validate_schema_header_resolution(
    target: str,
    schema: dict[str, SchemaFieldConfig],
    header_set: set[str],
) -> None:
    for field_name, field_config in schema.items():
        candidates = field_config.source_columns or [field_name]
        resolved = next(
            (candidate for candidate in candidates if candidate in header_set),
            None,
        )
        if resolved is None and field_config.required:
            raise CsvReadError(
                f"{target}.{field_name}: required raw column not found "
                f"(candidates: {', '.join(candidates)})"
            )


def _validate_key_header_resolution(
    target: str,
    key_fields: list[str],
    schema: dict[str, SchemaFieldConfig],
    header_set: set[str],
) -> None:
    for key_field in key_fields:
        if schema:
            field_config = schema.get(key_field)
            if field_config is None:
                raise CsvReadError(f"{target}.key: unknown key field '{key_field}' in schema")
            candidates = field_config.source_columns or [key_field]
            resolved = next(
                (candidate for candidate in candidates if candidate in header_set),
                None,
            )
            if resolved is None:
                raise CsvReadError(
                    f"{target}.key: missing key column '{key_field}' "
                    f"(candidates: {', '.join(candidates)})"
                )
            continue
        if key_field not in header_set:
            raise CsvReadError(f"{target}.key: missing key column '{key_field}'")


def _read_csv_header(csv_path: Path, encoding: str, delimiter: str) -> list[str]:
    try:
        with csv_path.open("r", encoding=encoding, newline="") as file:
            reader = csv.reader(file, delimiter=delimiter)
            header_row = next(reader, None)
    except FileNotFoundError as exc:
        raise CsvReadError(f"{csv_path}: CSV file not found") from exc
    except UnicodeError as exc:
        message = f"{csv_path}: cannot decode CSV with encoding '{encoding}': {exc}"
        raise CsvReadError(message) from exc
    except OSError as exc:
        raise CsvReadError(f"{csv_path}: cannot read CSV: {exc}") from exc
    except csv.Error as exc:
        raise CsvReadError(f"{csv_path}: cannot parse CSV: {exc}") from exc

    if header_row is None:
        raise CsvReadError(f"{csv_path}: CSV header row is empty")
    return header_row


def _count_csv_data_rows(csv_path: Path, encoding: str, delimiter: str) -> int:
    try:
        with csv_path.open("r", encoding=encoding, newline="") as file:
            reader = csv.reader(file, delimiter=delimiter)
            next(reader, None)
            return sum(1 for row in reader if row != [])
    except FileNotFoundError as exc:
        raise CsvReadError(f"{csv_path}: CSV file not found") from exc
    except UnicodeError as exc:
        message = f"{csv_path}: cannot decode CSV with encoding '{encoding}': {exc}"
        raise CsvReadError(message) from exc
    except OSError as exc:
        raise CsvReadError(f"{csv_path}: cannot read CSV: {exc}") from exc
    except csv.Error as exc:
        raise CsvReadError(f"{csv_path}: cannot parse CSV: {exc}") from exc


def _ensure_directory_creatable(parent: Path, target: str) -> None:
    if parent.exists():
        if not parent.is_dir():
            raise CsvWriteError(f"{target}: output directory is not a directory: {parent}")
        if not os.access(parent, os.W_OK | os.X_OK):
            raise CsvWriteError(f"{target}: output directory is not writable: {parent}")
        return

    ancestor = parent
    while not ancestor.exists():
        if ancestor.parent == ancestor:
            raise CsvWriteError(f"{target}: output directory cannot be created: {parent}")
        ancestor = ancestor.parent

    if not ancestor.is_dir():
        raise CsvWriteError(f"{target}: output directory is not a directory: {ancestor}")
    if not os.access(ancestor, os.W_OK | os.X_OK):
        raise CsvWriteError(f"{target}: output directory is not writable: {parent}")


def _resolve_path(path: str, base_path: Path) -> Path:
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return base_path / resolved


def _key_fields(key: str | list[str]) -> list[str]:
    return [key] if isinstance(key, str) else key


def _detect_config_kind(path: Path) -> PreflightKind:
    try:
        with path.open("r", encoding="utf-8") as file:
            raw_config: Any = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read config file: {exc}") from exc

    if raw_config is None:
        raise ConfigError(f"{path}: config file is empty")
    if not isinstance(raw_config, dict):
        raise ConfigError(f"{path}: top-level YAML value must be a mapping")

    if "jobs" in raw_config:
        return "run-all"
    if "merge" in raw_config:
        return "merge"
    if "union" in raw_config:
        return "union"
    if {"input", "unpivot", "output"}.issubset(raw_config):
        return "unpivot"
    if {"inputs", "outputs", "mappings"}.issubset(raw_config):
        return "migration"

    raise ConfigError(f"{path}: unsupported config structure for preflight")
