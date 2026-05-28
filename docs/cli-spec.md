# CLI Specification

## Exit Code Policy

- `0`: success
- `1`: validation, configuration, or runtime error
- `2`: CLI usage error

## datamapx validate-config migration.yml

### Purpose

Validate YAML syntax, schema structure, required sections, field references, output mapping consistency, and Phase 1 limitations.
For `type: date` fields, `date_format` can be used to request strict pandas date parsing.

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

## datamapx validate-design design.xlsx

### Purpose

Validate a standard `.xlsx` Excel design workbook against `docs/excel-design-spec.md`.
The command checks required sheets, required columns, job graph rules, and job-to-detail-sheet consistency.
It does not generate YAML, manifests, scripts, or execution outputs.

### Usage

```bash
datamapx validate-design examples/08_excel_design/datamapx_design_template.xlsx
datamapx validate-design design.xlsx --summary-json ./design-summary.json
datamapx validate-design design.xlsx --errors-csv ./design-errors.csv
datamapx validate-design design.xlsx --summary-json ./design-summary.json --errors-csv ./design-errors.csv
```

### Options

- `--summary-json PATH`: write a JSON summary when specified.
- `--errors-csv PATH`: write structured validation errors when specified.

### Expected output

On success:

```text
Design is valid: examples/08_excel_design/datamapx_design_template.xlsx
Project: invoice_migration
Sheets: 16
Jobs: 2
Enabled jobs: 2
```

On failure, print structured errors to stderr:

```text
Design is invalid: design.xlsx
- jobs row 3 column job_id: job_id is required
- jobs row 4 column job_type: unsupported job_type 'export'
```

### Exit code policy

- `0`: valid workbook
- `1`: invalid workbook, workbook read error, summary write error, or errors CSV write error
- `2`: invalid CLI usage

## datamapx generate-config --input ./input/users.csv --output ./output/users_out.csv --config ./migration.yml

### Purpose

Generate a basic Phase 1 migration YAML from the headers of a single input CSV.

The generated config is intentionally minimal: it creates canonical input schema field names, preserves the original input headers in `source_columns`, and generates `source` mappings only.

### Usage

```bash
datamapx generate-config \
  --input ./input/users.csv \
  --output ./output/users_out.csv \
  --config ./migration.yml
```

### Options

- `--input PATH` (required): input CSV path.
- `--output PATH` (required): main output CSV path to store in the generated YAML.
- `--config PATH` (required): destination path for the generated YAML.
- `--input-name TEXT`: YAML input key name. Default: `input`.
- `--output-name TEXT`: YAML output key name. Default: `output`.
- `--project-name TEXT`: project name written to YAML. Default: `generated_migration`.
- `--encoding TEXT`: input/output encoding written to YAML. Default: `utf-8-sig`.
- `--delimiter TEXT`: CSV delimiter written to YAML. Default: `,`.
- `--overwrite`: replace an existing config file.
- `--preserve-output-columns / --safe-output-columns`: keep original headers in `outputs.columns` or switch to safe generated names. Default: preserve output columns when possible.

### Expected output

On success:

```text
Config generated: ./migration.yml

Next steps:
1. datamapx validate-config ./migration.yml
2. datamapx dry-run ./migration.yml --limit 5
3. datamapx run ./migration.yml
```

### Limitations

- Only `source` mappings are generated.
- All schema fields are generated as `type: string`.
- All schema fields are generated with `required: false`.
- All schema fields use `normalize: [trim]`.
- `lookup`, `concat`, `map`, `when`, `expression`, `derived`, `filters`, `validations`, and `checks` are not generated.
- `header: false` CSV files are not supported.
- If raw output headers are duplicated or cannot be used safely, the generator may fall back to safe generated output column names to keep the config valid.

### Exit code policy

- `0`: config generated successfully
- `1`: CSV read failure, output overwrite conflict, or generated config write failure
- `2`: invalid CLI usage

## datamapx migration-wizard

### Purpose

Interactively generate a `migration.yml` configuration from a single input CSV and output path.

