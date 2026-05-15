# 03 validation_errors

英語版READMEはこちら: [README.md](README.md)

## 1. このexampleで学べること

- input validation と output validation の動き
- validation error rows が `errors.csv` に出ること
- validation error rows は output CSV に出ないこと

## 2. ファイル構成

```text
examples/03_validation_errors/
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
PYTHONPATH=src python -m datamapx.cli validate-config examples/03_validation_errors/migration.yml
PYTHONPATH=src python -m datamapx.cli dry-run examples/03_validation_errors/migration.yml --limit 5
PYTHONPATH=src python -m datamapx.cli run examples/03_validation_errors/migration.yml
```

インストール後:

```bash
datamapx validate-config examples/03_validation_errors/migration.yml
datamapx dry-run examples/03_validation_errors/migration.yml --limit 5
datamapx run examples/03_validation_errors/migration.yml
```

## 4. migration.yml の注目ポイント

- `validations.input`
- `validations.output`
- `required`
- `enum`
- `min` / `max`
- `regex`
- `length`

## 5. 出力されるファイル

- `output/users_out.csv`
- `reports/errors.csv`
- `reports/skipped.csv`
- `reports/summary.json`

## 6. 期待される結果

- 正常行だけが main output CSV に出る
- validation error rows は `errors.csv` に出る
- `skipped.csv` は filter を使っていないためヘッダーのみ
- `summary.json` で件数を確認できる
