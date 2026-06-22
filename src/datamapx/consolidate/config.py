"""Configuration models and YAML loading for consolidate pipeline."""

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

_PARENT_RULE_FIELDS = ("first", "last", "sum", "count", "require_same")
_CHILD_RULE_FIELDS = ("source", "parent_value")


class ParentColumnRule(StrictModel):
    """Aggregation rule for one parent output column."""

    first: str | None = None
    last: str | None = None
    sum: str | None = None
    count: str | None = None
    require_same: str | None = None

    @model_validator(mode="after")
    def validate_rule(self) -> ParentColumnRule:
        provided = [field for field in _PARENT_RULE_FIELDS if field in self.model_fields_set]
        if len(provided) != 1:
            raise ValueError("exactly one parent column rule must be set")
        rule_name = provided[0]
        value = getattr(self, rule_name)
        if value is None or not value.strip():
            raise ValueError(f"{rule_name} source must not be empty")
        return self

    def rule_name(self) -> str:
        for field in _PARENT_RULE_FIELDS:
            if field in self.model_fields_set:
                return field
        raise ValueError("parent rule is not set")


class ChildColumnRule(StrictModel):
    """Rule for one child output column."""

    source: str | None = None
    parent_value: str | None = None

    @model_validator(mode="after")
    def validate_rule(self) -> ChildColumnRule:
        provided = [field for field in _CHILD_RULE_FIELDS if field in self.model_fields_set]
        if len(provided) != 1:
            raise ValueError("exactly one child column rule must be set")
        rule_name = provided[0]
        value = getattr(self, rule_name)
        if value is None or not value.strip():
            raise ValueError(f"{rule_name} source must not be empty")
        return self

    def rule_name(self) -> str:
        for field in _CHILD_RULE_FIELDS:
            if field in self.model_fields_set:
                return field
        raise ValueError("child rule is not set")


class ParentSettings(StrictModel):
    """Parent consolidation output definition."""

    output: OutputConfig
    columns: dict[str, ParentColumnRule]


class ChildSettings(StrictModel):
    """Child consolidation output definition."""

    name: str
    output: OutputConfig
    columns: dict[str, ChildColumnRule]


class ConsolidateSettings(StrictModel):
    """Settings for grouped consolidation."""

    group_by: list[str]
    parent: ParentSettings
    children: list[ChildSettings] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_settings(self) -> ConsolidateSettings:
        errors: list[str] = []
        if not self.group_by:
            errors.append("consolidate.group_by: requires at least one field")
        if len(self.group_by) != len(set(self.group_by)):
            errors.append("consolidate.group_by: duplicate fields are not allowed")
        if not self.children:
            errors.append("consolidate.children: requires at least one child output")
        if errors:
            raise ValueError("; ".join(errors))
        return self


class ConsolidateConfig(StrictModel):
    """Top-level consolidate YAML model."""

    version: Literal[1]
    project: ProjectConfig
    input_: InputConfig = Field(alias="input")
    consolidate: ConsolidateSettings
    error_handling: ErrorHandlingConfig
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    @model_validator(mode="after")
    def validate_consolidate_consistency(self) -> ConsolidateConfig:
        errors: list[str] = []

        if not self.input_.fields_schema:
            errors.append("input.schema: consolidate requires input schema")
            if errors:
                raise ValueError("; ".join(errors))

        schema_fields = set(self.input_.fields_schema)
        missing_group_by = [
            column for column in self.consolidate.group_by if column not in schema_fields
        ]
        if missing_group_by:
            errors.append(
                "consolidate.group_by: unknown input schema fields: " + ", ".join(missing_group_by)
            )

        parent_columns = list(self.consolidate.parent.columns)
        if self.consolidate.parent.output.columns != parent_columns:
            errors.append(
                "consolidate.parent.output.columns: must match parent column rules exactly "
                f"({parent_columns})"
            )

        for output_name, rule in self.consolidate.parent.columns.items():
            source = getattr(rule, rule.rule_name())
            if source not in schema_fields:
                errors.append(
                    "consolidate.parent.columns."
                    f"{output_name}: unknown input schema field: {source}"
                )

        child_names: set[str] = set()
        for index, child in enumerate(self.consolidate.children):
            if child.name in child_names:
                errors.append(
                    "consolidate.children["
                    f"{index}].name: duplicate child name '{child.name}'"
                )
            child_names.add(child.name)
            child_columns = list(child.columns)
            if child.output.columns != child_columns:
                errors.append(
                    "consolidate.children["
                    f"{index}].output.columns: must match child column rules exactly "
                    f"({child_columns})"
                )
            for output_name, rule in child.columns.items():
                rule_name = rule.rule_name()
                source = getattr(rule, rule_name)
                if rule_name == "source" and source not in schema_fields:
                    errors.append(
                        "consolidate.children["
                        f"{index}].columns.{output_name}: unknown input schema field: {source}"
                    )
                if rule_name == "parent_value" and source not in self.consolidate.parent.columns:
                    errors.append(
                        "consolidate.children["
                        f"{index}].columns.{output_name}: unknown parent output column: {source}"
                    )

        if errors:
            raise ValueError("; ".join(errors))
        return self


def load_consolidate_config(path: str | Path) -> ConsolidateConfig:
    """Load and validate a consolidate YAML config."""

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
        return ConsolidateConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(config_path, exc)) from exc


def _format_validation_error(config_path: Path, exc: ValidationError) -> str:
    lines = [f"{config_path}: invalid configuration"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        lines.append(f"- {location}: {error['msg']}")
    return "\n".join(lines)
