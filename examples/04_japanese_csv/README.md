# 04 Japanese CSV

## 1. This example teaches

- How Japanese CSV headers map to canonical schema field names.
- How `source_columns` decouples input CSV names from schema names.
- How output CSV names can be independent from both raw input and schema names.

## 2. File layout

```text
examples/04_japanese_csv/
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
datamapx validate-config examples/04_japanese_csv/migration.yml
datamapx dry-run examples/04_japanese_csv/migration.yml --limit 5
datamapx run examples/04_japanese_csv/migration.yml
```

## 4. validate-config

Confirms that Japanese source column names map to canonical schema field names.

## 5. dry-run

Shows the normalized dataframe using the schema field names.

## 6. run

Writes the Excel-friendly UTF-8 BOM output CSV and the report files.

## 7. Output files

- `output/users_out.csv`
- `reports/errors.csv`
- `reports/skipped.csv`
- `reports/summary.json`

## 8. YAML highlights

- Japanese `source_columns`
- `trim`
- `remove_commas`
- `remove_currency_symbol`
- `lookup`
- `utf-8-sig` output

## 9. Expected result

- Input column names such as `顧客ID` and `部署コード` are mapped to canonical field names.
- Output column names such as `CustomerCode` and `CustomerName` are independent of the input schema names.
