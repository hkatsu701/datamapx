"""Configuration models and YAML loading for match pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, ValidationError, field_validator, model_validator

from datamapx.config import (
    ErrorHandlingConfig,
    InputConfig,
    OutputConfig,
    ProjectConfig,
    RuntimeConfig,
    StrictModel,
)
from datamapx.exceptions import ConfigError


class MatchSettings(StrictModel):
    """Settings for exact-match grouping."""

    keys: list[str]
    output_column: str
    id_prefix: str = "GROUP"
    id_padding: int = 6
    assign_singletons: bool = True
    on_missing_key: Literal["error"] = "error"

    @field_validator("output_column")
    @classmethod
    def validate_output_column(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("id_padding")
    @classmethod
    def validate_padding(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be a positive integer")
        return value

    @model_validator(mode="after")
    def validate_match_settings(self) -> MatchSettings:
        errors: list[str] = []
        if not self.keys:
            errors.append("match.keys: requires at least one field")
        if len(self.keys) != len(set(self.keys)):
            errors.append("match.keys: duplicate fields are not allowed")
        if self.output_column in self.keys:
            errors.append("match.output_column: must not be one of match.keys")
        if errors:
            raise ValueError("; ".join(errors))
        return self


class MatchConfig(StrictModel):
    """Top-level match YAML model."""

    version: Literal[1]
    project: ProjectConfig
    input_: InputConfig = Field(alias="input")
    match: MatchSettings
    output: OutputConfig
    error_handling: ErrorHandlingConfig
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    @model_validator(mode="after")
    def validate_match_consistency(self) -> MatchConfig:
        errors: list[str] = []

        if not self.input_.fields_schema:
            errors.append("input.schema: match requires input schema")
            if errors:
                raise ValueError("; ".join(errors))

        schema_fields = set(self.input_.fields_schema)
        missing_keys = [field for field in self.match.keys if field not in schema_fields]
        if missing_keys:
            errors.append("match.keys: unknown input schema fields: " + ", ".join(missing_keys))

        if self.match.output_column in schema_fields:
            errors.append(
                "match.output_column: must not collide with an existing input schema field"
            )

        output_columns = self.output.columns
        allowed_columns = schema_fields | {self.match.output_column}
        unknown_output_columns = [
            column for column in output_columns if column not in allowed_columns
        ]
        if unknown_output_columns:
            errors.append(
                "output.columns: unknown match output columns: "
                + ", ".join(unknown_output_columns)
            )
        if self.match.output_column not in output_columns:
            errors.append("output.columns: must include match.output_column")
        if len(output_columns) != len(set(output_columns)):
            errors.append("output.columns: duplicate output columns are not allowed")

        if errors:
            raise ValueError("; ".join(errors))
        return self


def load_match_config(path: str | Path) -> MatchConfig:
    """Load and validate a match YAML config."""

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
        return MatchConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(config_path, exc)) from exc


def _format_validation_error(config_path: Path, exc: ValidationError) -> str:
    lines = [f"{config_path}: invalid configuration"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        lines.append(f"- {location}: {error['msg']}")
    return "\n".join(lines)
