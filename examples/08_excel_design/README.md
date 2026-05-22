# 08 Excel Design Template Example

Japanese README: [README.ja.md](README.ja.md)

## 1. What this example is

- A standard DataMapX Excel migration design template sample.
- A workbook-style reference for the future `design-to-yaml` implementation.
- A sample that shows how one design can describe multiple merge and migration jobs.

## 2. What it contains

```text
examples/08_excel_design/
  README.md
  README.ja.md
  sheets/
    project.csv
    jobs.csv
    merge_inputs.csv
    merge_rules.csv
    migration_inputs.csv
    input_schema.csv
    references.csv
    reference_schema.csv
    derived.csv
    outputs.csv
    mappings.csv
    validations.csv
    filters.csv
    checks.csv
    error_handling.csv
    runtime.csv
```

## 3. How to read it

- `jobs.csv` defines the job graph and execution order.
- `merge_*.csv` rows define merge jobs.
- `migration_*.csv` rows define migration jobs.
- The detailed sheets are linked with `job_id`.
- The sample is intentionally structured so the future parser can generate multiple YAML files and an execution script.

## 4. Notes

- This example is documentation-first.
- It is not executable yet because the Excel parser and `design-to-yaml` command are not implemented.
- The sheet CSVs are the canonical template sample for the new Excel specification.
