# datamapx

For Japanese documentation, see [README.ja.md](README.ja.md).

datamapx is a Python CLI for CSV-to-CSV migration, transformation, and validation driven by YAML.

It is designed for projects where the migration rules should live in configuration, not in ad hoc Python scripts.

Current release: v0.3.1.

## What It Can Do

- Read one input CSV and multiple reference CSVs.
- Merge multiple CSVs into one staging CSV before conversion.
- Create a migration YAML scaffold interactively with `migration-wizard` using prompts for paths, numbered output column selection, per-column rename, input schema overrides, and optional advanced authoring for reference schema, references, derived fields, mapping rules, validations, filters, checks, output settings, error handling, runtime settings, and a final natural-language review before saving.
- Create a merge YAML scaffold interactively with `merge-wizard` using numbered selections for inputs, output columns, renames, and rules, with optional purpose-based templates, Japanese retry prompts for invalid input, a natural-language final review, and a limited back step from the final review. Input previews and numbered choices are shown in the same order, and long labels wrap for readability.
- Normalize and type-convert input fields from schema definitions.
- Map output columns with `source`, `value`, `concat`, `map`, `lookup`, `when`, `expression`, and `derived`.
- Apply filters and validations before writing the final output.
- Write `errors.csv`, `skipped.csv`, and `summary.json`.
- Run `generate-config`, `merge`, `merge-wizard`, `validate-config`, `inspect`, `profile-input`, `dry-run`, and `run`.

## What It Does Not Do in Phase 1

- Excel, JSON, or database input/output
- Multiple input joins
- Multiple output files
- Web UI
- Plugins
- Streaming processing
- AI-assisted YAML generation
- `check` rule execution beyond the current Phase 1 scope

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
- `migration-wizard` interactively generates a migration YAML scaffold with numbered output column selection, optional rename, input schema overrides, reference schema, advanced support for `lookup`, `derived`, `validations`, `filters`, `checks`, output settings, error handling, runtime settings, and a final review screen with limited redo.
- `merge` combines multiple CSV inputs into a staging CSV.
- `merge-wizard` interactively generates a merge YAML scaffold with numbered selections, fixed steps, rename confirmation, optional purpose-based templates, retry prompts for invalid input, a natural-language final review, and a limited back step from the final review. Input previews and numbered choices use the same ordering, and long labels wrap for readability.
- `validate-config` validates YAML structure, references, and Phase 1 constraints.
- `inspect` prints a human-readable summary of the configuration.
- `profile-input` shows a simple profile for the normalized input dataframe.
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
- [06_migration_wizard](examples/06_migration_wizard/README.md)

## Output Files

- Main output CSV: the transformed data selected by `outputs.<name>.columns`
- `errors.csv`: validation and runtime error rows
- `skipped.csv`: rows excluded by filters
- `summary.json`: run summary, counts, and resolved report paths

## Phase 1 Limitations

- Single input CSV only
- Multiple reference CSVs allowed
- Single output CSV only
- No Excel / JSON / DB support
- No multiple input joins
- No multiple output files
- `check` rule execution is not part of the core MVP scope

## Roadmap

See [docs/roadmap.md](docs/roadmap.md).

## Documentation

- [Concept](docs/concept.md)
- [Configuration specification](docs/config-spec.md)
- [CLI specification](docs/cli-spec.md)
- [Error policy](docs/error-policy.md)
- [Roadmap](docs/roadmap.md)

## License

MIT License. See [LICENSE](LICENSE).
