"""
=========================================
Sire Analyzer Ver2.2
bias.py
-----------------------------------------
コースバイアス分析
=========================================
"""

import pandas as pd
import config


# ==========================================
# 枠順抽出
# ==========================================

def filter_frame(
    df,
    frame_no
):
    """
    枠番抽出
    """

    if frame_no is None:

        return df.iloc[0:0]

    return df[
        df[config.COL_FRAME] == frame_no
    ]


# ==========================================
# 馬番抽出
# ==========================================

def filter_horse_no(
    df,
    horse_no
):
    """
    馬番抽出
    """

    if horse_no is None:

        return df.iloc[0:0]

    return df[
        df[config.COL_HORSE_NO] == horse_no
    ]

# ==========================================
# 枠順統計
# ==========================================

def calc_frame_statistics(
    race_df,
    frame
):

    df = race_df[
        race_df[config.COL_FRAME] == frame
    ]

    sample = len(df)

    if sample == 0:
        return None

    win_rate = (
        (df[config.COL_FINISH] == 1).mean() * 100
    )

    place_rate = (
        (df[config.COL_FINISH] <= 2).mean() * 100
    )

    show_rate = (
        (df[config.COL_FINISH] <= 3).mean() * 100
    )

    return {

        "sample": sample,

        "win_rate": round(win_rate, 1),

        "place_rate": round(place_rate, 1),

        "show_rate": round(show_rate, 1)

    }


# ==========================================
# 馬番統計
# ==========================================

def calc_horse_statistics(
    race_df,
    horse_no
):

    df = race_df[
        race_df[config.COL_HORSE_NO] == horse_no
    ]

    sample = len(df)

    if sample == 0:
        return None

    win_rate = (
        (df[config.COL_FINISH] == 1).mean() * 100
    )

    place_rate = (
        (df[config.COL_FINISH] <= 2).mean() * 100
    )

    show_rate = (
        (df[config.COL_FINISH] <= 3).mean() * 100
    )

    return {

        "sample": sample,

        "win_rate": round(win_rate, 1),

        "place_rate": round(place_rate, 1),

        "show_rate": round(show_rate, 1)

    }

