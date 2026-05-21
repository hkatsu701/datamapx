# Error Policy

## 1. Error Categories

### config error

Configuration cannot be parsed, validated, or safely executed. Examples include invalid YAML, missing required sections, undefined field references, unsupported Phase 1 settings, and output mapping mismatches.

In Phase 1, `validate-config` treats undefined field references as configuration errors. This includes references found in mappings, derived fields, expressions, conditions, filters, validations, and check rules that are expected to use only reserved summary variables.

### input validation error

An input row fails a validation rule or schema requirement, such as `required`, type conversion, or regex validation.
When `error_handling.on_validation_error` is `output_error`, the row is retained internally as an error row. When it is `stop`, execution stops.

### output validation error

A transformed output row fails an output validation rule, such as `required`, `enum`, `min`, `max`, `regex`, or `length`.

### lookup missing

A lookup key does not match any row in the configured reference CSV. In Phase 1 this is reported as a row-level mapping error when `error_handling.on_lookup_missing` is `output_error`, and as a fatal stop reason when it is `stop`.

### lookup duplicate

A reference CSV contains duplicate keys. Phase 1 supports only `on_duplicate: error`.

### transform error

A mapping, derived field, condition, or expression cannot be evaluated for a row. In Phase 1 this is reported as a row-level mapping error when `error_handling.on_transform_error` is `output_error`, and as a fatal stop reason when it is `stop`.

### skipped row

A row is intentionally excluded by a configured filter.

### warning

A non-fatal condition that should be visible to the user but does not make output invalid.

### check failure

A configured run-level check evaluated to false after the pipeline completed.

### fatal error

An error that requires execution to stop immediately, such as invalid configuration, unsupported settings, unreadable input files, reference duplicate keys, or reaching `max_errors`.

CSV reader errors are runtime errors in Phase 1 and produce CLI exit code `1`.

`dry-run` currently executes CSV loading, schema application, reference validation, validation filtering, and in-memory output preview construction for supported mappings. Errors in these steps stop the command with exit code `1`.

`run` executes the same pipeline and then writes the main output CSV plus `errors.csv`, `skipped.csv`, and `summary.json`. Validation error rows do not make `run` fail if the pipeline completes and the files are written successfully.

## 2. Default Behavior

- Invalid YAML structure: stop
- Undefined field reference: stop
- Output columns and mappings mismatch: stop
- Reference duplicate key: stop
- Lookup missing: row is retained internally as an error row when `error_handling.on_lookup_missing` is `output_error`; stop when it is `stop`
- Type conversion failure: stop during CSV loading
- Validation failure: row is retained internally as an error row when `error_handling.on_validation_error` is `output_error`; stop when it is `stop`
- Filter exclusion: row is retained internally as a skipped row and written to `skipped.csv` in `run`, or when `--write-reports` is used in `dry-run`
- Check failure: stop after the pipeline completes and report the failed assertion
- Reaching `max_errors`: stop
- CSV file missing or unreadable: stop
- Unsupported `header: false`: stop
- Required input column missing: stop
- Type conversion failure during CSV read/schema application: stop
- Reference key column missing: stop
- Reference key value missing: stop
- Reference key duplicate: stop
- Mapping source field missing: stop
- Concat field reference missing: stop
- Map source field missing: stop
- Map value unmatched and `default` omitted: stop
- Lookup reference missing or not loaded: stop
- Lookup input key field missing: stop
- Lookup value column missing from reference: stop
- Lookup single/composite key shape mismatch: stop
- Lookup missing with `on_missing: error`: stop
- Lookup missing with `on_missing: default`: use `default`, or stop if `default` is omitted
- Lookup missing with `on_missing: empty`: use an empty string
- Lookup missing with `on_missing: "null"`: use a missing value
- When mapping is malformed: stop
- When condition uses an unsupported expression: stop
- When condition references an unknown namespace or field: stop
- When no condition matches and `default` is omitted: stop
- When `then` or `default` uses an unsupported field reference: stop
- Expression is not a string: stop
- Expression references an unknown field: stop
- Expression references an unknown or unsupported namespace: stop
- Expression uses a missing field value: stop
- Expression calls a function outside the allowlist: stop
- Expression uses unsupported syntax or an unsupported operator: stop
- Expression evaluation fails: stop
- Derived field references an unknown derived field: stop
- Derived field dependencies cannot be resolved: stop
- Derived field circular dependency is detected: stop
- Derived field mapping execution fails: stop
- Filter condition uses an unsupported expression: stop
- Filter condition references an unknown namespace or field: stop
- Filter item is missing `if`: stop
- `filters.include` or `filters.exclude` is not a list: stop
- Filtered rows are retained internally as skipped rows during dry-run
- Unsupported mapping rule during execution: stop
- Mapping runtime error: fatal stop when the configured policy is `stop`; otherwise retain the row as an error row
- Output CSV write error: fatal stop
- Report write error: fatal stop

