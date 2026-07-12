"""
=========================================
Sire Analyzer Ver2.3
evaluation.py
-----------------------------------------
評価判定モジュール

方針
-----------------------------------------
・サンプル不足は「-」
・統計的に有利なら「◎」「○」
・どちらとも言えない場合は「△」
・統計的に不利と判断できる場合のみ「×」
=========================================
"""

import config


# ==========================================
# 安全変換
# ==========================================

def _safe_float(value, default=0.0):
    """
    float変換できない値を安全に処理する
    """

    try:
        if value is None:
            return default

        return float(value)

    except:
        return default


def _safe_int(value, default=0):
    """
    int変換できない値を安全に処理する
    """

    try:
        if value is None:
            return default

        return int(value)

    except:
        return default


def _get_config(name, default):
    """
    configに定義があれば使い、なければdefaultを使う
    """

    return getattr(
        config,
        name,
        default
    )


# ==========================================
# 父馬評価
# ==========================================

def judge(stats: dict) -> str:
    """
    統計値から父馬評価を返す

    Parameters
    ----------
    stats : dict

    想定キー
    ----------
    sample
    rr
    p_value

    追加で存在すれば利用
    ----------
    win_rr
    place_rr
    fukusho_rr
    win_rate
    place_rate
    base_win_rate
    base_place_rate
    """

    if stats is None:
        return "-"

    # -------------------------
    # 基本値
    # -------------------------

    sample = _safe_int(
        stats.get("sample", 0)
    )

    rr = _safe_float(
        stats.get("rr", 1.0),
        default=1.0
    )

    p = _safe_float(
        stats.get("p_value", 1.0),
        default=1.0
    )

    # -------------------------
    # サンプル不足
    # -------------------------

    min_sample = _get_config(
        "MIN_SAMPLE",
        5
    )

    if sample < min_sample:
        return "-"

    # -------------------------
    # 閾値
    # -------------------------

    rr_excellent = _get_config(
        "RR_EXCELLENT",
        1.5
    )

    rr_good = _get_config(
        "RR_GOOD",
        1.2
    )

    rr_normal = _get_config(
        "RR_NORMAL",
        1.0
    )

    # 不利判定用
    # configに無い場合は 0.80 を使う
    rr_bad = _get_config(
        "RR_BAD",
        0.80
    )

    p_excellent = _get_config(
        "P_EXCELLENT",
        0.05
    )

    p_good = _get_config(
        "P_GOOD",
        0.10
    )

    p_normal = _get_config(
        "P_NORMAL",
        0.20
    )

    # 不利判定用
    # 有利と同じく、ある程度の統計的根拠を求める
    p_bad = _get_config(
        "P_BAD",
        p_normal
    )

    # -------------------------
    # 明確に有利
    # -------------------------

    if rr >= rr_excellent and p <= p_excellent:
        return config.GRADE_MARK["excellent"]

    # -------------------------
    # 有利
    # -------------------------

    if rr >= rr_good and p <= p_good:
        return config.GRADE_MARK["good"]

    # -------------------------
    # 明確に不利
    # -------------------------
    # 重要：
    # 有利でないから即「×」にはしない。
    # rrが十分低く、p値も一定以下のときだけ「×」。
    # -------------------------

    if rr <= rr_bad and p <= p_bad:
        return config.GRADE_MARK["poor"]

    # -------------------------
    # どちらとも言えない
    # -------------------------
    # rrが平均前後、またはp値的に根拠が弱い場合。
    # -------------------------

    return config.GRADE_MARK["normal"]


# ==========================================
# コースバイアス評価
# ==========================================

def judge_bias(
    rank,
    total,
    sample,
    diff
):
    """
    枠順・馬番バイアス評価

    Parameters
    ----------
    rank : int
        順位

    total : int
        全枠数・全馬番数

    sample : int
        サンプル数

    diff : float
        全体平均との差
        正なら有利、負なら不利
    """

    # -------------------------
    # データ不足
    # -------------------------

    if rank is None:
        return "-"

    total = _safe_int(
        total,
        default=0
    )

    sample = _safe_int(
        sample,
        default=0
    )

    diff = _safe_float(
        diff,
        default=0.0
    )

    if total <= 0:
        return "-"

    bias_min_sample = _get_config(
        "BIAS_MIN_SAMPLE",
        5
    )

    if sample < bias_min_sample:
        return "-"

    # -------------------------
    # 閾値
    # -------------------------

    flat_diff = _get_config(
        "BIAS_FLAT_DIFF",
        1.0
    )

    good_diff = _get_config(
        "BIAS_GOOD_DIFF",
        3.0
    )

    bad_diff = _get_config(
        "BIAS_BAD_DIFF",
        -3.0
    )

    low_sample = _get_config(
        "BIAS_LOW_SAMPLE",
        10
    )

    safe_sample = _get_config(
        "BIAS_SAFE_SAMPLE",
        20
    )

    # -------------------------
    # 差がほぼない場合
    # -------------------------
    # 順位が良くても、平均との差が小さいなら中立。
    # -------------------------

    if abs(diff) < flat_diff:
        return "△"

    # -------------------------
    # 明確に不利
    # -------------------------

    if diff <= bad_diff:
        return "×"

    # -------------------------
    # 明確に有利
    # -------------------------

    if diff >= good_diff:

        # サンプルが少ない場合は過大評価しない
        if sample < low_sample:
            return "○"

        return "◎"

    # -------------------------
    # やや有利・やや不利
    # -------------------------

    if diff > 0:

        # サンプルが少ない場合は中立
        if sample < low_sample:
            return "△"

        # 十分なサンプルがあれば有利
        if sample >= safe_sample:
            return "○"

        return "○"

    if diff < 0:

        # サンプルが少ない場合は中立
        if sample < safe_sample:
            return "△"

        return "×"

    # -------------------------
    # 念のため
    # -------------------------

    return "△"


# ==========================================
# 評価コメント
# ==========================================

def judge_text(mark: str) -> str:
    """
    評価コメント
    """

    table = {

        "◎": "統計的にかなり有利",

        "○": "統計的に有利",

        "△": "中立・判断保留",

        "×": "統計的に不利",

        "-": "データ不足"

    }

    return table.get(
        mark,
        ""
    )


# ==========================================
# 評価 → 点数変換
# ==========================================

def grade_score(
    grade
):
    """
    評価記号を点数へ変換

    注意
    ----------
    app.py側でSCORE_MAPを使ってTOTALを再計算する場合、
    こちらはanalyzer.py内部用の補助点として使う。

    方針
    ----------
    ◎・○：加点
    △・-：0点
    ×：減点
    """

    table = {

        "◎": 4,

        "○": 3,

        "△": 0,

        "×": -2,

        "-": 0,

        None: 0

    }

    return table.get(
        grade,
        0
    )