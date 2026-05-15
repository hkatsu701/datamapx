# 02 Lookup

## 1. This example teaches

- How to resolve values from a reference CSV.
- Single-key lookup with `on_missing: default`.
- The shape of the reference file and lookup config.

## 2. File layout

```text
examples/02_lookup/
  input/
    users.csv
  ref/
    departments.csv
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
datamapx validate-config examples/02_lookup/migration.yml
datamapx dry-run examples/02_lookup/migration.yml --limit 5
datamapx run examples/02_lookup/migration.yml
```

## 4. validate-config

Checks that the lookup references the configured `departments` CSV and that the output columns are mapped.

## 5. dry-run

Shows lookup results in the output preview.

## 6. run

Writes the main output CSV and the three report files.

## 7. Output files

- `output/users_out.csv`
- `reports/errors.csv`
- `reports/skipped.csv`
- `reports/summary.json`

## 8. YAML highlights

- `lookup.reference`
- `lookup.key`
- `lookup.value`
- `lookup.on_missing: default`

## 9. Expected result

- Three output rows.
- One lookup falls back to `Unknown`.
- `errors.csv` has only a header row.
