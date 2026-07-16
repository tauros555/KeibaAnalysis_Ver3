"""Statistical engine for Sire Analyzer Ver5.

The public functions from Ver2 are retained for backward compatibility, while
new functions return continuous effect scores, partial pooling by sex, and
explainable statistics.
"""
from __future__ import annotations

import math
from typing import Any, Callable

import pandas as pd

import config


def _safe_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _rate_summary(df: pd.DataFrame) -> dict[str, float | int]:
    if df is None or len(df) == 0 or config.COL_FINISH not in df.columns:
        return {"sample": 0, "win": 0, "place": 0, "win_rate": 0.0, "place_rate": 0.0}
    finish = _safe_numeric(df[config.COL_FINISH])
    valid = finish.notna()
    finish = finish[valid]
    n = int(valid.sum())
    if n == 0:
        return {"sample": 0, "win": 0, "place": 0, "win_rate": 0.0, "place_rate": 0.0}
    win = int((finish == 1).sum())
    place = int((finish <= 3).sum())
    return {
        "sample": n,
        "win": win,
        "place": place,
        "win_rate": win / n * 100.0,
        "place_rate": place / n * 100.0,
    }


def _two_sided_normal_p(x: int, n: int, p0: float) -> float:
    if n <= 0 or p0 <= 0 or p0 >= 1:
        return 1.0
    sd = math.sqrt(n * p0 * (1.0 - p0))
    if sd == 0:
        return 1.0
    z = (x - n * p0) / sd
    return float(math.erfc(abs(z) / math.sqrt(2.0)))


def _confidence(sample: int, win_diff: float, place_diff: float, p_value: float) -> float:
    sample_target = float(getattr(config, "STAT_CONFIDENCE_SAMPLE", 30))
    sample_score = min(max(sample, 0) / max(sample_target, 1.0), 1.0)
    effect_score = min((abs(win_diff) / 5.0 + abs(place_diff) / 10.0) / 2.0, 1.0)
    if p_value <= 0.05:
        sig_score = 1.0
    elif p_value <= 0.10:
        sig_score = 0.7
    elif p_value <= 0.20:
        sig_score = 0.4
    else:
        sig_score = 0.15
    value = sample_score * 0.50 + effect_score * 0.35 + sig_score * 0.15
    return round(min(max(value, 0.0), 1.0), 4)


def _raw_stat_score(win_diff: float, place_diff: float, rr: float) -> float:
    # Effect is measured against the sire's own baseline, not absolute ability.
    rr_component = math.log(max(rr, 0.05)) * 2.0
    return win_diff * 0.55 + place_diff * 0.30 + rr_component * 0.15


def calc_effect_statistics(target_df: pd.DataFrame, sire_base_df: pd.DataFrame) -> dict[str, Any]:
    """Compare a sire's condition sample with that sire's own baseline."""
    target = _rate_summary(target_df)
    base = _rate_summary(sire_base_df)
    sample = int(target["sample"])
    if sample == 0 or int(base["sample"]) == 0:
        return {
            **target,
            "base_sample": int(base["sample"]),
            "base_win_rate": float(base["win_rate"]),
            "base_place_rate": float(base["place_rate"]),
            "win_rate_diff": 0.0,
            "place_rate_diff": 0.0,
            "rr": 1.0,
            "place_rr": 1.0,
            "p_value": 1.0,
            "confidence_score": 0.0,
            "stat_score": 0.0,
            "aptitude_index": 100,
        }
    base_win = float(base["win_rate"])
    base_place = float(base["place_rate"])
    win_rate = float(target["win_rate"])
    place_rate = float(target["place_rate"])
    rr = win_rate / base_win if base_win > 0 else 1.0
    place_rr = place_rate / base_place if base_place > 0 else 1.0
    win_diff = win_rate - base_win
    place_diff = place_rate - base_place
    p_value = _two_sided_normal_p(int(target["win"]), sample, base_win / 100.0)
    confidence = _confidence(sample, win_diff, place_diff, p_value)
    score = _raw_stat_score(win_diff, place_diff, rr) * confidence
    # Combined relative index, stable even when win rate is very small.
    aptitude_index = 100.0 * (0.55 * rr + 0.45 * place_rr)
    return {
        **target,
        "base_sample": int(base["sample"]),
        "base_win_rate": round(base_win, 3),
        "base_place_rate": round(base_place, 3),
        "win_rate_diff": round(win_diff, 3),
        "place_rate_diff": round(place_diff, 3),
        "rr": round(rr, 4),
        "place_rr": round(place_rr, 4),
        "p_value": round(p_value, 5),
        "confidence_score": confidence,
        "stat_score": round(score, 4),
        "aptitude_index": int(round(aptitude_index)),
    }


