# datamapx

For Japanese documentation, see [README.ja.md](README.ja.md).

datamapx is a Python CLI for CSV-to-CSV migration, transformation, and validation driven by YAML.

It is designed for projects where the migration rules should live in configuration, not in ad hoc Python scripts.

Current release: v0.3.1.

## What It Can Do

- Read one input CSV and multiple reference CSVs.
- Merge multiple CSVs into one staging CSV before conversion.
- Union same-format CSVs into one output CSV by appending rows in input order.
- Run several existing YAML jobs in sequence with a `run-all.yml` file.
- Create a migration YAML scaffold interactively with `migration-wizard` using prompts for paths, output column count and names, input column read settings, and optional advanced authoring for reference column read settings, references, derived fields, mapping rules, validations, filters, checks, output settings, error handling, runtime settings, and a final natural-language review before saving.
- Create a merge YAML scaffold interactively with `merge-wizard` using numbered selections for inputs, output columns, renames, and rules, with optional purpose-based templates, Japanese retry prompts for invalid input, a natural-language final review, and a limited back step from the final review. Input previews and numbered choices are shown in the same order, and long labels wrap for readability.
- Normalize and type-convert input fields from schema definitions.
- `normalize` supports `trim`, `zenkaku_to_hankaku`, `remove_commas`, and `remove_currency_symbol`.
- Use `date_format` on `type: date` fields when you need strict parsing of known date strings.
- When `schema` is defined, datamapx prunes CSV reads to the columns needed for that schema and keeps every `source_columns` candidate in the read set.
- Set `runtime.max_input_rows` and `runtime.max_reference_rows` to guard migration input and reference CSV loads before `profile-input`, `dry-run`, or `run` reads them.
- Use parentheses in `when` and `filters` conditions to group supported boolean logic.
- Validate a standard Excel design workbook with `validate-design`, which can optionally write `design-summary.json` and `design-errors.csv`.
- Map output columns with `source`, `value`, `concat`, `map`, `lookup`, `when`, `expression`, and `derived`.
- Apply filters, validations, and run-level checks before writing the final output.
- Write `errors.csv`, `skipped.csv`, `summary.json`, and optional `report.html`.
- Write output CSVs atomically so a failed output write does not overwrite the previous file.
- Run `generate-config`, `merge`, `union`, `merge-wizard`, `validate-config`, `validate-design`, `inspect`, `profile-input`, `dry-run`, and `run`.

## What It Does Not Do in Phase 1

- Excel, JSON, or database input/output
- Multiple input joins
- Multiple output files
- Web UI
- Plugins
- Streaming processing
- AI-assisted YAML generation

## Installation / Development Setup

Create a virtual environment and install development dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Quick Start

Validate a configuration:

```bash
datamapx validate-config examples/01_basic_mapping/migration.yml
```

Preview the pipeline without writing the main output CSV:

```bash
datamapx dry-run examples/01_basic_mapping/migration.yml --limit 5
```

Run the migration and write the main output CSV plus reports:

```bash
datamapx run examples/01_basic_mapping/migration.yml
```

Or create a starter YAML first:

```bash
datamapx generate-config \
  --input examples/01_basic_mapping/input/users.csv \
  --output examples/01_basic_mapping/output/generated_users_out.csv \
  --config /tmp/generated_migration.yml \
  --input-name users \
  --output-name users_out

datamapx validate-config /tmp/generated_migration.yml
datamapx dry-run /tmp/generated_migration.yml --limit 5
datamapx run /tmp/generated_migration.yml
```

Generate a starter configuration from a CSV header:

```bash
datamapx generate-config \
  --input examples/01_basic_mapping/input/users.csv \
  --output examples/01_basic_mapping/output/generated_users_out.csv \
  --config /tmp/generated_migration.yml \
  --input-name users \
  --output-name users_out
```

## CLI Commands

