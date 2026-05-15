"""Command line interface for datamapx."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer

from datamapx.config import DatamapxConfig, load_config
from datamapx.exceptions import ConfigError
from datamapx.io.csv_reader import profile_input_csv
from datamapx.io.csv_writer import write_output_csv
from datamapx.io.errors import CsvReadError, CsvWriteError
from datamapx.report import (
    ReportPaths,
    ReportWriteError,
    write_dry_run_reports,
    write_run_reports,
)
from datamapx.runner import DryRunResult, RunResult, run_dry_run, run_pipeline
from datamapx.transform.errors import MappingError
from datamapx.validation import ValidationError

app = typer.Typer(help="YAML-driven CSV migration and transformation tool.")


@app.command("validate-config")
def validate_config(config_path: Path) -> None:
    """Validate a datamapx YAML configuration file."""

    try:
        load_config(config_path)
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    typer.echo(f"Config is valid: {config_path}")


@app.command("inspect")
def inspect_config(config_path: Path) -> None:
    """Inspect a datamapx YAML configuration file."""

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    typer.echo(format_inspection(config))


@app.command("dry-run")
def dry_run(
    config_path: Path,
    limit: Annotated[int, typer.Option("--limit")] = -1,
    write_reports: Annotated[bool, typer.Option("--write-reports")] = False,
    reports_dir: Annotated[Path, typer.Option("--reports-dir")] = None,
) -> None:
    """Run the load phase without mapping, output, or report generation."""

    effective_limit = None if limit < 0 else limit
    if reports_dir is not None and not write_reports:
        typer.echo("--reports-dir requires --write-reports", err=True)
        raise typer.Exit(2)

    try:
        config = load_config(config_path)
        result = run_dry_run(config, config_path.parent, limit=effective_limit)
        report_paths: ReportPaths | None = None
        if write_reports:
            report_paths = write_dry_run_reports(
                result,
                config,
                config_path,
                reports_dir=reports_dir,
            )
    except (ConfigError, CsvReadError, MappingError, ValidationError, ReportWriteError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    typer.echo(format_dry_run_result(result))
    if write_reports and report_paths is not None:
        typer.echo("")
        typer.echo(format_report_written(report_paths))


@app.command("run")
def run(
    config_path: Path,
    reports_dir: Annotated[Path, typer.Option("--reports-dir")] = None,
) -> None:
    """Run the full pipeline and write output plus reports."""

    try:
        config = load_config(config_path)
        result = run_pipeline(config, config_path.parent)
        output_config = config.outputs[result.output_name]
        output_path = write_output_csv(
            result.output_preview_df,
            output_config,
            config_path.parent,
        )
        result = replace(
            result,
            output_file_written=True,
            output_path=str(output_path),
        )
        report_paths = write_run_reports(
            result,
            config,
            config_path,
            reports_dir=reports_dir,
        )
    except (
        ConfigError,
        CsvReadError,
        CsvWriteError,
        MappingError,
        ReportWriteError,
        ValidationError,
    ) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    typer.echo(format_run_result(result, report_paths))


@app.command("profile-input")
def profile_input(config_path: Path) -> None:
    """Profile the configured input CSV after schema normalization."""

    try:
        config = load_config(config_path)
        input_name, input_config = next(iter(config.inputs.items()))
        profile = profile_input_csv(input_name, input_config, config_path.parent)
    except (ConfigError, CsvReadError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    typer.echo(format_input_profile(profile))


def format_inspection(config: DatamapxConfig) -> str:
    """Return a human-readable configuration summary."""

    input_names = list(config.inputs)
    reference_names = list(config.references)
    output_names = list(config.outputs)

    lines = [
        "datamapx configuration",
        f"Project name: {config.project.name}",
        f"Input names: {', '.join(input_names) if input_names else '(none)'}",
        f"Reference names: {', '.join(reference_names) if reference_names else '(none)'}",
        f"Output names: {', '.join(output_names) if output_names else '(none)'}",
    ]

    for output_name, output_config in config.outputs.items():
        mapping_fields = sorted(config.mappings.get(output_name, {}))
        lines.extend(
            [
                f"Output columns ({output_name}): {', '.join(output_config.columns)}",
                f"Mapping fields ({output_name}): {', '.join(mapping_fields)}",
            ]
        )

    lines.extend(
        [
            f"Input validation count: {len(config.validations.input)}",
            f"Output validation count: {len(config.validations.output)}",
            f"Error output path: {config.error_handling.error_output}",
            f"Skipped output path: {config.error_handling.skipped_output}",
        ]
    )
    return "\n".join(lines)


def format_input_profile(profile: dict[str, object]) -> str:
    """Return a human-readable input profile summary."""

    lines = [
        "datamapx input profile",
        f"Input name: {profile['input_name']}",
        f"Path: {profile['path']}",
        f"Encoding: {profile['encoding']}",
        f"Delimiter: {profile['delimiter']}",
        f"Rows: {profile['rows']}",
        f"Columns: {', '.join(profile['columns'])}",
        "Missing counts:",
    ]

    missing_counts = profile["missing_counts"]
    sample_values = profile["sample_values"]
    dtypes = profile["dtypes"]
    if not isinstance(missing_counts, dict) or not isinstance(sample_values, dict):
        return "\n".join(lines)
    if not isinstance(dtypes, dict):
        return "\n".join(lines)

    for field in profile["columns"]:
        lines.append(f"- {field}: {missing_counts.get(field, 0)}")

    lines.append("Sample values:")
    for field in profile["columns"]:
        values = sample_values.get(field, [])
        lines.append(f"- {field}: {values}")

    lines.append("Inferred dtypes:")
    for field in profile["columns"]:
        lines.append(f"- {field}: {dtypes.get(field, 'unknown')}")

    return "\n".join(lines)


def format_dry_run_result(result: DryRunResult) -> str:
    """Return a human-readable dry-run summary."""

    load_result = result.load_result
    lines = [
        "Dry run completed",
        "",
        f"Project: {load_result.project_name}",
        f"Run ID: {result.run_id}",
        "",
        "Input:",
        f"- name: {load_result.input_name}",
        f"- path: {load_result.input_path}",
        f"- rows loaded: {load_result.input_rows}",
        f"- columns: {', '.join(load_result.input_columns)}",
        "",
        "References:",
    ]
    if load_result.references:
        for reference in load_result.references:
            key = (
                ", ".join(reference.key)
                if isinstance(reference.key, list)
                else reference.key
            )
            lines.extend(
                [
                    f"- {reference.name}",
                    f"  - path: {reference.path}",
                    f"  - rows loaded: {reference.rows}",
                    f"  - key: {key}",
                ]
            )
    else:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "Filter:",
            f"- rows before filter: {result.input_rows_before_filter}",
            f"- rows after filter: {result.input_rows_after_filter}",
            f"- skipped rows: {result.skipped_count}",
        ]
    )
    if result.skipped_rows:
        lines.extend(["", "Skipped preview:", "row_number,reason"])
        for skipped_row in result.skipped_rows[:5]:
            lines.append(f"{skipped_row.row_number},{skipped_row.reason}")

    lines.extend(
        [
            "",
            "Validation:",
            f"- input validation errors: {result.input_validation_error_count}",
            f"- output validation errors: {result.output_validation_error_count}",
            f"- total error rows: {result.total_error_count}",
        ]
    )
    if result.error_rows:
        lines.extend(["", "Error preview:", "row_number,stage,field,rule,message"])
        for error_row in result.error_rows[:5]:
            lines.append(
                f"{error_row.row_number},{error_row.stage},{error_row.field},"
                f"{error_row.rule},{error_row.message}"
            )

    preview_csv = result.output_preview_df.head().to_csv(index=False).strip()
    lines.extend(
        [
            "",
            "Output preview:",
            f"- name: {result.output_name}",
            f"- columns: {', '.join(result.output_columns)}",
            f"- rows previewed: {min(len(result.output_preview_df), 5)}",
            preview_csv,
            "",
            f"Limit: {load_result.limit if load_result.limit is not None else 'none'}",
            f"Status: {result.status}",
            "",
            "Note: output file is not written in dry-run.",
            "Note: errors.csv, skipped.csv, and summary.json are not written in dry-run.",
        ]
    )
    return "\n".join(lines)


def format_run_result(result: RunResult, report_paths: ReportPaths) -> str:
    """Return a human-readable run summary."""

    return "\n".join(
        [
            "Run completed",
            "",
            f"Run ID: {result.run_id}",
            f"Project: {result.load_result.project_name}",
            "",
            "Output:",
            f"- path: {result.output_path}",
            f"- rows written: {result.output_rows}",
            "",
            "Reports:",
            f"- errors: {report_paths.errors_csv}",
            f"- skipped: {report_paths.skipped_csv}",
            f"- summary: {report_paths.summary_json}",
            "",
            "Counts:",
            f"- input rows: {result.input_rows_before_validation}",
            f"- output rows: {result.output_rows}",
            f"- skipped rows: {result.skipped_count}",
            f"- error rows: {result.total_error_count}",
        ]
    )


def format_report_written(report_paths: ReportPaths) -> str:
    """Return a human-readable report write summary."""

    return "\n".join(
        [
            "Reports written:",
            f"- errors: {report_paths.errors_csv}",
            f"- skipped: {report_paths.skipped_csv}",
            f"- summary: {report_paths.summary_json}",
        ]
    )


if __name__ == "__main__":
    app()
