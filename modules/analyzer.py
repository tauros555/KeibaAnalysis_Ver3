"""Sire Analyzer Ver5.

Continuous statistics, partial pooling by sex, hierarchical course-distance
analysis, and corner-count aptitude. Public output keys remain compatible with
Ver3 app.py.
"""
from __future__ import annotations

from typing import Any, Callable
import pandas as pd

import config
from modules import statistics, evaluation, bias
from modules import filter as race_filter


class SireAnalyzer:
    def __init__(self, race_df: pd.DataFrame, course_df: pd.DataFrame, lucky_df: pd.DataFrame):
        self.race_df = race_df.copy() if race_df is not None else pd.DataFrame()
        self.course_df = course_df.copy() if course_df is not None else pd.DataFrame()
        self.lucky_df = lucky_df.copy() if lucky_df is not None else pd.DataFrame()
        self.race_df.columns = [str(c).strip() for c in self.race_df.columns]
        self.course_df.columns = [str(c).strip() for c in self.course_df.columns]

    @staticmethod
    def _empty_result(scope="データ不足"):
        stats = {
            "sample": 0, "base_sample": 0, "win": 0, "place": 0,
            "win_rate": 0.0, "place_rate": 0.0, "base_win_rate": 0.0,
            "base_place_rate": 0.0, "win_rate_diff": 0.0, "place_rate_diff": 0.0,
            "rr": 1.0, "place_rr": 1.0, "p_value": 1.0,
            "confidence_score": 0.0, "stat_score": 0.0, "aptitude_index": 100,
            "selected_scope": scope,
        }
        return {"stats": stats, "grade": "-", "grade_text": "データ不足", "stat_score": 0.0}

    def get_course_info(self, course_id):
        if course_id in [None, "", "未指定"] or self.course_df.empty or config.COL_COURSE_ID not in self.course_df.columns:
            return None
        values = self.course_df[config.COL_COURSE_ID].astype(str).str.strip()
        hit = self.course_df[values == str(course_id).strip()]
        return None if hit.empty else hit.iloc[0].to_dict()

    def _sire_all(self, sire_name):
        if self.race_df.empty or config.COL_SIRE not in self.race_df.columns:
            return pd.DataFrame(columns=self.race_df.columns)
        return self.race_df[self.race_df[config.COL_SIRE].astype(str).str.strip() == str(sire_name).strip()].copy()

    def _analyze_selector(self, sire_name: str, selector: Callable[[pd.DataFrame], pd.DataFrame], sex=None, scope=""):
        sire_all = self._sire_all(sire_name)
        if sire_all.empty:
            return self._empty_result(scope)
        stats_dict = statistics.analyze_condition(sire_all, selector, sex=sex)
        stats_dict["selected_scope"] = scope
        grade = evaluation.judge(stats_dict)
        return {
            "stats": stats_dict,
            "grade": grade,
            "grade_text": evaluation.judge_text(grade),
            "stat_score": float(stats_dict.get("stat_score", 0.0)),
        }

    def _course_distance_result(self, sire_name, place, distance, course_id, sex, course_info):
        sire_all = self._sire_all(sire_name)
        if sire_all.empty:
            return self._empty_result("データ不足")
        d = int(distance) if distance is not None else None
        surface = None
        if course_info:
            surface = course_info.get("芝・ダ")
        if surface is None and course_id:
            surface = "芝" if "芝" in str(course_id) else "ダ"

        def surface_mask(df):
            if surface is None:
                return pd.Series(True, index=df.index)
            # Prefer a dedicated surface column; otherwise course ID contains it.
            if "芝・ダ" in df.columns:
                return df["芝・ダ"].astype(str).str.strip().isin([surface, "ダート" if surface == "ダ" else surface])
            return df[config.COL_COURSE_ID].astype(str).str.contains(surface, na=False)

        exact = sire_all[
            (sire_all[config.COL_PLACE].astype(str).str.strip() == str(place).strip())
            & (pd.to_numeric(sire_all[config.COL_DISTANCE], errors="coerce") == d)
            & surface_mask(sire_all)
        ]
        exact_n = len(exact)
        nearby = sire_all[
            (sire_all[config.COL_PLACE].astype(str).str.strip() == str(place).strip())
            & (pd.to_numeric(sire_all[config.COL_DISTANCE], errors="coerce").between(d - config.COURSE_DISTANCE_MARGIN, d + config.COURSE_DISTANCE_MARGIN))
            & surface_mask(sire_all)
        ] if d is not None else exact
        nearby_n = len(nearby)
        distance_type = course_info.get(config.COL_DISTANCE_TYPE) if course_info else None
        dist_type_df = sire_all
        if distance_type and config.COL_DISTANCE_TYPE in sire_all.columns:
            dist_type_df = sire_all[(sire_all[config.COL_DISTANCE_TYPE] == distance_type) & surface_mask(sire_all)]
        dist_n = len(dist_type_df)

        if exact_n >= config.COURSE_EXACT_SAMPLE:
            selected = exact
            level = "exact"
            scope = f"{place}{surface or ''}{d}"
        elif nearby_n >= config.COURSE_NEARBY_SAMPLE:
            selected = nearby
            level = "nearby"
            scope = f"{place}{surface or ''}{d-config.COURSE_DISTANCE_MARGIN}～{d+config.COURSE_DISTANCE_MARGIN}"
        elif dist_n >= config.STAT_MIN_SAMPLE:
            selected = dist_type_df
            level = "distance_type"
            scope = f"全場{surface or ''}{distance_type or '距離区分'}"
        else:
            return self._empty_result("階層すべてサンプル不足")

        overall_stats = statistics.calc_effect_statistics(selected, sire_all)
        if sex not in [None, "", "すべて"] and config.COL_SEX in sire_all.columns:
            sex_all = sire_all[sire_all[config.COL_SEX].astype(str).str.strip() == str(sex).strip()]
            if level == "exact":
                sex_selected = sex_all[(sex_all[config.COL_PLACE].astype(str).str.strip() == str(place).strip()) & (pd.to_numeric(sex_all[config.COL_DISTANCE], errors="coerce") == d)]
            elif level == "nearby":
                sex_selected = sex_all[(sex_all[config.COL_PLACE].astype(str).str.strip() == str(place).strip()) & (pd.to_numeric(sex_all[config.COL_DISTANCE], errors="coerce").between(d-config.COURSE_DISTANCE_MARGIN, d+config.COURSE_DISTANCE_MARGIN))]
            else:
                sex_selected = sex_all[sex_all[config.COL_DISTANCE_TYPE] == distance_type] if distance_type and config.COL_DISTANCE_TYPE in sex_all.columns else sex_all
            sex_stats = statistics.calc_effect_statistics(sex_selected, sex_all)
            pooled = statistics.partial_pool_effect(overall_stats, sex_stats)
        else:
            pooled = overall_stats
            pooled.update({"sex_sample": 0, "sex_weight": 0.0, "pooling": "父馬全体"})
        pooled.update({
            "source_level": level, "selected_scope": scope,
            "exact_sample": exact_n, "nearby_sample": nearby_n,
            "distance_type_sample": dist_n,
        })
        grade = evaluation.judge(pooled)
        return {"stats": pooled, "grade": grade, "grade_text": evaluation.judge_text(grade), "stat_score": pooled.get("stat_score", 0.0)}

    def analyze_right_left(self, sire_name, right_left, sex=None):
        if right_left in [None, ""]: return None
        return self._analyze_selector(sire_name, lambda d: d[d[config.COL_RIGHT_LEFT] == right_left] if config.COL_RIGHT_LEFT in d.columns else d.iloc[0:0], sex, f"{right_left}回り")

    def analyze_slope(self, sire_name, slope, sex=None):
        if slope in [None, ""]: return None
        return self._analyze_selector(sire_name, lambda d: d[d[config.COL_SLOPE] == slope] if config.COL_SLOPE in d.columns else d.iloc[0:0], sex, f"坂:{slope}")

    def analyze_corner_count(self, sire_name, corner_count, sex=None):
        if corner_count in [None, ""]: return None
        c = float(corner_count)
        col = config.COL_CORNER_COUNT
        result = self._analyze_selector(sire_name, lambda d: d[pd.to_numeric(d[col], errors="coerce") == c] if col in d.columns else d.iloc[0:0], sex, f"コーナー{c:g}回")
        if result["grade"] == "-":
            group = "少" if c <= 2 else "多"
            result = self._analyze_selector(
                sire_name,
                lambda d: d[pd.to_numeric(d[col], errors="coerce").le(2) if group == "少" else pd.to_numeric(d[col], errors="coerce").gt(2)] if col in d.columns else d.iloc[0:0],
                sex,
                f"{group}コーナー",
            )
        return result

    def analyze_distance_type(self, sire_name, distance_type, sex=None):
        if distance_type in [None, ""]: return None
        return self._analyze_selector(sire_name, lambda d: d[d[config.COL_DISTANCE_TYPE] == distance_type] if config.COL_DISTANCE_TYPE in d.columns else d.iloc[0:0], sex, f"距離区分:{distance_type}")

    def analyze_frame(self, sire_name, frame=None, sex=None):
        if frame is None: return None
        return self._analyze_selector(sire_name, lambda d: d[pd.to_numeric(d[config.COL_FRAME], errors="coerce") == int(frame)] if config.COL_FRAME in d.columns else d.iloc[0:0], sex, f"枠{frame}")

    def analyze_horse_no(self, sire_name, horse_no=None, sex=None):
        if horse_no is None: return None
        return self._analyze_selector(sire_name, lambda d: d[pd.to_numeric(d[config.COL_HORSE_NO], errors="coerce") == int(horse_no)] if config.COL_HORSE_NO in d.columns else d.iloc[0:0], sex, f"馬番{horse_no}")

    def analyze_cushion(self, sire_name, cushion, sex=None):
        if cushion in [None, "", "未指定"]: return None
        return self._analyze_selector(sire_name, lambda d: race_filter.filter_cushion(d, cushion), sex, f"クッション:{cushion}")

    def analyze_going(self, sire_name, going, sex=None):
        if going in [None, "", "未指定", "未判明"]: return None
        return self._analyze_selector(sire_name, lambda d: race_filter.filter_going(d, going), sex, f"馬場:{going}")

    def analyze_core_distance(self, sire_name, sex=None):
        sire_all = self._sire_all(sire_name)
        if sire_all.empty or config.COL_DISTANCE not in sire_all.columns:
            return {"label": "-", "reason": "データ不足", "core": {}, "non_core": {}}
        if sex not in [None, "", "すべて"] and config.COL_SEX in sire_all.columns:
            sire_all = sire_all[sire_all[config.COL_SEX].astype(str).str.strip() == str(sex).strip()]
        dist = pd.to_numeric(sire_all[config.COL_DISTANCE], errors="coerce")
        core = statistics._rate_summary(sire_all[dist.mod(400).eq(0)])
        non = statistics._rate_summary(sire_all[~dist.mod(400).eq(0)])
        if min(core["sample"], non["sample"]) < config.STAT_MIN_SAMPLE:
            return {"label": "-", "reason": "サンプル不足", "core": core, "non_core": non}
        wd = core["win_rate"] - non["win_rate"]
        pdiff = core["place_rate"] - non["place_rate"]
        label = "根" if (wd >= 2 and pdiff >= 3) else "非根" if (wd <= -2 and pdiff <= -3) else "-"
        return {"label": label, "reason": "根幹優勢" if label == "根" else "非根幹優勢" if label == "非根" else "差が小さい", "core": core, "non_core": non}

    def get_lucky_number_rank(self, place, distance, horse_no):
        if horse_no is None or self.lucky_df.empty: return None
        df = self.lucky_df.copy()
        # Prefer course ID implementation when available.
        if "競馬場" in df.columns and "距離" in df.columns and "馬番" in df.columns:
            hit = df[(df["競馬場"].astype(str).str.strip() == str(place).strip()) & (pd.to_numeric(df["距離"], errors="coerce") == int(distance)) & (pd.to_numeric(df["馬番"], errors="coerce") == int(horse_no))]
            return "★" if not hit.empty else None
        return None

    @staticmethod
    def _group_score(father_result, key):
        item = father_result.get(key)
        return 0.0 if not isinstance(item, dict) else float(item.get("stat_score", item.get("stats", {}).get("stat_score", 0.0)) or 0.0)

    def analyze_all(self, horse_name, sire_name, sex, frame=None, horse_no=None, course_id=None, place=None, distance=None, cushion=None, going=None):
        course_info = self.get_course_info(course_id)
        cd = self._course_distance_result(sire_name, place, distance, course_id, sex, course_info)
        father = {"course_distance": cd}
        father["right_left"] = self.analyze_right_left(sire_name, course_info.get(config.COL_RIGHT_LEFT) if course_info else None, sex)
        father["slope"] = self.analyze_slope(sire_name, course_info.get(config.COL_SLOPE) if course_info else None, sex)
        father["corner_count"] = self.analyze_corner_count(sire_name, course_info.get(config.COL_CORNER_COUNT) if course_info else None, sex)
        father["distance_type"] = self.analyze_distance_type(sire_name, course_info.get(config.COL_DISTANCE_TYPE) if course_info else None, sex)
        father["frame"] = self.analyze_frame(sire_name, frame, sex)
        father["horse_no"] = self.analyze_horse_no(sire_name, horse_no, sex)
        father["cushion"] = self.analyze_cushion(sire_name, cushion, sex)
        father["going"] = self.analyze_going(sire_name, going, sex)
        father["core_distance"] = self.analyze_core_distance(sire_name, sex)

        # Course shape supplement grows as exact-course confidence falls.
        cd_conf = float(cd.get("stats", {}).get("confidence_score", 0.0) or 0.0)
        shape_parts = [self._group_score(father, k) for k in ["right_left", "slope", "corner_count", "distance_type"]]
        shape_score = sum(shape_parts) / max(sum(1 for x in shape_parts if x != 0), 1)
        course_group_score = self._group_score(father, "course_distance") * cd_conf + shape_score * (1.0 - cd_conf)
        market_score = self._group_score(father, "cushion") if cushion not in [None, "", "未指定"] else self._group_score(father, "going")
        frame_score = self._group_score(father, "frame") + 0.25 * self._group_score(father, "horse_no")

        # Bias remains course-side information.
        base_course_df = self.race_df
        if course_id and config.COL_COURSE_ID in base_course_df.columns:
            base_course_df = base_course_df[base_course_df[config.COL_COURSE_ID].astype(str).str.strip() == str(course_id).strip()]
        frame_bias = bias.analyze_frame_bias(base_course_df, frame) if frame is not None else None
        if frame_bias is not None:
            frame_bias["grade"] = evaluation.judge_bias(frame_bias.get("rank"), frame_bias.get("total"), frame_bias.get("sample"), frame_bias.get("diff"))
        lucky = self.get_lucky_number_rank(place, distance, horse_no)
        bias_score = 0.0
        if frame_bias:
            bias_score += float(frame_bias.get("diff", 0.0) or 0.0) * 0.15
        if lucky == "★": bias_score += 0.5
        bias_result = {"frame": frame_bias, "lucky": lucky, "stat_score": round(bias_score, 4)}

        total = round(course_group_score + market_score + frame_score + bias_score, 3)
        effect = cd.get("stats", {})
        overall_grade = evaluation.judge({
            "sample": effect.get("sample", 0),
            "stat_score": total,
            "confidence_score": max(cd_conf, 0.45 if total != 0 else 0.0),
            "win_rate_diff": effect.get("win_rate_diff", 0.0),
            "place_rate_diff": effect.get("place_rate_diff", 0.0),
        })
        return {
            "horse_name": horse_name, "sire": sire_name, "sex": sex, "frame": frame, "horse_no": horse_no,
            "grade": overall_grade, "grade_text": evaluation.judge_text(overall_grade), "total_score": total,
            "father": father, "bias": bias_result, "stats": effect, "course": course_info,
            "aptitude_effect": {
                "win_rate_diff": effect.get("win_rate_diff", 0.0),
                "place_rate_diff": effect.get("place_rate_diff", 0.0),
                "aptitude_index": effect.get("aptitude_index", 100),
                "display": f"{float(effect.get('win_rate_diff',0.0)):+.1f}pt（{int(round(float(effect.get('aptitude_index',100))))}）",
            },
            "stat_groups": {
                "course_distance": round(course_group_score, 4), "surface": round(market_score, 4),
                "frame": round(frame_score, 4), "bias": round(bias_score, 4),
            },
            "debug": {"course_id": course_id, "course_info": course_info},
        }

    # Compatibility helpers
    def analyze(self, sire_name, place=None, distance=None, sex=None):
        result = self._course_distance_result(sire_name, place, distance, None, sex, None)
        return {"stats": result["stats"], "grade": result["grade"], "grade_text": result["grade_text"]}
    def get_statistics(self, sire_name, place=None, distance=None, sex=None): return self.analyze(sire_name, place, distance, sex)["stats"]
    def get_grade_only(self, sire_name, place=None, distance=None, sex=None): return self.analyze(sire_name, place, distance, sex)["grade"]
    def has_data(self, sire_name, place=None, distance=None, sex=None): return not self._sire_all(sire_name).empty
