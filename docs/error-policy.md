# Error Policy

## 1. Error Categories

### config error

Configuration cannot be parsed, validated, or safely executed. Examples include invalid YAML, missing required sections, undefined field references, unsupported Phase 1 settings, and output mapping mismatches.

In Phase 1, `validate-config` treats undefined field references as configuration errors. This includes references found in mappings, derived fields, expressions, conditions, filters, validations, and check rules that are expected to use only reserved summary variables.

### input validation error

An input row fails a validation rule or schema requirement, such as `required`, type conversion, or regex validation.

### output validation error

A transformed output row fails an output validation rule, such as `required`, `enum`, `min`, `max`, `regex`, or `length`.

### lookup missing

A lookup key does not match any row in the configured reference CSV.

### lookup duplicate

A reference CSV contains duplicate keys. Phase 1 supports only `on_duplicate: error`.

### transform error

A mapping, derived field, condition, or expression cannot be evaluated for a row.

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
- Lookup missing: row is retained internally as an error row and written to `errors.csv` in `run`, or when `--write-reports` is used in `dry-run`
- Type conversion failure: stop during CSV loading
- Validation failure: row is retained internally as an error row and written to `errors.csv` in `run`, or when `--write-reports` is used in `dry-run`
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
- Mapping runtime error: fatal stop
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
Supported condition forms are direct comparisons, `in`, and `not in` against one input field reference.
General expressions, function calls, field-to-field comparisons, and logical `and` / `or` combinations are unsupported during execution.

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
- `input_rows`
- `output_rows`
- `error_rows`
- `skipped_rows`
- `reference_rows`
- `checks`
- `status`

The run summary also includes nested `input`, `references`, `output`, `counts`, `reports`, and `notes` sections. `output.path` records the resolved main output CSV path.

`status` should be one of:

- `success`
- `completed_with_errors`
- `failed`

JSON report writers use `ensure_ascii=False` so Japanese text is preserved in CSV JSON columns and `summary.json`.

## 6. Run Exit Policy

- Validation error rows are data quality failures, not fatal execution failures. `run` exits `0` when it completes and writes all configured files successfully.
- Mapping runtime errors are fatal in Phase 1. If a mapping rule cannot be evaluated safely, `run` exits `1`.
- CSV write failures for the main output CSV or report files are fatal and exit `1`.

## Open Questions

- Whether row-level errors should allow exit code `0` when the run completes according to configured policy.
- Behavior for existing `errors.csv`, `skipped.csv`, and `summary.json` when `if_exists: overwrite` is used in the future `run` command.
