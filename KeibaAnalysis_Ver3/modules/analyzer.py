"""
=========================================
Sire Analyzer Ver2.5
analyzer.py
-----------------------------------------
分析エンジン

改訂内容
-----------------------------------------
・父馬適性分析に性別要素を反映
・左右 / 坂 / 距離区分 / 枠 / 馬番は
  競馬場×距離に寄せすぎず、父馬×性別×該当条件で評価
・根幹 / 非根幹の好転条件を追加
・好転条件は点数化しない
・好転条件は「根」「非根」「-」で返す
=========================================
"""

import pandas as pd

import config

from modules import filter
from modules import statistics
from modules import evaluation
from modules import bias


class SireAnalyzer:
    """
    種牡馬分析クラス
    """

    def __init__(
        self,
        race_df: pd.DataFrame,
        course_df: pd.DataFrame,
        lucky_df: pd.DataFrame
    ):
        self.race_df = race_df
        self.course_df = course_df
        self.lucky_df = lucky_df

    # ==========================================
    # 安全系ユーティリティ
    # ==========================================

    def _safe_int(
        self,
        value,
        default=None
    ):
        """
        int変換を安全に行う
        """

        try:

            if value is None:
                return default

            if pd.isna(value):
                return default

            return int(value)

        except:

            return default

    def _safe_float(
        self,
        value,
        default=0.0
    ):
        """
        float変換を安全に行う
        """

        try:

            if value is None:
                return default

            if pd.isna(value):
                return default

            return float(value)

        except:

            return default

    def _clean_columns(
        self,
        df
    ):
        """
        列名の前後空白を除去
        """

        if df is None:
            return df

        df = df.copy()

        df.columns = [
            str(col).strip()
            for col in df.columns
        ]

        return df

    def _get_finish_column(
        self,
        df
    ):
        """
        着順列を取得
        """

        if df is None:
            return None

        candidates = []

        if hasattr(config, "COL_FINISH"):
            candidates.append(config.COL_FINISH)

        candidates.extend(
            [
                "確定着順",
                "着順",
                "入線順位",
                "着",
            ]
        )

        for col in candidates:

            if col in df.columns:
                return col

        return None

    def _calc_simple_rate(
        self,
        df
    ):
        """
        勝率・複勝率を簡易計算する
        """

        empty_result = {
            "sample": 0,
            "win": 0,
            "place": 0,
            "win_rate": 0.0,
            "place_rate": 0.0,
        }

        if df is None:
            return empty_result

        if len(df) == 0:
            return empty_result

        df = self._clean_columns(df)

        finish_col = self._get_finish_column(df)

        if finish_col is None:
            empty_result["sample"] = len(df)
            return empty_result

        finish = pd.to_numeric(
            df[finish_col],
            errors="coerce"
        )

        sample = len(df)

        win = int(
            (finish == 1).sum()
        )

        place = int(
            (finish <= 3).sum()
        )

        if sample <= 0:

            return empty_result

        return {
            "sample": sample,
            "win": win,
            "place": place,
            "win_rate": win / sample * 100,
            "place_rate": place / sample * 100,
        }

    def _is_core_distance(
        self,
        distance
    ):
        """
        根幹距離判定

        400mで割り切れる距離を根幹距離とする
        例:
        1200, 1600, 2000, 2400, 2800, 3200
        """

        distance = self._safe_int(
            distance,
            default=None
        )

        if distance is None:
            return None

        return distance % 400 == 0

    # ==========================================
    # 基本条件抽出
    # ==========================================

    def filter_base(
        self,
        place=None,
        distance=None,
        sex=None
    ):
        """
        基本条件で抽出
        """

        return filter.filter_race(
            self.race_df,
            place=place,
            distance=distance,
            sex=sex
        )

    # ==========================================
    # 父馬抽出
    # ==========================================

    def filter_sire(
        self,
        df,
        sire_name
    ):
        """
        父馬名で抽出
        """

        if df is None:
            return pd.DataFrame()

        if len(df) == 0:
            return pd.DataFrame()

        if config.COL_SIRE not in df.columns:
            return pd.DataFrame()

        return df[
            df[config.COL_SIRE] == sire_name
        ]

    # ==========================================
    # 基本統計計算
    # ==========================================

    def calculate_statistics(
        self,
        base_df,
        sire_df
    ):
        """
        基本統計計算
        """

        return statistics.calc_statistics(
            sire_df,
            base_df
        )

    # ==========================================
    # 評価取得
    # ==========================================

    def get_grade(
        self,
        stats_dict
    ):
        """
        評価記号取得
        """

        return evaluation.judge(
            stats_dict
        )

    # ==========================================
    # 評価コメント取得
    # ==========================================

    def get_grade_text(
        self,
        grade
    ):
        """
        評価コメント取得
        """

        return evaluation.judge_text(
            grade
        )

    # ==========================================
    # 分析結果生成
    # ==========================================

    def analyze(
        self,
        sire_name,
        place=None,
        distance=None,
        sex=None
    ):
        """
        基本分析
        """

        base_df = self.filter_base(
            place=place,
            distance=distance,
            sex=sex
        )

        sire_df = self.filter_sire(
            base_df,
            sire_name
        )

        stats_dict = self.calculate_statistics(
            base_df,
            sire_df
        )

        grade = self.get_grade(
            stats_dict
        )

        return {
            "stats": stats_dict,
            "grade": grade,
            "grade_text": self.get_grade_text(
                grade
            ),
        }

    # ==========================================
    # コース情報取得
    # ==========================================

    def get_course_info(
        self,
        course_id
    ):
        """
        コースIDからコース情報を取得

        例:
        東京芝1600
        中山ダ1200
        """

        if course_id in [None, "", "未指定"]:
            return None

        course_df = self.course_df

        if course_df is None:
            return None

        if len(course_df) == 0:
            return None

        course_df = self._clean_columns(
            course_df
        )

        if "コースID" not in course_df.columns:
            return None

        course_df["コースID"] = (
            course_df["コースID"]
            .astype(str)
            .str.strip()
        )

        target_course_id = str(
            course_id
        ).strip()

        hit_df = course_df[
            course_df["コースID"] == target_course_id
        ]

        if len(hit_df) == 0:
            return None

        return hit_df.iloc[0].to_dict()

    # ==========================================
    # コース条件分析
    # ==========================================

    def analyze_course(
        self,
        sire_name,
        course_id,
        place=None,
        distance=None,
        sex=None
    ):
        """
        コース条件を加味した分析
        """

        base_df = self.filter_base(
            place=place,
            distance=distance,
            sex=sex
        )

        if course_id is not None:

            base_df = statistics.filter_by_course(
                base_df,
                course_id
            )

        sire_df = self.filter_sire(
            base_df,
            sire_name
        )

        course_info = self.get_course_info(
            course_id
        )

        if course_info is None:
            return None

        stats_dict = self.calculate_statistics(
            base_df,
            sire_df
        )

        grade = self.get_grade(
            stats_dict
        )

        return {
            "course": course_info,
            "stats": stats_dict,
            "grade": grade,
            "grade_text": self.get_grade_text(
                grade
            ),
        }

    # ==========================================
    # ラッキー馬番判定
    # ==========================================

    def get_lucky_number_rank(
        self,
        place,
        distance,
        horse_no
    ):
        """
        ラッキー馬番判定
        """

        if horse_no is None:
            return None

        if self.lucky_df is None:
            return None

        if len(self.lucky_df) == 0:
            return None

        df = self.lucky_df.copy()

        if "競馬場" not in df.columns:
            return None

        if "距離" not in df.columns:
            return None

        if "馬番" not in df.columns:
            return None

        df = df[
            (df["競馬場"] == place)
            &
            (df["距離"] == distance)
        ]

        if df.empty:
            return None

        row = df[
            df["馬番"] == horse_no
        ]

        if row.empty:
            return None

        return "★"

    # ==========================================
    # 右左分析
    # ==========================================

    def analyze_right_left(
        self,
        sire_name,
        right_left,
        sex=None
    ):
        """
        父馬×性別×右左で分析

        競馬場×距離とは独立して、
        その産駒が右回り・左回りのどちらで走りやすいかを見る
        """

        if right_left in [None, "", "未指定"]:
            return None

        base_df = self.filter_base(
            place=None,
            distance=None,
            sex=sex
        )

        base_df = statistics.filter_by_right_left(
            base_df,
            right_left
        )

        sire_df = self.filter_sire(
            base_df,
            sire_name
        )

        stats_dict = self.calculate_statistics(
            base_df,
            sire_df
        )

        grade = self.get_grade(
            stats_dict
        )

        return {
            "stats": statistics.to_dict(
                stats_dict
            ),
            "grade": grade,
            "grade_text": self.get_grade_text(
                grade
            ),
        }

    # ==========================================
    # 坂分析
    # ==========================================

    def analyze_slope(
        self,
        sire_name,
        slope,
        sex=None
    ):
        """
        父馬×性別×坂で分析
        """

        if slope in [None, "", "未指定"]:
            return None

        base_df = self.filter_base(
            place=None,
            distance=None,
            sex=sex
        )

        base_df = statistics.filter_by_slope(
            base_df,
            slope
        )

        sire_df = self.filter_sire(
            base_df,
            sire_name
        )

        stats_dict = self.calculate_statistics(
            base_df,
            sire_df
        )

        grade = self.get_grade(
            stats_dict
        )

        return {
            "stats": statistics.to_dict(
                stats_dict
            ),
            "grade": grade,
            "grade_text": self.get_grade_text(
                grade
            ),
        }

    # ==========================================
    # 距離区分分析
    # ==========================================

    def analyze_distance_type(
        self,
        sire_name,
        distance_type,
        sex=None
    ):
        """
        父馬×性別×距離区分で分析
        """

        if distance_type in [None, "", "未指定"]:
            return None

        base_df = self.filter_base(
            place=None,
            distance=None,
            sex=sex
        )

        base_df = statistics.filter_by_distance_type(
            base_df,
            distance_type
        )

        sire_df = self.filter_sire(
            base_df,
            sire_name
        )

        stats_dict = self.calculate_statistics(
            base_df,
            sire_df
        )

        grade = self.get_grade(
            stats_dict
        )

        return {
            "stats": statistics.to_dict(
                stats_dict
            ),
            "grade": grade,
            "grade_text": self.get_grade_text(
                grade
            ),
        }

    # ==========================================
    # 枠番分析
    # ==========================================

    def analyze_frame(
        self,
        sire_name,
        frame=None,
        sex=None
    ):
        """
        父馬×性別×枠番分析

        枠順未発表時(frame=None)は分析しない
        """

        if frame is None:
            return None

        base_df = self.filter_base(
            place=None,
            distance=None,
            sex=sex
        )

        base_df = statistics.filter_by_frame(
            base_df,
            frame
        )

        sire_df = self.filter_sire(
            base_df,
            sire_name
        )

        stats_dict = self.calculate_statistics(
            base_df,
            sire_df
        )

        grade = self.get_grade(
            stats_dict
        )

        return {
            "stats": statistics.to_dict(
                stats_dict
            ),
            "grade": grade,
            "grade_text": self.get_grade_text(
                grade
            ),
        }

    # ==========================================
    # 馬番分析
    # ==========================================

    def analyze_horse_no(
        self,
        sire_name,
        horse_no=None,
        sex=None
    ):
        """
        父馬×性別×馬番分析
        """

        if horse_no is None:
            return None

        base_df = self.filter_base(
            place=None,
            distance=None,
            sex=sex
        )

        base_df = statistics.filter_by_horse_no(
            base_df,
            horse_no
        )

        sire_df = self.filter_sire(
            base_df,
            sire_name
        )

        stats_dict = self.calculate_statistics(
            base_df,
            sire_df
        )

        grade = self.get_grade(
            stats_dict
        )

        return {
            "stats": statistics.to_dict(
                stats_dict
            ),
            "grade": grade,
            "grade_text": self.get_grade_text(
                grade
            ),
        }

    # ==========================================
    # 芝クッション値分析
    # ==========================================

    def analyze_cushion(
        self,
        sire_name,
        cushion,
        sex=None
    ):
        """
        父馬×性別×クッション値分析
        """

        if cushion in [None, "", "未指定"]:
            return None

        base_df = self.filter_base(
            place=None,
            distance=None,
            sex=sex
        )

        base_df = filter.filter_cushion(
            base_df,
            cushion
        )

        sire_df = self.filter_sire(
            base_df,
            sire_name
        )

        stats_dict = self.calculate_statistics(
            base_df,
            sire_df
        )

        grade = self.get_grade(
            stats_dict
        )

        return {
            "stats": statistics.to_dict(
                stats_dict
            ),
            "grade": grade,
            "grade_text": self.get_grade_text(
                grade
            ),
        }

    # ==========================================
    # ダート馬場状態分析
    # ==========================================

    def analyze_going(
        self,
        sire_name,
        going,
        sex=None
    ):
        """
        父馬×性別×馬場状態分析
        """

        if going in [None, "", "未指定"]:
            return None

        base_df = self.filter_base(
            place=None,
            distance=None,
            sex=sex
        )

        base_df = filter.filter_going(
            base_df,
            going
        )

        sire_df = self.filter_sire(
            base_df,
            sire_name
        )

        stats_dict = self.calculate_statistics(
            base_df,
            sire_df
        )

        grade = self.get_grade(
            stats_dict
        )

        return {
            "stats": statistics.to_dict(
                stats_dict
            ),
            "grade": grade,
            "grade_text": self.get_grade_text(
                grade
            ),
        }

    # ==========================================
    # 根幹・非根幹 好転条件分析
    # ==========================================

    def analyze_core_distance(
        self,
        sire_name,
        sex=None
    ):
        """
        父馬×性別で根幹・非根幹の好転条件を分析

        戻り値
        ----------
        label:
            "根"   : 根幹距離で好成績
            "非根" : 非根幹距離で好成績
            "-"    : 差が小さい / サンプル不足

        注意
        ----------
        ・点数化はしない
        ・結果表の「好転条件」列に使う
        """

        base_df = self.filter_base(
            place=None,
            distance=None,
            sex=sex
        )

        if base_df is None:
            return {
                "label": "-",
                "reason": "データ不足",
                "core": {},
                "non_core": {},
            }

        if len(base_df) == 0:
            return {
                "label": "-",
                "reason": "データ不足",
                "core": {},
                "non_core": {},
            }

        base_df = self._clean_columns(
            base_df
        )

        distance_col = config.COL_DISTANCE

        if distance_col not in base_df.columns:
            return {
                "label": "-",
                "reason": "距離列なし",
                "core": {},
                "non_core": {},
            }

        sire_df = self.filter_sire(
            base_df,
            sire_name
        )

        if len(sire_df) == 0:
            return {
                "label": "-",
                "reason": "父馬データ不足",
                "core": {},
                "non_core": {},
            }

        sire_df = sire_df.copy()

        sire_df["_distance_int"] = pd.to_numeric(
            sire_df[distance_col],
            errors="coerce"
        )

        sire_df["_is_core"] = sire_df["_distance_int"].apply(
            self._is_core_distance
        )

        core_df = sire_df[
            sire_df["_is_core"] == True
        ]

        non_core_df = sire_df[
            sire_df["_is_core"] == False
        ]

        core_stats = self._calc_simple_rate(
            core_df
        )

        non_core_stats = self._calc_simple_rate(
            non_core_df
        )

        min_sample = getattr(
            config,
            "CORE_DISTANCE_MIN_SAMPLE",
            5
        )

        place_diff_threshold = getattr(
            config,
            "CORE_DISTANCE_PLACE_DIFF",
            5.0
        )

        win_diff_threshold = getattr(
            config,
            "CORE_DISTANCE_WIN_DIFF",
            3.0
        )

        if core_stats["sample"] < min_sample:
            return {
                "label": "-",
                "reason": "根幹サンプル不足",
                "core": core_stats,
                "non_core": non_core_stats,
            }

        if non_core_stats["sample"] < min_sample:
            return {
                "label": "-",
                "reason": "非根幹サンプル不足",
                "core": core_stats,
                "non_core": non_core_stats,
            }

        win_diff = (
            core_stats["win_rate"]
            - non_core_stats["win_rate"]
        )

        place_diff = (
            core_stats["place_rate"]
            - non_core_stats["place_rate"]
        )

        label = "-"
        reason = "差が小さい"

        # -----------------------------
        # 根幹優勢
        # -----------------------------

        if (
            place_diff >= place_diff_threshold
            and win_diff >= 0
        ) or (
            win_diff >= win_diff_threshold
            and place_diff >= 0
        ):

            label = "根"
            reason = "根幹優勢"

        # -----------------------------
        # 非根幹優勢
        # -----------------------------

        elif (
            place_diff <= -place_diff_threshold
            and win_diff <= 0
        ) or (
            win_diff <= -win_diff_threshold
            and place_diff <= 0
        ):

            label = "非根"
            reason = "非根幹優勢"

        return {
            "label": label,
            "reason": reason,
            "core": core_stats,
            "non_core": non_core_stats,
            "diff": {
                "win_rate_diff": win_diff,
                "place_rate_diff": place_diff,
            },
        }

    # ==========================================
    # コースID分析
    # ==========================================

    def analyze_course_id(
        self,
        sire_name,
        course_id,
        place=None,
        distance=None,
        sex=None
    ):
        """
        コースID単位分析
        """

        base_df = self.filter_base(
            place=place,
            distance=distance,
            sex=sex
        )

        if course_id is not None:

            base_df = statistics.filter_by_course(
                base_df,
                course_id
            )

        sire_df = self.filter_sire(
            base_df,
            sire_name
        )

        stats_dict = self.calculate_statistics(
            base_df,
            sire_df
        )

        grade = self.get_grade(
            stats_dict
        )

        return {
            "stats": statistics.to_dict(
                stats_dict
            ),
            "grade": grade,
            "grade_text": self.get_grade_text(
                grade
            ),
        }

    # ==========================================
    # 統計情報取得
    # ==========================================

    def get_statistics(
        self,
        sire_name,
        place=None,
        distance=None,
        sex=None
    ):
        """
        基本統計のみ取得
        """

        result = self.analyze(
            sire_name=sire_name,
            place=place,
            distance=distance,
            sex=sex
        )

        return statistics.to_dict(
            result["stats"]
        )

    # ==========================================
    # 評価のみ取得
    # ==========================================

    def get_grade_only(
        self,
        sire_name,
        place=None,
        distance=None,
        sex=None
    ):
        """
        評価記号のみ取得
        """

        result = self.analyze(
            sire_name=sire_name,
            place=place,
            distance=distance,
            sex=sex
        )

        return result["grade"]

    # ==========================================
    # データ存在確認
    # ==========================================

    def has_data(
        self,
        sire_name,
        place=None,
        distance=None,
        sex=None
    ):
        """
        対象データ有無
        """

        base_df = self.filter_base(
            place=place,
            distance=distance,
            sex=sex
        )

        sire_df = self.filter_sire(
            base_df,
            sire_name
        )

        return len(sire_df) > 0

    # ==========================================
    # 総合分析
    # ==========================================

    def analyze_all(
        self,
        horse_name,
        sire_name,
        sex,
        frame=None,
        horse_no=None,
        course_id=None,
        place=None,
        distance=None,
        cushion=None,
        going=None
    ):
        """
        出走馬1頭を総合分析
        """

        # -----------------------------
        # 基本条件抽出
        # 競馬場×距離の評価用
        # -----------------------------

        base_df = self.filter_base(
            place=place,
            distance=distance,
            sex=sex
        )

        if course_id is not None:

            base_df = statistics.filter_by_course(
                base_df,
                course_id
            )

        # -----------------------------
        # コース情報取得
        # -----------------------------

        course_info = None

        if course_id is not None:

            course_info = self.get_course_info(
                course_id
            )

        # -----------------------------
        # 父馬抽出
        # -----------------------------

        sire_df = self.filter_sire(
            base_df,
            sire_name
        )

        # -----------------------------
        # 競馬場×距離 成績
        # -----------------------------

        stats_dict = self.calculate_statistics(
            base_df,
            sire_df
        )

        grade = self.get_grade(
            stats_dict
        )

        # -----------------------------
        # 父馬適性分析
        # -----------------------------

        father_result = {}

        result_rl = None
        result_slope = None
        result_distance_type = None

        # ① 競馬場×距離
        father_result["course_distance"] = {
            "grade": grade,
            "grade_text": self.get_grade_text(
                grade
            ),
            "stats": statistics.to_dict(
                stats_dict
            ),
        }

        # ② 左右適性
        right_left = None

        if course_info:

            right_left = course_info.get(
                "右左"
            )

        if right_left:

            result_rl = self.analyze_right_left(
                sire_name=sire_name,
                right_left=right_left,
                sex=sex
            )

            father_result["right_left"] = result_rl

        else:

            father_result["right_left"] = None

        # ③ 坂適性
        slope = None

        if course_info:

            slope = course_info.get(
                "坂"
            )

        if slope:

            result_slope = self.analyze_slope(
                sire_name=sire_name,
                slope=slope,
                sex=sex
            )

            father_result["slope"] = result_slope

        else:

            father_result["slope"] = None

        # ④ 枠順適性
        if frame is not None:

            father_result["frame"] = self.analyze_frame(
                sire_name=sire_name,
                frame=frame,
                sex=sex
            )

        else:

            father_result["frame"] = None

        # ⑤ 馬番適性
        if horse_no is not None:

            father_result["horse_no"] = self.analyze_horse_no(
                sire_name=sire_name,
                horse_no=horse_no,
                sex=sex
            )

        else:

            father_result["horse_no"] = None

        # ⑥ 距離区分適性
        distance_type = None

        if course_info:

            distance_type = course_info.get(
                "距離区分"
            )

        if distance_type:

            result_distance_type = self.analyze_distance_type(
                sire_name=sire_name,
                distance_type=distance_type,
                sex=sex
            )

            father_result["distance_type"] = result_distance_type

        else:

            father_result["distance_type"] = None

        # ⑦ クッション値
        father_result["cushion"] = None

        if cushion not in [None, "", "未指定"]:

            father_result["cushion"] = self.analyze_cushion(
                sire_name=sire_name,
                cushion=cushion,
                sex=sex
            )

        # ⑧ 馬場状態
        father_result["going"] = None

        if going not in [None, "", "未指定"]:

            father_result["going"] = self.analyze_going(
                sire_name=sire_name,
                going=going,
                sex=sex
            )

        # ⑨ 根幹・非根幹 好転条件
        father_result["core_distance"] = self.analyze_core_distance(
            sire_name=sire_name,
            sex=sex
        )

        # -----------------------------
        # コースバイアス分析
        # -----------------------------

        bias_result = {}

        # ① 枠順バイアス
        bias_result["frame"] = None

        if frame is not None:

            frame_bias = bias.analyze_frame_bias(
                base_df,
                frame
            )

            if frame_bias is not None:

                frame_bias["grade"] = evaluation.judge_bias(
                    rank=frame_bias.get(
                        "rank",
                        None
                    ),
                    total=frame_bias.get(
                        "total",
                        0
                    ),
                    sample=frame_bias.get(
                        "sample",
                        0
                    ),
                    diff=frame_bias.get(
                        "diff",
                        0.0
                    ),
                )

            bias_result["frame"] = frame_bias

        # ② ラッキー馬番
        bias_result["lucky"] = self.get_lucky_number_rank(
            place,
            distance,
            horse_no
        )

        # -----------------------------
        # TOTAL SCORE
        # -----------------------------
        # app.py側のSCORE_MAPで再計算するため、
        # ここは内部参考値として残す。
        # -----------------------------

        total_score = 0

        for key, value in father_result.items():

            if value is None:
                continue

            if key == "core_distance":
                continue

            if isinstance(value, dict) and "grade" in value:

                total_score += evaluation.grade_score(
                    value["grade"]
                )

        if bias_result["frame"] is not None:

            total_score += evaluation.grade_score(
                bias_result["frame"].get(
                    "grade",
                    "-"
                )
            )

        if bias_result["lucky"] == "★":

            total_score += 1

        # -----------------------------
        # 戻り値
        # -----------------------------

        result = {
            "horse_name": horse_name,
            "sire": sire_name,
            "sex": sex,
            "frame": frame,
            "horse_no": horse_no,

            # -------------------------
            # 総合評価
            # -------------------------

            "grade": grade,
            "grade_text": self.get_grade_text(
                grade
            ),
            "total_score": total_score,

            # -------------------------
            # 父馬適性
            # -------------------------

            "father": father_result,

            # -------------------------
            # コースバイアス
            # -------------------------

            "bias": bias_result,

            # -------------------------
            # 基本統計
            # -------------------------

            "stats": statistics.to_dict(
                stats_dict
            ),

            # -------------------------
            # コース情報
            # -------------------------

            "course": course_info,

            # -------------------------
            # DEBUG
            # -------------------------

            "debug": {
                "course_id": course_id,
                "course_info": course_info,
                "right_left": right_left,
                "slope": slope,
                "distance_type": distance_type,
                "result_rl": result_rl,
                "result_slope": result_slope,
                "result_distance_type": result_distance_type,
                "core_distance": father_result.get(
                    "core_distance",
                    None
                ),
            },
        }

        return result