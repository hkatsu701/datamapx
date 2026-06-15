# CLI Specification

## Exit Code Policy

- `0`: success
- `1`: validation, configuration, or runtime error
- `2`: CLI usage error

## datamapx validate-config migration.yml

### Purpose

Validate YAML syntax, schema structure, required sections, field references, output mapping consistency, and Phase 1 limitations. This includes validating `generate_id.fields` references and `referential_integrity` references.
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

## datamapx preflight config.yml

### Purpose

Run a read-only preflight check before execution. `preflight` does not write output CSVs, reports, or logs.
It supports migration, merge, union, unpivot, aggregate, and run-all configs. For migration, merge, union, unpivot, and aggregate configs it checks:

- config validation
- CSV path existence
- `header: true`
- readable CSV headers
- schema `required` / `source_columns` resolution
- `referential_integrity` validation `reference_key` resolution against reference headers
- key column resolution for merge and union inputs, and reference keys in migration configs
- unpivot input schema/output consistency for unpivot configs
- aggregate input schema/output consistency for aggregate configs
- output path parent directory writability or creatability
- `if_exists: error` output conflicts
- `runtime.max_input_rows` / `runtime.max_reference_rows` guardrails when configured

For `run-all.yml`, `preflight` loads each job config in order and stops at the first failing job.

### Usage

```bash
datamapx preflight migration.yml
datamapx preflight merge.yml
datamapx preflight union.yml
datamapx preflight unpivot.yml
datamapx preflight aggregate.yml
datamapx preflight run-all.yml
```

### Options

No extra options are required.

### Expected output

On success, `preflight` prints the config type, config path, and a readable list of checks that passed.

On failure, it prints the first preflight error with its target context and exits with code `1`.

### Exit code policy

- `0`: preflight succeeded
- `1`: configuration error, CSV path/header error, key/source column resolution error, output conflict, or row guardrail failure
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
- report files are written atomically through temporary files and then renamed into place
- the configured output CSV is written atomically through a temporary file and then renamed into place
- `runtime.max_output_rows` can stop the command before the output CSV is written if any output exceeds the limit
- a merge summary is printed to the console
- when `runtime.max_output_rows` is exceeded, the CLI prints the output row count and configured limit in the stop message

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
- report files are written atomically through temporary files and then renamed into place
- the configured output CSV is written atomically through a temporary file and then renamed into place
- `runtime.max_output_rows` can stop the command before the output CSV is written if any output exceeds the limit
- a union summary is printed to the console
- when `runtime.max_output_rows` is exceeded, the CLI prints the output row count and configured limit in the stop message

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

## datamapx unpivot unpivot.yml

### Purpose

Expand a single normalized input CSV from wide form to long form without transformation rules.

`unpivot` reads one input CSV, applies the configured schema, and emits rows in the exact order `[id_columns..., variable_column, value_column]`.

### Usage

```bash
datamapx unpivot unpivot.yml
datamapx unpivot unpivot.yml --reports-dir ./reports
datamapx unpivot unpivot.yml --reports-dir ./reports --html-report
```

### Configuration

```yaml
input:
  path: ./input/payments_wide.csv
  header: true
  schema:
    customer_id:
      type: string
      required: true
    amount_2023:
      type: decimal
    amount_2024:
      type: decimal

filters:
  exclude:
    - if: input.amount_2023 is null and input.amount_2024 is null
      reason: All amount columns are blank

unpivot:
  id_columns: [customer_id]
  variable_column: year
  value_column: amount
  value_columns:
    amount_2023: "2023"
    amount_2024: "2024"
  drop_null_values: true

output:
  columns: [customer_id, year, amount]
```

### Rules

