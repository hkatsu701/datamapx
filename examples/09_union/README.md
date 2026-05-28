# 09_union

How to vertically append two same-format CSV files with `datamapx union`.

```bash
datamapx union examples/09_union/union.yml
```

The example keeps the row order of `file_a` first, then `file_b`.
Keys are required and duplicate or missing keys fail the run.
