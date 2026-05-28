# Roadmap

## v0.3.1

- `merge-wizard` command for interactive merge YAML generation
- Merge YAML scaffolding from CSV headers and merge rules
- Merge-wizard output columns selected by number
- Merge-wizard output column rename assistance
- Merge-wizard purpose-based templates
- Merge-wizard clearer retry messages for invalid input
- Merge-wizard limited back button for the last step
- Merge-wizard natural-language review output

## merge-wizard usability roadmap

Goal: make `merge-wizard` usable by people who know what they want to merge but do not write YAML.

Each step should be small, covered by focused tests, and documented in `README.md`, `README.ja.md`, and `docs/cli-spec.md` when behavior changes.

Completed:

- `examples/05_merge_wizard/`

Future candidates:

- `--infer-types`
- `--template`
- AI-assisted config generation

## migration-wizard completion roadmap

Goal: keep `migration-wizard` usable for people who want a complete `migration.yml` but do not write YAML by hand.

Completed:

- `examples/06_migration_wizard/`

Future candidates:

- Guided natural-language explanations for advanced rule choices
- More template-driven presets for common migration patterns

## practical migration sample roadmap

Goal: keep adding end-to-end migration examples that behave like real projects and double as regression fixtures.

Completed:

- `examples/07_practical_migration/`

Future candidates:

- Additional billing, customer master, and inventory-style migration examples

## Excel design to YAML roadmap

Goal: generate multiple `merge.yml` and `migration.yml` files, plus execution scripts, from a standard DataMapX Excel migration design workbook.

Completed:

- `docs/excel-design-spec.md`
- `examples/08_excel_design/`

Future candidates:

- Excel parser and intermediate design model
- `design-to-yaml` CLI
- manifest and batch/script generation

## v0.3.0

- `merge` command for staging multiple CSV inputs
- Exact key-based joins
- Explicit aggregation rules for staging CSV creation

## v0.2.0

- Basic `generate-config`
- Header-based YAML scaffolding
- Source mappings only

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
- Run-level checks
- Main output CSV writer
- run_id logs
- Examples
- Tests

## Phase 2

Completed:

- Multiple outputs
- [examples/10_multiple_outputs/](../examples/10_multiple_outputs/README.md)
- Enhanced `profile-input`
- Date format conversion
- `zenkaku_to_hankaku` normalize
- HTML report

Future candidates:

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
