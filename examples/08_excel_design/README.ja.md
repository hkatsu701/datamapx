# 08 Excel 設計テンプレート例

英語版READMEはこちら: [README.md](README.md)

## 1. このexampleの位置づけ

- DataMapX 標準の Excel 移行設計書テンプレート例です。
- 将来の `design-to-yaml` 実装に向けた workbook 仕様の参照用です。
- 1つの設計書から複数の merge job / migration job を表現する例です。

## 2. 含まれる内容

```text
examples/08_excel_design/
  README.md
  README.ja.md
  generate_template.py
  datamapx_design_template.xlsx
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

## 3. 見方

- `jobs.csv` に job の並びと依存関係を書きます。
- `merge_*.csv` は merge job 用です。
- `migration_*.csv` は migration job 用です。
- 詳細シートはすべて `job_id` で紐づけます。
- この sample は、将来の parser が複数 YAML と実行スクリプトを作る前提で置いています。
- `datamapx_design_template.xlsx` が Excel で確認する本体です。
- `python generate_template.py` で CSV のシート定義から再生成できます。

## 4. 補足

- この example は documentation-first です。
- Excel parser と `design-to-yaml` コマンドはまだ未実装です。
- 各 sheet の CSV は、標準テンプレートのひな形として使います。
