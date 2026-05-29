"""Configuration models and YAML loading for aggregate pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, ValidationError, model_validator

from datamapx.config import (
    ErrorHandlingConfig,
    InputConfig,
    OutputConfig,
    ProjectConfig,
    RuntimeConfig,
    StrictModel,
)
from datamapx.exceptions import ConfigError

_RULE_FIELDS = ("group_key", "sum", "count", "min", "max", "first", "last")


class AggregateColumnRule(StrictModel):
    """Aggregation rule for one output column."""

    group_key: str | None = None
    sum: str | None = None
    count: str | None = None
    min: str | None = None
    max: str | None = None
    first: str | None = None
    last: str | None = None

    @model_validator(mode="after")
    def validate_aggregate_column_rule(self) -> AggregateColumnRule:
        provided = [
            field_name for field_name in _RULE_FIELDS if field_name in self.model_fields_set
        ]
        if len(provided) != 1:
            raise ValueError("exactly one aggregate rule must be set")

        rule_name = provided[0]
        rule_value = getattr(self, rule_name)
        if rule_name == "count":
            if rule_value is not None and not str(rule_value).strip():
                raise ValueError("count source must not be empty")
            return self

        if rule_value is None or not str(rule_value).strip():
            raise ValueError(f"{rule_name} source must not be empty")
        return self

    def rule_name(self) -> str:
        for field_name in _RULE_FIELDS:
            if field_name in self.model_fields_set:
                return field_name
        raise ValueError("aggregate rule is not set")


class AggregateSettings(StrictModel):
    """Settings for one aggregate transformation."""

    group_by: list[str]
    columns: dict[str, AggregateColumnRule]

    @model_validator(mode="after")
    def validate_aggregate_settings(self) -> AggregateSettings:
        errors: list[str] = []

        if not self.group_by:
            errors.append("aggregate.group_by: requires at least one column")
        if len(self.group_by) != len(set(self.group_by)):
            errors.append("aggregate.group_by: duplicate group_by columns are not allowed")
        if not self.columns:
            errors.append("aggregate.columns: requires at least one output column")

        if errors:
            raise ValueError("; ".join(errors))
        return self


class AggregateConfig(StrictModel):
    """Top-level aggregate YAML model."""

    version: Literal[1]
    project: ProjectConfig
    input_: InputConfig = Field(alias="input")
    aggregate: AggregateSettings
    output: OutputConfig
    error_handling: ErrorHandlingConfig
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    @model_validator(mode="after")
    def validate_aggregate_consistency(self) -> AggregateConfig:
        errors: list[str] = []

        if not self.input_.fields_schema:
            errors.append("input.schema: aggregate requires input schema")

        expected_columns = list(self.aggregate.columns)
        if self.output.columns != expected_columns:
            errors.append(
                f"output.columns: must match aggregate output columns exactly ({expected_columns})"
            )

        schema_fields = set(self.input_.fields_schema)
        missing_group_by = [
            column for column in self.aggregate.group_by if column not in schema_fields
        ]
        if missing_group_by:
            errors.append(
                "aggregate.group_by: unknown input schema fields: " + ", ".join(missing_group_by)
            )

        used_group_by_sources: list[str] = []
        for output_name, rule in self.aggregate.columns.items():
            rule_name = rule.rule_name()
            source = getattr(rule, rule_name)
            if rule_name == "group_key":
                if source is None or not str(source).strip():
                    errors.append(f"aggregate.columns.{output_name}.group_key: must not be empty")
                    continue
                if source not in schema_fields:
                    errors.append(
                        "aggregate.columns."
                        f"{output_name}.group_key: unknown input schema field: {source}"
                    )
                    continue
                if source not in self.aggregate.group_by:
                    errors.append(
                        "aggregate.columns."
                        f"{output_name}.group_key: source must be one of aggregate.group_by"
                    )
                    continue
                if source in used_group_by_sources:
                    errors.append(
                        "aggregate.columns."
                        f"{output_name}.group_key: duplicate group key source '{source}'"
                    )
                    continue
                used_group_by_sources.append(source)
                continue

            if source is None:
                if rule_name == "count":
                    continue
                errors.append(f"aggregate.columns.{output_name}.{rule_name}: must not be empty")
                continue

            if isinstance(source, str) and not source.strip():
                if rule_name == "count":
                    continue
                errors.append(f"aggregate.columns.{output_name}.{rule_name}: must not be empty")
                continue

            if source not in schema_fields:
                errors.append(
                    "aggregate.columns."
                    f"{output_name}.{rule_name}: unknown input schema field: {source}"
                )

        missing_group_key_sources = [
            column for column in self.aggregate.group_by if column not in used_group_by_sources
        ]
        if missing_group_key_sources:
            errors.append(
                "aggregate.group_by: missing group_key columns for: "
                + ", ".join(missing_group_key_sources)
            )

        if errors:
            raise ValueError("; ".join(errors))
        return self


def load_aggregate_config(path: str | Path) -> AggregateConfig:
    """Load and validate an aggregate YAML config."""

    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as file:
            raw_config = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{config_path}: invalid YAML: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"{config_path}: cannot read config file: {exc}") from exc

    if raw_config is None:
        raise ConfigError(f"{config_path}: config file is empty")
    if not isinstance(raw_config, dict):
        raise ConfigError(f"{config_path}: top-level YAML value must be a mapping")

    try:
        return AggregateConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(config_path, exc)) from exc


def _format_validation_error(config_path: Path, exc: ValidationError) -> str:
    lines = [f"{config_path}: invalid configuration"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        lines.append(f"- {location}: {error['msg']}")
    return "\n".join(lines)