- Exactly one input CSV is supported.
- The input schema must be defined so the normalized dataframe can be pruned and validated before unpivoting.
- `filters.include` and `filters.exclude` are applied after schema normalization and before unpivot expansion.
- Filtered rows are written to `skipped.csv`; `filters.exclude[].reason` controls the recorded reason.
- `output.columns` must match `[id_columns..., variable_column, value_column]` exactly.
- `drop_null_values: true` drops rows whose unpivoted value is null or blank.
- `errors.csv`, `skipped.csv`, `summary.json`, and optional `report.html` are written for the unpivot command.
- `runtime.max_output_rows` stops the command with exit code `1` when the expanded output exceeds the configured limit.
- `if_exists: error` prevents overwriting an existing output CSV.
- `--reports-dir` and `--html-report` work the same way as `merge` and `union`.

## datamapx aggregate aggregate.yml

### Purpose

Aggregate a single normalized input CSV by `group_by` keys and summarize rows into one output row per group.

`aggregate` reads one input CSV, applies the configured schema, and groups the normalized dataframe by the configured key columns.

### Usage

```bash
datamapx aggregate aggregate.yml
datamapx aggregate aggregate.yml --reports-dir ./reports
datamapx aggregate aggregate.yml --reports-dir ./reports --html-report
```

### Configuration

```yaml
input:
  path: ./input/payment_lines.csv
  header: true
  schema:
    customer_id:
      type: string
      required: true
    amount:
      type: decimal
    paid_on:
      type: date
      date_format: "%Y-%m-%d"

aggregate:
  group_by: [customer_id]
  columns:
    customer_id:
      group_key: customer_id
    total_amount:
      sum: amount
    payment_count:
      count:
    first_paid_on:
      min: paid_on
    last_paid_on:
      max: paid_on

output:
  path: ./output/payment_summary.csv
  columns: [customer_id, total_amount, payment_count, first_paid_on, last_paid_on]
```

### Rules

- Exactly one input CSV is supported.
- The input schema must be defined so the normalized dataframe can be pruned and validated before aggregation.
- `output.columns` must match the keys of `aggregate.columns` exactly and in the same order.
- `group_key` copies a grouped key column into the output.
- `sum`, `min`, and `max` require numeric-compatible values for non-date inputs.
- `first` and `last` use the first/last non-null value in each group.
- `count` counts non-null values when a source is set; otherwise it counts the rows in the group.
- `errors.csv`, `skipped.csv`, `summary.json`, and optional `report.html` are written for the aggregate command.
- `runtime.max_output_rows` stops the command with exit code `1` when the aggregated output exceeds the configured limit.
- `if_exists: error` prevents overwriting an existing output CSV.
- `--reports-dir` and `--html-report` work the same way as `merge` and `union`.

## datamapx run-all run-all.yml

### Purpose

Run multiple existing YAML jobs sequentially with fail-fast behavior.
`run-all` is a thin orchestrator over the existing `run`, `merge`, `union`, `unpivot`, and `aggregate` execution paths.
It reads a `run-all.yml` file that declares a project and a `jobs` list, then executes jobs in the order listed.
If any job fails, the command stops immediately and exits with code `1`.

### Usage

```bash
datamapx run-all run-all.yml
```

### Options

No extra options are required.

### Configuration

`run-all.yml` uses the following top-level structure:

```yaml
version: 1
project:
  name: example_run_all
jobs:
  - name: migration_job
    type: run
    config: ./migration.yml
    reports_dir: ./reports/migration
    html_report: true
  - name: merge_job
    type: merge
    config: ./merge.yml
    reports_dir: ./reports/merge
    html_report: false
  - name: union_job
    type: union
    config: ./union.yml
  - name: unpivot_job
    type: unpivot
    config: ./unpivot.yml
    reports_dir: ./reports/unpivot
    html_report: false
  - name: aggregate_job
    type: aggregate
    config: ./aggregate.yml
    reports_dir: ./reports/aggregate
    html_report: false
```

Job fields:

- `name`: unique job name used in run-all progress output.
- `type`: one of `run`, `merge`, `union`, `unpivot`, or `aggregate`.
- `config`: path to the existing YAML config for that job, resolved relative to `run-all.yml`.
- `reports_dir`: optional report directory, also resolved relative to `run-all.yml`.
- `html_report`: optional boolean. When `true`, the job writes `report.html` beside `errors.csv`, `skipped.csv`, and `summary.json`.

