# datamapx

英語版READMEはこちら: [README.md](README.md)

DataMapX は、YAML 設定に基づいて CSV を CSV に変換・検証する Python CLI ツールです。日本語CSVや日本企業のデータ移行でも使いやすいように、入力列名・内部field名・出力列名を分けて扱えます。

Current release: v0.2.1.

## 1. DataMapXとは

- 1つの入力CSVと複数の参照CSVを扱えます。
- YAML で変換ルールを定義します。
- 変換、lookup、条件分岐、計算、検証、レポート出力までを CLI で実行できます。

## 2. 主な機能

- `source` / `value` / `concat` / `map` / `lookup` / `when` / `expression` / `derived`
- フィルタによる行除外
- 入力・出力 validation
- `errors.csv` / `skipped.csv` / `summary.json`
- `validate-config` / `inspect` / `profile-input` / `dry-run` / `run`
- `generate-config` による YAML ひな形生成

## 3. 現時点でできること

- CSV ヘッダーから最低限動作する `migration.yml` を作る
- 日本語ヘッダーを `source_columns` に保持する
- `dry-run` で変換結果を確認する
- `run` で main output CSV とレポートを出力する

## 4. 現時点でできないこと

- 型推定
- `required` 推定
- lookup 自動生成
- validation 自動生成
- filters 自動生成
- template / wizard / AI 支援
- Excel / JSON / DB 対応
- 複数 Input / 複数 Output
- `check` rule の本格実行

## 5. インストール / 開発環境セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## 6. クイックスタート

1. CSV を用意します。
2. `generate-config` で `migration.yml` のひな形を作ります。
3. 必要に応じて YAML を修正します。
4. `validate-config` で確認します。
5. `dry-run` でプレビューします。
6. `run` で出力します。

```bash
PYTHONPATH=src python -m datamapx.cli generate-config \
  --input examples/01_basic_mapping/input/users.csv \
  --output examples/01_basic_mapping/output/generated_users_out.csv \
  --config /tmp/generated_migration.yml \
  --input-name users \
  --output-name users_out

PYTHONPATH=src python -m datamapx.cli validate-config /tmp/generated_migration.yml
PYTHONPATH=src python -m datamapx.cli dry-run /tmp/generated_migration.yml --limit 5
PYTHONPATH=src python -m datamapx.cli run /tmp/generated_migration.yml
```

インストール後は `PYTHONPATH=src` は不要です。

```bash
datamapx generate-config --input ... --output ... --config ...
datamapx validate-config /tmp/generated_migration.yml
datamapx dry-run /tmp/generated_migration.yml --limit 5
datamapx run /tmp/generated_migration.yml
```

## 7. generate-config で migration.yml を作る

`generate-config basic` は、CSV ヘッダーから最低限動作する `migration.yml` のひな形を作る機能です。

- 型推定はしません
- `required` 推定はしません
- lookup や validation は自動生成しません
- 生成後に必要に応じて `migration.yml` を編集します
- まずは `validate-config` と `dry-run` で確認します

## 8. validate-config

YAML の構造、参照先、Phase 1 の制約を確認します。

## 9. dry-run

実ファイルを書かずに、入力・参照・フィルタ・validation・出力プレビューを確認します。

## 10. run

main output CSV と以下のレポートを出力します。

- `errors.csv`
- `skipped.csv`
- `summary.json`

## 11. 出力ファイル

- main output CSV: 変換後の本体CSV
- `errors.csv`: validation や runtime error の行
- `skipped.csv`: filter で除外された行
- `summary.json`: 件数、状態、出力先パスのサマリ

## 12. YAML設定の最小例

```yaml
version: 1

project:
  name: user_migration

inputs:
  users:
    path: ./input/users.csv
    encoding: utf-8-sig
    delimiter: ","
    header: true
    schema:
      user_id:
        source_columns: ["顧客ID"]
        type: string
        required: false
        normalize: [trim]

outputs:
  users_out:
    path: ./output/users_out.csv
    encoding: utf-8-sig
    delimiter: ","
    header: true
    newline: "\n"
    if_exists: overwrite
    columns:
      - CustomerCode

mappings:
  users_out:
    CustomerCode:
      source: users.user_id
```

## 13. examples

- [01_basic_mapping](examples/01_basic_mapping/README.md) / [日本語](examples/01_basic_mapping/README.ja.md)
- [02_lookup](examples/02_lookup/README.md) / [日本語](examples/02_lookup/README.ja.md)
- [03_validation_errors](examples/03_validation_errors/README.md) / [日本語](examples/03_validation_errors/README.ja.md)
- [04_japanese_csv](examples/04_japanese_csv/README.md) / [日本語](examples/04_japanese_csv/README.ja.md)

## 14. 日本語CSVの扱い

- 日本語ヘッダーは `source_columns` に保持します。
- 内部field名は `col_001`、`col_002` のような安全名になることがあります。
- `outputs.columns` はデフォルトでは元CSVヘッダーを使えます。
- UTF-8 BOM 付きCSVには `utf-8-sig` を使うと Excel で扱いやすくなります。
- CSV 上の項目名、schema の内部field名、output CSV の項目名は分けて扱えます。

例:

- input CSV: `顧客ID`
- schema field: `user_id`
- output column: `CustomerCode`

```yaml
schema:
  user_id:
    source_columns: ["顧客ID"]
    type: string
    required: false
    normalize:
      - trim

mappings:
  users_out:
    CustomerCode:
      source: users.user_id
```

## 15. 制限事項

- 単一 input CSV のみ
- 複数 reference CSV は可
- 単一 output CSV のみ
- Excel / JSON / DB 非対応
- 複数 Input join 非対応
- 複数 Output 非対応
- `check` rule の本格実行は未対応

## 16. ロードマップ

[docs/roadmap.md](docs/roadmap.md) を参照してください。

## 17. ライセンス

MIT License。詳細は [LICENSE](LICENSE) を参照してください。