The wizard is a configuration authoring aid only. It does not run validation or write any output CSV.
It prompts for project metadata, paths, input/output names, the number of output columns to create, the output column names themselves, and optional column read settings.
In advanced mode it can also add input column read settings, reference column read settings, reference CSVs, derived fields, validations, filters, checks, output settings, error handling, runtime settings, and per-column rules for `source`, `value`, `concat`, `map`, `when`, `lookup`, and `expression`.
Before saving, the wizard shows a natural-language review of the generated migration and lets you save, redo only the output column / rule section, or cancel.
See [examples/06_migration_wizard/README.md](../examples/06_migration_wizard/README.md) for a runnable migration-wizard example.

### Usage

```bash
datamapx migration-wizard
```

### Expected output

On success:

```text
migration.yml を作成しました

保存先: ./migration.yml
プロジェクト名: generated_migration
入力CSV: ./input/users.csv
出力CSV: ./output/users_out.csv
入力名: input
出力名: output
出力列数: 2
設定モード: 基本設定のみ
reference 数: 0
reference 列設定数: 0
derived 数: 0
validation 数: 0
filter 数: 0
check 数: 0
input 列設定数: 0
output.if_exists: error
output.newline: \n
error_handling.max_errors: 1000
runtime.log_level: INFO
出力列: 顧客ID, total_amount

次にやること:
1. datamapx validate-config ./migration.yml
2. datamapx dry-run ./migration.yml --limit 5
3. datamapx run ./migration.yml
```

### Limitations

- Generates a migration YAML scaffold only.
- Basic mode uses `source` mappings only.
- Advanced mode can generate input and reference column read settings, `lookup`, `derived`, `validations`, `filters`, `checks`, `output` settings, `error_handling`, and `runtime` sections plus non-source mapping rules.
- Does not execute the migration.
- Uses the same safe field-name helper as `generate-config`, so headers that cannot be made safe fall back to generated names like `field_001`.
- Lets you declare the output column count and output column names explicitly.
- Displays the output column list before rule assignment.
- Shows a final review screen and supports redo for the output column / mapping section only.

### Exit code policy

- `0`: migration YAML generated successfully
- `1`: CSV read failure, config validation failure, overwrite conflict, or write failure
- `2`: invalid CLI usage

## datamapx merge merge.yml

### Purpose

Merge multiple CSV inputs into a single staging CSV before running the existing migration pipeline.

The initial merge implementation is YAML-driven and focuses on exact key-based joins and explicit column aggregation rules.

### Usage

```bash
datamapx merge merge.yml
```

### Options

- `--reports-dir PATH`: override the directory where `errors.csv`, `skipped.csv`, and `summary.json` are written.
- `--html-report`: also write `report.html` beside the other reports.

### Expected output

On success:

- a staging CSV is written to the configured `output.path`
- `errors.csv`, `skipped.csv`, and `summary.json` are written
- `report.html` is written when `--html-report` is set
- a merge summary is printed to the console

### Limitations

- Exact-match joins only
- `left` and `inner` joins only
- No fuzzy matching or AI-assisted name matching
- No multiple-output merge
- The merge stage is separate from the existing `run` transformation pipeline

### Exit code policy

- `0`: merge completed successfully
- `1`: config error, CSV read error, key validation error, merge rule error, output write error, or report write error
- `2`: invalid CLI usage

## datamapx union union.yml

### Purpose

Append multiple same-format CSV inputs into one output CSV without transformation rules.

Phase 1 `union` is YAML-driven and focuses on vertical concatenation with explicit key validation.
Each input must define the same key fields, rows with missing keys fail, and duplicate keys are rejected both within an input and across all inputs.
The configured schema is applied before columns are appended in the order listed under `union.columns` and `output.columns`.

### Usage

```bash
datamapx union union.yml
```

### Options

- `--reports-dir PATH`: override the directory where `errors.csv`, `skipped.csv`, and `summary.json` are written.
- `--html-report`: also write `report.html` beside the other reports.

### Expected output

On success:

- the output CSV is written to the configured `output.path`
- `errors.csv`, `skipped.csv`, and `summary.json` are written
- `report.html` is written when `--html-report` is set
- a union summary is printed to the console

### Limitations

- No transformation rules
- Same-format CSV inputs only
- `union.columns` must match `output.columns`
- Duplicate keys are rejected within each input and across inputs
- Missing keys are rejected

