# 01 基本の変換

英語版READMEはこちら: [README.md](README.md)

## 1. このexampleで学べること

- CSV 変換の最小構成
- `source` / `value` / `concat` / `map` / `expression` の使い方
- `run` で main output CSV と reports が出ること

## 2. ファイル構成

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
    output/users_out.csv
    reports/errors.csv
    reports/skipped.csv
    reports/summary.json
```

## 3. 実行コマンド

開発環境:

```bash
PYTHONPATH=src python -m datamapx.cli validate-config examples/01_basic_mapping/migration.yml
PYTHONPATH=src python -m datamapx.cli dry-run examples/01_basic_mapping/migration.yml --limit 5
PYTHONPATH=src python -m datamapx.cli run examples/01_basic_mapping/migration.yml
```

インストール後:

```bash
datamapx validate-config examples/01_basic_mapping/migration.yml
datamapx dry-run examples/01_basic_mapping/migration.yml --limit 5
datamapx run examples/01_basic_mapping/migration.yml
```

## 4. migration.yml の注目ポイント

- `source`: 元CSVの列をそのまま出す
- `value`: 固定値を入れる
- `concat`: 姓名を連結する
- `map`: コード値を表示名に変える
- `expression`: 金額計算をする

## 5. 出力されるファイル

- `output/users_out.csv`
- `reports/errors.csv`
- `reports/skipped.csv`
- `reports/summary.json`

## 6. 期待される結果

- 3 行の出力が作られる
- `errors.csv` はヘッダーのみ
- `skipped.csv` はヘッダーのみ
- `summary.json` に件数が入る