- `generate-config` creates a basic YAML scaffold from CSV headers.
- `migration-wizard` interactively generates a migration YAML scaffold with explicit output column count and names, input column read settings, reference column read settings, advanced support for `lookup`, `derived`, `validations`, `filters`, `checks`, output settings, error handling, runtime settings, and a final review screen with limited redo.
- `merge` combines multiple CSV inputs into a staging CSV.
- `union` appends same-format CSV inputs into a single CSV while enforcing required keys and duplicate-key checks.
- `run-all` runs multiple existing YAML jobs sequentially and stops at the first failure.
- `merge-wizard` interactively generates a merge YAML scaffold with numbered selections, fixed steps, rename confirmation, optional purpose-based templates, retry prompts for invalid input, a natural-language final review, and a limited back step from the final review. Input previews and numbered choices use the same ordering, and long labels wrap for readability.
- `validate-config` validates YAML structure, references, and Phase 1 constraints.
- `when` and `filters` conditions can use parentheses for boolean grouping.
- `validate-design` validates a standard Excel design workbook and can optionally write `design-summary.json` and `design-errors.csv`.
- `inspect` prints a human-readable summary of the configuration.
- `profile-input` shows an enhanced profile for the normalized input dataframe, with optional `--limit` sampling, `--chunk-size` chunked profiling, and `--format json` output.
- `dry-run` executes the pipeline in memory and shows previews.
- `run` writes the main output CSV plus `errors.csv`, `skipped.csv`, and `summary.json`.

### Example

```yaml
version: 1

project:
  name: user_migration

inputs:
  users:
    path: ./input/users.csv
    encoding: utf-8-sig
    delimiter: ","
    header: true
    schema:
      user_id:
        type: string
        required: true
        normalize: [trim]

outputs:
  users_out:
    path: ./output/users_out.csv
    encoding: utf-8-sig
    delimiter: ","
    header: true
    newline: "\n"
    if_exists: overwrite
    columns:
      - id

mappings:
  users_out:
    id:
      source: users.user_id
```

## Examples

Each example contains a runnable `migration.yml`, input files, and expected artifacts.

- [01_basic_mapping](examples/01_basic_mapping/README.md)
- [02_lookup](examples/02_lookup/README.md)
- [03_validation_errors](examples/03_validation_errors/README.md)
- [04_japanese_csv](examples/04_japanese_csv/README.md)
- [05_merge_wizard](examples/05_merge_wizard/README.md)
- [09_union](examples/09_union/README.md)
- [06_migration_wizard](examples/06_migration_wizard/README.md)
- [07_practical_migration](examples/07_practical_migration/README.md)
- [08_excel_design](examples/08_excel_design/README.md)
- [10_multiple_outputs](examples/10_multiple_outputs/README.md)

## Output Files

- Output CSVs: the transformed data selected by each `outputs.<name>.columns`
- `errors.csv`: validation and runtime error rows
- `skipped.csv`: rows excluded by filters
- `summary.json`: run summary, counts, and resolved report paths
- `report.html`: optional self-contained HTML summary when `--html-report` is used
- Report files are written atomically through temporary files and then renamed into place.
- `runtime.max_output_rows`: optional guardrail that stops `run`, `dry-run`, `merge`, or `union` when any output exceeds the configured row count.

## Phase 1 Limitations

- Single input CSV only
- Multiple reference CSVs allowed
- Multiple output CSVs allowed
- No Excel / JSON / DB support
- Excel design-to-YAML is planned separately; Excel is not an execution input format
- No multiple input joins

## Roadmap

See [docs/roadmap.md](docs/roadmap.md).

## Documentation

- [Concept](docs/concept.md)
- [Configuration specification](docs/config-spec.md)
- [Excel design specification](docs/excel-design-spec.md)
- [CLI specification](docs/cli-spec.md)
- [Error policy](docs/error-policy.md)
- [Roadmap](docs/roadmap.md)

## License

MIT License. See [LICENSE](LICENSE).
