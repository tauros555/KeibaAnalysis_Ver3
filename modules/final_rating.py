"""Sire Analyzer Ver6 final rating layer.

Hierarchical, surface-specific weights validated in Blocks 14M-14P.
Legacy StatScore remains available separately; this module owns S/A/B/C/降格.
"""
from __future__ import annotations

POS = {"◎","○","〇"}

TURF_THRESHOLDS = (6.55, 4.70, 3.00)
DIRT_THRESHOLDS = (4.85, 3.75, 2.75)


def _txt(v): return "" if v is None else str(v).strip()
def _pos(v): return _txt(v) in POS or _txt(v).upper() in {"TRUE","1","YES"}
def _jirai(v): return _txt(v) in {"◎","○","〇","◯","1","True","TRUE","true"}
def _sign(v):
    t=_txt(v)
    if t=="◎": return 1.25
    if t in {"○","〇"}: return 1.0
    if t=="×": return -1.0
    return 0.0

def _group(v):
    t=_txt(v)
    if t in POS: return "プラス"
    if t=="×": return "マイナス"
    if t=="△": return "中立"
    return "評価不可"


def calculate(result, training_record=None, surface="芝"):
    training_record = training_record or {}
    father = result.get("father", {}) or {}
    surface = "ダート" if str(surface).strip() in {"ダ","ダート"} else "芝"

    main = father.get("course_distance") or {}
    rl = father.get("right_left") or {}
    slope = father.get("slope") or {}
    dtype = father.get("distance_type") or {}
    frame = father.get("frame") or {}
    horse = father.get("horse_no") or {}
    cushion = father.get("cushion") or {}
    going = father.get("going") or {}
    own = result.get("own_cushion") or {}

    main_grade = main.get("grade","-")
    main_group = _group(main_grade)
    rl_s, slope_s, dtype_s = _sign(rl.get("grade")), _sign(slope.get("grade")), _sign(dtype.get("grade"))
    frame_s, horse_s = _sign(frame.get("grade")), _sign(horse.get("grade"))

    # Training layer. 調教コース判定 is the app-side name of verified コース判定.
    w = {"honmei":6.0, "course":2.0 if surface=="芝" else 1.0, "a3":2.0,
         "main":3.0, "comp":3.0, "rescue":0.5,
         "frame":1.0 if surface=="芝" else 0.5, "slope":1.0,
         "market":2.0 if surface=="芝" else 0.5, "own":1.0 if surface=="芝" else 0.0}

    score=0.0
    reasons=[]
    if _pos(training_record.get("調教本命","")):
        score += w["honmei"]; reasons.append("調教本命")
    if _pos(training_record.get("調教コース判定", training_record.get("コース判定",""))):
        score += w["course"]; reasons.append("調教コース判定プラス")
    if _pos(training_record.get("A3高勝率Lap","")):
        score += w["a3"]; reasons.append("A3高勝率Lap")

    score += _sign(main_grade)*w["main"]
    if main_group=="プラス": reasons.append("父馬×競馬場×距離プラス")
    elif main_group=="マイナス": reasons.append("父馬×競馬場×距離マイナス")

    comp=0.0
    if main_group in {"中立","評価不可"}:
        if surface=="芝":
            comp = (1.0 if rl_s>0 else 0.0) + (0.35 if dtype_s>0 else 0.0) - (0.60 if dtype_s<0 else 0.0)
            if rl_s>0: reasons.append("左右適性補完")
            if dtype_s<0: reasons.append("距離区分警告")
        else:
            comp = (1.0 if dtype_s>0 else 0.0) - (1.0 if dtype_s<0 else 0.0) + (0.25 if rl_s>0 else 0.0) - (0.70 if slope_s<0 else 0.0)
            if dtype_s>0: reasons.append("距離区分補完")
            if dtype_s<0: reasons.append("距離区分マイナス")
        score += comp*w["comp"]

    if main_group=="マイナス":
        rescue=(0.4 if rl_s>0 else 0.0)+(0.6 if dtype_s>0 else 0.0)
        score += rescue*w["rescue"]
        if rescue>0: reasons.append("父馬主評価マイナスの救済要素")

    if main_group=="プラス":
        support=(0.7 if frame_s>0 else 0.0)+(0.9 if horse_s>0 else 0.0)+(0.6 if frame_s>0 and horse_s>0 else 0.0)-(0.5 if horse_s<0 else 0.0)
        score += support*w["frame"]
        if support>0: reasons.append("枠・馬番支持")
        if horse_s<0: reasons.append("馬番適性警告")

    if surface=="ダート" and slope_s<0:
        score -= w["slope"]; reasons.append("坂適性マイナス")
    elif surface=="芝" and slope_s<0:
        score -= 0.2*w["slope"]

    if surface=="芝":
        market_s=_sign(cushion.get("grade"))
        score += market_s*w["market"]
        if market_s>0: reasons.append("クッション値適性プラス")
        elif market_s<0: reasons.append("クッション値適性マイナス")
        own_score=float(own.get("score",0.0) or 0.0)
        # avoid excessive double-add: if sire cushion is positive, own-good is support display only.
        if market_s>0 and own_score>0:
            own_add=0.0
            reasons.append("本人クッション良好（支持）")
        else:
            own_add=own_score*w["own"]
            score += own_add
            if own_score>0: reasons.append("本人クッション良好")
            elif own_score<0: reasons.append("本人クッション不振")
    else:
        market_s=_sign(going.get("grade"))
        score += market_s*w["market"]
        if market_s>0: reasons.append("当日馬場状態適性プラス")
        elif market_s<0: reasons.append("当日馬場状態適性マイナス")

    score=round(float(score),3)
    thresholds=TURF_THRESHOLDS if surface=="芝" else DIRT_THRESHOLDS
    if score>=thresholds[0]: grade="S"
    elif score>=thresholds[1]: grade="A"
    elif score>=thresholds[2]: grade="B"
    else: grade="C"

    if _jirai(training_record.get("地雷ラップ判定","")):
        grade="降格"
        reasons.append("地雷ラップ：強制降格")

    return {"score":score,"grade":grade,"reason":" / ".join(reasons) if reasons else "中立", "thresholds":thresholds}
