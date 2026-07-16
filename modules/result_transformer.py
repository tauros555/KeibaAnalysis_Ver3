"""Transform TARGET race-wide result data to one row per horse."""
from __future__ import annotations
import pandas as pd

ABNORMAL_CODE_MAP = {0:"正常",1:"出走取消",2:"発走除外",3:"競走除外",4:"競走中止",5:"失格",6:"落馬再騎乗",7:"降着"}
REFUND_CODES = {1,2,3}


def _num(value):
    return pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]


def transform_results(race_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, race in race_df.iterrows():
        win_payout = {}
        place_payout = {}
        for i in range(1,4):
            no = _num(race.get(f"単勝馬番{i}")); pay = _num(race.get(f"単勝配当{i}"))
            if pd.notna(no): win_payout[int(no)] = float(pay) if pd.notna(pay) else 0.0
        for i in range(1,6):
            no = _num(race.get(f"複勝馬番{i}")); pay = _num(race.get(f"複勝配当{i}"))
            if pd.notna(no): place_payout[int(no)] = float(pay) if pd.notna(pay) else 0.0
        year, month, day = [_num(race.get(x)) for x in ["年","月","日"]]
        date = ""
        if all(pd.notna(x) for x in [year,month,day]): date = f"{int(year):04d}{int(month):02d}{int(day):02d}"
        for horse_no in range(1,19):
            finish = _num(race.get(f"{horse_no}番馬着順"))
            abnormal = _num(race.get(f"{horse_no}番馬異常コード"))
            popularity = _num(race.get(f"{horse_no}番馬人気"))
            odds = _num(race.get(f"{horse_no}番馬単勝オッズ"))
            # Unused slots beyond field size are blank.
            field_size = _num(race.get("頭数"))
            field_size = int(field_size) if pd.notna(field_size) else 0
            if all(pd.isna(x) for x in [finish, abnormal, popularity, odds]) and horse_no > field_size:
                continue
            code = int(abnormal) if pd.notna(abnormal) else 0
            valid_bet = code not in REFUND_CODES
            finish_int = int(finish) if pd.notna(finish) and finish > 0 else None
            rows.append({
                "年月日": date, "場所": race.get("場所", ""), "R": _num(race.get("レース番号")),
                "レースID": str(race.get("レースID", "")).strip(), "馬番": horse_no,
                "確定着順": finish_int, "異常コード": code, "異常内容": ABNORMAL_CODE_MAP.get(code, "不明"),
                "人気": popularity, "単勝オッズ": odds, "単勝払戻": win_payout.get(horse_no, 0.0),
                "複勝払戻": place_payout.get(horse_no, 0.0), "検証対象": valid_bet,
                "勝利": bool(valid_bet and finish_int == 1), "連対": bool(valid_bet and finish_int is not None and finish_int <= 2),
                "複勝": bool(valid_bet and finish_int is not None and finish_int <= 3),
            })
    return pd.DataFrame(rows)
