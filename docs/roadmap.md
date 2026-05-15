# Roadmap

## v0.2.0

- Basic `generate-config`
- Header-based YAML scaffolding
- Source mappings only

Future candidates:

- `--infer-types`
- `--template`
- Wizard
- AI-assisted config generation

## Phase 1

- CSV-to-CSV MVP
- YAML config
- CLI
- Pydantic config validation
- `validate-config`, `inspect`, `profile-input`
- `dry-run` and `run`
- Input and output validations
- Normalize functions
- Source, value, concat, map, when, lookup, and expression mappings
- Derived fields
- Filters
- `errors.csv`
- `skipped.csv`
- `summary.json`
- Main output CSV writer
- run_id logs
- Examples
- Tests

## Phase 2

- Enhanced `profile-input`
- Stronger date format conversion
- `zenkaku_to_hankaku`
- Multiple outputs
- More detailed checks
- HTML report
- Improvements for large CSV files

## Phase 3

- Excel input
- JSON input
- DB input and output
- Plugin system
- pandas/polars backend selection
- Web UI
- AI-assisted YAML generation

## Open Questions

- Which Phase 2 feature should be prioritized after the CSV-to-CSV MVP is stable.
- Whether large CSV improvements should focus on chunked pandas processing or a separate streaming design.
