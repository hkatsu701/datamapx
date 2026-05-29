# Configuration Specification

This document is the source of truth for Phase 1 YAML behavior.

## 1. Overview

datamapx uses a YAML file to define CSV input, reference CSVs, filters, derived fields, output CSV, mappings, validations, checks, error handling, and runtime behavior.
The `migration-wizard` can author the same input and reference column read settings, output mappings, and advanced sections interactively.
It now also shows a final natural-language review before saving and allows redo only for the output column / mapping section.
See [examples/06_migration_wizard/README.md](../examples/06_migration_wizard/README.md) for a runnable wizard-authored migration configuration.

Phase 1 supports:

- Single input CSV
- Multiple reference CSVs
- Multiple output CSVs
- CSV-to-CSV transformation
- YAML-driven behavior

Phase 1 does not support multiple input joins in the migration pipeline.

The separate `merge` command uses its own YAML configuration to combine multiple CSV files into a staging CSV before the main `run` pipeline is executed.
The separate `union` command uses its own YAML configuration to vertically append same-format CSV inputs with key validation and report output.

## 2. Full YAML example

```yaml
version: 1

project:
  name: user_migration
  description: Convert user CSV to target CRM format

inputs:
  users:
    path: ./input/users.csv
    encoding: utf-8-sig
    delimiter: ","
    header: true
    schema:
      user_id:
        source_columns: ["user_id", "顧客ID", "顧客コード"]
        type: string
        required: true
        normalize: [trim]
      last_name:
        type: string
        normalize: [trim]
      first_name:
        type: string
        normalize: [trim]
      department_code:
        type: string
        normalize: [trim]
      active:
        type: boolean
      price:
        type: decimal
        normalize: [trim, remove_commas, remove_currency_symbol]
      quantity:
        type: integer
      amount:
        type: decimal
        normalize: [trim, remove_commas]

references:
  departments:
    path: ./ref/departments.csv
    encoding: utf-8-sig
    delimiter: ","
    header: true
    key: department_code
    on_duplicate: error

filters:
  exclude:
    - if: users.user_id == ""
      reason: "user_id is empty"

derived:
  full_name:
    concat:
      values:
        - users.last_name
        - " "
        - users.first_name

  total_amount:
    expression: users.price * users.quantity

outputs:
  users_out:
    path: ./output/users_migrated.csv
    encoding: utf-8-sig
    delimiter: ","
    header: true
    newline: "\n"
    if_exists: error
    columns:
      - id
      - name
      - source_system
      - status
      - department_name
      - total_amount

mappings:
  users_out:
    id:
      source: users.user_id

    name:
      source: derived.full_name

    source_system:
      value: CRM

    status:
      when:
        - if: users.active == true
          then: "有効"
        - if: users.active == false
          then: "無効"
      default: "不明"

    department_name:
      lookup:
        reference: departments
        key: users.department_code
        value: department_name
        on_missing: error

    total_amount:
      expression: users.price * users.quantity

validations:
  input:
    - field: users.user_id
      rule: required

  output:
    - field: id
      rule: required
    - field: status
      rule: enum
      values: ["有効", "無効", "不明"]
    - field: total_amount
      rule: min
      value: 0

checks:
  - name: row_count_check
    rule: input_rows == output_rows + error_rows + skipped_rows

error_handling:
  on_validation_error: output_error
  on_lookup_missing: output_error
  on_transform_error: output_error
  max_errors: 1000
  error_output: ./output/errors.csv
  skipped_output: ./output/skipped.csv
  include_original_row: true

runtime:
  run_id: auto
  log_dir: ./logs
  log_level: INFO
```

## 3. version

`version` identifies the configuration schema version.

Phase 1 supports only:

```yaml
version: 1
```

## 4. project

`project` provides human-readable metadata.

```yaml
project:
  name: user_migration
  description: Convert user CSV to target CRM format
```

## 5. inputs

Phase 1 supports exactly one input entry.

```yaml
inputs:
  users:
    path: ./input/users.csv
    encoding: utf-8-sig
    delimiter: ","
    header: true
    schema:
      user_id:
        source_columns: ["user_id", "顧客ID"]
        type: string
        required: true
        normalize: [trim]
```

Supported field types:

- `string`
- `integer`
- `decimal`
- `boolean`
- `date`

