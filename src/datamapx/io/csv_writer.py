"""CSV writer for output dataframes."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd

from datamapx.config import OutputConfig
from datamapx.io.errors import CsvWriteError


def resolve_output_path(path: str, base_path: Path | None = None) -> Path:
    """Resolve an output CSV path against an optional base directory."""

    output_path = Path(path)
    if output_path.is_absolute() or base_path is None:
        return output_path
    return base_path / output_path


def write_output_csv(
    output_df: pd.DataFrame,
    output_config: OutputConfig,
    base_path: Path | None = None,
) -> Path:
    """Write an output dataframe according to output CSV settings."""

    output_path = resolve_output_path(output_config.path, base_path)
    if output_path.exists() and output_config.if_exists == "error":
        raise CsvWriteError(f"{output_path}: output file already exists")
    if not output_config.header:
        raise CsvWriteError("outputs.header: false is not supported in Phase 1 CSV writer")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=output_config.encoding,
            newline="",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
        output_df.to_csv(
            temp_path,
            encoding=output_config.encoding,
            sep=output_config.delimiter,
            header=output_config.header,
            index=False,
            lineterminator=output_config.newline,
        )
        os.replace(temp_path, output_path)
    except OSError as exc:
        raise CsvWriteError(f"{output_path}: cannot write output CSV: {exc}") from exc
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
    return output_path
