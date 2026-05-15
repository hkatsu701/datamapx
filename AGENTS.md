# AGENTS.md

## Project

datamapx is a Python CLI tool for CSV data migration, transformation, and validation based on YAML configuration.

Phase 1 is limited to a robust CSV-to-CSV MVP. Do not implement Excel, DB, Web UI, multiple input joins, multiple outputs, plugins, or streaming in Phase 1.

## Core Principles

1. Configuration-driven
   - Do not write project-specific business logic directly in Python code.
   - Express transformation rules in YAML.

2. Reproducibility
   - The same input files and the same configuration file must produce the same output.

3. Explainability
   - Results must be explainable through `errors.csv`, `skipped.csv`, `summary.json`, and logs.

4. Safety
   - Do not silently accept undefined fields, missing lookup matches, duplicate lookup keys, invalid types, or transformation errors.
   - Do not use Python `eval` directly.
   - Do not execute arbitrary code from YAML.

5. MVP discipline
   - Keep Phase 1 focused on CSV-to-CSV migration and transformation.
   - Do not implement out-of-scope features unless explicitly instructed.

## Phase 1 Scope

- Single input CSV
- Multiple reference CSVs
- Single output CSV
- YAML config
- CLI
- Pydantic config validation
- CSV encoding and delimiter support
- Schema-based input validation
- Normalize functions
- `source`, `value`, `concat`, `map`, `when`, `lookup`, and `expression` mappings
- Derived fields
- Filters
- Input and output validations
- `errors.csv`
- `skipped.csv`
- `summary.json`
- `run_id` logs
- `dry-run`
- `inspect`
- `validate-config`
- `profile-input` simple version

## Development Rules

- Use Python 3.12+.
- Use `pandas`.
- Use `pydantic v2`.
- Use `typer`.
- Use `PyYAML`.
- Use `simpleeval` or another explicitly approved safe expression evaluator.
- Use `pytest`.
- Use `ruff`.
- Keep changes small and testable.
- Prefer clear, boring implementation over clever abstractions.
- Update documentation when behavior or configuration specification changes.
- Keep `docs/config-spec.md` as the source of truth for YAML behavior.

## Testing Policy

- Every feature must have tests.
- `pytest` must pass before marking a task complete.
- Config, mapping, lookup, validation, CLI, and report behavior must be tested.
- For documentation-only tasks, file existence and content checks are sufficient unless behavior changes.

## Security Policy

- Do not use Python `eval` directly.
- Do not execute arbitrary code from YAML.
- Expression support must be limited to a safe evaluator or a whitelisted expression system.
- Treat configuration errors as failures, not warnings, when they can affect output correctness.

## Reporting Policy

After each task, report:

- Changed files
- Implementation summary
- Commands run
- Test results
- Remaining issues or open questions
