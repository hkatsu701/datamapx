# 04 Japanese CSV

英語版READMEはこちら: [README.md](README.md)

## 1. このexampleで学べること

- 日本語ヘッダーを扱う方法
- `source_columns` の使い方
- input CSV 上の項目名、schema field 名、output CSV 項目名を分ける考え方
- UTF-8 BOM 付きCSVを `utf-8-sig` で扱う方法

## 2. ファイル構成

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
    output/users_out.csv
    reports/errors.csv
    reports/skipped.csv
    reports/summary.json
```

## 3. 実行コマンド

開発環境:

```bash
PYTHONPATH=src python -m datamapx.cli validate-config examples/04_japanese_csv/migration.yml
PYTHONPATH=src python -m datamapx.cli dry-run examples/04_japanese_csv/migration.yml --limit 5
PYTHONPATH=src python -m datamapx.cli run examples/04_japanese_csv/migration.yml
```

インストール後:

```bash
datamapx validate-config examples/04_japanese_csv/migration.yml
datamapx dry-run examples/04_japanese_csv/migration.yml --limit 5
datamapx run examples/04_japanese_csv/migration.yml
```

## 4. migration.yml の注目ポイント

- 日本語ヘッダーを `source_columns` に保持する
- 内部 field 名は `col_001` のような安全名になることがある
- `trim` / `remove_commas` / `remove_currency_symbol`
- `lookup`
- `utf-8-sig`

## 5. 出力されるファイル

- `output/users_out.csv`
- `reports/errors.csv`
- `reports/skipped.csv`
- `reports/summary.json`

## 6. 期待される結果

- `顧客ID` や `部署コード` が内部 field 名に対応づけられる
- output CSV の項目名は `CustomerCode` や `CustomerName` のように別名にできる
- Excel で開きやすい UTF-8 BOM 付きCSV が出力される
