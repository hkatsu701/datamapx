# Multiple Outputs Example

This example shows Phase 2 `run` writing two output CSVs from the same input.

## Files

- `migration.yml`
- `input_users.csv`
- `ref_departments.csv`

## Run

```bash
datamapx run migration.yml
```

Expected outputs:

- `output/users_out.csv`
- `output/users_out_copy.csv`
- `reports/errors.csv`
- `reports/skipped.csv`
- `reports/summary.json`
