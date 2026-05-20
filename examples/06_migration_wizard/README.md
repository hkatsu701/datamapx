# 06 Migration Wizard Example

Japanese README: [README.ja.md](README.ja.md)

## 1. This example teaches

- How to build a full `migration.yml` with `migration-wizard`.
- Numbered selection, rename, schema overrides, `lookup`, `derived`, `expression`, `when`, `validations`, `filters`, and `checks`.
- How the wizard stays usable for people who want the result but do not write YAML by hand.

## 2. File layout

```text
examples/06_migration_wizard/
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
datamapx validate-config examples/06_migration_wizard/migration.yml
datamapx dry-run examples/06_migration_wizard/migration.yml --limit 5
```

## 4. validate-config

Checks that the full wizard-authored YAML is structurally valid and that all references resolve.

## 5. dry-run

Loads the input and reference CSVs, applies the schema, and shows the output preview without writing files.

## 6. YAML highlights

- Input schema overrides for `user_id`, `full_name`, `department_code`, `amount`, `status_code`, and `active_flag`
- Reference schema overrides for `dept_code`, `dept_name`, and `bonus_rate`
- `lookup` for department name and bonus rate
- `derived.tax_amount`
- `expression` for gross amount
- `when` for `status_label`
- `validations` for input and output fields
- `filters` for positive amounts and excluded rows
- `checks` for row-count summary assertions

## 7. Expected result

- The YAML validates successfully.
- `dry-run` completes successfully.
- The preview shows the configured output columns and the derived / lookup / conditional fields.
