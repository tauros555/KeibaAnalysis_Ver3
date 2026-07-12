"""
=========================================
Sire Analyzer Ver2
statistics.py
-----------------------------------------
統計計算モジュール
=========================================
"""

import math
import config


def calc_statistics(target_df, base_df):
    """
    統計値を計算して辞書で返す
    """

    sample = len(target_df)

    if sample == 0:
        return {
            "sample": 0,
            "win": 0,
            "place": 0,
            "win_rate": 0.0,
            "place_rate": 0.0,
            "rr": 0.0,
            "p_value": 1.0
        }

    win = (target_df[config.COL_FINISH] == 1).sum()

    place = (target_df[config.COL_FINISH] <= 3).sum()

    win_rate = round(win / sample * 100, 1)

    place_rate = round(place / sample * 100, 1)

    rr = calc_rr(target_df, base_df)

    p_value = calc_p_value(target_df, base_df)

    return {

        "sample": sample,

        "win": win,

        "place": place,

        "win_rate": win_rate,

        "place_rate": place_rate,

        "rr": rr,

        "p_value": p_value

    }


def calc_rr(target_df, base_df):

    if len(base_df) == 0:
        return 0.0

    base_rate = (base_df[config.COL_FINISH] == 1).mean()

    if base_rate == 0:
        return 0.0

    target_rate = (target_df[config.COL_FINISH] == 1).mean()

    return round(target_rate / base_rate, 3)


def calc_p_value(target_df, base_df):

    n = len(target_df)

    N = len(base_df)

    if n == 0 or N == 0:
        return 1.0

    p = (base_df[config.COL_FINISH] == 1).mean()

    if p == 0:
        return 1.0

    x = (target_df[config.COL_FINISH] == 1).sum()

    mean = n * p

    sd = math.sqrt(n * p * (1 - p))

    if sd == 0:
        return 1.0

    z = (x - mean) / sd

    return round(math.erfc(abs(z) / math.sqrt(2)), 4)
import pandas as pd


# ==========================================
# 条件抽出
# ==========================================

def filter_by_value(df: pd.DataFrame, column: str, value):

    if column not in df.columns:
        return pd.DataFrame(columns=df.columns)

    return df[df[column] == value]


# ==========================================
# コースID抽出
# ==========================================

def filter_by_course(df: pd.DataFrame, course_id):

    return filter_by_value(
        df,
        config.COL_COURSE_ID,
        course_id
    )


# ==========================================
# 距離区分抽出
# ==========================================

def filter_by_distance_type(df, distance_type):

    return filter_by_value(
        df,
        config.COL_DISTANCE_TYPE,
        distance_type
    )


# ==========================================
# 右左抽出
# ==========================================

def filter_by_right_left(df, right_left):

    return filter_by_value(
        df,
        config.COL_RIGHT_LEFT,
        right_left
    )


# ==========================================
# 坂抽出
# ==========================================

def filter_by_slope(df, slope):

    return filter_by_value(
        df,
        config.COL_SLOPE,
        slope
    )


# ==========================================
# 枠抽出
# ==========================================

def filter_by_frame(df, frame):

    return filter_by_value(
        df,
        config.COL_FRAME,
        frame
    )


# ==========================================
# 馬番抽出
# ==========================================

def filter_by_horse_no(df, horse_no):

    return filter_by_value(
        df,
        config.COL_HORSE_NO,
        horse_no
    )


# ==========================================
# クッション値判定抽出
# ==========================================

def filter_by_cushion(df, cushion):

    return filter_by_value(
        df,
        config.COL_CUSHION_GROUP,
        cushion
    )


# ==========================================
# ダート馬場状態抽出
# ==========================================

def filter_by_going(df, going):

    return filter_by_value(
        df,
        config.COL_GOING,
        going
    )


# ==========================================
# ラッキー馬番抽出
# ==========================================

def filter_lucky_number(df_lucky, course_id):

    if config.COL_COURSE_ID not in df_lucky.columns:
        return pd.DataFrame()

    return df_lucky[
        df_lucky[config.COL_COURSE_ID] == course_id
    ]


# ==========================================
# 辞書化
# ==========================================

def to_dict(stats):

    return {

        "sample": stats["sample"],

        "win": stats["win"],

        "place": stats["place"],

        "win_rate": stats["win_rate"],

        "place_rate": stats["place_rate"],

        "rr": stats["rr"],

        "p_value": stats["p_value"]

    }