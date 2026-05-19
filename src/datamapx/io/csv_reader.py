"""CSV readers for input and reference data."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from datamapx.config import InputConfig, ReferenceConfig, SchemaFieldConfig
from datamapx.io.errors import CsvReadError
from datamapx.transform.normalize import apply_normalizers
from datamapx.transform.types import convert_series_type

ROW_NUMBER_COLUMN = "__row_number"


def read_csv_frame(
    path: str,
    encoding: str,
    delimiter: str,
    header: bool,
    base_path: Path | None = None,
    nrows: int | None = None,
) -> pd.DataFrame:
    """Read a CSV into a dataframe with consistent error handling."""

    return _read_raw_csv(path, encoding, delimiter, header, base_path, nrows)


def read_input_csv(
    input_name: str,
    input_config: InputConfig,
    base_path: Path | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """Read an input CSV and return a normalized dataframe with schema field names."""

    raw_df = _read_raw_csv(
        input_config.path,
        input_config.encoding,
        input_config.delimiter,
        input_config.header,
        base_path,
        nrows=limit,
    )
    return apply_schema(raw_df, input_config.fields_schema, f"inputs.{input_name}")


def read_reference_csv(
    reference_name: str,
    reference_config: ReferenceConfig,
    base_path: Path | None = None,
) -> pd.DataFrame:
    """Read a reference CSV and validate configured reference keys."""

    raw_df = _read_raw_csv(
        reference_config.path,
        reference_config.encoding,
        reference_config.delimiter,
        reference_config.header,
        base_path,
        nrows=None,
    )
    if reference_config.fields_schema:
        df = apply_schema(raw_df, reference_config.fields_schema, f"references.{reference_name}")
    else:
        df = raw_df.copy()
        df.insert(0, ROW_NUMBER_COLUMN, range(1, len(df) + 1))

    key_columns = (
        [reference_config.key] if isinstance(reference_config.key, str) else reference_config.key
    )
    _validate_reference_keys(df, reference_name, key_columns)
    return df


def profile_input_csv(
    input_name: str,
    input_config: InputConfig,
    base_path: Path | None = None,
) -> dict[str, object]:
    """Return a simple profile for the configured input CSV."""

    df = read_input_csv(input_name, input_config, base_path)
    schema_fields = list(input_config.fields_schema)
    return {
        "input_name": input_name,
        "path": input_config.path,
        "encoding": input_config.encoding,
        "delimiter": input_config.delimiter,
        "rows": len(df),
        "columns": schema_fields,
        "missing_counts": {
            field: int(df[field].isna().sum()) for field in schema_fields if field in df.columns
        },
        "sample_values": {
            field: [str(value) for value in df[field].dropna().head(3).tolist()]
            for field in schema_fields
            if field in df.columns
        },
        "dtypes": {field: str(df[field].dtype) for field in schema_fields if field in df.columns},
    }


def apply_schema(
    raw_df: pd.DataFrame,
    schema: Mapping[str, SchemaFieldConfig],
    context: str,
) -> pd.DataFrame:
    """Apply schema column resolution, normalization, and type conversion."""

    result = pd.DataFrame(index=raw_df.index)
    result[ROW_NUMBER_COLUMN] = range(1, len(raw_df) + 1)

    for field_name, field_config in schema.items():
        source_column = _resolve_source_column(raw_df, field_name, field_config)
        if source_column is None:
            if field_config.required:
                raise CsvReadError(f"{context}.{field_name}: required column not found")
            result[field_name] = pd.Series(
                [pd.NA] * len(raw_df),
                index=raw_df.index,
                dtype="object",
            )
            continue

        series = raw_df[source_column]
        try:
            field_context = f"{context}.{field_name}"
            normalized = apply_normalizers(series, field_config.normalize, field_context)
            result[field_name] = convert_series_type(normalized, field_context, field_config)
        except ValueError as exc:
            raise CsvReadError(str(exc)) from exc

    return result


def _read_raw_csv(
    path: str,
    encoding: str,
    delimiter: str,
    header: bool,
    base_path: Path | None,
    nrows: int | None,
) -> pd.DataFrame:
    if not header:
        raise CsvReadError("header: false is not supported in Phase 1 CSV reader")

    csv_path = _resolve_path(path, base_path)
    try:
        return pd.read_csv(csv_path, encoding=encoding, sep=delimiter, dtype=object, nrows=nrows)
    except FileNotFoundError as exc:
        raise CsvReadError(f"{csv_path}: CSV file not found") from exc
    except UnicodeError as exc:
        message = f"{csv_path}: cannot decode CSV with encoding '{encoding}': {exc}"
        raise CsvReadError(message) from exc
    except OSError as exc:
        raise CsvReadError(f"{csv_path}: cannot read CSV: {exc}") from exc
    except pd.errors.ParserError as exc:
        raise CsvReadError(f"{csv_path}: cannot parse CSV: {exc}") from exc


def _resolve_path(path: str, base_path: Path | None) -> Path:
    csv_path = Path(path)
    if csv_path.is_absolute() or base_path is None:
        return csv_path
    return base_path / csv_path


def _resolve_source_column(
    raw_df: pd.DataFrame,
    field_name: str,
    field_config: SchemaFieldConfig,
) -> str | None:
    candidates = field_config.source_columns or [field_name]
    for candidate in candidates:
        if candidate in raw_df.columns:
            return candidate
    return None


def _validate_reference_keys(
    df: pd.DataFrame,
    reference_name: str,
    key_columns: list[str],
) -> None:
    for key_column in key_columns:
        if key_column not in df.columns:
            message = f"references.{reference_name}.key: missing key column '{key_column}'"
            raise CsvReadError(message)

    missing_mask = df[key_columns].isna().any(axis=1)
    if missing_mask.any():
        rows = df.loc[missing_mask, ROW_NUMBER_COLUMN].head(5).tolist()
        raise CsvReadError(f"references.{reference_name}.key: missing key values at rows {rows}")

    duplicate_mask = df.duplicated(subset=key_columns, keep=False)
    if duplicate_mask.any():
        rows = df.loc[duplicate_mask, ROW_NUMBER_COLUMN].head(5).tolist()
        keys = ", ".join(key_columns)
        raise CsvReadError(
            f"references.{reference_name}.key: duplicate key values for ({keys}) at rows {rows}"
        )