### Exit code policy

- `0`: union completed successfully
- `1`: config error, CSV read error, key validation error, output write error, or report write error
- `2`: invalid CLI usage

## datamapx merge-wizard

### Purpose

Interactively generate a `merge.yml` configuration from multiple CSV headers and merge rules.

The wizard is a configuration authoring aid only. It does not execute the merge itself.
Input selection, output column selection, output column renaming, join type, rule type, and merge references are chosen by number to reduce typing errors.
Purpose-based templates can apply recommended rules to numbered output columns before manual rule entry.
The screen flow is: project/path setup -> input registration -> merge policy -> output columns -> output column renaming -> template selection -> column rules -> review -> save / redo column rules / cancel.
Invalid numeric input is retried up to three times with Japanese guidance.
From the review screen, you can save the YAML, redo only the column rules, or cancel.
The review screen summarizes the merge in natural language so non-YAML users can confirm the result before saving.
Input previews and numbered choices are displayed in the same order, and long labels wrap across multiple lines for readability.
See [examples/05_merge_wizard/README.md](../examples/05_merge_wizard/README.md) for a runnable merge-wizard example.

### Usage

```bash
datamapx merge-wizard
```

### Options

No explicit options are required in Phase 1.

### Expected output

On success:

```text
merge.yml を作成しました

保存先: ./merge.yml
プロジェクト名: generated_merge
入力CSV数: 2
出力列: id, primary_name

次にやること:
1. datamapx merge ./merge.yml
2. datamapx validate-config <migration.yml>
3. datamapx dry-run <migration.yml> --limit 5
```

### Limitations

- Generates merge YAML only.
- Uses exact key-based merge rules only.
- Uses numbered selections for inputs, output columns, join type, rule types, and merge references.
- Displays input previews and numbered choices in the same order.
- Wraps long labels across multiple lines.
- Shows the selected source column, CSV header, and sample values before each output column rename.
- Allows selected output column names to be renamed one by one before rule assignment.
- Can apply purpose-based recommended rules to numbered output columns.
- Allows optional manual output column names only for columns that cannot be chosen directly from the numbered candidates.
- Retries invalid numeric and text input up to three times with Japanese retry messages.
- Does not infer types.
- Does not infer lookup, validation, filters, or transform rules.
- Does not perform merge execution.
- Does not support fuzzy matching or AI-assisted configuration.

### Exit code policy

- `0`: merge YAML generated successfully
- `1`: CSV read failure, config validation failure, overwrite conflict, or write failure
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
If `runtime.max_input_rows` or `runtime.max_reference_rows` is configured, the corresponding CSV is counted before loading and the command fails with exit code `1` when a limit is exceeded.

The current Phase 1 implementation performs:

- config loading and validation
- input CSV loading
- schema application
- normalize and type conversion
- reference CSV loading
- reference key validation
- output dataframe construction for `source`, `value`, `concat`, and `map`
- checks evaluation against run-level summary variables
- output preview display for one or more configured outputs

### Usage

```bash
datamapx dry-run migration.yml --limit 20
```

### Options

- `--limit INTEGER`: maximum number of input rows to load. If omitted, all input rows are loaded.
- `--write-reports`: write `errors.csv`, `skipped.csv`, and `summary.json` after dry-run completes.
- `--reports-dir PATH`: override report output directory. This option requires `--write-reports`.
- `--html-report`: also write `report.html`. This option requires `--write-reports`.

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
- check counts
- error preview
- error details
- output name(s)
- output columns
- rows previewed
- output preview(s)
- limit
- status

Output files are not written during `dry-run`.

When `--write-reports` is set, dry-run writes the internal error rows, skipped rows, and summary data to report files. In that mode, the CLI prints a `Reports written:` block with the resolved paths.
When `--html-report` is also set, dry-run writes a browser-readable `report.html` beside the other reports and includes it in the same `Reports written:` block.
If `--html-report` is used without `--write-reports`, the command fails as CLI usage with exit code `2`.

The summary file includes row-category breakdowns for validation errors, mapping errors, lookup missing errors, and transform errors, plus `notes.final_outcome` for the overall result label.