The default policy favors correctness and explainability over permissive output.

During `dry-run`, input rows may be limited with `--limit`, but references are still loaded fully. Reference duplicate detection is always performed against all configured reference rows.

Phase 1 field reference validation rules:

- `input_name.field_name` must reference a field defined in `inputs.<input_name>.schema`.
- `derived.field_name` must reference a key defined in `derived`.
- `validations.input[].field` must reference the single input namespace.
- `validations.output[].field` must be an output column name.
- `checks[].rule` may use only `input_rows`, `output_rows`, `error_rows`, and `skipped_rows` as reserved summary variables.
- `validate-config` does not evaluate expressions or conditions; it validates only their field references or reserved variable names.

Phase 1 `when` execution uses a limited parser instead of Python `eval`.
Supported condition forms are direct comparisons, `in`, `not in`, logical `and` / `or`, `is null`, `is not null`, and bare boolean field references against `users.*` or `derived.*`.
General arithmetic expressions, function calls, field-to-field comparisons, and grouped parenthesized expressions are unsupported during execution.

Phase 1 `expression` execution uses a safe arithmetic evaluator instead of Python `eval`.
Only `+`, `-`, `*`, `/`, `//`, `%`, `**`, parentheses, and the functions `round`, `abs`, `min`, and `max` are supported.
Expression field references must use the single input namespace.

Phase 1 derived fields are evaluated before output mappings. Derived fields may depend on other derived fields; dependencies are resolved before execution. Circular dependencies and unresolved `derived.*` references stop execution with exit code `1`.

Phase 1 filters run after derived field calculation and before output mapping. Include rules run before exclude rules. Skipped row metadata includes the original `__row_number`, reason, and normalized row data. `skipped.csv` is written by `run`, and dry-run only displays a skipped preview unless `--write-reports` is enabled.

Phase 1 checks run after output validation. `dry-run` and `run` both evaluate checks and exit with code `1` when any check fails.

## 3. errors.csv Schema

`errors.csv` records row-level failures that prevent a row from being written to the main output. In Phase 1 dry-run, `errors.csv` is written only when `--write-reports` is used. In `run`, it is always written.

Required columns:

- `run_id`
- `row_number`
- `stage`
- `field`
- `error_code`
- `message`
- `original_row_json`
- `normalized_row_json`

Recommended `stage` values:

- `input_validation`
- `normalize`
- `filter`
- `derived`
- `mapping`
- `lookup`
- `expression`
- `output_validation`

## 4. skipped.csv Schema

`skipped.csv` records rows intentionally excluded by filters. In Phase 1 dry-run, `skipped.csv` is written only when `--write-reports` is used. In `run`, it is always written.

Required columns:

- `run_id`
- `row_number`
- `reason`
- `original_row_json`

## 5. summary.json Schema

`summary.json` records the run-level result. In Phase 1 dry-run, `summary.json` is written only when `--write-reports` is used. In `run`, it is always written.

Required fields:

- `run_id`
- `project_name`
- `started_at`
- `finished_at`
- `config_path`
- `status`

The run summary also includes nested `input`, `references`, `output`, `counts`, `reports`, and `notes` sections. `output.path` records the resolved main output CSV path.

`counts` includes the aggregate row totals plus category breakdowns for validation errors, mapping errors, lookup missing errors, and transform errors. `notes` includes operational flags such as `dry_run`, `output_file_written`, `checks_passed`, `fatal_error`, `stop_reason`, `stop_message`, `max_errors_exceeded`, `completed_with_row_errors`, and `final_outcome`.

`status` records the runner command state. Current values include:

- `dry_run_completed`
- `dry_run_completed_with_check_failures`
- `completed`
- `completed_with_check_failures`
- `failed`

`notes.final_outcome` should be one of:

- `success`
- `completed_with_row_errors`
- `completed_with_check_failures`
- `failed`

JSON report writers use `ensure_ascii=False` so Japanese text is preserved in CSV JSON columns and `summary.json`.

## 6. Run Exit Policy

- Validation error rows are data quality failures, not fatal execution failures. `run` exits `0` when it completes and writes all configured files successfully.
- Mapping runtime errors respect `error_handling.on_lookup_missing` and `error_handling.on_transform_error`. `run` exits `0` when those policies are `output_error` and the pipeline completes successfully.
- CSV write failures for the main output CSV or report files are fatal and exit `1`.
- `summary.json` can report `notes.final_outcome == completed_with_row_errors` when row-level errors were retained but execution completed successfully.

## Open Questions

- Whether row-level errors should allow exit code `0` when the run completes according to configured policy.
- Behavior for existing `errors.csv`, `skipped.csv`, and `summary.json` when `if_exists: overwrite` is used in the future `run` command.
