"""Ver6 turf cushion aptitude helpers.

Uses the live cushion value directly. Sire aptitude uses adaptive widths
±0.3 -> ±0.5 -> ±0.8. Own-horse history becomes formal from 3 samples.
"""
from __future__ import annotations
import pandas as pd
import config
from modules import statistics, evaluation


def _num(v):
    try:
        return float(v)
    except Exception:
        return None


def analyze_sire_cushion(race_df, sire_name, cushion, sex=None):
    value = _num(cushion)
    if value is None or race_df is None or len(race_df) == 0:
        return {
            "stats": {"sample": 0, "selected_scope": "数値クッション値なし"},
            "grade": "-", "grade_text": "データ不足", "stat_score": 0.0,
            "width": None, "value": value, "confidence_label": "評価不可", "method": "実数±幅方式",
        }
    if config.COL_SIRE not in race_df.columns or config.COL_CUSHION not in race_df.columns:
        return {
            "stats": {"sample": 0, "selected_scope": "クッション値列なし"},
            "grade": "-", "grade_text": "データ不足", "stat_score": 0.0,
            "width": None, "value": value, "confidence_label": "評価不可", "method": "実数±幅方式",
        }
    sire = race_df[race_df[config.COL_SIRE].astype(str).str.strip() == str(sire_name).strip()].copy()
    if sire.empty:
        return {
            "stats": {"sample": 0, "selected_scope": "父馬データなし"},
            "grade": "-", "grade_text": "データ不足", "stat_score": 0.0,
            "width": None, "value": value, "confidence_label": "評価不可", "method": "実数±幅方式",
        }
    sire[config.COL_CUSHION] = pd.to_numeric(sire[config.COL_CUSHION], errors="coerce")
    sire = sire[sire[config.COL_CUSHION].notna()].copy()
    if sire.empty:
        return {
            "stats": {"sample": 0, "selected_scope": "過去クッション実数なし"},
            "grade": "-", "grade_text": "データ不足", "stat_score": 0.0,
            "width": None, "value": value, "confidence_label": "評価不可", "method": "実数±幅方式",
        }
    widths = [0.3, 0.5, 0.8]
    chosen = 0.8
    for width in widths:
        n = int(sire[config.COL_CUSHION].between(value-width, value+width, inclusive="both").sum())
        chosen = width
        if n >= int(getattr(config, "STAT_MIN_SAMPLE", 5)):
            break
    def selector(df):
        vals = pd.to_numeric(df[config.COL_CUSHION], errors="coerce")
        return df[vals.between(value-chosen, value+chosen, inclusive="both")]
    stats = statistics.analyze_condition(sire, selector, sex=sex)
    stats["selected_scope"] = f"クッション{value:.1f}±{chosen:.1f}"
    stats["cushion_width"] = chosen
    stats["cushion_value"] = value
    grade = evaluation.judge(stats)
    return {
        "stats": stats,
        "grade": grade,
        "grade_text": evaluation.judge_text(grade),
        "stat_score": float(stats.get("stat_score", 0.0)),
        "width": chosen,
        "value": value,
        "confidence_label": "通常" if chosen == 0.3 else ("補完" if chosen == 0.5 else "低信頼度参考"),
        "method": "実数±幅方式",
    }


def analyze_horse_cushion(race_df, horse_name, cushion):
    value = _num(cushion)
    if value is None or race_df is None or len(race_df) == 0 or "馬名" not in race_df.columns:
        return {"judgement":"評価なし","sample":0,"width":None,"score":0.0,"formal":False}
    h = race_df[race_df["馬名"].astype(str).str.strip() == str(horse_name).strip()].copy()
    if h.empty or config.COL_CUSHION not in h.columns:
        return {"judgement":"評価なし","sample":0,"width":None,"score":0.0,"formal":False}
    h[config.COL_CUSHION] = pd.to_numeric(h[config.COL_CUSHION], errors="coerce")
    h[config.COL_FINISH] = pd.to_numeric(h[config.COL_FINISH], errors="coerce")
    chosen = 0.8
    target = h.iloc[0:0]
    for width in [0.3,0.5,0.8]:
        target = h[h[config.COL_CUSHION].between(value-width,value+width,inclusive="both")].copy()
        chosen = width
        if len(target) >= 3:
            break
    n = len(target)
    if n == 0:
        return {"judgement":"評価なし","sample":0,"width":None,"score":0.0,"formal":False}
    formal = n >= 3
    if not formal:
        return {"judgement":"参考","sample":n,"width":chosen,"score":0.0,"formal":False}
    base_finish = h[config.COL_FINISH].dropna()
    tgt_finish = target[config.COL_FINISH].dropna()
    if len(base_finish) == 0 or len(tgt_finish) == 0:
        return {"judgement":"中立","sample":n,"width":chosen,"score":0.0,"formal":True}
    base_place = float((base_finish <= 3).mean()*100)
    tgt_place = float((tgt_finish <= 3).mean()*100)
    base_avg = float(base_finish.mean())
    tgt_avg = float(tgt_finish.mean())
    place_diff = tgt_place-base_place
    finish_gain = base_avg-tgt_avg
    raw = place_diff/8.0 + finish_gain/2.0
    if raw >= 0.75:
        judgement, score = "良好", 1.0
    elif raw <= -0.75:
        judgement, score = "不振", -0.7
    else:
        judgement, score = "中立", 0.0
    conf = 1.0 if chosen == 0.3 else (0.75 if chosen == 0.5 else 0.35)
    return {
        "judgement":judgement,"sample":n,"width":chosen,"score":score*conf,"formal":True,
        "place_rate":round(tgt_place,2),"place_diff":round(place_diff,2),"avg_finish":round(tgt_avg,2)
    }
