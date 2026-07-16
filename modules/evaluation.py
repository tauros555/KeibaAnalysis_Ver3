"""Evaluation rules for Sire Analyzer Ver5."""
from __future__ import annotations
from typing import Any
import config


def judge(stats: dict[str, Any] | None) -> str:
    if not stats:
        return "-"
    sample = int(stats.get("sample", 0) or 0)
    if sample < int(getattr(config, "STAT_MIN_SAMPLE", 5)):
        return "-"
    score = float(stats.get("stat_score", 0.0) or 0.0)
    confidence = float(stats.get("confidence_score", 0.0) or 0.0)
    win_diff = float(stats.get("win_rate_diff", 0.0) or 0.0)
    place_diff = float(stats.get("place_rate_diff", 0.0) or 0.0)
    if score >= float(getattr(config, "STAT_GRADE_EXCELLENT", 2.5)) and confidence >= 0.55:
        return config.GRADE_MARK["excellent"]
    if score >= float(getattr(config, "STAT_GRADE_GOOD", 0.8)) and (win_diff > 0 or place_diff > 0):
        return config.GRADE_MARK["good"]
    if score <= float(getattr(config, "STAT_GRADE_POOR", -1.2)) and confidence >= 0.45:
        return config.GRADE_MARK["poor"]
    return config.GRADE_MARK["normal"]


def judge_text(mark: str) -> str:
    return {
        "◎": "父馬基準より明確に有利",
        "○": "父馬基準より有利",
        "△": "中立・判断保留",
        "×": "父馬基準より不利",
        "-": "データ不足",
    }.get(mark, "")


def grade_score(grade):
    # Backward compatibility only. Ver5 TOTAL uses stat_score directly.
    return {"◎": 2.5, "○": 1.0, "△": 0.0, "×": -1.5, "-": 0.0, None: 0.0}.get(grade, 0.0)


def judge_bias(rank, total, sample, diff):
    if rank is None or int(sample or 0) < int(getattr(config, "BIAS_MIN_SAMPLE", 20)):
        return "-"
    diff = float(diff or 0.0)
    if diff >= float(getattr(config, "BIAS_GOOD_DIFF", 3.0)):
        return "◎" if int(sample or 0) >= int(getattr(config, "BIAS_SAFE_SAMPLE", 20)) else "○"
    if diff <= float(getattr(config, "BIAS_BAD_DIFF", -3.0)):
        return "×"
    return "△"
