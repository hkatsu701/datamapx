# Concept

## datamapxの目的

datamapxは、YAML設定に基づいてCSVデータの読み込み、正規化、参照マスタlookup、項目マッピング、条件分岐、計算、バリデーション、エラー出力、集計レポート出力を行うPython CLIツールです。

目的は、データ移行やCSV変換のたびにPythonコードを書き換えず、設定ファイルだけで再現可能な変換処理を実行できるようにすることです。

## 解決する課題

- 移行案件ごとに個別スクリプトが乱立する
- CSV変換の仕様がコード内に埋もれて説明しづらい
- エラー行、除外行、出力件数の根拠が残らない
- lookup未突合や型不正が黙って処理される
- Excel手作業や手順書ベースの変換が再現しづらい

## 想定ユーザー

- データ移行担当者
- 業務システム導入・移行エンジニア
- SFA/CRM/会計ソフト向けCSVを作成する担当者
- Pythonは使えるが、案件ごとに変換コードを書きたくない開発者
- Excel手作業を設定ファイル化したい業務改善担当者

## 代表的な利用シーン

- CSV移行
- SFA/CRMデータ変換
- 会計ソフト投入用CSV変換
- マスタ突合
- Excel手作業の置き換え

## Phase 1の対象範囲

- 単一Input CSV
- 複数Reference CSV
- 単一Output CSV
- YAML設定ファイル
- CLI実行
- 設定検証
- schema-based input validation
- normalize
- mapping
- derived fields
- filters
- input and output validation
- `errors.csv`
- `skipped.csv`
- `summary.json`
- run_id付きlog
- dry-run
- inspect
- validate-config
- profile-input simple version

## Phase 1で対象外にする範囲

- Excel入力
- JSON入力
- DB入力
- 複数Input join
- 複数Output
- Web UI
- pandas/polars backend切替
- HTMLレポート
- plugin
- AIによるYAML生成補助
- streaming処理

## 設計思想

### 設定ファイル駆動

個別業務ロジックをPythonコードに直接書かず、変換仕様はYAMLで表現します。

### 再現性

同じ入力ファイルと同じ設定ファイルで、同じ出力が得られることを重視します。

### 説明可能性

なぜエラーになったか、何件入力され、何件出力され、何件除外され、何件エラーになったか、どの設定で実行されたかを確認できるようにします。

### 安全性

未定義field、lookup未突合、重複キー、型不正、変換エラーを黙って通しません。Pythonの`eval`は直接使いません。

### 小さく作る

Phase 1ではCSV-to-CSVに集中し、堅牢なMVPを作り切ります。

## Open Questions

- `date`型のPhase 1対応範囲をparse中心に限定するか。
- `profile-input`簡易版で出す統計情報の最小セット。