Lookup, when, expression, derived, and filter results are included in the output preview when those mappings are configured.

`dry-run` displays a filter summary and a skipped preview. `skipped.csv` is not written during dry-run.
When row-level errors exist, `dry-run` also prints an `Error details:` block with row numbers, fields, rules, messages, and row values so the failure cause can be inspected without opening `errors.csv`.

Validations are included in the preview data. Dry-run still succeeds when validation error rows exist, as long as preview construction and optional report writing complete successfully.

Checks are evaluated during dry-run. If any check fails, the command exits with code `1` after the preview and optional reports are produced.
If execution stops because of validation policy or a mapping/runtime error configured to stop, the CLI prints a `Stop:` block before exiting with code `1`.

### Exit code policy

- `0`: dry-run completed successfully
- `1`: configuration error, input CSV read error, type conversion error, reference CSV read error, reference key validation error, mapping error, fatal validation stop, or report write error
- `2`: invalid CLI usage

## datamapx run migration.yml

### Purpose

Execute the configured CSV-to-CSV migration and write output, error, skipped, summary, and log files.

This command is implemented in Phase 1.
If `runtime.max_input_rows` or `runtime.max_reference_rows` is configured, the corresponding CSV is counted before loading and the command fails with exit code `1` when a limit is exceeded.

### Usage

```bash
datamapx run migration.yml
```

### Options

- `--reports-dir PATH`: override the directory for `errors.csv`, `skipped.csv`, and `summary.json`.
- `--html-report`: also write `report.html` beside the other reports.

### Expected output

Print run summary:

- `run_id`
- input rows
- output rows
- skipped rows
- error rows
- output file path(s)
- error file path
- skipped file path
- summary file path
- final status
- error details

`run` always writes the main output CSV and the report files when execution completes successfully. Validation error rows do not make the command fail if the configured policy is `output_error`.
When `--html-report` is enabled, `run` also writes `report.html` beside the other reports and prints its path in the `Reports:` block.

The summary file includes row-category breakdowns for validation errors, mapping errors, lookup missing errors, and transform errors, plus `notes.final_outcome` for the overall result label.

Checks are evaluated during `run`. If any check fails, the command exits with code `1` after the output and report files are written.
When row-level errors exist, `run` also prints an `Error details:` block with row numbers, fields, rules, messages, and row values.
If execution stops because of validation policy or a mapping/runtime error configured to stop, `run` skips writing the main output CSV, writes the reports when possible, prints a `Stop:` block, and exits with code `1`.

### Exit code policy

- `0`: run completed successfully
- `1`: configuration error, fatal runtime error, CSV write error, report write error, fatal validation stop, or check failure
- `2`: invalid CLI usage

## datamapx profile-input migration.yml

### Purpose

Inspect the configured input CSV after schema column resolution, normalization, and type conversion.
The command is read-only and does not write output CSVs or reports.
If `runtime.max_input_rows` is configured, the input file is counted before loading and the command fails with exit code `1` when the file exceeds the configured limit.

### Usage

```bash
datamapx profile-input migration.yml
datamapx profile-input migration.yml --limit 100
datamapx profile-input migration.yml --format json
datamapx profile-input migration.yml --limit 100 --format json
```

### Options

- `--limit N`: profile only the first `N` normalized input rows. `N` must be a positive integer.
- `--format text|json`: output format. Default: `text`.

### Expected output

Text output keeps the existing heading labels and adds per-column metrics:

- input name
- path
- encoding
- delimiter
- row count
- profiled row count
- canonical schema field names
- missing value counts per schema field
- sample values per schema field
- simple inferred dtype per schema field
- per-column `missing_rate`, `non_null_count`, `unique_count`, `duplicate_count`, `top_values`, and numeric/string metrics

When `--limit` is used, the output makes it clear that the metrics are based on the limited sample.
JSON output returns a machine-readable object with `input_name`, `path`, `encoding`, `delimiter`, `profiled_rows`, `limit`, and a `columns` array containing the per-field metrics.

The profile is based on the normalized dataframe, not the raw CSV column names.

### Exit code policy

- `0`: profile completed
- `1`: configuration error or CSV read/schema/type conversion error
- `2`: invalid CLI usage
