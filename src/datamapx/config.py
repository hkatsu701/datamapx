"""Configuration models and YAML loading for datamapx."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from datamapx.exceptions import ConfigError

FIELD_REFERENCE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([^\s\[\]\(\),+\-*/%<>=!&|:]+)")
CHECK_RESERVED_NAMES = {"input_rows", "output_rows", "error_rows", "skipped_rows"}


class StrictModel(BaseModel):
    """Base model that rejects unknown keys in structured config sections."""

    model_config = ConfigDict(extra="forbid")


class ProjectConfig(StrictModel):
    name: str
    description: str | None = None


class SchemaFieldConfig(StrictModel):
    source_columns: list[str] | None = None
    type: Literal["string", "integer", "decimal", "boolean", "date"] = "string"
    required: bool = False
    date_format: str | None = None
    normalize: list[
        Literal["trim", "remove_commas", "remove_currency_symbol", "zenkaku_to_hankaku"]
    ] = Field(default_factory=list)
    true_values: list[str] | None = None
    false_values: list[str] | None = None

    @model_validator(mode="after")
    def validate_date_format(self) -> SchemaFieldConfig:
        if self.date_format is not None and self.type != "date":
            raise ValueError("date_format is only supported when type is date")
        if self.date_format == "":
            raise ValueError("date_format must not be empty")
        return self


class InputConfig(StrictModel):
    path: str
    encoding: str = "utf-8-sig"
    delimiter: str = ","
    header: bool = True
    fields_schema: dict[str, SchemaFieldConfig] = Field(default_factory=dict, alias="schema")


class ReferenceConfig(StrictModel):
    path: str
    encoding: str = "utf-8-sig"
    delimiter: str = ","
    header: bool = True
    fields_schema: dict[str, SchemaFieldConfig] = Field(default_factory=dict, alias="schema")
    key: str | list[str]
    on_duplicate: Literal["error"] = "error"


class FilterRule(StrictModel):
    if_: str = Field(alias="if")
    reason: str | None = None


class FiltersConfig(StrictModel):
    include: list[FilterRule] = Field(default_factory=list)
    exclude: list[FilterRule] = Field(default_factory=list)


class ConcatRule(StrictModel):
    values: list[Any]


class MapRule(StrictModel):
    source: str
    values: dict[str, Any]
    default: Any = None


class WhenRule(StrictModel):
    if_: str = Field(alias="if")
    then: Any


class LookupRule(StrictModel):
    reference: str
    key: str | list[str]
    value: str
    on_missing: Literal["error", "null", "empty", "default"] = "error"
    default: Any = None


class MappingRule(StrictModel):
    source: str | None = None
    value: Any = None
    concat: ConcatRule | None = None
    map: MapRule | None = None
    when: list[WhenRule] | None = None
    lookup: LookupRule | None = None
    expression: str | None = None
    default: Any = None

    @model_validator(mode="after")
    def validate_one_rule_type(self) -> MappingRule:
        rule_keys = {"source", "value", "concat", "map", "when", "lookup", "expression"}
        present = [key for key in rule_keys if key in self.model_fields_set]
        if len(present) != 1:
            raise ValueError(
                "mapping rule must define exactly one of: "
                "source, value, concat, map, when, lookup, expression"
            )
        return self


class OutputConfig(StrictModel):
    path: str
    encoding: str = "utf-8-sig"
    delimiter: str = ","
    header: bool = True
    newline: str = "\n"
    if_exists: Literal["error", "overwrite"] = "error"
    columns: list[str]


class ValidationRule(StrictModel):
    field: str
    output: str | None = None
    rule: Literal["required", "enum", "min", "max", "regex", "length"]
    values: list[Any] | None = None
    value: Any = None
    pattern: str | None = None
    min: int | None = None
    max: int | None = None

    @model_validator(mode="after")
    def validate_rule_requirements(self) -> ValidationRule:
        if self.rule == "enum" and not self.values:
            raise ValueError("enum validation requires values")
        if self.rule in {"min", "max"} and self.value is None:
            raise ValueError(f"{self.rule} validation requires value")
        if self.rule == "regex" and not self.pattern:
            raise ValueError("regex validation requires pattern")
        if self.rule == "length" and self.min is None and self.max is None:
            raise ValueError("length validation requires min or max")
        return self


class ValidationsConfig(StrictModel):
    input: list[ValidationRule] = Field(default_factory=list)
    output: list[ValidationRule] = Field(default_factory=list)


class CheckConfig(StrictModel):
    name: str
    rule: str


class ErrorHandlingConfig(StrictModel):
    on_validation_error: Literal["output_error", "stop"] = "output_error"
    on_lookup_missing: Literal["output_error", "stop"] = "output_error"
    on_transform_error: Literal["output_error", "stop"] = "output_error"
    max_errors: int = 1000
    error_output: str
    skipped_output: str
    include_original_row: bool = True


class RuntimeConfig(StrictModel):
    run_id: str = "auto"
    log_dir: str = "./logs"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    summary_output: str | None = None
    max_input_rows: int | None = None
    max_reference_rows: int | None = None

    @field_validator("max_input_rows", "max_reference_rows")
    @classmethod
    def validate_positive_limit(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("must be a positive integer")
        return value


class DatamapxConfig(StrictModel):
    version: Literal[1]
    project: ProjectConfig
    inputs: dict[str, InputConfig]
    references: dict[str, ReferenceConfig] = Field(default_factory=dict)
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    derived: dict[str, MappingRule] = Field(default_factory=dict)
    outputs: dict[str, OutputConfig]
    mappings: dict[str, dict[str, MappingRule]]
    validations: ValidationsConfig = Field(default_factory=ValidationsConfig)
    checks: list[CheckConfig] = Field(default_factory=list)
    error_handling: ErrorHandlingConfig
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    @model_validator(mode="after")
    def validate_phase1_consistency(self) -> DatamapxConfig:
        errors: list[str] = []

        if len(self.inputs) != 1:
            errors.append("inputs: Phase 1 supports exactly one input")
        input_name = next(iter(self.inputs), None)
        output_names = set(self.outputs)

        for output_name, output_config in self.outputs.items():
            if output_name not in self.mappings:
                errors.append(f"mappings.{output_name}: mappings for output are required")
                continue
            output_columns = set(output_config.columns)
            mapping_fields = set(self.mappings[output_name])
            missing = sorted(output_columns - mapping_fields)
            extra = sorted(mapping_fields - output_columns)
            if missing:
                errors.append(
                    f"mappings.{output_name}: missing mappings for output columns: "
                    f"{', '.join(missing)}"
                )
            if extra:
                errors.append(
                    f"mappings.{output_name}: mappings contain unknown output columns: "
                    f"{', '.join(extra)}"
                )

        unknown_mapping_outputs = sorted(set(self.mappings) - set(self.outputs))
        if unknown_mapping_outputs:
            errors.append(
                "mappings: contains unknown output names: " + ", ".join(unknown_mapping_outputs)
            )

        for ref_name, ref_config in self.references.items():
            if ref_config.on_duplicate != "error":
                errors.append(
                    f"references.{ref_name}.on_duplicate: Phase 1 supports only 'error'"
                )

        if input_name is not None:
            input_fields = set(self.inputs[input_name].fields_schema)
            derived_fields = set(self.derived)
            for field_name, rule in self.derived.items():
                self._validate_mapping_rule_references(
                    rule,
                    f"derived.{field_name}",
                    input_name,
                    input_fields,
                    derived_fields,
                    errors,
                )
            for map_output, output_mappings in self.mappings.items():
                for field_name, rule in output_mappings.items():
                    self._validate_mapping_rule_references(
                        rule,
                        f"mappings.{map_output}.{field_name}",
                        input_name,
                        input_fields,
                        derived_fields,
                        errors,
                    )

            self._validate_filter_references(input_name, input_fields, derived_fields, errors)
        self._validate_validation_fields(input_name, input_fields, output_names, errors)
        self._validate_check_references(errors)

        if errors:
            raise ValueError("; ".join(errors))
        return self

    def _validate_mapping_rule_references(
        self,
        rule: MappingRule,
        context: str,
        input_name: str,
        input_fields: set[str],
        derived_fields: set[str],
        errors: list[str],
    ) -> None:
        if rule.source is not None:
            self._validate_field_reference(
                rule.source, f"{context}.source", input_name, input_fields, derived_fields, errors
            )
        if rule.concat is not None:
            for index, value in enumerate(rule.concat.values):
                if isinstance(value, str) and _looks_like_field_reference(value):
                    self._validate_field_reference(
                        value,
                        f"{context}.concat.values[{index}]",
                        input_name,
                        input_fields,
                        derived_fields,
                        errors,
                    )
        if rule.map is not None:
            self._validate_field_reference(
                rule.map.source,
                f"{context}.map.source",
                input_name,
                input_fields,
                derived_fields,
                errors,
            )
        if rule.when is not None:
            for index, when_rule in enumerate(rule.when):
                self._validate_expression_references(
                    when_rule.if_,
                    f"{context}.when[{index}].if",
                    input_name,
                    input_fields,
                    derived_fields,
                    errors,
                )
                if isinstance(when_rule.then, str) and _looks_like_field_reference(when_rule.then):
                    self._validate_field_reference(
                        when_rule.then,
                        f"{context}.when[{index}].then",
                        input_name,
                        input_fields,
                        derived_fields,
                        errors,
                    )
        if "default" in rule.model_fields_set and isinstance(rule.default, str):
            if _looks_like_field_reference(rule.default):
                self._validate_field_reference(
                    rule.default,
                    f"{context}.default",
                    input_name,
                    input_fields,
                    derived_fields,
                    errors,
                )
        if rule.lookup is not None:
            if rule.lookup.reference not in self.references:
                errors.append(
                    f"{context}.lookup.reference: unknown reference '{rule.lookup.reference}'"
                )
            lookup_keys = (
                [rule.lookup.key] if isinstance(rule.lookup.key, str) else rule.lookup.key
            )
            for index, lookup_key in enumerate(lookup_keys):
                self._validate_field_reference(
                    lookup_key,
                    f"{context}.lookup.key[{index}]",
                    input_name,
                    input_fields,
                    derived_fields,
                    errors,
                )
        if rule.expression is not None:
            self._validate_expression_references(
                rule.expression,
                f"{context}.expression",
                input_name,
                input_fields,
                derived_fields,
                errors,
            )

    def _validate_filter_references(
        self,
        input_name: str,
        input_fields: set[str],
        derived_fields: set[str],
        errors: list[str],
    ) -> None:
        for index, filter_rule in enumerate(self.filters.include):
            self._validate_expression_references(
                filter_rule.if_,
                f"filters.include[{index}].if",
                input_name,
                input_fields,
                derived_fields,
                errors,
            )
        for index, filter_rule in enumerate(self.filters.exclude):
            self._validate_expression_references(
                filter_rule.if_,
                f"filters.exclude[{index}].if",
                input_name,
                input_fields,
                derived_fields,
                errors,
            )

    def _validate_validation_fields(
        self,
        input_name: str,
        input_fields: set[str],
        output_names: set[str],
        errors: list[str],
    ) -> None:
        for index, rule in enumerate(self.validations.input):
            context = f"validations.input[{index}].field"
            if "." not in rule.field:
                errors.append(
                    f"{context}: input validation field must reference the single input "
                    f"namespace '{input_name}': {rule.field}"
                )
                continue
            namespace, field = rule.field.split(".", 1)
            if namespace != input_name:
                errors.append(
                    f"{context}: input validation field must reference the single input "
                    f"namespace '{input_name}': {rule.field}"
                )
                continue
            if field not in input_fields:
                errors.append(f"{context}: unknown input field '{rule.field}'")

        for index, rule in enumerate(self.validations.output):
            context = f"validations.output[{index}].field"
            target_output = rule.output
            if target_output is None:
                if len(output_names) != 1:
                    errors.append(
                        f"{context}: output validation requires output when "
                        "multiple outputs are configured"
                    )
                    continue
                target_output = next(iter(output_names))
            if target_output not in self.outputs:
                errors.append(f"{context}: unknown output '{target_output}'")
                continue
            if rule.field not in self.outputs[target_output].columns:
                errors.append(
                    f"{context}: output validation field is not defined in output columns of "
                    f"{target_output}: {rule.field}"
                )

    def _validate_check_references(
        self,
        errors: list[str],
    ) -> None:
        for index, check in enumerate(self.checks):
            self._validate_check_rule(check.rule, f"checks[{index}].rule", errors)

    def _validate_check_rule(
        self,
        rule: str,
        context: str,
        errors: list[str],
    ) -> None:
        try:
            tree = ast.parse(rule, mode="eval")
        except SyntaxError:
            errors.append(f"{context}: invalid syntax")
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                errors.append(f"{context}: field references are not supported in checks")
                return
            if isinstance(node, ast.Call):
                errors.append(f"{context}: function calls are not supported in checks")
                return
            if isinstance(node, ast.Name) and node.id not in CHECK_RESERVED_NAMES:
                errors.append(f"{context}: unknown check variable '{node.id}'")
                return

    def _validate_expression_references(
        self,
        expression: str,
        context: str,
        input_name: str,
        input_fields: set[str],
        derived_fields: set[str],
        errors: list[str],
    ) -> None:
        for reference in _extract_field_references(expression):
            self._validate_field_reference(
                reference,
                context,
                input_name,
                input_fields,
                derived_fields,
                errors,
            )

    @staticmethod
    def _validate_field_reference(
        reference: str,
        context: str,
        input_name: str,
        input_fields: set[str],
        derived_fields: set[str],
        errors: list[str],
    ) -> None:
        if "." not in reference:
            errors.append(f"{context}: field reference must use '<namespace>.<field>'")
            return

        namespace, field = reference.split(".", 1)
        if namespace == input_name:
            if field not in input_fields:
                errors.append(f"{context}: unknown input field '{reference}'")
            return
        if namespace == "derived":
            if field not in derived_fields:
                errors.append(f"{context}: unknown derived field '{reference}'")
            return
        errors.append(f"{context}: unknown field namespace '{namespace}'")


def _looks_like_field_reference(value: str) -> bool:
    if "." not in value:
        return False
    namespace, field = value.split(".", 1)
    return namespace.isidentifier() and bool(field) and " " not in namespace


def _extract_field_references(expression: str) -> list[str]:
    """Extract Phase 1 field references from an expression-like string."""

    references: list[str] = []
    for match in FIELD_REFERENCE_RE.finditer(expression):
        namespace, raw_field = match.groups()
        field = raw_field.strip("\"'")
        if namespace in CHECK_RESERVED_NAMES:
            continue
        references.append(f"{namespace}.{field}")
    return references


def load_config(path: str | Path) -> DatamapxConfig:
    """Load and validate a datamapx YAML config."""

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
        return DatamapxConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(config_path, exc)) from exc


def _format_validation_error(config_path: Path, exc: ValidationError) -> str:
    lines = [f"{config_path}: invalid configuration"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        lines.append(f"- {location}: {error['msg']}")
    return "\n".join(lines)