### Expected output

On success, each job prints its usual summary in order, followed by:

```text
Run-all completed
```

If a job fails, `run-all` prints that job's normal failure summary and stops before running later jobs.

### Limitations

- Sequential execution only
- No parallel execution
- No branching or retries
- No job-to-job variable expansion
- No manifest generation
- No batch/script generation
- No dry-run batch execution

### Exit code policy

- `0`: all jobs completed successfully
- `1`: any job failed or reported a runtime/configuration error
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
Report files are written atomically through temporary files and then renamed into place when they are produced.
`runtime.max_output_rows` can stop dry-run with exit code `1` if any output exceeds the limit.
For `run`, the stop message identifies the specific `outputs.<name>` target; for `merge` and `union`, the CLI stop message includes the output row count and configured limit.

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
datamapx run migration.yml --limit 20
```

### Options

- `--limit INTEGER`: maximum number of input rows to load from the migration input CSV. `INTEGER` must be a positive integer. If omitted, all input rows are loaded.
- `--reports-dir PATH`: override the directory for `errors.csv`, `skipped.csv`, and `summary.json`.
- `--html-report`: also write `report.html` beside the other reports.

### Expected output

Print run summary:

- progress percentage and current phase while the command is running
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

Progress is printed as `Progress: NN% - phase`. It covers input/reference loading,
validation, row preparation, output mapping, CSV writing, and report writing. The percentage
shows pipeline progress rather than an exact remaining-time estimate.

`run` always writes the main output CSV and the report files when execution completes successfully. Validation error rows do not make the command fail if the configured policy is `output_error`.
The main output CSV is written atomically through a temporary file and then renamed into place. If the write fails, the previous final file is left unchanged and the temporary file is cleaned up when possible.
When `--html-report` is enabled, `run` also writes `report.html` beside the other reports and prints its path in the `Reports:` block.
Report files are written atomically through temporary files and then renamed into place when they are produced.
When `--limit` is used, only the first `N` normalized input rows are loaded from the migration input CSV. Reference CSVs are still loaded fully so duplicate-key and referential-integrity checks continue to see all reference rows. The CLI summary, `summary.json`, and `report.html` show that the execution was limited and include the limit value.
`runtime.max_output_rows` can stop `run` before the output CSV is written if any output exceeds the limit.
The stop message identifies the specific `outputs.<name>` target and includes the output row count and configured limit.

The summary file includes row-category breakdowns for validation errors, mapping errors, lookup missing errors, and transform errors, plus `notes.final_outcome` for the overall result label.

Lookup indexes are built once per execution and reused. Derived fields, filters, and mappings use
whole-dataframe execution when possible. If a mapping error must be attributed to individual rows,
the affected batch falls back to row-level execution so existing error-report behavior is preserved.
The command still loads migration inputs and references into memory; datasets that exceed available
memory require a future streaming migration implementation.

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
datamapx profile-input migration.yml --chunk-size 500
datamapx profile-input migration.yml --format json
datamapx profile-input migration.yml --limit 100 --chunk-size 500 --format json
```

### Options

- `--limit N`: profile only the first `N` normalized input rows. `N` must be a positive integer.
- `--chunk-size N`: profile the input by reading it in chunks of `N` rows. `N` must be a positive integer. When omitted, the command keeps the existing whole-file behavior.
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
When `--chunk-size` is used, the command reads the CSV with `pandas.read_csv(..., chunksize=N)` and still returns the same `InputProfile` / `ColumnProfile` structure as the non-chunked path.
JSON output returns a machine-readable object with `input_name`, `path`, `encoding`, `delimiter`, `profiled_rows`, `limit`, and a `columns` array containing the per-field metrics.

The profile is based on the normalized dataframe, not the raw CSV column names.

### Exit code policy

- `0`: profile completed
- `1`: configuration error or CSV read/schema/type conversion error
- `2`: invalid CLI usage
