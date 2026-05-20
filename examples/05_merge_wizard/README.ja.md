# 05 Merge Wizard Example

英語版READMEはこちら: [README.md](README.md)

## 1. このexampleで学べること

- `merge-wizard` で merge.yml を作る流れ
- 入力CSV、出力列、列名変更、ルールを番号で選ぶ考え方
- 2つのCSVを left join して staging CSV にまとめる方法

## 2. ファイル構成

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

## 3. 実行コマンド

```bash
datamapx validate-config examples/05_merge_wizard/merge.yml
datamapx merge examples/05_merge_wizard/merge.yml
```

## 4. validate-config

merge.yml の構造と参照先が正しいかを確認します。

## 5. merge

staging CSV を `output/merged.csv` に出力し、reports も作成します。

## 6. YAML の注目ポイント

- `merge.base: users`
- `merge.join_type: left`
- `id` は `users.id` をそのまま使う
- `display_name` は `accounts.account_name` を先に使い、必要なら `users.name` に戻る
- `total_amount` は 2つの amount を合計する

## 7. 期待される結果

- 3 行の出力が作られる
- `output/merged.csv` が `expected/output/merged.csv` と一致する
- reports も出力される

