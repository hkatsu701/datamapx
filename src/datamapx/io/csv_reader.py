"""CSV readers for input and reference data."""

from __future__ import annotations

import csv
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from datamapx.config import InputConfig, ReferenceConfig, SchemaFieldConfig
from datamapx.io.errors import CsvReadError
from datamapx.transform.normalize import apply_normalizers
from datamapx.transform.types import convert_series_type

ROW_NUMBER_COLUMN = "__row_number"


@dataclass(frozen=True)
class ColumnProfile:
    """Profile metrics for one normalized input column."""

    name: str
    schema_type: str
    dtype: str
    missing_count: int
    missing_rate: float
    non_null_count: int
    unique_count: int
    duplicate_count: int
    sample_values: list[Any]
    top_values: list[dict[str, Any]] = field(default_factory=list)
    min_length: int | None = None
    max_length: int | None = None
    min: float | int | None = None
    max: float | int | None = None
    mean: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "schema_type": self.schema_type,
            "dtype": self.dtype,
            "missing_count": self.missing_count,
            "missing_rate": self.missing_rate,
            "non_null_count": self.non_null_count,
            "unique_count": self.unique_count,
            "duplicate_count": self.duplicate_count,
            "sample_values": [_json_safe(item) for item in self.sample_values],
        }
        if self.top_values:
            data["top_values"] = [
                {"value": _json_safe(item["value"]), "count": item["count"]}
                for item in self.top_values
            ]
        if self.min_length is not None:
            data["min_length"] = self.min_length
        if self.max_length is not None:
            data["max_length"] = self.max_length
        if self.min is not None:
            data["min"] = self.min
        if self.max is not None:
            data["max"] = self.max
        if self.mean is not None:
            data["mean"] = self.mean
        return data


@dataclass(frozen=True)
class InputProfile:
    """Profile summary for one normalized input CSV."""

    input_name: str
    path: str
    encoding: str
    delimiter: str
    profiled_rows: int
    limit: int | None
    columns: list[ColumnProfile]

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_name": self.input_name,
            "path": self.path,
            "encoding": self.encoding,
            "delimiter": self.delimiter,
            "profiled_rows": self.profiled_rows,
            "limit": self.limit,
            "columns": [column.to_dict() for column in self.columns],
        }


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
    max_rows: int | None = None,
) -> pd.DataFrame:
    """Read an input CSV and return a normalized dataframe with schema field names."""

    if not input_config.header:
        raise CsvReadError("header: false is not supported in Phase 1 CSV reader")

    if max_rows is not None:
        csv_path = _resolve_path(input_config.path, base_path)
        row_count = _count_csv_data_rows(csv_path, input_config.encoding, input_config.delimiter)
        if row_count > max_rows:
            raise CsvReadError(
                f"inputs.{input_name}: row count {row_count} exceeds "
                f"runtime.max_input_rows {max_rows}"
            )

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
    max_rows: int | None = None,
) -> pd.DataFrame:
    """Read a reference CSV and validate configured reference keys."""

    if not reference_config.header:
        raise CsvReadError("header: false is not supported in Phase 1 CSV reader")

    if max_rows is not None:
        csv_path = _resolve_path(reference_config.path, base_path)
        row_count = _count_csv_data_rows(
            csv_path,
            reference_config.encoding,
            reference_config.delimiter,
        )
        if row_count > max_rows:
            raise CsvReadError(
                f"references.{reference_name}: row count {row_count} exceeds "
                f"runtime.max_reference_rows {max_rows}"
            )

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
    limit: int | None = None,
    max_rows: int | None = None,
) -> InputProfile:
    """Return a profile for the configured input CSV."""

    df = read_input_csv(
        input_name,
        input_config,
        base_path,
        limit=limit,
        max_rows=max_rows,
    )
    columns = [
        _profile_column(field_name, field_config, df[field_name])
        for field_name, field_config in input_config.fields_schema.items()
        if field_name in df.columns
    ]
    return InputProfile(
        input_name=input_name,
        path=input_config.path,
        encoding=input_config.encoding,
        delimiter=input_config.delimiter,
        profiled_rows=len(df),
        limit=limit,
        columns=columns,
    )


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


def _count_csv_data_rows(csv_path: Path, encoding: str, delimiter: str) -> int:
    try:
        with csv_path.open("r", encoding=encoding, newline="") as file:
            reader = csv.reader(file, delimiter=delimiter)
            next(reader, None)
            return sum(1 for row in reader if row != [])
    except FileNotFoundError as exc:
        raise CsvReadError(f"{csv_path}: CSV file not found") from exc
    except UnicodeError as exc:
        message = f"{csv_path}: cannot decode CSV with encoding '{encoding}': {exc}"
        raise CsvReadError(message) from exc
    except OSError as exc:
        raise CsvReadError(f"{csv_path}: cannot read CSV: {exc}") from exc
    except csv.Error as exc:
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


def _profile_column(
    field_name: str,
    field_config: SchemaFieldConfig,
    series: pd.Series,
) -> ColumnProfile:
    profiled_rows = len(series)
    missing_count = int(series.isna().sum())
    non_null = series.dropna()
    non_null_count = int(len(non_null))
    unique_count = int(non_null.nunique(dropna=True))
    duplicate_count = int(non_null_count - unique_count)
    missing_rate = float(missing_count / profiled_rows) if profiled_rows else 0.0
    sample_values = [_json_safe(value) for value in non_null.head(3).tolist()]

    top_values: list[dict[str, Any]] = []
    min_length: int | None = None
    max_length: int | None = None
    min_value: float | int | None = None
    max_value: float | int | None = None
    mean_value: float | None = None

    if field_config.type == "string":
        top_values = [
            {"value": _json_safe(value), "count": int(count)}
            for value, count in non_null.value_counts(dropna=True).head(5).items()
        ]
        lengths = non_null.astype(str).map(len)
        if not lengths.empty:
            min_length = int(lengths.min())
            max_length = int(lengths.max())
    elif field_config.type in {"integer", "decimal"}:
        numeric = pd.to_numeric(non_null, errors="coerce")
        if not numeric.empty:
            min_value = _json_safe(numeric.min())
            max_value = _json_safe(numeric.max())
            mean_value = float(numeric.mean())

    return ColumnProfile(
        name=field_name,
        schema_type=field_config.type,
        dtype=str(series.dtype),
        missing_count=missing_count,
        missing_rate=missing_rate,
        non_null_count=non_null_count,
        unique_count=unique_count,
        duplicate_count=duplicate_count,
        sample_values=sample_values,
        top_values=top_values,
        min_length=min_length,
        max_length=max_length,
        min=min_value,
        max=max_value,
        mean=mean_value,
    )


def _json_safe(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:  # pragma: no cover - defensive
            return str(value)
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # pragma: no cover - defensive
            return str(value)
    return value