def analyze_frame_bias(base_df, target_frame):
    """
    枠順バイアスを分析する関数

    Parameters
    ----------
    base_df : pd.DataFrame
        対象コースで絞り込まれた過去データ
    target_frame : int
        今回評価したい枠番

    Returns
    -------
    dict
        枠順バイアス評価結果
    """

    empty_result = {
        "grade": "-",
        "score": 0,
        "rank": None,
        "target": target_frame,
        "total": 0,
        "sample": 0,
        "diff": 0.0,
        "出走数": 0,
        "勝利数": 0,
        "勝率": 0.0,
        "複勝数": 0,
        "複勝率": 0.0,
        "comment": "枠順バイアスを判定できるデータが不足しています。",
        "bias_df": pd.DataFrame(),
    }

    if base_df is None:
        return empty_result

    if len(base_df) == 0:
        return empty_result

    required_cols = ["枠番", "確定着順"]

    for col in required_cols:
        if col not in base_df.columns:
            empty_result["comment"] = f"枠順バイアス分析に必要な列「{col}」がありません。"
            return empty_result

    df = base_df.copy()

    df["枠番"] = pd.to_numeric(df["枠番"], errors="coerce")
    df["確定着順"] = pd.to_numeric(df["確定着順"], errors="coerce")

    df = df.dropna(subset=["枠番", "確定着順"])

    if len(df) == 0:
        return empty_result

    df["枠番"] = df["枠番"].astype(int)

    grouped = df.groupby("枠番")

    bias_df = grouped.agg(
        出走数=("確定着順", "count"),
        勝利数=("確定着順", lambda x: (x == 1).sum()),
        複勝数=("確定着順", lambda x: (x <= 3).sum()),
    ).reset_index()

    if len(bias_df) == 0:
        return empty_result

    bias_df["勝率"] = bias_df["勝利数"] / bias_df["出走数"] * 100
    bias_df["複勝率"] = bias_df["複勝数"] / bias_df["出走数"] * 100

    # 全体平均勝率との差
    overall_win_rate = df["確定着順"].eq(1).mean() * 100
    bias_df["diff"] = bias_df["勝率"] - overall_win_rate

    # 勝率を主、複勝率を補助にしたバイアススコア
    bias_df["bias_score"] = (
        bias_df["勝率"] * 0.7
        + bias_df["複勝率"] * 0.3
    )

    bias_df = bias_df.sort_values(
        by=["bias_score", "勝率", "複勝率", "出走数"],
        ascending=[False, False, False, False]
    ).reset_index(drop=True)

    bias_df["rank"] = bias_df.index + 1

    try:
        target_frame = int(target_frame)
    except Exception:
        empty_result["comment"] = "対象枠番が数値ではありません。"
        return empty_result

    target_row = bias_df[bias_df["枠番"] == target_frame]

    if len(target_row) == 0:
        empty_result["comment"] = f"{target_frame}枠の過去データがありません。"
        empty_result["bias_df"] = bias_df
        return empty_result

    row = target_row.iloc[0]

    rank = int(row["rank"])
    total_frames = len(bias_df)
    diff = float(row["diff"])

    if rank == 1 and diff > 0:
        grade = "◎"
        score = 100
        comment = f"{target_frame}枠はこの条件で最も有利な枠です。"
    elif rank <= max(2, total_frames * 0.25) and diff > 0:
        grade = "○"
        score = 80
        comment = f"{target_frame}枠はこの条件で有利な枠です。"
    elif diff >= -1.0:
        grade = "△"
        score = 50
        comment = f"{target_frame}枠はこの条件で大きな有利不利はありません。"
    else:
        grade = "×"
        score = 20
        comment = f"{target_frame}枠はこの条件ではやや不利な傾向です。"

    return {
        "grade": grade,
        "score": score,
        "rank": rank,
        "target": target_frame,
        "total": int(row["出走数"]),
        "sample": int(row["出走数"]),
        "diff": round(diff, 1),
        "出走数": int(row["出走数"]),
        "勝利数": int(row["勝利数"]),
        "勝率": round(float(row["勝率"]), 1),
        "複勝数": int(row["複勝数"]),
        "複勝率": round(float(row["複勝率"]), 1),
        "comment": comment,
        "bias_df": bias_df,
    }
# =====================================================
# ラッキー馬番分析
# コースID × 馬番で判定
# =====================================================

def analyze_lucky_number(lucky_df, course_id, horse_number):
    """
    ラッキー馬番を分析する関数

    Parameters
    ----------
    lucky_df : pd.DataFrame
        芝ラッキー馬番 or ダートラッキー馬番のCSV
    course_id : str
        例: 中山芝1600, 東京ダ1600
    horse_number : int
        今回評価したい馬番

    Returns
    -------
    dict
        ラッキー馬番評価結果
    """

    empty_result = {
        "grade": "-",
        "score": 0,
        "target": horse_number,
        "is_lucky": False,
        "出走数": 0,
        "勝利数": 0,
        "勝率": "-",
        "平均勝率": "-",
        "p値": None,
        "comment": "ラッキー馬番データがありません。",
    }

    if lucky_df is None:
        return empty_result

    if len(lucky_df) == 0:
        return empty_result

    required_cols = ["コースID", "馬番", "出走数", "勝利数", "勝率", "平均勝率", "p値"]

    for col in required_cols:
        if col not in lucky_df.columns:
            empty_result["comment"] = f"ラッキー馬番分析に必要な列「{col}」がありません。"
            return empty_result

    df = lucky_df.copy()

    df["馬番"] = pd.to_numeric(df["馬番"], errors="coerce")
    df = df.dropna(subset=["馬番"])

    if len(df) == 0:
        return empty_result

    df["馬番"] = df["馬番"].astype(int)

    try:
        horse_number = int(horse_number)
    except Exception:
        empty_result["comment"] = "対象馬番が数値ではありません。"
        return empty_result

    target_df = df[
        (df["コースID"].astype(str) == str(course_id))
        & (df["馬番"] == horse_number)
    ]

    if len(target_df) == 0:
        empty_result["comment"] = f"{course_id} の {horse_number}番はラッキー馬番には該当しません。"
        return empty_result

    row = target_df.iloc[0]

    p_value = pd.to_numeric(row["p値"], errors="coerce")

    if pd.notna(p_value) and p_value <= 0.01:
        grade = "S"
        score = 100
        comment = f"{course_id} の {horse_number}番は非常に強いラッキー馬番です。"
    elif pd.notna(p_value) and p_value <= 0.05:
        grade = "A"
        score = 85
        comment = f"{course_id} の {horse_number}番は統計的に有利なラッキー馬番です。"
    else:
        grade = "B"
        score = 70
        comment = f"{course_id} の {horse_number}番はラッキー馬番候補です。"

    return {
        "grade": grade,
        "score": score,
        "target": horse_number,
        "is_lucky": True,
        "出走数": int(row["出走数"]),
        "勝利数": int(row["勝利数"]),
        "勝率": row["勝率"],
        "平均勝率": row["平均勝率"],
        "p値": None if pd.isna(p_value) else float(p_value),
        "comment": comment,
    }