`date` fields may also define `date_format`, which uses pandas/Python strftime-style
format strings such as `%Y%m%d`, `%Y-%m-%d`, and `%Y/%m/%d`. When `date_format` is
omitted, datamapx keeps the existing mixed parsing behavior.

Supported normalize functions:

- `trim`: remove leading and trailing whitespace
- `zenkaku_to_hankaku`: convert common full-width alphanumerics and symbols to half-width with Unicode NFKC normalization
- `remove_commas`: remove comma separators
- `remove_currency_symbol`: remove common currency symbols before numeric conversion

Phase 1 CSV reader behavior:

- `header: true` is supported.
- `header: false` is not implemented and fails with a clear CSV read error.
- Schema field names are canonical field names in the normalized dataframe.
- If `source_columns` is set, datamapx uses the first listed source column that exists in the CSV.
- If `source_columns` is not set, datamapx looks for a CSV column with the same name as the schema field.
- Missing `required: true` columns fail.
- Missing optional columns are created with missing values.
- CSV columns not defined in `schema` are ignored in Phase 1.
- When `schema` is defined, datamapx reads only the columns needed to resolve that schema. All `source_columns` candidates are included in the read set, and fields without `source_columns` read the canonical schema field name. This pruning applies only when schema exists; schema-free reference CSVs still read all columns.
- An internal `__row_number` column is added. Data rows are numbered from 1; the header row is not counted.

Normalize functions run before type conversion.

Phase 1 type conversion behavior:

- `string`: non-missing values are converted to strings; missing values remain missing.
- `integer`: values are converted with pandas numeric conversion and stored as nullable integer.
- `decimal`: values are converted with pandas numeric conversion.
- `boolean`: values are converted using `true_values` / `false_values` when configured, otherwise built-in defaults.
- `date`: values are parsed with `pandas.to_datetime`. If `date_format` is configured,
  parsing is strict against that format. If it is omitted, the existing mixed parsing
  behavior is preserved. Missing and blank values remain missing.

Default boolean values:

- true: `["true", "1", "yes", "y", "Y", "TRUE", "True"]`
- false: `["false", "0", "no", "n", "N", "FALSE", "False"]`

## 6. references

`references` defines lookup CSV files.

```yaml
references:
  departments:
    path: ./ref/departments.csv
    encoding: utf-8-sig
    delimiter: ","
    header: true
    key: department_code
    on_duplicate: error
```

Phase 1 supports multiple reference CSVs.

`on_duplicate` supports only:

- `error`

Duplicate reference keys must not be silently accepted.

Reference CSV reader behavior:

- `header: true` is supported.
- `header: false` is not implemented and fails with a clear CSV read error.
- If a reference defines `schema`, schema application follows the same source column and type conversion rules as inputs.
- If a reference defines `schema`, datamapx prunes the read to the schema-required columns using the same source column resolution rules as inputs.
- If a reference does not define `schema`, CSV column names are used as-is and the CSV is read without pruning.
- `key` may be a string or list of strings.
- Missing key columns fail.
- Missing key values fail.
- Duplicate key values fail because Phase 1 supports only `on_duplicate: error`.
- For composite keys, the combination of all configured key columns is checked for duplicates.

## 7. filters

`filters` defines row inclusion or exclusion rules.

```yaml
filters:
  include:
    - if: users.active == true
      reason: "active users only"
  exclude:
    - if: users.amount == 0
      reason: "zero amount is excluded"
```

Execution status: supported in dry-run.

Filter execution order:

1. `include`
2. `exclude`

`include` rules are optional. When `filters.include` is configured, only rows matching at least one include condition are kept. Rows matching no include condition are skipped with the standard reason `No include condition matched`.

`exclude` rules are optional. When `filters.exclude` is configured, rows matching an exclude condition are skipped. If `reason` is configured, that reason is retained. If `reason` is omitted, `Excluded by filter` is used. If multiple exclude rules match, the first matching rule supplies the reason.

Filter conditions use the same limited condition syntax as `when`. Both `users.*` and `derived.*` references are supported. Derived fields are computed before filters so they can be used in filter conditions.

Skipped rows are retained internally during dry-run and shown in the dry-run skipped preview. `skipped.csv` file output is produced only when dry-run is run with `--write-reports`; `run` always writes `skipped.csv`.

## 8. derived

