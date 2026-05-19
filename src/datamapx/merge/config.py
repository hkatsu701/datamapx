"""Configuration models and YAML loading for merge pipeline."""

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


class MergeInputConfig(StrictModel):
    path: str
    encoding: str = "utf-8-sig"
    delimiter: str = ","
    header: bool = True
    fields_schema: dict[str, SchemaFieldConfig] = Field(default_factory=dict, alias="schema")
    key: str | list[str]

    @model_validator(mode="after")
    def validate_key(self) -> MergeInputConfig:
        key_fields = [self.key] if isinstance(self.key, str) else self.key
        if not key_fields:
            raise ValueError("merge input key requires at least one field")
        if any(not field.strip() for field in key_fields):
            raise ValueError("merge input key fields must not be empty")
        return self


class MergeOutputRule(StrictModel):
    source: str | None = None
    first: list[str] | None = None
    last: list[str] | None = None
    sum: list[str] | None = None
    min: list[str] | None = None
    max: list[str] | None = None
    count: list[str] | None = None

    @model_validator(mode="after")
    def validate_one_rule_type(self) -> MergeOutputRule:
        rule_keys = {"source", "first", "last", "sum", "min", "max", "count"}
        present = [key for key in rule_keys if key in self.model_fields_set]
        if len(present) != 1:
            raise ValueError(
                "merge output rule must define exactly one of: "
                "source, first, last, sum, min, max, count"
            )
        if self.source is not None and not self.source.strip():
            raise ValueError("merge output rule requires a source reference")
        for field_name in ("first", "last", "sum", "min", "max", "count"):
            values = getattr(self, field_name)
            if values is not None and not values:
                raise ValueError(
                    f"merge output rule '{field_name}' requires at least one reference"
                )
        return self


class MergeSettings(StrictModel):
    base: str
    join_type: Literal["left", "inner"] = "left"
    columns: dict[str, MergeOutputRule]


class MergeConfig(StrictModel):
    version: Literal[1]
    project: ProjectConfig
    inputs: dict[str, MergeInputConfig]
    merge: MergeSettings
    output: OutputConfig
    error_handling: ErrorHandlingConfig
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    @model_validator(mode="after")
    def validate_merge_consistency(self) -> MergeConfig:
        errors: list[str] = []

        if len(self.inputs) < 2:
            errors.append("inputs: merge requires at least two inputs")

        if self.merge.base not in self.inputs:
            errors.append(f"merge.base: unknown base input '{self.merge.base}'")

        output_columns = set(self.output.columns)
        merge_columns = set(self.merge.columns)
        missing = sorted(output_columns - merge_columns)
        extra = sorted(merge_columns - output_columns)
        if missing:
            errors.append(
                "merge.columns: missing merge rules for output columns: " + ", ".join(missing)
            )
        if extra:
            errors.append(
                "merge.columns: merge rules contain unknown output columns: "
                + ", ".join(extra)
            )

        input_names = set(self.inputs)
        base_key_fields: list[str] = []
        if self.merge.base in self.inputs:
            base_key_fields = (
                [self.inputs[self.merge.base].key]
                if isinstance(self.inputs[self.merge.base].key, str)
                else self.inputs[self.merge.base].key
            )
        for input_name, input_config in self.inputs.items():
            key_fields = (
                [input_config.key]
                if isinstance(input_config.key, str)
                else input_config.key
            )
            schema_fields = set(input_config.fields_schema)
            if base_key_fields and len(key_fields) != len(base_key_fields):
                errors.append(
                    f"inputs.{input_name}.key: key count must match base input key count"
                )
            for key_field in key_fields:
                if schema_fields and key_field not in schema_fields:
                    errors.append(
                        f"inputs.{input_name}.key: unknown key field '{key_field}' in schema"
                    )

        for output_name, rule in self.merge.columns.items():
            self._validate_merge_rule_references(
                rule,
                f"merge.columns.{output_name}",
                input_names,
                self.inputs,
                errors,
            )

        if errors:
            raise ValueError("; ".join(errors))
        return self

    @staticmethod
    def _validate_merge_rule_references(
        rule: MergeOutputRule,
        context: str,
        input_names: set[str],
        inputs: dict[str, MergeInputConfig],
        errors: list[str],
    ) -> None:
        if rule.source is not None:
            MergeConfig._validate_merge_reference(rule.source, context, input_names, inputs, errors)
        for field_name in ("first", "last", "sum", "min", "max", "count"):
            values = getattr(rule, field_name)
            if values is None:
                continue
            if not isinstance(values, list):
                errors.append(f"{context}.{field_name}: must be a list of field references")
                continue
            for reference in values:
                MergeConfig._validate_merge_reference(
                    reference, f"{context}.{field_name}", input_names, inputs, errors
                )

    @staticmethod
    def _validate_merge_reference(
        reference: str,
        context: str,
        input_names: set[str],
        inputs: dict[str, MergeInputConfig],
        errors: list[str],
    ) -> None:
        match = FIELD_REFERENCE_RE.fullmatch(reference)
        if match is None:
            errors.append(f"{context}: field reference must use '<input>.<field>': {reference}")
            return
        namespace, field_name = match.groups()
        if namespace not in input_names:
            errors.append(f"{context}: unknown input namespace '{namespace}'")
            return
        schema_fields = set(inputs[namespace].fields_schema)
        if schema_fields and field_name not in schema_fields:
            errors.append(f"{context}: unknown input field '{reference}'")


def load_merge_config(path: str | Path) -> MergeConfig:
    """Load and validate a merge YAML config."""

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
        return MergeConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(config_path, exc)) from exc


def _format_validation_error(config_path: Path, exc: ValidationError) -> str:
    lines = [f"{config_path}: invalid configuration"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        lines.append(f"- {location}: {error['msg']}")
    return "\n".join(lines)
