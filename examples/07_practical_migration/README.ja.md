# 07 Practical Migration Example

英語版READMEはこちら: [README.md](README.md)

## 1. このexampleで学べること

- 実案件に近い請求・入金の migration を `migration.yml` で表現する方法
- `lookup`、複合 `lookup`、`derived`、`when`、`expression`、`filters`、`validations`、`checks`、`summary.json` のつながり
- 1つの input CSV、2つの reference CSV、1つの output CSV を手書き Python なしで整合させる流れ

## 2. ファイル構成

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

## 3. 実行コマンド

```bash
datamapx validate-config examples/07_practical_migration/migration.yml
datamapx dry-run examples/07_practical_migration/migration.yml --write-reports --reports-dir /tmp/datamapx-reports
datamapx run examples/07_practical_migration/migration.yml --reports-dir /tmp/datamapx-reports
```

## 4. validate-config

YAML の構造と参照先が正しいかを確認します。

## 5. dry-run と run

validation error、lookup error、filter skip が同時に起きても、全体としては処理が完了する例です。

## 6. YAML の注目ポイント

- `customer_code` から `customer_id` を引く `lookup`
- `customer_class` と `billing_type` を組み合わせた複合 `lookup`
- `outstanding_amount` の `expression`
- `derived` を使った `payment_state`
- 入力値に応じた `invoice_category` の `when`
- `CANCELLED` 行を落とす `filters`
- 0円行の validation
- 行数確認の `checks`

## 7. 期待される結果

- `validate-config` が成功する
- `dry-run` が成功し、必要なら reports も出る
- `run` が成功し、output と reports が出る
- summary に row-level error と `completed_with_row_errors` が出る
