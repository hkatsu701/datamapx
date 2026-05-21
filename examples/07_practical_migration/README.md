# 07 Practical Migration Example

Japanese README: [README.ja.md](README.ja.md)

## 1. This example teaches

- How to model a realistic billing migration with `migration.yml`.
- How `lookup`, composite `lookup`, `derived`, `when`, `expression`, `filters`, `validations`, `checks`, and `summary.json` work together.
- How to keep one input CSV, two reference CSVs, and one output CSV consistent without hand-writing Python.

## 2. File layout

```text
examples/07_practical_migration/
  input/
    invoices.csv
  ref/
    customers.csv
    account_mappings.csv
  migration.yml
  output/
    .gitkeep
  reports/
    .gitkeep
```

## 3. Commands

```bash
datamapx validate-config examples/07_practical_migration/migration.yml
datamapx dry-run examples/07_practical_migration/migration.yml --write-reports --reports-dir /tmp/datamapx-reports
datamapx run examples/07_practical_migration/migration.yml --reports-dir /tmp/datamapx-reports
```

## 4. validate-config

Checks that the migration YAML is structurally valid and that all references resolve.

## 5. dry-run and run

The sample shows how row-level validation errors, lookup errors, and filter skips can coexist while the pipeline still completes.

## 6. YAML highlights

- `customer_id` is resolved from the customer code with `lookup`.
- `account_code` uses a composite `lookup` from customer class and billing type.
- `outstanding_amount` is calculated with `expression`.
- `payment_state` is assigned with `when` from a derived field.
- `invoice_category` is assigned with `when` directly from the input class.
- `CANCELLED` rows are excluded by `filters`.
- A zero-amount row triggers validation.
- Run-level checks assert row counts.

## 7. Expected result

- `validate-config` succeeds.
- `dry-run` succeeds and writes report files when requested.
- `run` succeeds and writes output plus reports.
- The summary reports row-level errors and `completed_with_row_errors`.
