# Core Engine Readiness

This document summarizes the Phase 2 core engine scope that is ready before moving to Excel design work.
It covers only the CSV core engine and excludes wizard / Excel design tooling that is already implemented elsewhere.

## Ready Scope

The current core engine supports the following CSV-to-CSV workflows:

- `validate-config`
- `preflight`
- `inspect`
- `profile-input`
- `dry-run`
- `run`
- `merge`
- `union`
- `unpivot`
- `aggregate`
- `run-all`

It also includes the supporting runtime and report behavior needed for those commands:

- YAML config validation with `pydantic`
- CSV schema loading, normalization, type conversion, and column pruning
- `source`, `value`, `concat`, `map`, `lookup`, `when`, `expression`, `derived`, and `generate_id`
- Input and output validations, including `referential_integrity`
- Filters and run-level checks
- `errors.csv`, `skipped.csv`, `summary.json`, and optional `report.html`
- Atomic output CSV writes and atomic report writes
- Row guardrails such as `runtime.max_input_rows`, `runtime.max_reference_rows`, and `runtime.max_output_rows`
- Limited execution for `run --limit`
- `profile-input` enhancement, including `--limit`, `--chunk-size`, and JSON output

## Explicitly Out of Scope

The following remain outside the current core engine readiness scope:

- Excel parser and Excel-to-YAML conversion
- `design-to-yaml`
- manifest generation
- batch or script generation
- Web UI
- plugins
- JSON, database, and Excel input/output
- streaming migration and streaming writers
- pandas/polars backend selection
- AI-assisted YAML generation

## Purpose

The goal of this document is to separate the finished CSV core engine from the later Excel design layer. The CSV engine is ready for use as a stable foundation, and the next major step is to connect it to Excel design workflows without changing the existing core command behavior. `design-to-yaml` should be treated as a separate task only after the standard Excel design workbook format is finalized.
