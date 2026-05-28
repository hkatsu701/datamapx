# 複数出力の例

Phase 2 の `run` で、同じ入力から 2 つの出力 CSV を書き出す例です。

## ファイル

- `migration.yml`
- `input_users.csv`
- `ref_departments.csv`

## 実行

```bash
datamapx run migration.yml
```

出力されるファイル:

- `output/users_out.csv`
- `output/users_out_copy.csv`
- `reports/errors.csv`
- `reports/skipped.csv`
- `reports/summary.json`
