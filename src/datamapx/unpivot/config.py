"""Configuration models and YAML loading for unpivot pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, ValidationError, model_validator

from datamapx.config import (
    FIELD_REFERENCE_RE,
    ErrorHandlingConfig,
    FiltersConfig,
    InputConfig,
    OutputConfig,
    ProjectConfig,
    RuntimeConfig,
    StrictModel,
)
from datamapx.exceptions import ConfigError


class UnpivotSettings(StrictModel):
    """Settings for one unpivot transformation."""

    id_columns: list[str]
    variable_column: str
    value_column: str
    value_columns: dict[str, Any]
    drop_null_values: bool = False

    @model_validator(mode="after")
    def validate_unpivot_settings(self) -> UnpivotSettings:
        errors: list[str] = []

        if not self.id_columns:
            errors.append("unpivot.id_columns: requires at least one column")
        if not self.variable_column.strip():
            errors.append("unpivot.variable_column: must not be empty")
        if not self.value_column.strip():
            errors.append("unpivot.value_column: must not be empty")
        if not self.value_columns:
            errors.append("unpivot.value_columns: requires at least one value column")

        output_columns = self.id_columns + [self.variable_column, self.value_column]
        if len(output_columns) != len(set(output_columns)):
            errors.append("unpivot: output columns must be unique")

        if errors:
            raise ValueError("; ".join(errors))
        return self


class UnpivotConfig(StrictModel):
    """Top-level unpivot YAML model."""

    version: Literal[1]
    project: ProjectConfig
    input_: InputConfig = Field(alias="input")
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    unpivot: UnpivotSettings
    output: OutputConfig
    error_handling: ErrorHandlingConfig
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    @model_validator(mode="after")
    def validate_unpivot_consistency(self) -> UnpivotConfig:
        errors: list[str] = []

        if not self.input_.fields_schema:
            errors.append("input.schema: unpivot requires input schema")

        expected_columns = (
            list(self.unpivot.id_columns)
            + [self.unpivot.variable_column, self.unpivot.value_column]
        )
        if self.output.columns != expected_columns:
            errors.append(
                "output.columns: must match unpivot output columns exactly "
                f"({expected_columns})"
            )

        if self.input_.fields_schema:
            schema_fields = set(self.input_.fields_schema)
            missing_id_columns = [
                column for column in self.unpivot.id_columns if column not in schema_fields
            ]
            missing_value_columns = [
                column for column in self.unpivot.value_columns if column not in schema_fields
            ]
            if missing_id_columns:
                errors.append(
                    "unpivot.id_columns: unknown input schema fields: "
                    + ", ".join(missing_id_columns)
                )
            if missing_value_columns:
                errors.append(
                    "unpivot.value_columns: unknown input schema fields: "
                    + ", ".join(missing_value_columns)
                )
            self._validate_filter_references(schema_fields, errors)

        if errors:
            raise ValueError("; ".join(errors))
        return self

    def _validate_filter_references(
        self,
        schema_fields: set[str],
        errors: list[str],
    ) -> None:
        for section_name, rules in (
            ("include", self.filters.include),
            ("exclude", self.filters.exclude),
        ):
            for index, rule in enumerate(rules):
                context = f"filters.{section_name}[{index}].if"
                for match in FIELD_REFERENCE_RE.finditer(rule.if_):
                    namespace, raw_field = match.groups()
                    field = raw_field.strip("\"'")
                    if namespace != "input":
                        errors.append(
                            f"{context}: unknown field namespace '{namespace}'"
                        )
                    elif field not in schema_fields:
                        errors.append(
                            f"{context}: unknown input field 'input.{field}'"
                        )


def load_unpivot_config(path: str | Path) -> UnpivotConfig:
    """Load and validate an unpivot YAML config."""

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
        return UnpivotConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(config_path, exc)) from exc


def _format_validation_error(config_path: Path, exc: ValidationError) -> str:
    lines = [f"{config_path}: invalid configuration"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        lines.append(f"- {location}: {error['msg']}")
    return "\n".join(lines)
