"""Minimal mapping engine for output dataframe construction."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from datamapx.config import DatamapxConfig, LookupRule, MappingRule, ReferenceConfig
from datamapx.transform.conditions import evaluate_condition
from datamapx.transform.errors import MappingError
from datamapx.transform.expressions import (
    evaluate_expression_series,
    extract_expression_references,
)

FIELD_REFERENCE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")


def build_output_dataframe(
    config: DatamapxConfig,
    input_df: pd.DataFrame,
    reference_dfs: dict[str, pd.DataFrame] | None = None,
    derived_values: dict[str, pd.Series] | None = None,
) -> pd.DataFrame:
    """Build the single Phase 1 output dataframe from supported mapping rules."""

    input_name = next(iter(config.inputs))
    output_name, output_config = next(iter(config.outputs.items()))
    output_mappings = config.mappings.get(output_name, {})
    reference_dfs = reference_dfs or {}
    derived_values = (
        compute_derived_fields(config, input_df, reference_dfs)
        if derived_values is None
        else derived_values
    )

    output_columns = output_config.columns
    missing = sorted(set(output_columns) - set(output_mappings))
    extra = sorted(set(output_mappings) - set(output_columns))
    if missing:
        raise MappingError(f"mappings.{output_name}: missing mappings for: {', '.join(missing)}")
    if extra:
        raise MappingError(f"mappings.{output_name}: unknown mapping fields: {', '.join(extra)}")

    output_df = pd.DataFrame(index=input_df.index)
    for output_column in output_columns:
        output_df[output_column] = apply_mapping_rule(
            output_mappings[output_column],
            input_df,
            input_name,
            output_column,
            config.references,
            reference_dfs,
            derived_values,
        )
    return output_df.reset_index(drop=True)


def compute_derived_fields(
    config: DatamapxConfig,
    input_df: pd.DataFrame,
    reference_dfs: dict[str, pd.DataFrame] | None = None,
) -> dict[str, pd.Series]:
    """Compute derived fields in dependency order."""

    input_name = next(iter(config.inputs))
    reference_dfs = reference_dfs or {}
    derived_values: dict[str, pd.Series] = {}
    visiting: set[str] = set()
    visited: set[str] = set()

    def compute_one(field_name: str) -> None:
        if field_name in visited:
            return
        if field_name in visiting:
            raise MappingError(f"derived field cycle detected: {field_name}")
        if field_name not in config.derived:
            raise MappingError(f"derived field is not defined: derived.{field_name}")

        visiting.add(field_name)
        for dependency in _derived_dependencies(config.derived[field_name]):
            compute_one(dependency)
        try:
            derived_values[field_name] = apply_mapping_rule(
                config.derived[field_name],
                input_df,
                input_name,
                f"derived.{field_name}",
                config.references,
                reference_dfs,
                derived_values,
            )
        except MappingError as exc:
            raise MappingError(f"derived.{field_name}: {exc}") from exc
        visiting.remove(field_name)
        visited.add(field_name)

    for field_name in config.derived:
        compute_one(field_name)
    return derived_values


def apply_mapping_rule(
    rule: MappingRule,
    input_df: pd.DataFrame,
    input_name: str,
    output_column: str,
    reference_configs: dict[str, ReferenceConfig],
    reference_dfs: dict[str, pd.DataFrame],
    derived_values: dict[str, pd.Series] | None = None,
) -> pd.Series:
    """Apply one supported mapping rule."""

    derived_values = derived_values or {}
    if rule.source is not None:
        return _source_series(rule.source, input_df, input_name, output_column, derived_values)
    if "value" in rule.model_fields_set:
        return pd.Series([rule.value] * len(input_df), index=input_df.index)
    if rule.concat is not None:
        return _concat_series(
            rule.concat.values,
            input_df,
            input_name,
            output_column,
            derived_values,
        )
    if rule.map is not None:
        return _map_series(
            rule.map.source,
            rule.map.values,
            rule.map.default,
            input_df,
            input_name,
            derived_values,
        )
    if rule.when is not None:
        return _when_series(rule, input_df, input_name, output_column, derived_values)
    if rule.expression is not None:
        return evaluate_expression_series(
            rule.expression,
            input_df,
            input_name,
            output_column,
            derived_values,
        )
    if rule.lookup is not None:
        return _lookup_series(
            rule.lookup,
            input_df,
            input_name,
            output_column,
            reference_configs,
            reference_dfs,
            derived_values,
        )
    raise MappingError(f"{output_column}: unsupported mapping rule")


def _source_series(
    reference: str,
    input_df: pd.DataFrame,
    input_name: str,
    output_column: str,
    derived_values: dict[str, pd.Series],
) -> pd.Series:
    series = _reference_series(reference, input_df, input_name, output_column, derived_values)
    if series is None:
        raise MappingError(f"{output_column}: source field is not defined: {reference}")
    return series


def _concat_series(
    values: list[Any],
    input_df: pd.DataFrame,
    input_name: str,
    output_column: str,
    derived_values: dict[str, pd.Series],
) -> pd.Series:
    result = pd.Series([""] * len(input_df), index=input_df.index, dtype="object")
    for value in values:
        if isinstance(value, str) and _looks_like_reference(value):
            series = _reference_series(value, input_df, input_name, output_column, derived_values)
            if series is None:
                raise MappingError(f"{output_column}: concat field is not defined: {value}")
            part = series.fillna("").astype(str)
        else:
            part = "" if pd.isna(value) else str(value)
        result = result + part
    return result


def _map_series(
    source: str,
    values: dict[str, Any],
    default: Any,
    input_df: pd.DataFrame,
    input_name: str,
    derived_values: dict[str, pd.Series],
) -> pd.Series:
    source_series = _reference_series(source, input_df, input_name, "map", derived_values)
    if source_series is None:
        raise MappingError(f"map: source field is not defined: {source}")

    mapped = source_series.map(values)
    unmatched = source_series.notna() & mapped.isna()
    if unmatched.any() and default is None:
        examples = ", ".join(repr(value) for value in source_series.loc[unmatched].head(5))
        raise MappingError(f"map: unmapped values without default for {source}: {examples}")
    if default is not None:
        mapped = mapped.where(~unmatched, default)
    return mapped


def _lookup_series(
    lookup: LookupRule,
    input_df: pd.DataFrame,
    input_name: str,
    output_column: str,
    reference_configs: dict[str, ReferenceConfig],
    reference_dfs: dict[str, pd.DataFrame],
    derived_values: dict[str, pd.Series],
) -> pd.Series:
    if lookup.reference not in reference_configs:
        raise MappingError(f"{output_column}: lookup reference is not defined: {lookup.reference}")
    if lookup.reference not in reference_dfs:
        raise MappingError(f"{output_column}: lookup reference is not loaded: {lookup.reference}")

    reference_config = reference_configs[lookup.reference]
    reference_df = reference_dfs[lookup.reference]
    if lookup.value not in reference_df.columns:
        raise MappingError(
            f"{output_column}: lookup value column is not defined in reference "
            f"'{lookup.reference}': {lookup.value}"
        )

    lookup_key_is_list = isinstance(lookup.key, list)
    reference_key_is_list = isinstance(reference_config.key, list)
    input_key_refs = [lookup.key] if isinstance(lookup.key, str) else lookup.key
    reference_keys = (
        [reference_config.key]
        if isinstance(reference_config.key, str)
        else reference_config.key
    )
    _validate_lookup_key_shape(
        input_key_refs,
        reference_keys,
        lookup_key_is_list,
        reference_key_is_list,
        output_column,
    )

    input_key_series = [
        _reference_series(input_key_ref, input_df, input_name, output_column, derived_values)
        for input_key_ref in input_key_refs
    ]
    for input_key_ref, series in zip(input_key_refs, input_key_series, strict=True):
        if series is None:
            raise MappingError(f"{output_column}: lookup key field is not defined: {input_key_ref}")
    for reference_key in reference_keys:
        if reference_key not in reference_df.columns:
            raise MappingError(
                f"{output_column}: reference key column is not defined in reference "
                f"'{lookup.reference}': {reference_key}"
            )

    lookup_index = {
        _key_tuple(row, reference_keys): row[lookup.value]
        for _, row in reference_df.iterrows()
    }

    output_values: list[Any] = []
    missing_keys: list[tuple[Any, ...]] = []
    for row_index in input_df.index:
        key = tuple(series.loc[row_index] for series in input_key_series if series is not None)
        if key in lookup_index:
            output_values.append(lookup_index[key])
        else:
            output_values.append(_missing_lookup_value(lookup, key, output_column))
            if lookup.on_missing == "error":
                missing_keys.append(key)

    if missing_keys:
        raise MappingError(
            f"lookup missing: reference={lookup.reference} key={_format_key(missing_keys[0])}"
        )
    return pd.Series(output_values, index=input_df.index)


def _when_series(
    rule: MappingRule,
    input_df: pd.DataFrame,
    input_name: str,
    output_column: str,
    derived_values: dict[str, pd.Series],
) -> pd.Series:
    if not isinstance(rule.when, list):
        raise MappingError(f"{output_column}: when must be a list")

    has_default = "default" in rule.model_fields_set
    output = pd.Series([pd.NA] * len(input_df), index=input_df.index, dtype="object")
    matched = pd.Series([False] * len(input_df), index=input_df.index)

    for index, item in enumerate(rule.when):
        condition, then_value = _when_item_parts(item, output_column, index)
        if _looks_like_reference(str(then_value)):
            raise MappingError(f"{output_column}: when.then field references are not supported")
        condition_result = evaluate_condition(condition, input_df, input_name, derived_values)
        apply_mask = condition_result & ~matched
        output.loc[apply_mask] = then_value
        matched = matched | apply_mask

    unmatched = ~matched
    if unmatched.any():
        if not has_default:
            raise MappingError(f"{output_column}: no when condition matched and default is missing")
        if _looks_like_reference(str(rule.default)):
            raise MappingError(f"{output_column}: when default field references are not supported")
        output.loc[unmatched] = rule.default
    return output


def _when_item_parts(item: Any, output_column: str, index: int) -> tuple[str, Any]:
    if isinstance(item, dict):
        if "if" not in item:
            raise MappingError(f"{output_column}: when[{index}] is missing if")
        if "then" not in item:
            raise MappingError(f"{output_column}: when[{index}] is missing then")
        return item["if"], item["then"]
    if not hasattr(item, "if_"):
        raise MappingError(f"{output_column}: when[{index}] is missing if")
    if not hasattr(item, "then"):
        raise MappingError(f"{output_column}: when[{index}] is missing then")
    return item.if_, item.then


def _validate_lookup_key_shape(
    input_key_refs: list[str],
    reference_keys: list[str],
    lookup_key_is_list: bool,
    reference_key_is_list: bool,
    output_column: str,
) -> None:
    if not lookup_key_is_list and reference_key_is_list:
        raise MappingError(
            f"{output_column}: lookup.key is string but reference.key is composite"
        )
    if lookup_key_is_list and not reference_key_is_list:
        raise MappingError(
            f"{output_column}: lookup.key is composite but reference.key is string"
        )
    if len(input_key_refs) != len(reference_keys):
        raise MappingError(
            f"{output_column}: lookup.key count does not match reference.key count"
        )


def _key_tuple(row: pd.Series, key_columns: list[str]) -> tuple[Any, ...]:
    return tuple(row[column] for column in key_columns)


def _missing_lookup_value(lookup: LookupRule, key: tuple[Any, ...], output_column: str) -> Any:
    if lookup.on_missing == "error":
        return pd.NA
    if lookup.on_missing == "default":
        if "default" not in lookup.model_fields_set:
            raise MappingError(
                f"{output_column}: lookup on_missing 'default' requires default value"
            )
        return lookup.default
    if lookup.on_missing == "empty":
        return ""
    if lookup.on_missing == "null":
        return pd.NA
    raise MappingError(f"{output_column}: unsupported lookup on_missing: {lookup.on_missing}")


def _format_key(key: tuple[Any, ...]) -> Any:
    if len(key) == 1:
        return key[0]
    return key


def _reference_series(
    reference: str,
    input_df: pd.DataFrame,
    input_name: str,
    context: str,
    derived_values: dict[str, pd.Series],
) -> pd.Series | None:
    if "." not in reference:
        raise MappingError(f"{context}: field reference must use '<input>.<field>': {reference}")
    namespace, field_name = reference.split(".", 1)
    if namespace == "derived":
        return derived_values.get(field_name)
    if namespace != input_name:
        raise MappingError(f"{context}: unknown input namespace in mapping: {reference}")
    if field_name not in input_df.columns:
        return None
    return input_df[field_name]


def _looks_like_reference(value: str) -> bool:
    if "." not in value:
        return False
    namespace, field_name = value.split(".", 1)
    return namespace.isidentifier() and bool(field_name) and " " not in namespace


def _derived_dependencies(rule: MappingRule) -> set[str]:
    dependencies: set[str] = set()
    if rule.source is not None:
        _add_derived_reference(rule.source, dependencies)
    if rule.concat is not None:
        for value in rule.concat.values:
            if isinstance(value, str):
                _add_derived_reference(value, dependencies)
    if rule.map is not None:
        _add_derived_reference(rule.map.source, dependencies)
    if rule.lookup is not None:
        lookup_keys = [rule.lookup.key] if isinstance(rule.lookup.key, str) else rule.lookup.key
        for lookup_key in lookup_keys:
            _add_derived_reference(lookup_key, dependencies)
    if rule.when is not None:
        for when_rule in rule.when:
            dependencies.update(_derived_references_in_text(when_rule.if_))
    if rule.expression is not None:
        dependencies.update(
            reference.split(".", 1)[1]
            for reference in extract_expression_references(rule.expression)
            if reference.startswith("derived.")
        )
    return dependencies


def _add_derived_reference(value: str, dependencies: set[str]) -> None:
    if value.startswith("derived.") and _looks_like_reference(value):
        dependencies.add(value.split(".", 1)[1])


def _derived_references_in_text(text: str) -> set[str]:
    return {
        match.group(2)
        for match in FIELD_REFERENCE_RE.finditer(text)
        if match.group(1) == "derived"
    }