# =====================================================
# ラッキー馬番分析
# コースID × 馬番で判定
# =====================================================

def analyze_lucky_number(lucky_df, course_id, horse_number):
    """
    ラッキー馬番を分析する関数

    Parameters
    ----------
    lucky_df : pd.DataFrame
        芝ラッキー馬番 or ダートラッキー馬番のCSV
    course_id : str
        例: 中山芝1600, 東京ダ1600
    horse_number : int
        今回評価したい馬番

    Returns
    -------
    dict
        ラッキー馬番評価結果
    """

    empty_result = {
        "grade": "-",
        "score": 0,
        "target": horse_number,
        "is_lucky": False,
        "出走数": 0,
        "勝利数": 0,
        "勝率": "-",
        "平均勝率": "-",
        "p値": None,
        "comment": "ラッキー馬番データがありません。",
    }

    if lucky_df is None:
        return empty_result

    if len(lucky_df) == 0:
        return empty_result

    required_cols = ["コースID", "馬番", "出走数", "勝利数", "勝率", "平均勝率", "p値"]

    for col in required_cols:
        if col not in lucky_df.columns:
            empty_result["comment"] = f"ラッキー馬番分析に必要な列「{col}」がありません。"
            return empty_result

    df = lucky_df.copy()

    df["馬番"] = pd.to_numeric(df["馬番"], errors="coerce")
    df = df.dropna(subset=["馬番"])

    if len(df) == 0:
        return empty_result

    df["馬番"] = df["馬番"].astype(int)

    try:
        horse_number = int(horse_number)
    except Exception:
        empty_result["comment"] = "対象馬番が数値ではありません。"
        return empty_result

    target_df = df[
        (df["コースID"].astype(str) == str(course_id))
        & (df["馬番"] == horse_number)
    ]

    if len(target_df) == 0:
        empty_result["comment"] = f"{course_id} の {horse_number}番はラッキー馬番には該当しません。"
        return empty_result

    row = target_df.iloc[0]

    p_value = pd.to_numeric(row["p値"], errors="coerce")

    if pd.notna(p_value) and p_value <= 0.01:
        grade = "S"
        score = 100
        comment = f"{course_id} の {horse_number}番は非常に強いラッキー馬番です。"
    elif pd.notna(p_value) and p_value <= 0.05:
        grade = "A"
        score = 85
        comment = f"{course_id} の {horse_number}番は統計的に有利なラッキー馬番です。"
    else:
        grade = "B"
        score = 70
        comment = f"{course_id} の {horse_number}番はラッキー馬番候補です。"

    return {
        "grade": grade,
        "score": score,
        "target": horse_number,
        "is_lucky": True,
        "出走数": int(row["出走数"]),
        "勝利数": int(row["勝利数"]),
        "勝率": row["勝率"],
        "平均勝率": row["平均勝率"],
        "p値": None if pd.isna(p_value) else float(p_value),
        "comment": comment,
    }