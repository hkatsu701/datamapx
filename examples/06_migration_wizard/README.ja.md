# 06 Migration Wizard Example

英語版READMEはこちら: [README.md](README.md)

## 1. このexampleで学べること

- `migration-wizard` で full の `migration.yml` を作る流れ
- 出力列数と列名の明示入力、入力列と参照列の読み込み設定、`lookup`、`derived`、`expression`、`when`、`validations`、`filters`、`checks`
- YAML を手書きしない人でも、欲しい変換を wizard で組み立てられること

## 2. ファイル構成

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

## 3. 実行コマンド

```bash
datamapx validate-config examples/06_migration_wizard/migration.yml
datamapx dry-run examples/06_migration_wizard/migration.yml --limit 5
```

## 4. validate-config

wizard で作った YAML の構造と参照先が正しいかを確認します。

## 5. dry-run

入力CSVと参照CSVを読み込み、出力プレビューを表示します。ファイルは書き込みません。

## 6. YAML の注目ポイント

- `user_id`、`full_name`、`department_code`、`amount`、`status_code`、`active_flag` の入力列の読み込み設定
- 出力列 6 本の定義と、それぞれの rule
- `dept_code`、`dept_name`、`bonus_rate` の参照列の読み込み設定
- 部署名と料率を取る `lookup`
- `derived.tax_amount`
- `gross_amount` の `expression`
- `status_label` の `when`
- input / output の `validations`
- 正の金額だけを通す `filters`
- 行数確認用の `checks`

## 7. 期待される結果

- YAML が正しく検証される
- `dry-run` が成功する
- 出力プレビューに lookup、derived、条件分岐の結果が反映される
