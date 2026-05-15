# 01 Basic Mapping

## 1. This example teaches

- The smallest CSV-to-CSV transformation path.
- `source`, `value`, `concat`, `map`, and `expression` mappings.
- How `run` writes the main output CSV and report files.

## 2. File layout

```text
examples/01_basic_mapping/
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

Installed command:

```bash
datamapx validate-config examples/01_basic_mapping/migration.yml
datamapx dry-run examples/01_basic_mapping/migration.yml --limit 5
datamapx run examples/01_basic_mapping/migration.yml
```

Module command:

```bash
python -m datamapx.cli validate-config examples/01_basic_mapping/migration.yml
python -m datamapx.cli dry-run examples/01_basic_mapping/migration.yml --limit 5
python -m datamapx.cli run examples/01_basic_mapping/migration.yml
```

## 4. validate-config

Confirms that the YAML file is structurally valid and that field references resolve.

## 5. dry-run

Shows the load phase, filter summary, validation summary, and output preview.

## 6. run

Writes:

- `output/users_out.csv`
- `reports/errors.csv`
- `reports/skipped.csv`
- `reports/summary.json`

## 7. Output files

- `output/users_out.csv`: main converted CSV
- `reports/errors.csv`: row-level validation and transform errors
- `reports/skipped.csv`: skipped rows
- `reports/summary.json`: run summary

## 8. YAML highlights

- `source`: `user_id`
- `value`: `CRM`
- `concat`: full name from last and first name
- `map`: `status_code` to display status
- `expression`: `price * quantity`

## 9. Expected result

- Three output rows.
- No skipped rows.
- `errors.csv` contains only a header row.
- `summary.json` reports `output_rows: 3`.
