Sire Analyzer Ver5
===================

主な変更
- SCORE_MAPを廃止し、勝率差・複勝率差・RR・サンプル数から連続StatScoreを計算
- 父馬全体と父馬×性別を部分プーリング
- 競馬場×距離を「完全一致→同競馬場±200m→全場距離区分」で階層分析
- 左右・坂・距離区分・コーナー回数でサンプル不足を補足
- コーナー回数適性を追加
- 適性効果「+x.xpt（指数）」を追加
- 分析結果を data/prediction_history.csv に自動保存
- TARGETヘッダーなし「オッズ成績データA」を読み込み、レースID＋馬番で照合
- data/validation_history.csv を作成し、判定別・適性別の勝率/複勝率/回収率を表示
- 異常コード0～7に対応（1～3は返還扱いで検証分母から除外）

導入
1. 現在のプロジェクトをバックアップ
2. このZIP内の app.py / config.py / modules / requirements.txt を上書き
3. 既存の data フォルダは削除しない
4. コースマスタ.csvには既存のコースID列とコーナー回数列が必要
5. 調教判定表.csvにはレースID・血統登録番号・馬番・Rが必要
6. python -m streamlit run app.py

注意
- アプリ側ではコースIDを生成しません。
- prediction_history.csv と validation_history.csv は初回実行時に自動作成されます。
- 初期のStatScore閾値は検証データ蓄積後に調整する前提です。
