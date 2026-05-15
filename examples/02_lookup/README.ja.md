# 02 lookup

英語版READMEはこちら: [README.md](README.md)

## 1. このexampleで学べること

- reference CSV を使った lookup
- `department_code` から `department_name` を引く例
- `on_missing: default` の意味

## 2. ファイル構成

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
    output/users_out.csv
    reports/errors.csv
    reports/skipped.csv
    reports/summary.json
```

## 3. 実行コマンド

開発環境:

```bash
PYTHONPATH=src python -m datamapx.cli validate-config examples/02_lookup/migration.yml
PYTHONPATH=src python -m datamapx.cli dry-run examples/02_lookup/migration.yml --limit 5
PYTHONPATH=src python -m datamapx.cli run examples/02_lookup/migration.yml
```

インストール後:

```bash
datamapx validate-config examples/02_lookup/migration.yml
datamapx dry-run examples/02_lookup/migration.yml --limit 5
datamapx run examples/02_lookup/migration.yml
```

## 4. migration.yml の注目ポイント

- `references.departments`
- `lookup.reference`
- `lookup.key`
- `lookup.value`
- `lookup.on_missing: default`

## 5. 出力されるファイル

- `output/users_out.csv`
- `reports/errors.csv`
- `reports/skipped.csv`
- `reports/summary.json`

## 6. 期待される結果

- `department_code` に対応する部署名が出力される
- 見つからない値は `Unknown` になる
- `errors.csv` はヘッダーのみ
