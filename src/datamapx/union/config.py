"""Configuration models and YAML loading for union pipeline."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, ValidationError, model_validator

from datamapx.config import (
    ErrorHandlingConfig,
    OutputConfig,
    ProjectConfig,
    RuntimeConfig,
    SchemaFieldConfig,
    StrictModel,
)
from datamapx.exceptions import ConfigError

FIELD_REFERENCE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([^\s\[\]\(\),+\-*/%<>=!&|:]+)")


class UnionInputConfig(StrictModel):
    path: str
    encoding: str = "utf-8-sig"
    delimiter: str = ","
    header: bool = True
    fields_schema: dict[str, SchemaFieldConfig] = Field(default_factory=dict, alias="schema")
    key: str | list[str]

    @model_validator(mode="after")
    def validate_key(self) -> UnionInputConfig:
        key_fields = [self.key] if isinstance(self.key, str) else self.key
        if not key_fields:
            raise ValueError("union input key requires at least one field")
        if any(not field.strip() for field in key_fields):
            raise ValueError("union input key fields must not be empty")
        return self


class UnionSettings(StrictModel):
    columns: list[str]

    @model_validator(mode="after")
    def validate_columns(self) -> UnionSettings:
        if not self.columns:
            raise ValueError("union.columns requires at least one column")
        return self


class UnionConfig(StrictModel):
    version: Literal[1]
    project: ProjectConfig
    inputs: dict[str, UnionInputConfig]
    union: UnionSettings
    output: OutputConfig
    error_handling: ErrorHandlingConfig
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    @model_validator(mode="after")
    def validate_union_consistency(self) -> UnionConfig:
        errors: list[str] = []

        if len(self.inputs) < 2:
            errors.append("inputs: union requires at least two inputs")

        if self.union.columns != self.output.columns:
            errors.append("union.columns: must match output.columns exactly")

        input_names = list(self.inputs)
        base_key_fields: list[str] = []
        if input_names:
            first_input = self.inputs[input_names[0]]
            base_key_fields = (
                [first_input.key] if isinstance(first_input.key, str) else first_input.key
            )

        for input_name, input_config in self.inputs.items():
            key_fields = (
                [input_config.key] if isinstance(input_config.key, str) else input_config.key
            )
            schema_fields = set(input_config.fields_schema)
            if base_key_fields and key_fields != base_key_fields:
                errors.append(
                    f"inputs.{input_name}.key: key must match the first input key exactly"
                )
            for key_field in key_fields:
                if schema_fields and key_field not in schema_fields:
                    errors.append(
                        f"inputs.{input_name}.key: unknown key field '{key_field}' in schema"
                    )

        if errors:
            raise ValueError("; ".join(errors))
        return self


def load_union_config(path: str | Path) -> UnionConfig:
    """Load and validate a union YAML config."""

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
        return UnionConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(config_path, exc)) from exc


def _format_validation_error(config_path: Path, exc: ValidationError) -> str:
    lines = [f"{config_path}: invalid configuration"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        lines.append(f"- {location}: {error['msg']}")
    return "\n".join(lines)
