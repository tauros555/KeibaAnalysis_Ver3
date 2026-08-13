# -*- coding: utf-8 -*-
from functools import lru_cache
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
JOCKEY_RULE_PATH = DATA_DIR / "騎手条件マスタ.csv"
SIRE_JOCKEY_RULE_PATH = DATA_DIR / "父馬騎手相性マスタ.csv"


def _norm_text(v):
    if v is None:
        return ""
    s = str(v).replace("　", "").replace(" ", "").strip()
    if s in {"nan", "None", "NaN"}:
        return ""
    return s


def _norm_surface(v):
    s = _norm_text(v)
    if s in {"ダ", "ダート", "D", "d", "dirt", "Dirt"}:
        return "ダート"
    if s in {"芝", "T", "t", "turf", "Turf"}:
        return "芝"
    return s


def distance_category(distance):
    try:
        d = int(float(distance))
    except Exception:
        return ""
    if d <= 1400:
        return "短距離"
    if d <= 1600:
        return "マイル"
    if d <= 2000:
        return "中距離"
    return "長距離"


@lru_cache(maxsize=1)
def load_jockey_rules():
    if not JOCKEY_RULE_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(JOCKEY_RULE_PATH, encoding="utf-8-sig")
    for c in ["場所", "表面", "騎手", "レベル", "条件値", "判定"]:
        if c in df.columns:
            df[c] = df[c].map(_norm_text)
    return df


@lru_cache(maxsize=1)
def load_sire_jockey_rules():
    if not SIRE_JOCKEY_RULE_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(SIRE_JOCKEY_RULE_PATH, encoding="utf-8-sig")
    for c in ["表面", "父馬名", "騎手", "判定"]:
        if c in df.columns:
            df[c] = df[c].map(_norm_text)
    return df


def evaluate_jockey_condition(place, surface, distance, jockey):
    """参考表示専用。最終評価・最終スコアには使用しない。"""
    place = _norm_text(place)
    surface = _norm_surface(surface)
    jockey = _norm_text(jockey)
    if not place or not surface or not jockey or jockey == "-":
        return "-"

    rules = load_jockey_rules()
    if rules.empty:
        return "-"

    try:
        dist = str(int(float(distance)))
    except Exception:
        dist = ""

    # 1) 競馬場×表面×正確な距離を最優先
    if dist:
        m = rules[
            rules["場所"].eq(place)
            & rules["表面"].eq(surface)
            & rules["騎手"].eq(jockey)
            & rules["レベル"].eq("距離")
            & rules["条件値"].eq(dist)
        ]
        if not m.empty:
            mark = _norm_text(m.iloc[0].get("判定", "-"))
            return mark if mark in {"◎", "×"} else "-"

    # 2) 距離別が母数不足/非該当なら距離区分へフォールバック
    cat = distance_category(distance)
    if cat:
        m = rules[
            rules["場所"].eq(place)
            & rules["表面"].eq(surface)
            & rules["騎手"].eq(jockey)
            & rules["レベル"].eq("距離区分")
            & rules["条件値"].eq(cat)
        ]
        if not m.empty:
            mark = _norm_text(m.iloc[0].get("判定", "-"))
            return mark if mark in {"◎", "×"} else "-"

    return "-"


def evaluate_sire_jockey(surface, sire, jockey):
    """芝/ダ別の父馬×騎手相性。参考表示専用で加減点しない。"""
    surface = _norm_surface(surface)
    sire = _norm_text(sire)
    jockey = _norm_text(jockey)
    if not surface or not sire or not jockey or jockey == "-":
        return "-"

    rules = load_sire_jockey_rules()
    if rules.empty:
        return "-"

    m = rules[
        rules["表面"].eq(surface)
        & rules["父馬名"].eq(sire)
        & rules["騎手"].eq(jockey)
    ]
    if m.empty:
        return "-"
    mark = _norm_text(m.iloc[0].get("判定", "-"))
    return mark if mark in {"◎", "×"} else "-"
