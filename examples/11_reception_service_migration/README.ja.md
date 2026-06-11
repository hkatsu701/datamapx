# 受付・サービスCSV作成

1つの入力CSVから、受付CSVとサービスCSVを作成するWindows向けサンプルです。

## ファイル構成

- `reception.yml`: 受付CSV作成
- `service.yml`: サービスCSV作成
- `run-all.yml`: 2つの処理を順次実行
- `run_migration.bat`: Windows実行用バッチ
- `run_service.bat`: 今回の正式なサービスCSVだけを作成するWindows実行用バッチ
- `uppercase_csv_headers.ps1`: 入力・参照CSVのヘッダーを大文字化する前処理

## 実行前提

Python 3.12以上とDataMapXをインストールします。

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
```

## 実行方法

サービスCSVだけを作成する場合:

```bat
examples\11_reception_service_migration\run_service.bat C:\data\sougou_uketsuke_icz_2024.csv C:\data\CHIBAN.csv
```

引数を省略する場合は、次のファイルを配置します。

```text
examples\11_reception_service_migration\input\sougou_uketsuke_icz_2024.csv
examples\11_reception_service_migration\input\CHIBAN.csv
```

受付・サービスの旧サンプルをまとめて動かす場合:

入力ファイルを引数で指定します。

```bat
examples\11_reception_service_migration\run_migration.bat C:\data\INPUT.csv C:\data\CHIBAN.csv
```

引数を省略する場合は、以下に配置してください。

```text
examples\11_reception_service_migration\input\INPUT.csv
examples\11_reception_service_migration\input\CHIBAN.csv
```

## 出力

```text
output\受付.csv
output\サービス.csv
reports\reception\
reports\service\
```

## 現在の前提

- 正式な`service.yml`では`ACCOUNT_R.MCODE__C`を`MCODE__C`へ出力します。
- `LOTNUMBER__R.CHIBANNO__C`は墓地フラグ時に`ICZ_B_CHIBAN_NO`、無量寿堂フラグ時に`ICZ_M_CHIBAN_NO`を出力します。
- 読経・無量寿堂・墓地フラグのうち複数が`1`の対象行はmapping errorとして`errors.csv`へ出力し、`service.csv`から除外します。
- `CHIBAN.csv` は `ICZ_M_CHIBAN_NO = CHIBANNO__C` で参照し、`RECORDTYPE.NAME` から第一・第二無量寿堂フラグを設定します。
- CHIBANに一致しない場合、両方の無量寿堂フラグを`FALSE`にします。
- 金額3項目の空欄は0として合計し、5000以上なら`一座教懇志`、それ未満なら`一般懇志`を設定します。
- 元CSVは変更せず、ヘッダーを大文字化した作業用CSVを`work`へ作成します。
