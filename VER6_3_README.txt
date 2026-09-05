統合版 Ver6.3

今回の原因:
ユーザー出力CSVで、
当日クッション値=9.5 に対して
クッション判定範囲=「クッション:9.5」
となっていました。

新方式の正常値は
「クッション9.5±0.3」
のようになります。

これは新app.pyに対して旧modules/analyzer.pyが動いていたことを示します。

Ver6.3の対策:
- app.pyで analyze_all() 実行直後にクッション評価を必ず強制再計算
- analyzer.pyの版に依存せず、新しい数値方式で上書き
- ±0.3 → ±0.5 → ±0.8
- 結果に「クッション方式」を表示
- 正常なら「実数±幅方式」
- クッション判定範囲は「クッション9.5±0.3」等になる

削除:
- Ver6検証機能
- TARGET結果CSVアップロード
- 予想履歴自動保存
- validation.py
- result_loader.py
- result_transformer.py
- prediction_history.py

旧判定評価 / StatScore / 推奨度も引き続き非表示。
