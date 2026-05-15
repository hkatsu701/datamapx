# CLI Specification

## Exit Code Policy

- `0`: success
- `1`: validation, configuration, or runtime error
- `2`: CLI usage error

## datamapx validate-config migration.yml

### Purpose

Validate YAML syntax, schema structure, required sections, field references, output mapping consistency, and Phase 1 limitations.

### Usage

```bash
datamapx validate-config migration.yml
```

### Options

No Phase 1 options are required.

### Expected output

On success:

```text
Config is valid: migration.yml
```

On failure, print configuration errors with section and field context.

### Exit code policy

- `0`: valid configuration
- `1`: invalid YAML, invalid config, unsupported setting, or unresolved reference
- `2`: invalid CLI usage

## datamapx inspect migration.yml

### Purpose

Print a human-readable summary of the configured project, input, references, output, mappings, validations, filters, checks, and runtime settings.

### Usage

```bash
datamapx inspect migration.yml
```

### Options

No Phase 1 options are required.

### Expected output

Summarized configuration, including:

- project name
- input path
- reference names and paths
- output path
- output columns
- mapping count
- validation count
- error output paths

### Exit code policy

- `0`: inspection completed
- `1`: configuration could not be loaded or validated
- `2`: invalid CLI usage

## datamapx dry-run migration.yml --limit 20

### Purpose

Run the load phase without writing outputs or reports.

The current Phase 1 implementation performs:

- config loading and validation
- input CSV loading
- schema application
- normalize and type conversion
- reference CSV loading
- reference key validation
- output dataframe construction for `source`, `value`, `concat`, and `map`
- output preview display

### Usage

```bash
datamapx dry-run migration.yml --limit 20
```

### Options

- `--limit INTEGER`: maximum number of input rows to load. If omitted, all input rows are loaded.
- `--write-reports`: write `errors.csv`, `skipped.csv`, and `summary.json` after dry-run completes.
- `--reports-dir PATH`: override report output directory. This option requires `--write-reports`.

References are always loaded fully, even when `--limit` is set, because duplicate key validation must inspect all reference rows.

### Expected output

Print a load phase summary:

- run ID
- project name
- input name
- input path
- input rows loaded
- normalized input columns
- reference names
- reference paths
- reference rows loaded
- reference keys
- filter rows before filtering
- filter rows after filtering
- skipped row count
- skipped preview
- validation error counts
- error preview
- output name
- output columns
- rows previewed
- output preview
- limit
- status

Output files are not written during `dry-run`.

When `--write-reports` is set, dry-run writes the internal error rows, skipped rows, and summary data to report files. In that mode, the CLI prints a `Reports written:` block with the resolved paths.

Lookup, when, expression, derived, and filter results are included in the output preview when those mappings are configured.

`dry-run` displays a filter summary and a skipped preview. `skipped.csv` is not written during dry-run.

Validations are included in the preview data. Dry-run still succeeds when validation error rows exist, as long as preview construction and optional report writing complete successfully.

### Exit code policy

- `0`: dry-run completed successfully
- `1`: configuration error, input CSV read error, type conversion error, reference CSV read error, reference key validation error, mapping error, or report write error
- `2`: invalid CLI usage

## datamapx run migration.yml

### Purpose

Execute the configured CSV-to-CSV migration and write output, error, skipped, summary, and log files.

This command is implemented in Phase 1.

### Usage

```bash
datamapx run migration.yml
```

### Options

- `--reports-dir PATH`: override the directory for `errors.csv`, `skipped.csv`, and `summary.json`.

### Expected output

Print run summary:

- `run_id`
- input rows
- output rows
- skipped rows
- error rows
- output file path
- error file path
- skipped file path
- summary file path
- final status

`run` always writes the main output CSV and the report files. Validation error rows do not make the command fail if the pipeline completes and reports are written successfully.

### Exit code policy

- `0`: run completed successfully
- `1`: configuration error, fatal runtime error, CSV write error, or report write error
- `2`: invalid CLI usage

## datamapx profile-input migration.yml

### Purpose

Inspect the configured input CSV after schema column resolution, normalization, and type conversion.

### Usage

```bash
datamapx profile-input migration.yml
```

### Options

No Phase 1 options are required.

### Expected output

Simple Phase 1 profile:

- input name
- path
- encoding
- delimiter
- row count
- canonical schema field names
- missing value counts per schema field
- sample values per schema field
- simple inferred dtype per schema field

The profile is based on the normalized dataframe, not the raw CSV column names.

### Exit code policy

- `0`: profile completed
- `1`: configuration error or CSV read/schema/type conversion error
- `2`: invalid CLI usage

## Open Questions

- Final exact output format for `inspect`.
- Final default value for `dry-run --limit`.
- Whether `profile-input` should support a sample row limit option in Phase 1.
