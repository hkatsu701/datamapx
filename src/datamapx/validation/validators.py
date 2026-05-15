"""Row-level validation execution for Phase 1."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from datamapx.config import DatamapxConfig, ValidationRule
from datamapx.validation.errors import ValidationError, ValidationErrorRow

ValidationStage = Literal["input_validation", "output_validation"]


@dataclass(frozen=True)
class ValidationResult:
    """Validation result with surviving rows and row-level errors."""

    dataframe: pd.DataFrame
    row_numbers: pd.Series
    error_rows: list[ValidationErrorRow]
    rows_before_validation: int
    rows_after_validation: int

    @property
    def error_count(self) -> int:
        return len(self.error_rows)


def validate_input_rows(
    config: DatamapxConfig,
    input_df: pd.DataFrame,
    input_name: str,
) -> ValidationResult:
    """Validate normalized input rows before derived/filter stages."""

    row_numbers = _row_numbers(input_df)
    return _validate_rows(
        df=input_df,
        row_numbers=row_numbers,
        rules=config.validations.input,
        stage="input_validation",
        input_name=input_name,
        output_columns=None,
    )


def validate_output_rows(
    config: DatamapxConfig,
    output_df: pd.DataFrame,
    row_numbers: pd.Series,
    output_name: str,
) -> ValidationResult:
    """Validate mapped output rows before preview/report generation."""

    output_columns = set(config.outputs[output_name].columns)
    return _validate_rows(
        df=output_df,
        row_numbers=row_numbers,
        rules=config.validations.output,
        stage="output_validation",
        input_name=next(iter(config.inputs)),
        output_columns=output_columns,
    )


def _validate_rows(
    df: pd.DataFrame,
    row_numbers: pd.Series,
    rules: list[ValidationRule],
    stage: ValidationStage,
    input_name: str,
    output_columns: set[str] | None,
) -> ValidationResult:
    error_rows: list[ValidationErrorRow] = []
    invalid_indexes: set[Any] = set()

    for rule_index, rule in enumerate(rules):
        _validate_rule_config(rule, stage, rule_index, output_columns)

    for index, row in df.iterrows():
        row_errors: list[ValidationErrorRow] = []
        for rule in rules:
            field_name, value = _resolve_field_value(
                rule.field,
                df,
                row,
                input_name,
                output_columns,
                stage,
            )
            messages = _validate_rule_value(rule, value)
            for message in messages:
                row_errors.append(
                    ValidationErrorRow(
                        row_number=row_numbers.loc[index],
                        stage=stage,
                        field=field_name,
                        rule=rule.rule,
                        message=message,
                        normalized_row=row.to_dict() if stage == "input_validation" else None,
                        output_row=row.to_dict() if stage == "output_validation" else None,
                    )
                )
        if row_errors:
            invalid_indexes.add(index)
            error_rows.extend(row_errors)

    valid_df = df.drop(index=invalid_indexes)
    valid_row_numbers = row_numbers.drop(index=invalid_indexes)
    return ValidationResult(
        dataframe=valid_df,
        row_numbers=valid_row_numbers,
        error_rows=error_rows,
        rows_before_validation=len(df),
        rows_after_validation=len(valid_df),
    )


def _validate_rule_config(
    rule: ValidationRule,
    stage: ValidationStage,
    rule_index: int,
    output_columns: set[str] | None,
) -> None:
    if rule.rule == "enum" and not rule.values:
        raise ValidationError(f"{stage}[{rule_index}]: enum validation requires values")
    if rule.rule in {"min", "max"} and rule.value is None:
        raise ValidationError(f"{stage}[{rule_index}]: {rule.rule} validation requires value")
    if rule.rule == "regex" and not rule.pattern:
        raise ValidationError(f"{stage}[{rule_index}]: regex validation requires pattern")
    if rule.rule == "length" and rule.min is None and rule.max is None:
        raise ValidationError(f"{stage}[{rule_index}]: length validation requires min or max")
    if output_columns is not None and rule.field not in output_columns:
        raise ValidationError(
            f"{stage}[{rule_index}]: output validation field is not defined in output columns: "
            f"{rule.field}"
        )


def _resolve_field(
    field: str,
    df: pd.DataFrame,
    input_name: str,
    output_columns: set[str] | None,
    stage: ValidationStage,
) -> tuple[str, pd.Series]:
    field_name, series = _resolve_field_series(field, df, input_name, output_columns, stage)
    return field_name, series


def _resolve_field_value(
    field: str,
    df: pd.DataFrame,
    row: pd.Series,
    input_name: str,
    output_columns: set[str] | None,
    stage: ValidationStage,
) -> tuple[str, Any]:
    field_name, series = _resolve_field_series(field, df, input_name, output_columns, stage)
    return field_name, row[field_name]


def _resolve_field_series(
    field: str,
    df: pd.DataFrame,
    input_name: str,
    output_columns: set[str] | None,
    stage: ValidationStage,
) -> tuple[str, pd.Series]:
    if stage == "input_validation":
        if "." not in field:
            raise ValidationError(
                "input_validation field must reference the single input namespace "
                f"'{input_name}': {field}"
            )
        namespace, field_name = field.split(".", 1)
        if namespace != input_name:
            raise ValidationError(
                "input_validation field must reference the single input namespace "
                f"'{input_name}': {field}"
            )
        if field_name not in df.columns:
            raise ValidationError(f"input validation field is not defined: {field}")
        return field_name, df[field_name]

    if output_columns is not None and field not in output_columns:
        raise ValidationError(f"output validation field is not defined in output columns: {field}")
    if field not in df.columns:
        raise ValidationError(f"output validation field is not defined in output columns: {field}")
    return field, df[field]


def _validate_rule_value(rule: ValidationRule, value: Any) -> list[str]:
    if rule.rule == "required":
        if _is_missing(value):
            return ["required validation failed"]
        return []
    if _is_missing(value):
        return []

    if rule.rule == "enum":
        if value not in (rule.values or []):
            return [f"enum validation failed: {value!r} is not allowed"]
        return []
    if rule.rule == "min":
        numeric = _as_number(value)
        if numeric is None:
            return [f"min validation failed: {value!r} is not numeric"]
        if numeric < rule.value:
            return [f"min validation failed: {numeric} < {rule.value}"]
        return []
    if rule.rule == "max":
        numeric = _as_number(value)
        if numeric is None:
            return [f"max validation failed: {value!r} is not numeric"]
        if numeric > rule.value:
            return [f"max validation failed: {numeric} > {rule.value}"]
        return []
    if rule.rule == "regex":
        if not isinstance(value, str):
            value = str(value)
        if re.fullmatch(rule.pattern or "", value) is None:
            return [f"regex validation failed: {value!r} does not match {rule.pattern}"]
        return []
    if rule.rule == "length":
        text = value if isinstance(value, str) else str(value)
        length = len(text)
        if rule.min is not None and length < rule.min:
            return [f"length validation failed: {length} < {rule.min}"]
        if rule.max is not None and length > rule.max:
            return [f"length validation failed: {length} > {rule.max}"]
        return []
    raise ValidationError(f"unsupported validation rule: {rule.rule}")


def _row_numbers(df: pd.DataFrame) -> pd.Series:
    if "__row_number" in df.columns:
        return df["__row_number"].reset_index(drop=True)
    return pd.Series(range(1, len(df) + 1), index=df.index)


def _is_missing(value: Any) -> bool:
    if pd.isna(value):
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _as_number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        numeric = pd.to_numeric([value], errors="coerce")[0]
    except Exception:  # pragma: no cover - defensive
        return None
    if pd.isna(numeric):
        return None
    return numeric
