# 09_union

同じフォーマットのCSV 2件を `datamapx union` で縦結合する例です。

```bash
datamapx union examples/09_union/union.yml
```

`file_a` の行が先に出力され、そのあとに `file_b` の行が続きます。
キーは必須で、重複キーと欠損キーはエラーになります。
