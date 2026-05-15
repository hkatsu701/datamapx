# 03 Validation Errors

## 1. This example teaches

- How input and output validation rules work.
- How validation error rows are written to `errors.csv`.
- How `run` still completes successfully when row-level errors exist.

## 2. File layout

```text
examples/03_validation_errors/
  input/
    users.csv
  migration.yml
  output/
    .gitkeep
  reports/
    .gitkeep
  expected/
    .gitkeep
```

## 3. Commands

```bash
datamapx validate-config examples/03_validation_errors/migration.yml
datamapx dry-run examples/03_validation_errors/migration.yml --limit 5
datamapx run examples/03_validation_errors/migration.yml
```

## 4. validate-config

Checks the validation rule structure before execution.

## 5. dry-run

Shows validation error counts and an error preview.

## 6. run

Writes:

- main output CSV with valid rows only
- `errors.csv` with validation error rows
- `skipped.csv` with a header row only if no filters are configured
- `summary.json` with counts and file paths

## 7. Output files

- `output/users_out.csv`
- `reports/errors.csv`
- `reports/skipped.csv`
- `reports/summary.json`

## 8. YAML highlights

- `validations.input`
- `validations.output`
- `required`
- `enum`
- `min`
- `max`
- `regex`
- `length`

## 9. Expected result

- Only valid rows are written to the main output CSV.
- `errors.csv` contains row-level failures.
- `skipped.csv` contains only a header row because no filters are configured.