`derived` defines intermediate fields that can be used by mappings but are not written directly unless mapped.

```yaml
derived:
  full_name:
    concat:
      values:
        - users.last_name
        - " "
        - users.first_name
```

Derived fields may use the same mapping rule types as output mappings.

Execution status: supported.

Phase 1 derived fields:

- are computed before output mappings
- produce one Series with the same row count as the input
- are referenced as `derived.<field_name>`
- may use `source`, `value`, `concat`, `map`, `lookup`, `when`, and `expression`
- may reference other derived fields
- are dependency-sorted before execution
- fail with a mapping error when a circular dependency is detected

Example with derived dependencies:

```yaml
derived:
  total_amount:
    expression: users.price * users.quantity

  amount_with_tax:
    expression: derived.total_amount * 1.1
```

## 9. outputs

Phase 1 supports one or more output entries.

```yaml
outputs:
  users_out:
    path: ./output/users_migrated.csv
    encoding: utf-8-sig
    delimiter: ","
    header: true
    newline: "\n"
    if_exists: error
    columns:
      - id
      - name
```

`if_exists` supports:

- `error`
- `overwrite`

During `run`, `if_exists` controls each configured output CSV. `error` stops when an output file already exists, and `overwrite` replaces it. Output CSVs are written atomically through a temporary file and then renamed into place so a failed write does not corrupt the previous final file. Report files are handled separately from output CSVs.

## 10. mappings

`mappings` defines output field values for each output.

```yaml
mappings:
  users_out:
    id:
      source: users.user_id
```

Every output column must have a mapping. A mapping for an unknown output column is a configuration error.

Field references in mappings are validated by `validate-config`.

Phase 1 supports only these field reference forms:

- `<input_name>.<field_name>`
- `derived.<field_name>`

For example:

- `users.user_id`
- `users.department_code`
- `derived.total_amount`

Input field references must use field names defined under `inputs.<input_name>.schema`.
`source_columns` values are CSV aliases and are not valid field references.

Phase 1 does not support direct reference paths such as:

- `references.departments.department_name`
- `outputs.users_out.id`
- nested JSON paths
- array access

## 11. validations

`validations` defines input and output validation rules.

```yaml
validations:
  input:
    - field: users.user_id
      rule: required
  output:
    - field: status
      rule: enum
      values: ["有効", "無効", "不明"]
```

Phase 1 validation rules:

- `required`
- `enum`
- `min`
- `max`
- `regex`
- `length`

`validations.input[].field` must reference the single input namespace:

```yaml
validations:
  input:
    - field: users.user_id
      rule: required
```

`validations.input[].field` must not reference `derived`.

`validations.output[].output` selects which output CSV the rule applies to.
When multiple outputs are configured, `validations.output[].output` is required.
When only one output is configured, `validations.output[].output` may be omitted and is treated as that single output.

```yaml
validations:
  output:
    - output: users_out
      field: id
      rule: required
```

`validations.output[].field` must use an output column name directly:

`validations.output[].field` must not use `users.id` or `derived.id`.

## 12. checks

`checks` defines run-level assertions.

```yaml
checks:
  - name: row_count_check
    rule: input_rows == output_rows + error_rows + skipped_rows
```

Phase 1 evaluates configured checks after output preview construction and stores the results in `summary.json`.
Check rules may use the run-level summary variables below.

During `validate-config`, Phase 1 does not evaluate check expressions. It validates that `checks[].rule` uses only supported summary variables.

The following summary variables are allowed in `checks[].rule` and are not treated as field references:

- `input_rows`
- `output_rows`
- `error_rows`
- `skipped_rows`

## 13. error_handling

`error_handling` defines how row-level and runtime errors are handled.
Phase 1 honors `on_validation_error`, `on_lookup_missing`, `on_transform_error`, and `max_errors` during execution and records fatal stop reasons in `summary.json`.
When `on_lookup_missing` or `on_transform_error` is `output_error`, the affected row is kept as an error row and omitted from the output preview. When either option is `stop`, execution stops immediately.

```yaml
error_handling:
  on_validation_error: output_error
  on_lookup_missing: output_error
  on_transform_error: output_error
  max_errors: 1000
  error_output: ./output/errors.csv
  skipped_output: ./output/skipped.csv
  include_original_row: true
```

## 14. runtime

