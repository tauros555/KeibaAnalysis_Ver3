"""
=========================================
Sire Analyzer Ver2
filter.py
-----------------------------------------
検索条件によるデータ抽出
=========================================
"""

import pandas as pd
import config


def filter_race(
    df: pd.DataFrame,
    place=None,
    distance=None,
    sex=None
) -> pd.DataFrame:
    """
    レース条件で抽出
    """

    result = df.copy()

    if place not in [None, "", "すべて"]:
        result = result[result[config.COL_PLACE] == place]

    if distance not in [None, "", "すべて"]:
        result = result[result[config.COL_DISTANCE] == distance]

    if sex not in [None, "", "すべて"]:
        result = result[result[config.COL_SEX] == sex]

    return result


def filter_sire(
    df: pd.DataFrame,
    sire_name: str
) -> pd.DataFrame:
    """
    種牡馬抽出
    """

    if sire_name == "":
        return pd.DataFrame(columns=df.columns)

    return df[
        df[config.COL_SIRE].astype(str).str.strip() == sire_name.strip()
    ]


def normalize_cushion_label(value):
    """
    クッション値区分の表記ゆれを統一する

    対応例
    ----------
    8.0～8.5 → 8-8.5
    8.0〜8.5 → 8-8.5
    8～8.5   → 8-8.5
    10.6～11.0 → 10.6-11
    11.6以上 → 11.6以上
    """

    if value is None:
        return ""

    value = str(value).strip()

    value = value.replace("　", "")
    value = value.replace(" ", "")
    value = value.replace("〜", "～")
    value = value.replace("～", "-")
    value = value.replace("以上", "以上")
    value = value.replace("未満", "未満")

    # 表記ゆれ補正
    replace_map = {
        "8.0-8.5": "8-8.5",
        "8-8.5": "8-8.5",

        "8.6-9.0": "8.6-9.0",
        "8.6-9": "8.6-9.0",

        "9.1-9.5": "9.1-9.5",

        "9.6-10.0": "9.6-10.0",
        "9.6-10": "9.6-10.0",

        "10.1-10.5": "10.1-10.5",

        "10.6-11.0": "10.6-11",
        "10.6-11": "10.6-11",

        "11.1-11.5": "11.1-11.5",

        "8未満": "8未満",
        "11.6以上": "11.6以上",
    }

    return replace_map.get(value, value)


def cushion_value_to_label(value):
    """
    数値のクッション値を区分に変換する
    """

    try:
        v = float(value)
    except:
        return normalize_cushion_label(value)

    if v < 8.0:
        return "8未満"

    if 8.0 <= v <= 8.5:
        return "8-8.5"

    if 8.6 <= v <= 9.0:
        return "8.6-9.0"

    if 9.1 <= v <= 9.5:
        return "9.1-9.5"

    if 9.6 <= v <= 10.0:
        return "9.6-10.0"

    if 10.1 <= v <= 10.5:
        return "10.1-10.5"

    if 10.6 <= v <= 11.0:
        return "10.6-11"

    if 11.1 <= v <= 11.5:
        return "11.1-11.5"

    if v >= 11.6:
        return "11.6以上"

    return ""


def filter_cushion(df, cushion):
    """
    クッション値区分で抽出する

    CSV側が
    ・クッション値区分
    ・クッション
    ・クッション値
    のどれでも対応する
    """

    if df is None:
        return df

    if cushion in [None, "", "未指定"]:
        return df

    if len(df) == 0:
        return df

    df = df.copy()

    df.columns = [
        str(col).strip()
        for col in df.columns
    ]

    target_label = normalize_cushion_label(
        cushion
    )

    # -----------------------------
    # クッション区分列を探す
    # -----------------------------

    label_cols = [
        "クッション値区分",
        "クッション区分",
        "クッション",
    ]

    for col in label_cols:

        if col in df.columns:

            df["_cushion_label"] = df[col].apply(
                normalize_cushion_label
            )

            return df[
                df["_cushion_label"] == target_label
            ].copy()

    # -----------------------------
    # 数値のクッション値列を探す
    # -----------------------------

    value_cols = [
        "クッション値",
        "芝クッション値",
    ]

    for col in value_cols:

        if col in df.columns:

            df["_cushion_label"] = df[col].apply(
                cushion_value_to_label
            )

            return df[
                df["_cushion_label"] == target_label
            ].copy()

    # -----------------------------
    # 対象列がない場合
    # -----------------------------

    return df.iloc[0:0].copy()


def filter_going(
    df: pd.DataFrame,
    going=None
) -> pd.DataFrame:
    """
    ダート馬場状態
    """

    if going in [None, "", "未判明"]:
        return df

    return df[
        df[config.COL_GOING] == going
    ]