def partial_pool_effect(overall_stats: dict[str, Any], sex_stats: dict[str, Any] | None) -> dict[str, Any]:
    """Shrink sex-specific estimates toward the sire-overall estimate."""
    if not sex_stats or int(sex_stats.get("sample", 0)) <= 0:
        result = dict(overall_stats)
        result.update({"sex_sample": 0, "sex_weight": 0.0, "pooling": "父馬全体"})
        return result
    sex_sample = int(sex_stats.get("sample", 0))
    target = float(getattr(config, "SEX_POOLING_SAMPLE", 30))
    w = min(sex_sample / max(target, 1.0), 1.0)
    result = dict(overall_stats)
    for key in [
        "win_rate", "place_rate", "win_rate_diff", "place_rate_diff", "rr",
        "place_rr", "confidence_score", "stat_score", "aptitude_index"
    ]:
        a = float(overall_stats.get(key, 0.0))
        b = float(sex_stats.get(key, a))
        result[key] = round(b * w + a * (1.0 - w), 4)
    result["sample"] = int(round(sex_sample * w + int(overall_stats.get("sample", 0)) * (1.0 - w)))
    result["sex_sample"] = sex_sample
    result["sex_weight"] = round(w, 4)
    result["pooling"] = "性別中心" if w >= 0.67 else "部分プーリング"
    return result


def analyze_condition(
    sire_all_df: pd.DataFrame,
    condition_selector: Callable[[pd.DataFrame], pd.DataFrame],
    sex: str | None = None,
) -> dict[str, Any]:
    overall_condition = condition_selector(sire_all_df)
    overall = calc_effect_statistics(overall_condition, sire_all_df)
    if sex in [None, "", "すべて"] or config.COL_SEX not in sire_all_df.columns:
        overall.update({"sex_sample": 0, "sex_weight": 0.0, "pooling": "父馬全体"})
        return overall
    sex_base = sire_all_df[sire_all_df[config.COL_SEX].astype(str).str.strip() == str(sex).strip()]
    sex_condition = condition_selector(sex_base)
    sex_stats = calc_effect_statistics(sex_condition, sex_base)
    return partial_pool_effect(overall, sex_stats)


# ------------------------------------------------------------------
# Backward-compatible Ver2 API
# ------------------------------------------------------------------
def calc_statistics(target_df, base_df):
    sample = _rate_summary(target_df)
    base = _rate_summary(base_df)
    base_win = float(base["win_rate"])
    rr = float(sample["win_rate"]) / base_win if base_win > 0 else 0.0
    p_value = _two_sided_normal_p(int(sample["win"]), int(sample["sample"]), base_win / 100.0) if base_win > 0 else 1.0
    return {
        "sample": int(sample["sample"]), "win": int(sample["win"]), "place": int(sample["place"]),
        "win_rate": round(float(sample["win_rate"]), 1), "place_rate": round(float(sample["place_rate"]), 1),
        "rr": round(rr, 3), "p_value": round(p_value, 4),
    }


def calc_rr(target_df, base_df):
    return calc_statistics(target_df, base_df)["rr"]


def calc_p_value(target_df, base_df):
    return calc_statistics(target_df, base_df)["p_value"]


def filter_by_value(df: pd.DataFrame, column: str, value):
    if df is None or column not in df.columns:
        return pd.DataFrame(columns=[] if df is None else df.columns)
    return df[df[column] == value]


def filter_by_course(df, course_id): return filter_by_value(df, config.COL_COURSE_ID, course_id)
def filter_by_distance_type(df, value): return filter_by_value(df, config.COL_DISTANCE_TYPE, value)
def filter_by_right_left(df, value): return filter_by_value(df, config.COL_RIGHT_LEFT, value)
def filter_by_slope(df, value): return filter_by_value(df, config.COL_SLOPE, value)
def filter_by_corner_count(df, value): return filter_by_value(df, getattr(config, "COL_CORNER_COUNT", "コーナー回数"), value)
def filter_by_frame(df, value): return filter_by_value(df, config.COL_FRAME, value)
def filter_by_horse_no(df, value): return filter_by_value(df, config.COL_HORSE_NO, value)
def filter_by_cushion(df, value): return filter_by_value(df, config.COL_CUSHION_GROUP, value)
def filter_by_going(df, value): return filter_by_value(df, config.COL_GOING, value)


def to_dict(stats):
    if stats is None:
        return {}
    if isinstance(stats, dict):
        return stats
    try:
        return dict(stats)
    except Exception:
        return {}