`runtime` defines execution metadata and logging behavior.

```yaml
runtime:
  run_id: auto
  log_dir: ./logs
  log_level: INFO
  summary_output: ./output/summary.json
  max_input_rows: 100000
  max_reference_rows: 500000
  max_output_rows: 100000
```

`run_id: auto` means datamapx generates a run identifier.
`summary_output` is optional. When omitted, `summary.json` defaults to the same directory as `error_handling.error_output`.
When dry-run is executed with `--write-reports --reports-dir`, that directory overrides the configured report paths. When `run` is executed, report files are always written and use the same path resolution rules. If the CLI is invoked with `--html-report`, a browser-readable `report.html` is written beside the other reports without changing the CSV or JSON report structures.
All report files (`errors.csv`, `skipped.csv`, `summary.json`, and optional `report.html`) are written atomically through a temporary file in the target directory. If a report write fails, the previous final file is left untouched and the temporary file is removed when possible.
`max_input_rows` and `max_reference_rows` are optional positive integers. When set, datamapx counts CSV data rows before loading the migration input or reference CSV with pandas and raises a CSV read error if the file exceeds the configured limit. These limits are used by `profile-input`, `dry-run`, and `run`, and are not applied by `merge` or `union`.
`max_output_rows` is an optional positive integer. When set, datamapx checks the number of output rows produced by `run`, `dry-run`, `merge`, and `union`. If any output exceeds the limit, execution stops with exit code `1`. For `run`, the stop message identifies the specific `outputs.<name>` target. For `merge` and `union`, the CLI stop message includes the output row count and configured limit. `run`, `merge`, and `union` do not write the output CSV when the limit is exceeded.

## 15. union

`union` appends multiple same-format CSV inputs into one output CSV without transformation rules.

```yaml
union:
  columns: [id, name, amount]
```

Execution status: supported.

Rules:

- Phase 1 supports at least two inputs.
- Each input must define `key`.
- All inputs must define the same `key` fields in the same order.
- `union.columns` must match `output.columns`.
- `union` does not support transformation rules.
- The configured schema is applied before rows are appended.
- Rows with missing keys fail.
- Duplicate keys fail within each input and across all inputs.
- Columns are appended in the order listed under `output.columns`.
- `errors.csv`, `skipped.csv`, and `summary.json` are written for the union command.
When `--html-report` is used with `run`, `dry-run --write-reports`, `merge`, or `union`, a self-contained `report.html` is written beside the other report files.

## 16. Mapping rule types

### source

Copies a value from input or derived fields.

```yaml
id:
  source: users.user_id
```

Execution status: supported for input fields and `derived.*` references.

### value

Outputs a fixed value.

```yaml
source_system:
  value: CRM
```

Execution status: supported.

### concat

Concatenates literal strings and field references.

```yaml
name:
  concat:
    values:
      - users.last_name
      - " "
      - users.first_name
```

Execution status: supported for input field references and string literals. Missing values are treated as empty strings.

### map

Maps source values to configured values.

```yaml
status:
  map:
    source: users.status_code
    values:
      A: active
      I: inactive
    default: unknown
```

Execution status: supported. If `default` is omitted and an unmapped non-missing value appears, mapping fails.

Use `map` for small value conversions that can be represented directly in YAML. Use `lookup` when values should be retrieved from an external reference CSV.

### when

Evaluates conditions in order and returns the first matching result.

```yaml
status:
  when:
    - if: users.active == true
      then: "有効"
    - if: users.active == false
      then: "無効"
  default: "不明"
```

