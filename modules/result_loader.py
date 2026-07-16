"""Load TARGET Odds/Results A data (headerless, one race per row)."""
from __future__ import annotations
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
import pandas as pd
import config


def build_result_columns() -> list[str]:
    cols = ["年","月","日","回次","場所","日次","レース番号","レース名","クラスコード","芝・ダ","コースコード","距離","馬場状態","頭数","レースID"]
    for n in range(1, 19):
        cols += [f"{n}番馬着順", f"{n}番馬異常コード", f"{n}番馬人気", f"{n}番馬単勝オッズ"]
    for n in range(1, 4): cols += [f"単勝馬番{n}", f"単勝配当{n}"]
    for n in range(1, 6): cols += [f"複勝馬番{n}", f"複勝配当{n}"]
    for bet, count in [("枠連",3),("馬連",3),("ワイド",7)]:
        for n in range(1, count+1): cols += [f"{bet}目小{n}", f"{bet}目大{n}", f"{bet}配当{n}", f"{bet}人気{n}"]
    for n in range(1, 7): cols += [f"馬単目先{n}", f"馬単目後{n}", f"馬単配当{n}", f"馬単人気{n}"]
    for n in range(1, 4): cols += [f"３連複目小{n}", f"３連複目中{n}", f"３連複目大{n}", f"３連複配当{n}", f"３連複人気{n}"]
    for n in range(1, 7): cols += [f"３連単目1着{n}", f"３連単目2着{n}", f"３連単目3着{n}", f"３連単配当{n}", f"３連単人気{n}"]
    return cols

RESULT_COLUMNS = build_result_columns()


def load_target_result_csv(source) -> pd.DataFrame:
    last_error = None
    raw = source.read() if hasattr(source, "read") else Path(source).read_bytes()
    for enc in getattr(config, "RESULT_ENCODING_CANDIDATES", ["cp932", "utf-8-sig"]):
        try:
            df = pd.read_csv(BytesIO(raw), header=None, encoding=enc, dtype=str)
            if df.shape[1] != len(RESULT_COLUMNS):
                raise ValueError(f"列数不一致: 想定{len(RESULT_COLUMNS)}列、実際{df.shape[1]}列")
            df.columns = RESULT_COLUMNS
            return df
        except Exception as exc:
            last_error = exc
    raise ValueError(f"TARGET結果CSVを読み込めません: {last_error}")
