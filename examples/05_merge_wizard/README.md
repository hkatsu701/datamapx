# 05 Merge Wizard Example

Japanese README: [README.ja.md](README.ja.md)

## 1. This example teaches

- How to build a merge configuration with `merge-wizard`.
- Numbered selection for inputs, output columns, renames, and merge rules.
- A simple left join that combines two CSV files into one staging CSV.

## 2. File layout

```text
examples/05_merge_wizard/
  input/
    users.csv
    accounts.csv
  merge.yml
  output/
    .gitkeep
  reports/
    .gitkeep
  expected/
    output/
      merged.csv
```

## 3. Commands

```bash
datamapx validate-config examples/05_merge_wizard/merge.yml
datamapx merge examples/05_merge_wizard/merge.yml
```

## 4. validate-config

Checks that the merge YAML is structurally valid and that merge references resolve.

## 5. merge

Writes the staging CSV to `output/merged.csv` and writes merge reports under `reports/`.

## 6. YAML highlights

- `merge.base: users`
- `merge.join_type: left`
- `id` uses `users.id` directly
- `display_name` uses `accounts.account_name` first, then `users.name`
- `total_amount` sums the two amount columns

## 7. Expected result

- Three output rows.
- `output/merged.csv` matches `expected/output/merged.csv`.
- Merge reports are written next to the output CSV.