Execution status: supported for the limited Phase 1 condition syntax documented in
[Condition expression](#17-condition-expression).

Rules:

- `when` must be a list.
- Each item must contain `if` and `then`.
- Items are evaluated from top to bottom.
- The first matching `then` value is used.
- If no condition matches, `default` is used.
- If no condition matches and `default` is omitted, mapping fails.

Phase 1 `then` and `default` values support literal strings, numbers, booleans, and null.
`then` and `default` also support field references such as `then: users.status` and
`default: derived.active_state`.

### lookup

Looks up a value from a reference CSV.

```yaml
department_name:
  lookup:
    reference: departments
    key: users.department_code
    value: department_name
    on_missing: error
```

Execution status: supported.

`lookup.key` may be a string or list of strings:

```yaml
department_name:
  lookup:
    reference: departments
    key:
      - users.region_code
      - users.department_code
    value: department_name
    on_missing: default
    default: Unknown
```

For single-key lookup, `references.<name>.key` must be a string. For composite-key lookup, `references.<name>.key` must be a list with the same length as `lookup.key`.

Supported `on_missing` values:

- `error`: fail with a mapping error
- `default`: use `lookup.default`; fails if `default` is not configured
- `empty`: use an empty string
- `"null"`: use a missing value

### expression

Evaluates a safe arithmetic expression for each input row.

```yaml
total_amount:
  expression: users.price * users.quantity
```

Execution status: supported for Phase 1 arithmetic expressions.

Supported operators:

- `+`
- `-`
- `*`
- `/`
- `//`
- `%`
- `**`
- parentheses

Allowed functions:

- `round`
- `abs`
- `min`
- `max`

Field reference rules:

- `users.field` may reference a field in the single configured input.
- `derived.field` may reference a computed derived field.
- Unknown input fields fail with a mapping error.
- Unknown derived fields fail with a mapping error.
- Unknown namespaces fail with a mapping error.
- `references.*` and `outputs.*` references are not implemented for expression execution.
- If any referenced field value is missing in a row, expression mapping fails.

Expression execution does not use Python `eval`. Field references such as `users.price` are rewritten to safe internal variable names before evaluation, and only row-local values are provided to the evaluator.

## 17. Condition expression

Condition expressions are used by `filters`, `when`, and `checks`.

For `when` mapping execution, Phase 1 supports only these forms:

- `users.field == value`
- `derived.field == value`
- `users.field != value`
- `users.field > value`
- `users.field >= value`
- `users.field < value`
- `users.field <= value`
- `users.field == true`
- `users.field == false`
- `users.field == null`
- `users.field != null`
- `users.field`
- `users.field in ["active", "pending"]`
- `users.field not in ["deleted", "cancelled"]`

Supported value literals:

- `true` / `false`
- `null`
- quoted strings such as `"active"` or `'active'`
- numbers such as `100` or `100.5`
- lists such as `["active", "pending"]`

Unsupported condition examples:

- `users.amount + users.tax > 1000`
- `round(users.amount) > 100`
- `users.a == users.b`
- `users.name.startswith("A")`

Supported logical combinations:

- `users.active and users.amount > 100`
- `users.status == "active" or users.status == "pending"`
- `(users.active or users.status == "pending") and users.amount > 100`
- `users.active or (users.status == "pending" and users.amount > 100)`
- `users.deleted_at is null`
- `users.deleted_at is not null`
- `users.active`

During `validate-config`, Phase 1 does not evaluate condition expressions. It extracts and validates basic field references such as `users.active` and `derived.total_amount`.

During `when` execution, both `users.*` and `derived.*` references are supported.

## 18. Expression safety

Python `eval` must not be used directly.

Phase 1 uses a dedicated safe arithmetic evaluator with a strict allowlist.

The current Phase 1 configuration validation step does not execute expressions. It validates field references in `expression`, `when.if`, `when.then`, `when.default`, `filters.include[].if`, and `filters.exclude[].if`. It validates `checks[].rule` against the reserved summary variables listed above.

`when` mapping execution uses a limited parser instead of Python `eval`.
Supported condition forms are direct comparisons, `in`, `not in`, logical `and` / `or`, `is null`, `is not null`, bare boolean field references against `users.*` or `derived.*`, and parenthesized grouping of those supported forms.
General arithmetic expressions, function calls, and field-to-field comparisons are unsupported during execution.

`when` mapping execution uses a dedicated limited parser. It does not use Python `eval` and does not use the planned general-purpose expression evaluator.

`expression` mapping execution supports only arithmetic operators and explicitly allowed functions. It does not allow imports, attributes, arbitrary function calls, comprehensions, lambdas, assignment, indexing, or access to Python builtins.

Expressions must not:

- Import modules
- Access attributes outside configured field references
- Call arbitrary functions
- Read or write files
- Execute shell commands

## 19. Defaults

Phase 1 defaults:

- `encoding`: `utf-8-sig` when omitted
- `delimiter`: `,` when omitted
- `header`: `true` when omitted
- `if_exists`: `error` when omitted
- `on_duplicate`: `error`
- `runtime.run_id`: `auto`
- `runtime.log_level`: `INFO`
- `runtime.summary_output`: omitted, and `summary.json` defaults to the directory of `error_handling.error_output`

## 20. Phase 1 limitations

- `on_duplicate` supports only `error`.
- `if_exists` supports only `error` and `overwrite`.
- Multiple input joins are not supported.
- Excel, JSON, DB, Web UI, plugins, and streaming are not supported.
- Advanced date input/output format conversion is not included.
- Dry-run builds an output preview for `source`, `value`, `concat`, `map`, `when`, `lookup`, `expression`, and `derived` mappings.
- Dry-run does not write the output file.
- Filters, validations, and report generation are supported in dry-run and run.
- `dry-run --write-reports` can write `errors.csv`, `skipped.csv`, and `summary.json` without writing the main output CSV.
- `run` always writes the main output CSV and report files.
- `--html-report` is optional CLI output only; it writes `report.html` beside the other reports and does not alter `summary.json`, `errors.csv`, or `skipped.csv`.
- `runtime.max_input_rows` and `runtime.max_reference_rows` are guardrails only; they do not change normal loading behavior when omitted.

## 21. Generate-config basic

`generate-config` creates a minimal Phase 1 YAML skeleton from the input CSV headers.

Generation rules:

- `source_columns` always stores the original CSV header name.
- Internal schema field names are generated as safe snake_case names when possible.
- Headers with spaces, hyphens, and uppercase letters are normalized to snake_case.
- Headers starting with a digit receive a `col_` prefix.
- Headers that cannot be made safe, such as Japanese headers, use generated names like `field_001`, `field_002`.
- Duplicate safe names receive suffixes such as `_2`, `_3`.
- `type` is always `string`.
- `required` is always `false`.
- `normalize` is always `[trim]`.
- `references`, `derived`, `filters`, `validations`, and `checks` are omitted.
- `mappings` contains only `source` mappings.
- `outputs.columns` preserves the original headers by default when they are suitable for a valid config.
- When original headers cannot be used safely, the generator may fall back to safe generated output column names.
- `header: false` input files are not supported by the generator.

## 22. Profile-input enhanced

`profile-input` inspects the normalized input dataframe without writing any output files or reports.
It supports a `--limit N` option to profile only the first `N` normalized rows, a `--chunk-size N` option to read the CSV with `pandas.read_csv(..., chunksize=N)`, and a `--format text|json` option.
`--limit` and `--chunk-size` can be combined.

Text output keeps the existing headings:

- `datamapx input profile`
- `Input name:`
- `Rows:`

and adds `Profiled rows:`, `Limit:`, a per-column metric block, and limited-sample note when `--limit` is used.

JSON output returns:

- `input_name`
- `path`
- `encoding`
- `delimiter`
- `profiled_rows`
- `limit`
- `columns`

Each column entry includes:

- `name`
- `schema_type`
- `dtype`
- `missing_count`
- `missing_rate`
- `non_null_count`
- `unique_count`
- `duplicate_count`
- `sample_values`
- `top_values` for string fields
- `min_length` and `max_length` for string fields
- `min`, `max`, and `mean` for integer and decimal fields

Chunked profiling keeps the same `InputProfile` / `ColumnProfile` structure as the whole-file path.
Because the command still reports exact `unique_count` and `top_values`, high-cardinality columns may use additional in-memory aggregation state while chunks are processed.

## 23. Preflight

`preflight` is a read-only lightweight inspection command for migration, merge, union, and run-all configs.
It validates the loaded config first, then checks the configured CSV files without loading full dataframes.

Phase 2 preflight checks:

- config validation through the existing loaders
- CSV file existence
- `header: true`
- readable CSV header rows
- `schema` field resolution against raw header columns
- `required` schema fields must resolve to at least one raw column
- `source_columns` candidates are all considered raw-column candidates
- key columns in merge/union inputs and migration references must resolve
- output path parent directories must already exist or be creatable
- `if_exists: error` must fail when the final output file already exists
- `runtime.max_input_rows` and `runtime.max_reference_rows`, when configured, must be enforced using row counting without loading the full dataframe

For `run-all.yml`, the command resolves each job in order and stops at the first failing job.
Preflight does not create output CSVs, reports, or logs.

## Open Questions

- Column naming rules when `header: false`.
