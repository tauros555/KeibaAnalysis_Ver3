# =====================================================
# app.py Ver7.2
# Runaway's UI統合 + JRA馬場情報 + 単勝オッズ自動取得 + 妙味自動判定 対応版 v11
# =====================================================

import streamlit as st
import pandas as pd

from io import StringIO
from pathlib import Path
import html as html_lib
import re
import time
from urllib.request import Request, urlopen

import config

from modules import loader
from modules.analyzer import SireAnalyzer
from modules import final_rating, cushion_analyzer, jockey_reference

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODULES_DIR = BASE_DIR / "modules"



# =====================================================
# パス設定
# =====================================================

TRAINING_CSV_PATH = DATA_DIR / "調教判定表.csv"
TITLE_IMAGE_PATH = BASE_DIR / "タイトル.png"


# =====================================================
# 共通ユーティリティ
# =====================================================

def normalize_text(value):
    """
    馬名・コースIDなどの表記ゆれ対策
    半角/全角スペース、改行、nan を整理する
    """

    if value is None:
        return ""

    value = str(value)
    value = value.replace("　", "")
    value = value.replace(" ", "")
    value = value.replace("\n", "")
    value = value.replace("\r", "")
    value = value.strip()

    if value in ["nan", "None", "NaN"]:
        return ""

    return value


def normalize_surface(value):
    """
    芝・ダート表記を統一
    """

    value = str(value).strip()

    if value in ["芝", "T", "t", "1"]:
        return "芝"

    if value in ["ダ", "ダート", "D", "d", "2"]:
        return "ダ"

    return value


def to_int_or_none(value):
    """
    数値化できるものだけ int にする
    """

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    try:
        return int(float(value))
    except Exception:
        return None


def normalize_manual_sex(value):
    """
    手入力の性別を正規化する
    空欄・未入力は None として、性別で絞り込まない
    性齢が「牡3」「牝2」「セ4」のような形式でも拾う
    """

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    value = str(value).strip()

    if value in ["", "-", "なし", "無し", "nan", "None", "NaN"]:
        return None

    if "牡" in value:
        return "牡"

    if "牝" in value:
        return "牝"

    if "せ" in value or "セ" in value or "騙" in value:
        return "せん"

    return None


def is_positive_mark(value):
    """
    〇・○・◎・★・True・1 を有効判定にする
    ×・なし・False・0・空欄は無効
    """

    if value is None:
        return False

    value = str(value).strip()

    if value in ["〇", "○", "◎", "★", "True", "true", "1"]:
        return True

    return False


def is_negative_or_empty(value):
    """
    ×・なし・False・0・空欄などを無効扱いにする
    """

    if value is None:
        return True

    value = str(value).strip()

    if value in [
        "",
        "-",
        "なし",
        "無し",
        "nan",
        "None",
        "NaN",
        "×",
        "False",
        "false",
        "0",
    ]:
        return True

    return False


# =====================================================
# 調教判定表 連携用関数
# =====================================================

def make_unique_columns(columns):
    """
    重複列名を一意化する
    例: コース判定, コース判定 → コース判定, コース判定.1
    """

    new_columns = []
    col_count = {}

    for col in columns:
        col = str(col).strip()

        if col not in col_count:
            col_count[col] = 0
            new_columns.append(col)
        else:
            col_count[col] += 1
            new_columns.append(f"{col}.{col_count[col]}")

    return new_columns


def format_a3_high_win_lap(value):
    """
    調教判定表の「A3高勝率Lap」を画面表示用に変換する。

    CSV上で「〇」または「○」の場合は「★」、
    「なし」の場合は「なし」、欠損時は「-」を返す。
    """

    if value is None or pd.isna(value):
        return "-"

    text = str(value).strip()

    if text in {"〇", "○"}:
        return "★"

    if text == "なし":
        return "なし"

    if text == "":
        return "-"

    return text


def normalize_training_df(training_df):
    """
    調教判定表の列名をアプリ用に整理
    """

    if training_df is None:
        return None

    df = training_df.copy()

    # 列名の前後空白を削除して重複列名を一意化
    df.columns = make_unique_columns(df.columns)

    # -----------------------------
    # 列名変換
    # -----------------------------

    rename_dict = {}

    # 前半のコース判定 = アプリのコースID
    if "コース判定" in df.columns and "コースID" not in df.columns:
        rename_dict["コース判定"] = "コースID"
    elif "コース判定" in df.columns and "コースID" in df.columns:
        # すでにコースIDがある場合は、後でコース判定側を調教コース判定候補にする
        rename_dict["コース判定"] = "調教コース判定"

    # 後半のコース判定 = 調教コース判定
    if "コース判定.1" in df.columns:
        rename_dict["コース判定.1"] = "調教コース判定"

    if "コース判定.2" in df.columns:
        rename_dict["コース判定.2"] = "調教コース判定"

    if "コースID.1" in df.columns:
        rename_dict["コースID.1"] = "調教コース判定"

    # 父馬・種牡馬対応
    if "父" not in df.columns:
        if "父馬" in df.columns:
            rename_dict["父馬"] = "父"
        elif "種牡馬" in df.columns:
            rename_dict["種牡馬"] = "父"

    # 本命・相手
    if "本命候補判定" in df.columns:
        rename_dict["本命候補判定"] = "調教本命"

    if "相手候補判定" in df.columns:
        rename_dict["相手候補判定"] = "調教相手"

    # 調教師・騎手
    if "調教師" not in df.columns:
        for c in ["調教師名", "Trainer"]:
            if c in df.columns:
                rename_dict[c] = "調教師"
                break
    if "騎手" not in df.columns:
        for c in ["騎手名", "Jockey"]:
            if c in df.columns:
                rename_dict[c] = "騎手"
                break

    # 枠番
    if "枠番" not in df.columns and "枠" in df.columns:
        rename_dict["枠"] = "枠番"

    # Ver7.0: 調教判定表から開催場・レース番号・表面を自動認識
    if "場所" not in df.columns:
        for c in ["競馬場", "開催場", "場名"]:
            if c in df.columns:
                rename_dict[c] = "場所"
                break
    if "R" not in df.columns:
        for c in ["レース番号", "R番号", "レース"]:
            if c in df.columns:
                rename_dict[c] = "R"
                break
    if "芝・ダ" not in df.columns:
        for c in ["芝ダ", "芝ダート", "馬場種別", "表面"]:
            if c in df.columns:
                rename_dict[c] = "芝・ダ"
                break

    df = df.rename(columns=rename_dict)

    # rename後にも重複があれば再度一意化
    df.columns = make_unique_columns(df.columns)

    # rename後に コースID.1 が残った場合は調教コース判定として扱う
    if "コースID.1" in df.columns and "調教コース判定" not in df.columns:
        df = df.rename(columns={"コースID.1": "調教コース判定"})

    # -----------------------------
    # 照合用キー
    # -----------------------------

    if "馬名" in df.columns:
        df["馬名_key"] = df["馬名"].apply(normalize_text)

    if "コースID" in df.columns:
        df["コースID_key"] = df["コースID"].apply(normalize_text)

    # 芝・ダの表記統一
    if "芝・ダ" in df.columns:
        df["芝・ダ"] = df["芝・ダ"].apply(normalize_surface)

    return df


def load_training_csv(path):
    """
    調教判定表CSVを自動読み込みする
    utf-8-sig → cp932 の順に試す
    """

    if path is None:
        return None

    path = Path(path)

    if not path.exists():
        return None

    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="cp932")

    return normalize_training_df(df)


def get_training_record(training_df, horse_name, course_id=None, race_no=None):
    """
    調教判定表から1頭分のデータを取得
    基本は 馬名 で照合
    コースIDがある場合は 馬名 + コースID を優先
    """

    if training_df is None:
        return None

    if len(training_df) == 0:
        return None

    if "馬名_key" not in training_df.columns:
        return None

    df = training_df.copy()

    target_horse = normalize_text(horse_name)
    target_course_id = normalize_text(course_id)

    hit_df = df[df["馬名_key"] == target_horse]

    if len(hit_df) == 0:
        return None

    if target_course_id != "" and "コースID_key" in hit_df.columns:
        hit_course_df = hit_df[hit_df["コースID_key"] == target_course_id]
        if len(hit_course_df) > 0:
            hit_df = hit_course_df

    if race_no is not None and "R" in hit_df.columns:
        race_values = pd.to_numeric(hit_df["R"], errors="coerce")
        hit_race_df = hit_df[race_values == int(race_no)]
        if len(hit_race_df) == 0:
            return None
        hit_df = hit_race_df

    return hit_df.iloc[0].to_dict()


def create_horses_from_training_df(
    training_df,
    place,
    race_no,
    surface,
    distance,
):
    """
    調教判定表CSVから指定レースの出走馬リストを作成
    """

    if training_df is None:
        return []

    if len(training_df) == 0:
        return []

    df = training_df.copy()

    required_cols = [
        "場所",
        "R",
        "芝・ダ",
        "距離",
        "馬番",
        "馬名",
        "性別",
        "父",
    ]

    for col in required_cols:
        if col not in df.columns:
            return []

    df["場所"] = df["場所"].astype(str).str.strip()
    df["芝・ダ"] = df["芝・ダ"].apply(normalize_surface)

    df["R"] = pd.to_numeric(df["R"], errors="coerce")
    df["距離"] = pd.to_numeric(df["距離"], errors="coerce")
    df["馬番"] = pd.to_numeric(df["馬番"], errors="coerce")

    target_surface = normalize_surface(surface)

    target_df = df[
        (df["場所"] == str(place).strip())
        & (df["R"] == int(race_no))
        & (df["芝・ダ"] == target_surface)
        & (df["距離"] == int(distance))
    ].copy()

    if len(target_df) == 0:
        return []

    target_df = target_df.sort_values("馬番", ascending=True)

    horses = []

    for _, row in target_df.iterrows():
        horses.append(
            {
                "horse_name": str(row.get("馬名", "")).strip(),
                "sire": str(row.get("父", "")).strip(),
                "sex": str(row.get("性別", "")).strip(),
                "frame": to_int_or_none(row.get("枠番", None)),
                "horse_no": to_int_or_none(row.get("馬番", None)),
            }
        )

    return horses


# =====================================================
# 手入力出馬表 連携用関数
# =====================================================

COLUMN_MAP = {
    "horse_name": [
        "馬名",
        "馬 名",
        "Horse",
    ],
    "sire": [
        "父",
        "父馬",
        "父馬名",
        "種牡馬",
    ],
    "sex": [
        "性別",
        "性",
        "性齢",
    ],
    "frame": [
        "枠番",
        "枠",
        "枠No",
    ],
    "horse_no": [
        "馬番",
        "馬No",
        "馬番号",
        "馬",
    ],
}


# Ver5ではSCORE_MAPを使用せず、各統計項目の連続StatScoreを使用します。

def find_column(df, aliases):
    """
    aliasesに一致する列名を返す
    """

    for col in aliases:
        if col in df.columns:
            return col

    return None


def normalize_horse_df(raw_df):
    """
    手入力の出馬表をアプリ内部形式に正規化
    """

    if raw_df is None:
        return pd.DataFrame()

    df = raw_df.copy()

    df.columns = (
        df.columns.astype(str)
        .str.replace("\ufeff", "", regex=False)
        .str.strip()
    )

    horse_col = find_column(df, COLUMN_MAP["horse_name"])
    sire_col = find_column(df, COLUMN_MAP["sire"])
    sex_col = find_column(df, COLUMN_MAP["sex"])
    frame_col = find_column(df, COLUMN_MAP["frame"])
    horse_no_col = find_column(df, COLUMN_MAP["horse_no"])

    # 手入力では「父」だけ必須。
    # 馬名・性別は事前予想時に未入力でも分析できるようにする。
    if sire_col is None:
        raise ValueError("必須列がありません：父")

    result = pd.DataFrame()

    if horse_col is not None:
        result["馬名"] = (
            df[horse_col]
            .fillna("")
            .astype(str)
            .str.strip()
        )
    else:
        result["馬名"] = [
            f"馬{i + 1}"
            for i in range(len(df))
        ]

    # 馬名が空欄の場合も、表示・結果作成用に仮名を付ける
    result["馬名"] = [
        name if str(name).strip() != "" else f"馬{i + 1}"
        for i, name in enumerate(result["馬名"].tolist())
    ]

    result["父"] = (
        df[sire_col]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    if sex_col is not None:
        result["性別"] = df[sex_col].apply(normalize_manual_sex)
    else:
        result["性別"] = None

    if frame_col:
        result["枠番"] = df[frame_col]
    else:
        result["枠番"] = None

    if horse_no_col:
        result["馬番"] = df[horse_no_col]
    else:
        result["馬番"] = None

    # 父だけは分析に必須。馬名・性別は必須にしない。
    result = result[
        result["父"].astype(str).str.strip() != ""
    ].copy()

    return result


def read_manual_race_text(race_text):
    """
    手入力出馬表を安全に読み込む

    対応形式
    ----------
    1. CSV形式
       馬名,性別,父
       A,牡,キズナ

    2. タブ区切り
       馬名    性別    父

    3. 父だけ1列
       父
       キズナ
       ハービンジャー

    4. ヘッダーなし父だけ
       キズナ
       ハービンジャー
    """

    text = str(race_text).strip()

    if text == "":
        return pd.DataFrame()

    lines = [
        line.strip()
        for line in text.splitlines()
        if str(line).strip() != ""
    ]

    if len(lines) == 0:
        return pd.DataFrame()

    first_line = lines[0]

    # -----------------------------
    # カンマ区切り
    # -----------------------------

    if "," in first_line:
        df = pd.read_csv(
            StringIO(text),
            sep=",",
        )

    # -----------------------------
    # タブ区切り
    # -----------------------------

    elif "\t" in first_line:
        df = pd.read_csv(
            StringIO(text),
            sep="\t",
        )

    # -----------------------------
    # 1列入力
    # -----------------------------

    else:
        # 1行目が列名の場合
        if first_line in ["父", "父馬", "種牡馬"]:
            df = pd.DataFrame(
                {
                    "父": lines[1:]
                }
            )

        elif first_line in ["馬名", "馬 名"]:
            df = pd.DataFrame(
                {
                    "馬名": lines[1:]
                }
            )

        elif first_line in ["性別", "性", "性齢"]:
            df = pd.DataFrame(
                {
                    "性別": lines[1:]
                }
            )

        # ヘッダーなしの場合は父だけ入力とみなす
        else:
            df = pd.DataFrame(
                {
                    "父": lines
                }
            )

    # -----------------------------
    # 列名クリーニング
    # -----------------------------

    df.columns = (
        df.columns
        .astype(str)
        .str.replace("\ufeff", "", regex=False)
        .str.strip()
    )

    return df


def parse_horses_from_manual_text(race_text):
    """
    手入力欄から horses を作成
    区切り文字を自動推定せず、安全に読み込む
    """

    if race_text is None:
        return [], pd.DataFrame()

    if str(race_text).strip() == "":
        return [], pd.DataFrame()

    raw_df = read_manual_race_text(
        race_text
    )

    if raw_df is None or len(raw_df) == 0:
        return [], pd.DataFrame()

    horse_df = normalize_horse_df(
        raw_df
    )

    horses = []

    for _, row in horse_df.iterrows():
        horses.append(
            {
                "horse_name": row.get("馬名", ""),
                "sire": row.get("父", ""),
                "sex": row.get("性別", None),
                "frame": to_int_or_none(row.get("枠番", None)),
                "horse_no": to_int_or_none(row.get("馬番", None)),
            }
        )

    return horses, horse_df


def make_preview_df_from_horses(horses):
    """
    horsesリストをプレビュー用DataFrameにする
    """

    if len(horses) == 0:
        return pd.DataFrame()

    df = pd.DataFrame(horses)

    df = df.rename(
        columns={
            "horse_no": "馬番",
            "frame": "枠番",
            "horse_name": "馬名",
            "sire": "父",
            "sex": "性別",
        }
    )

    preview_columns = [
        "馬番",
        "枠番",
        "馬名",
        "父",
        "性別",
    ]

    preview_columns = [
        col for col in preview_columns
        if col in df.columns
    ]

    return df[preview_columns]


# =====================================================
# 最終判定関数
# =====================================================

def has_jirai_lap(value):
    """
    地雷ラップ判定
    〇・○・◎・True・1 のときだけ地雷あり
    """

    return is_positive_mark(value)


def apply_jirai_downgrade(final_judgement, jirai_value):
    """
    地雷ラップによる強制降格
    """

    if not has_jirai_lap(jirai_value):
        return final_judgement, "-"

    downgrade_map = {
        "本命継続": "本命注意",
        "本命注意": "評価下げ",
        "相手昇格": "相手候補",
        "相手候補": "評価下げ",
        "穴候補": "評価下げ",
        "様子見": "評価下げ",
        "評価下げ": "評価下げ",
    }

    downgraded = downgrade_map.get(final_judgement, final_judgement)

    return downgraded, "地雷ラップ：強制降格"


def count_effective_good_grades(row):
    """
    重複を避けた有効適性一致数を数える。

    最大4グループ
    1. コース・距離適性
    2. 馬場適性
    3. 枠・馬番適性
    4. コースバイアス
    """

    count = 0

    # 1. コース・距離適性グループ
    course_distance_main = row.get("競馬場×距離", "-")
    course_distance_sub = [
        row.get("距離区分", "-"),
        row.get("左右", "-"),
        row.get("坂", "-"),
        row.get("コーナー", "-"),
    ]

    if course_distance_main in ["◎", "○"]:
        count += 1
    elif course_distance_main in ["△", "-", None, ""]:
        good_sub_count = sum(
            1
            for mark in course_distance_sub
            if mark in ["◎", "○"]
        )
        if good_sub_count >= 2:
            count += 1

    # 2. 馬場適性グループ
    if (
        row.get("クッション", "-") in ["◎", "○"]
        or row.get("馬場状態", "-") in ["◎", "○"]
    ):
        count += 1

    # 3. 枠・馬番適性グループ
    if (
        row.get("枠適性", "-") in ["◎", "○"]
        or row.get("馬番適性", "-") in ["◎", "○"]
    ):
        count += 1

    # 4. コースバイアスグループ
    if (
        row.get("枠バイアス", "-") in ["◎", "○"]
        or row.get("Lucky", "-") in ["★", "◎", "○"]
    ):
        count += 1

    return count


def count_effective_bad_grades(row):
    """
    重複を避けた有効不安材料数を数える。

    最大4グループ
    """

    count = 0

    # 1. コース・距離適性グループ
    if row.get("競馬場×距離", "-") == "×":
        count += 1
    else:
        bad_sub_count = sum(
            1
            for mark in [
                row.get("距離区分", "-"),
                row.get("左右", "-"),
                row.get("坂", "-"),
                row.get("コーナー", "-"),
            ]
            if mark == "×"
        )
        if bad_sub_count >= 2:
            count += 1

    # 2. 馬場適性グループ
    if (
        row.get("クッション", "-") == "×"
        or row.get("馬場状態", "-") == "×"
    ):
        count += 1

    # 3. 枠・馬番適性グループ
    if (
        row.get("枠適性", "-") == "×"
        or row.get("馬番適性", "-") == "×"
    ):
        count += 1

    # 4. コースバイアスグループ
    if (
        row.get("枠バイアス", "-") == "×"
        or row.get("Lucky", "-") == "×"
    ):
        count += 1

    return count

def judge_final_result(row):
    """
    Ver5 最終判定（確定版）。

    優先順位
    0. 枠バイアス×・馬場状態×・クッション値× → 原則評価下げ（調教本命〇／A3高勝率Lap★は本命注意）
    1. 調教本命〇 または A3高勝率Lap★ → 本命継続
       ただし、地雷ラップ〇・競馬場×距離×のいずれかがあれば本命注意
    2. 調教相手〇 + 統計評価◎/○ → 相手昇格
    3. 調教相手〇、調教師判定〇、統計評価◎/○ → 相手候補
    4. 統計評価△ + プラス材料あり → 穴候補
    5. 統計評価△/▲ + プラス材料なし → 様子見
    6. 統計評価× → 評価下げ

    地雷ラップは基礎判定の後に強制降格する。
    """

    stat_grade = str(row.get("統計評価", "-") or "-").strip()
    training_honmei = is_positive_mark(row.get("調教本命", ""))
    training_aite = is_positive_mark(row.get("調教相手", ""))
    trainer_positive = is_positive_mark(row.get("調教師判定", ""))

    a3_value = str(row.get("A3高勝率Lap", "") or "").strip()
    a3_high_win = a3_value == "★" or is_positive_mark(a3_value)

    try:
        good_count = int(row.get("適性一致数", 0) or 0)
    except (TypeError, ValueError):
        good_count = 0

    # 本命系シグナル。A3高勝率Lap★は調教本命〇と同格で扱う。
    primary_signal = training_honmei or a3_high_win

    # 本命注意にする追加の不安条件。
    # 表示名の揺れに備えて、旧名・新名の両方を確認する。
    cushion_grade = str(
        row.get("クッション", row.get("クッション値", "-")) or "-"
    ).strip()
    course_distance_grade = str(
        row.get("競馬場×距離", row.get("競馬場・距離", "-")) or "-"
    ).strip()
    frame_bias_grade = str(row.get("枠バイアス", "-") or "-").strip()
    jirai_exists = has_jirai_lap(row.get("地雷ラップ判定", ""))

    going_grade = str(row.get("馬場状態", "-") or "-").strip()

    # 最優先の強制評価下げ条件。
    # 調教本命・A3高勝率Lap・統計評価など、ほかの条件より必ず優先する。
    forced_down_factors = []
    if frame_bias_grade == "×":
        forced_down_factors.append("枠バイアス×")
    if going_grade == "×":
        forced_down_factors.append("馬場状態×")
    if cushion_grade == "×":
        forced_down_factors.append("クッション値×")

    if forced_down_factors:
        # 例外：調教本命〇またはA3高勝率Lap★に該当する馬は、
        # 強制評価下げ条件があっても「本命注意」に留める。
        if primary_signal:
            return "本命注意", " / ".join(forced_down_factors)
        return "評価下げ", " / ".join(forced_down_factors)

    caution_factors = []
    if course_distance_grade == "×":
        caution_factors.append("競馬場・距離×")

    # 調教本命〇またはA3高勝率Lap★でも、
    # 地雷ラップまたは競馬場・距離×があれば本命注意。
    if primary_signal:
        if jirai_exists:
            return "本命注意", "地雷ラップ：本命注意"
        if caution_factors:
            return "本命注意", " / ".join(caution_factors)
        return "本命継続", "-"

    elif training_aite and stat_grade in {"◎", "○"}:
        judgement = "相手昇格"

    elif training_aite or trainer_positive or stat_grade in {"◎", "○"}:
        judgement = "相手候補"

    elif stat_grade == "△" and good_count >= 1:
        judgement = "穴候補"

    elif stat_grade in {"△", "▲"}:
        judgement = "様子見"

    elif stat_grade == "×":
        judgement = "評価下げ"

    else:
        # 未判定・データ不足時は積極評価せず中立扱い。
        judgement = "様子見"

    return apply_jirai_downgrade(
        judgement,
        row.get("地雷ラップ判定", ""),
    )

def safe_get_grade(value):
    """
    分析結果の dict から grade を安全に取り出す
    """

    if value is None:
        return "-"

    if isinstance(value, dict):
        return value.get("grade", "-")

    return "-"





def apply_live_cushion_override(result, race_df, cushion, target_surface):
    """
    Ver6.3:
    analyzer.py のバージョン差に影響されないよう、
    芝のクッション適性を app.py 側で必ず実数方式で再計算して上書きする。
    """
    if result is None or target_surface != "芝":
        return result

    if cushion in [None, "", "未指定"]:
        return result

    sire_name = result.get("sire", "")
    horse_name = result.get("horse_name", "")
    sex = result.get("sex", None)

    sire_cushion = cushion_analyzer.analyze_sire_cushion(
        race_df=race_df,
        sire_name=sire_name,
        cushion=cushion,
        sex=sex,
    )
    own_cushion = cushion_analyzer.analyze_horse_cushion(
        race_df=race_df,
        horse_name=horse_name,
        cushion=cushion,
    )

    result.setdefault("father", {})
    result["father"]["cushion"] = sire_cushion
    result["own_cushion"] = own_cushion

    result.setdefault("debug", {})
    result["debug"]["cushion_input"] = cushion
    result["debug"]["cushion_grade"] = sire_cushion.get("grade", "-")
    result["debug"]["cushion_scope"] = sire_cushion.get("stats", {}).get("selected_scope", "-")
    result["debug"]["cushion_method"] = "app強制再計算・実数±幅方式"

    return result




def color_score_star(v):
    text = str(v).strip()
    if text == "★★★":
        return "background-color: #ffd54f; color: #000000; font-weight: bold; text-align: center;"
    if text == "★★":
        return "background-color: #fff3cd; color: #000000; font-weight: bold; text-align: center;"
    return ""


def color_value_condition(v):
    text = str(v).strip()
    if "★★★" in text:
        return "background-color: #ffe0b2; color: #000000; font-weight: bold;"
    if "★★" in text:
        return "background-color: #fff3e0; color: #000000;"
    return ""


def top_row_horse_style(row):
    styles = [""] * len(row)
    if str(row.get("★", "")).strip() in {"★★", "★★★"} and "馬名" in row.index:
        styles[row.index.get_loc("馬名")] = (
            "background-color: #ffcc80; color: #000000; font-weight: bold;"
        )
    return styles


def color_top_final_grade(v):
    """トップページ注目レース：S評価セルだけ黄色表示"""
    if str(v).strip() == "S":
        return "background-color: #fff59d; color: #000000; font-weight: bold;"
    return ""


def normalize_surface_label(surface):
    text = "" if surface is None else str(surface).strip()
    if text in {"ダ", "ダート", "D", "dirt", "Dirt"}:
        return "ダート"
    if text in {"芝", "T", "turf", "Turf"}:
        return "芝"
    return text


def score_star(surface, score):
    """
    妙味スコア表示。
    表面名は ダ/ダート、芝 などの表記ゆれを吸収する。
    """
    surface = normalize_surface_label(surface)

    try:
        v = float(score)
    except Exception:
        return ""

    if surface == "ダート":
        if v >= 8.0:
            return "★★★"
        if v >= 7.5:
            return "★★"
        return ""

    if surface == "芝":
        if v >= 8.5:
            return "★★★"
        if v >= 8.25:
            return "★★"
        return ""

    return ""


def value_star_with_odds(surface, score, odds):
    """最終スコア + 現在単勝オッズで、実際に妙味条件へ入った時だけ★を返す。"""
    surface = normalize_surface_label(surface)
    try:
        v = float(score)
        o = float(odds)
    except Exception:
        return ""

    if surface == "ダート":
        if v >= 8.0 and 10.0 <= o <= 20.0:
            return "★★★"
        if v >= 7.5 and 10.0 <= o <= 20.0:
            return "★★"
        return ""

    if surface == "芝":
        if v >= 8.5 and 20.0 <= o <= 50.0:
            return "★★★"
        if v >= 8.25 and 10.0 <= o <= 20.0:
            return "★★"
        return ""

    return ""


def value_judgement_with_odds(surface, score, odds):
    """現在単勝オッズ込みの妙味判定。未取得時は理論条件を残す。"""
    theoretical = value_condition(surface, score)
    if theoretical == "-":
        return "-"
    try:
        o = float(odds)
    except Exception:
        return f"オッズ未取得｜{theoretical}"

    star = value_star_with_odds(surface, score, o)
    if star:
        label = theoretical.split("：", 1)[0]
        return f"{label}【該当】"
    return f"条件外（単勝{o:.1f}倍）"


def value_condition(surface, score):
    surface = normalize_surface_label(surface)

    try:
        v = float(score)
    except Exception:
        return "-"

    if surface == "ダート":
        if v >= 8.0:
            return "安定妙味★★★：単勝10〜20倍"
        if v >= 7.5:
            return "安定妙味★★：単勝10〜20倍"
        return "-"

    if surface == "芝":
        if v >= 8.5:
            return "強い妙味★★★：単勝20〜50倍"
        if v >= 8.25:
            return "妙味★★：単勝10〜20倍"
        return "-"

    return "-"


    if surface == "ダート":
        if v >= 8.0:
            return "安定妙味★★★：単勝10〜20倍"
        if v >= 7.5:
            return "安定妙味★★：単勝10〜20倍"
        return "-"

    if surface == "芝":
        if v >= 8.5:
            return "強い妙味★★★：単勝20〜50倍"
        if v >= 8.25:
            return "妙味★★：単勝10〜20倍"
        return "-"

    return "-"


# =====================================================
# Ver7.0: ZI（独立した相手候補軸。最終スコアには加点しない）
# =====================================================

def add_zi_partner_columns(df):
    out = df.copy()
    if "ZI" not in out.columns:
        out["ZI"] = "-"
    zi = pd.to_numeric(out["ZI"], errors="coerce")
    zi = zi.where(zi > 0)  # ZI=0 は未取得扱い
    out["ZI"] = ["-" if pd.isna(v) else int(v) if float(v).is_integer() else float(v) for v in zi]
    out["ZI順位"] = zi.rank(method="min", ascending=False).astype("Int64")
    valid = zi.dropna().sort_values(ascending=False)
    gap = float(valid.iloc[0] - valid.iloc[1]) if len(valid) >= 2 else None
    out["ZI差"] = pd.Series(["-"] * len(out), index=out.index, dtype="object")
    out["ZI相手判定"] = "-"
    if len(valid) > 0:
        top = valid.iloc[0]
        top_mask = zi.eq(top)
        if gap is not None:
            gap_disp = int(gap) if float(gap).is_integer() else round(gap, 1)
            out.loc[top_mask, "ZI差"] = str(gap_disp)
        mark = "○"
        if gap is not None and gap >= 10:
            mark = "◎◎"
        elif gap is not None and gap >= 5:
            mark = "◎"
        out.loc[top_mask, "ZI相手判定"] = mark
    out["ZI順位"] = out["ZI順位"].astype(object).where(out["ZI順位"].notna(), "-")
    return out

# =====================================================
# トップページ：注目レース一覧用関数
# =====================================================

def is_target_training_horse(record):
    """
    調教判定で本命または相手になっている馬だけ対象にする
    """

    if record is None:
        return False

    honmei = is_positive_mark(record.get("調教本命", ""))
    aite = is_positive_mark(record.get("調教相手", ""))

    return honmei or aite


def is_final_judgement_target(judgement):
    """
    トップページに表示する最終判定
    相手候補以上を対象にする
    """

    target_judgements = [
        "本命継続",
        "本命注意",
        "相手昇格",
        "相手候補",
        "穴候補",
    ]

    return judgement in target_judgements


def build_judgement_row_from_result(
    result,
    training_record,
    target_surface,
):
    """
    analyzer.analyze_all() の結果と調教判定データから、
    judge_final_result() に渡す1行分の辞書を作る
    """

    row = {}

    row["馬名"] = result.get("horse_name", "")
    row["父"] = result.get("sire", "")
    row["馬番"] = result.get("horse_no", "-")

    father = result.get("father", {})
    bias = result.get("bias", {})

    row["競馬場×距離"] = safe_get_grade(
        father.get("course_distance")
    )

    row["左右"] = safe_get_grade(
        father.get("right_left")
    )

    row["坂"] = safe_get_grade(
        father.get("slope")
    )

    row["距離区分"] = safe_get_grade(
        father.get("distance_type")
    )

    row["コーナー"] = safe_get_grade(
        father.get("corner_count")
    )

    row["枠適性"] = safe_get_grade(
        father.get("frame")
    )

    row["馬番適性"] = safe_get_grade(
        father.get("horse_no")
    )

    row["枠バイアス"] = safe_get_grade(
        bias.get("frame")
    )

    row["Lucky"] = bias.get("lucky", "-")

    if row["Lucky"] is None:
        row["Lucky"] = "-"

    if normalize_surface(target_surface) == "芝":
        row["クッション"] = safe_get_grade(
            father.get("cushion")
        )
    else:
        row["馬場状態"] = safe_get_grade(
            father.get("going")
        )

    if training_record is None:
        row["調教本命"] = "-"
        row["調教相手"] = "-"
        row["調教師判定"] = "-"
        row["A3高勝率Lap"] = "-"
        row["地雷ラップ判定"] = "-"
    else:
        row["調教本命"] = training_record.get("調教本命", "-")
        row["調教相手"] = training_record.get("調教相手", "-")
        row["調教師判定"] = training_record.get("調教師判定", "-")
        row["A3高勝率Lap"] = format_a3_high_win_lap(
            training_record.get("A3高勝率Lap", "-")
        )
        row["地雷ラップ判定"] = training_record.get("地雷ラップ判定", "-")

    row["StatScore"] = float(result.get("total_score", 0.0) or 0.0)
    row["適性一致数"] = count_effective_good_grades(row)
    row["不安材料数"] = count_effective_bad_grades(row)

    return row


def create_top_race_summary_by_full_analysis(
    training_df,
    analyzer,
    surface,
    place_list=None,
    cushion=None,
    going=None,
    cushion_map=None,
    going_map=None,
):
    """
    調教判定CSVをもとに全レースを分析し、
    調教本命または調教相手のうち、
    最終判定が相手候補以上の馬がいるレースを抽出する
    """

    if training_df is None:
        return pd.DataFrame()

    if len(training_df) == 0:
        return pd.DataFrame()

    df = training_df.copy()

    required_cols = [
        "場所",
        "R",
        "芝・ダ",
        "距離",
        "馬名",
        "父",
        "性別",
        "馬番",
        "調教本命",
        "調教相手",
    ]

    missing_cols = [
        col for col in required_cols
        if col not in df.columns
    ]

    if len(missing_cols) > 0:
        return pd.DataFrame()

    # -----------------------------
    # 表記統一
    # -----------------------------

    df["場所"] = df["場所"].astype(str).str.strip()
    df["芝・ダ"] = df["芝・ダ"].apply(normalize_surface)

    target_surface = normalize_surface(surface)

    df = df[
        df["芝・ダ"] == target_surface
    ].copy()

    if place_list is not None and len(place_list) > 0:
        df = df[
            df["場所"].isin(place_list)
        ].copy()

    if len(df) == 0:
        return pd.DataFrame()

    # -----------------------------
    # 調教本命・相手だけに絞る
    # -----------------------------

    df["調教本命_flag"] = df["調教本命"].apply(is_positive_mark)
    df["調教相手_flag"] = df["調教相手"].apply(is_positive_mark)

    df = df[
        (df["調教本命_flag"])
        | (df["調教相手_flag"])
    ].copy()

    if len(df) == 0:
        return pd.DataFrame()

    # -----------------------------
    # 数値変換
    # -----------------------------

    df["R"] = pd.to_numeric(df["R"], errors="coerce")
    df["距離"] = pd.to_numeric(df["距離"], errors="coerce")
    df["馬番"] = pd.to_numeric(df["馬番"], errors="coerce")

    if "枠番" not in df.columns and "枠" in df.columns:
        df["枠番"] = df["枠"]

    if "枠番" in df.columns:
        df["枠番"] = pd.to_numeric(df["枠番"], errors="coerce")
    else:
        df["枠番"] = None

    # -----------------------------
    # 1頭ずつ分析
    # -----------------------------

    rows = []

    for _, record in df.iterrows():
        place = str(record.get("場所", "")).strip()
        race_no = record.get("R", None)
        distance = record.get("距離", None)

        if place == "" or pd.isna(race_no) or pd.isna(distance):
            continue

        surface_code = "芝" if target_surface == "芝" else "ダ"
        course_id = f"{place}{surface_code}{int(distance)}"

        frame = to_int_or_none(record.get("枠番", None))
        horse_no = to_int_or_none(record.get("馬番", None))

        live_cushion = (cushion_map or {}).get(place, cushion) if target_surface == "芝" else None
        live_going = (going_map or {}).get(place, going) if target_surface != "芝" else None

        result = analyzer.analyze_all(
            horse_name=record.get("馬名", ""),
            sire_name=record.get("父", ""),
            sex=record.get("性別", ""),
            frame=frame,
            horse_no=horse_no,
            course_id=course_id,
            place=place,
            distance=int(distance),
            cushion=live_cushion,
            going=live_going,
        )

        if result is None:
            continue

        result = apply_live_cushion_override(
            result=result,
            race_df=analyzer.race_df,
            cushion=live_cushion,
            target_surface=target_surface,
        )

        training_record = record.to_dict()

        row_for_judge = build_judgement_row_from_result(
            result=result,
            training_record=training_record,
            target_surface=target_surface,
        )

        # Ver7.0: 中央の注目レースは最終評価Sのみ
        vr = final_rating.calculate(result, training_record, target_surface)
        if vr["grade"] != "S":
            continue

        rows.append(
            {
                "場所": place,
                "R": int(race_no),
                "芝・ダ": target_surface,
                "距離": int(distance),
                "レース名": record.get("レース名", ""),
                "馬番": horse_no if horse_no is not None else "-",
                "馬名": record.get("馬名", ""),
                "調教師": record.get("調教師", "-"),
                "騎手": record.get("騎手", "-"),
                "父": record.get("父", ""),
                "調教本命": record.get("調教本命", "-"),
                "調教相手": record.get("調教相手", "-"),
                "最終評価": vr["grade"],
                "最終スコア": vr["score"],
                "★": score_star(target_surface, vr["score"]),
                "妙味条件": value_condition(target_surface, vr["score"]),
                "評価理由": vr["reason"],
                "適性一致数": row_for_judge["適性一致数"],
                "不安材料数": row_for_judge["不安材料数"],
                "地雷補正": "地雷ラップ：強制降格" if vr["grade"] == "降格" else "-",
                "ZI": record.get("ZI", "-"),
                "脚質": record.get("脚質", "-"),
            }
        )

    if len(rows) == 0:
        return pd.DataFrame()

    result_df = pd.DataFrame(rows)
    # S馬の行にも同一レース内ZI相手情報を付与（元の全頭ZI順位は詳細表で確認）

    rank_order = {"S":0, "A":1, "B":2, "C":3, "降格":4}
    result_df["_評価順"] = result_df["最終評価"].map(rank_order).fillna(9)
    result_df = result_df.sort_values(
        ["場所", "R", "_評価順", "最終スコア"],
        ascending=[True, True, True, False],
    ).drop(columns=["_評価順"]).reset_index(drop=True)

    return result_df

# =====================================================
# ページ設定
# =====================================================

st.set_page_config(
    page_title="Runaway's | Race Analysis System Ver7.1",
    page_icon="🏇",
    layout="wide",
)

# Ver7.1: タイトル画像の世界観に合わせたダークネイビー × ゴールドUI
st.markdown("""
<style>
:root {
    --rw-bg: #061729;
    --rw-bg-2: #0a2238;
    --rw-panel: rgba(9, 34, 56, 0.94);
    --rw-panel-2: rgba(12, 43, 69, 0.96);
    --rw-border: #456b8a;
    --rw-border-soft: rgba(94, 139, 173, .55);
    --rw-gold: #f1c76a;
    --rw-gold-2: #d9a83f;
    --rw-text: #f7f9fc;
    --rw-muted: #afc3d5;
    --rw-blue: #3ea6ff;
    --rw-green: #2cd0a0;
}

html, body, [class*="css"] {
    color: var(--rw-text);
}

[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at 78% 0%, rgba(22, 67, 103, .34), transparent 34%),
        linear-gradient(180deg, #041321 0%, var(--rw-bg) 38%, #071c30 100%);
}

[data-testid="stHeader"] {
    background: rgba(4, 19, 33, .86);
}

.block-container {
    padding-top: .65rem;
    padding-bottom: 2.5rem;
    max-width: 1500px;
}

/* タイトル画像 */
[data-testid="stImage"] img {
    width: 100%;
    height: auto;
    max-height: none;
    object-fit: contain;
    object-position: center;
    border-radius: 10px;
    border: 1px solid rgba(241, 199, 106, .50);
    box-shadow: 0 14px 34px rgba(0, 0, 0, .34);
}
.rw-version {
    margin: .35rem 0 1.15rem 0;
    color: var(--rw-gold);
    text-align: center;
    font-weight: 700;
    letter-spacing: .06em;
}
.rw-tagline {
    color: var(--rw-muted);
    text-align: center;
    margin-top: -.75rem;
    margin-bottom: 1.1rem;
    font-size: .92rem;
}

/* 見出し */
h1, h2, h3, h4 {
    color: var(--rw-text) !important;
}
h2, h3 {
    letter-spacing: .02em;
}
[data-testid="stCaptionContainer"], .stCaption {
    color: var(--rw-muted) !important;
}

/* カード・パネル */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: linear-gradient(180deg, rgba(12, 43, 69, .95), rgba(6, 28, 48, .96));
    border-color: var(--rw-border-soft) !important;
    border-radius: 12px !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.025);
}

/* 入力欄 */
[data-baseweb="input"] > div,
[data-baseweb="select"] > div,
[data-baseweb="textarea"] > div,
.stTextInput input,
.stNumberInput input,
.stTextArea textarea {
    background-color: #0d2a43 !important;
    color: var(--rw-text) !important;
    border-color: var(--rw-border) !important;
}
[data-baseweb="select"] span,
[data-baseweb="select"] input,
.stTextInput label, .stSelectbox label, .stTextArea label, .stRadio label, .stCheckbox label {
    color: var(--rw-text) !important;
}

/* ボタン */
.stButton > button {
    background: linear-gradient(180deg, #f6d77e, var(--rw-gold));
    color: #17202a !important;
    border: 1px solid #ffd980;
    border-radius: 8px;
    font-weight: 800;
}
.stButton > button:hover {
    background: #ffe19a;
    border-color: #fff0bd;
    color: #0e1720 !important;
}

/* チェックボックス */
[data-testid="stCheckbox"] {
    color: var(--rw-text) !important;
}

/* 表 */
[data-testid="stDataFrame"] {
    border: 1px solid var(--rw-border-soft);
    border-radius: 10px;
    overflow: hidden;
    background: rgba(5, 25, 43, .90);
}

/* Alert */
[data-testid="stAlert"] {
    background: rgba(11, 40, 64, .95);
    color: var(--rw-text);
    border: 1px solid rgba(89, 132, 164, .48);
}

/* expander */
[data-testid="stExpander"] {
    border-color: var(--rw-border-soft) !important;
    background: rgba(8, 31, 51, .86);
}

/* 下部データ読込パネル */
.rw-data-panel {
    margin-top: 1.45rem;
    padding: .95rem 1.15rem .45rem 1.15rem;
    border: 1px solid var(--rw-border-soft);
    border-radius: 12px;
    background: linear-gradient(180deg, rgba(11, 39, 63, .96), rgba(7, 29, 49, .96));
}
.rw-data-title {
    color: var(--rw-text);
    font-size: 1.15rem;
    font-weight: 800;
}
.rw-data-title span {
    color: var(--rw-gold);
    margin-right: .45rem;
}
.rw-footer {
    margin-top: 1.75rem;
    padding-top: .95rem;
    border-top: 1px solid var(--rw-gold-2);
    color: var(--rw-muted);
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    font-size: .88rem;
}
.rw-footer strong { color: var(--rw-text); }
.rw-footer .gold { color: var(--rw-gold); font-style: italic; }
</style>
""", unsafe_allow_html=True)

if TITLE_IMAGE_PATH.exists():
    st.image(str(TITLE_IMAGE_PATH), use_container_width=True)
else:
    st.markdown("# 🏇 Runaway's")

st.markdown('<div class="rw-version">Race Analysis System — Ver7.1</div>', unsafe_allow_html=True)
st.markdown('<div class="rw-tagline">データで見抜く、勝利への直線。</div>', unsafe_allow_html=True)


# =====================================================
# データ読込
# =====================================================

data = loader.load_data()

course_df = data["course"]


# =====================================================
# 調教判定表読み込み
# =====================================================

training_df = None

# Ver7.1: 判定表使用チェックは画面最下部に配置。
# 値はsession_stateから先に参照し、チェック変更時のrerunで全体へ反映する。
if "use_training_data" not in st.session_state:
    st.session_state["use_training_data"] = True
use_training_data = bool(st.session_state.get("use_training_data", True))

training_load_status = []

if not use_training_data:
    if "training_df" in st.session_state:
        del st.session_state["training_df"]

    training_df = None

    st.info(
        "調教判定表は使用しません。手入力モードで分析します。"
    )

else:
    # 1. data/調教判定表.csv を自動読み込み
    training_df = load_training_csv(TRAINING_CSV_PATH)

    if training_df is not None:
        st.session_state["training_df"] = training_df

        training_load_status.append(("success", f"調教判定表CSVを読み込みました：{TRAINING_CSV_PATH}"))

    else:
        training_load_status.append(("info", f"事前配置CSVが見つかりません：{TRAINING_CSV_PATH}"))

        training_file = st.file_uploader(
            "調教判定表Excelをアップロードする場合はこちら",
            type=["xlsx"],
        )

        if training_file is not None:
            target_sheet_name = "メイン判定"

            try:
                training_file.seek(0)

                excel_file = pd.ExcelFile(
                    training_file,
                    engine="openpyxl",
                )

                sheet_name_map = {
                    str(sheet).strip(): sheet
                    for sheet in excel_file.sheet_names
                }

                if target_sheet_name not in sheet_name_map:
                    st.error(
                        f"Excel内に「{target_sheet_name}」というシートが見つかりません。"
                    )
                    st.write("Excel内のシート一覧:", excel_file.sheet_names)
                    st.stop()

                actual_sheet_name = sheet_name_map[target_sheet_name]

                training_file.seek(0)

                training_df = pd.read_excel(
                    training_file,
                    sheet_name=actual_sheet_name,
                    engine="openpyxl",
                )

                training_df = normalize_training_df(training_df)

                st.session_state["training_df"] = training_df

                training_load_status.append(("success", f"調教判定表を読み込みました。読み込みシート：{actual_sheet_name}"))

            except Exception as e:
                st.error("調教判定表の読み込み中にエラーが発生しました。")
                st.write(e)
                st.stop()

        elif "training_df" in st.session_state:
            training_df = st.session_state["training_df"]


# 必要列確認
if training_df is not None:
    required_training_cols = [
        "馬名",
        "調教本命",
        "調教相手",
        "地雷ラップ判定",
        "調教師判定",
        "調教コース判定",
    ]

    missing_cols = [
        col for col in required_training_cols
        if col not in training_df.columns
    ]

    if len(missing_cols) > 0:
        st.warning(
            "調教判定に必要な列が見つかりません: "
            + "、".join(missing_cols)
        )

        with st.expander("読み込んだ列名を確認"):
            st.write(training_df.columns.tolist())
    else:
        training_load_status.append(("success", "調教判定に必要な列を確認できました。"))


# =====================================================
# JRA 馬場情報 自動取得
# =====================================================

JRA_BABA_URLS = [
    "https://www.jra.go.jp/keiba/baba/index.html",
    "https://www.jra.go.jp/keiba/baba/index2.html",
    "https://www.jra.go.jp/keiba/baba/index3.html",
]


def _strip_html(raw):
    """最小限のHTML→テキスト変換。追加パッケージに依存しない。"""
    if raw is None:
        return ""
    text = re.sub(r"<script\b.*?</script>", " ", str(raw), flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _decode_jra_response(raw_bytes, content_type=""):
    """JRAページの文字コードを安全側に寄せて判定する。"""
    candidates = []
    m = re.search(r"charset=([\w\-]+)", content_type or "", flags=re.I)
    if m:
        candidates.append(m.group(1))
    candidates += ["utf-8", "cp932", "shift_jis"]
    for enc in candidates:
        try:
            return raw_bytes.decode(enc)
        except Exception:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def _parse_jra_baba_page(page_html, url):
    """JRA馬場情報1ページから、競馬場・クッション値・芝/ダート状態を抽出する。"""
    plain = _strip_html(page_html)

    venue = None
    for pat in [
        r"馬場情報[（(]\s*([^）)]+?)競馬場\s*[）)]",
        r"([^\s]+?)競馬場\s+馬場情報",
    ]:
        m = re.search(pat, plain)
        if m:
            venue = m.group(1).strip()
            break

    # JRAのクッション値はJavaScript描画後に実測値へ更新される。
    # 生HTMLでは目盛りの 12 / 10 / 8 / 7 を誤取得するため、ここでは読まない。
    # 実測値は _fetch_rendered_cushion_values() で描画後DOMから取得する。
    cushion = None

    cushion_time = None
    m = re.search(
        r'id=["\']cushion_list["\'][^>]*>\s*<option[^>]*>(.*?)</option>',
        page_html,
        flags=re.I | re.S,
    )
    if m:
        cushion_time = _strip_html(m.group(1)) or None

    turf_going = None
    dirt_going = None
    # 「馬場状態」から「芝のクッション値」までにある芝/ダート状態を優先して読む。
    status_match = re.search(r"馬場状態(.*?)芝のクッション値", plain, flags=re.S)
    status_text = status_match.group(1) if status_match else plain
    m = re.search(
        r"芝\s*(良|稍重|重|不良).*?ダート\s*(良|稍重|重|不良)",
        status_text,
        flags=re.S,
    )
    if m:
        turf_going, dirt_going = m.group(1), m.group(2)

    status_time = None
    m = re.search(r"馬場状態[（(]([^）)]+?現在)[）)]", plain)
    if m:
        status_time = m.group(1).strip()

    return {
        "venue": venue,
        "cushion": cushion,
        "cushion_time": cushion_time,
        "turf_going": turf_going,
        "dirt_going": dirt_going,
        "status_time": status_time,
        "url": url,
    }


def _fetch_rendered_cushion_values(urls):
    """Selenium/ChromiumでJRAページ描画後の実測クッション値を取得する。"""
    rendered = {}
    errors = []
    driver = None
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280,900")
        options.add_argument("--lang=ja-JP")
        options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36")

        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 15)

        for url in urls:
            try:
                driver.get(url)
                value_el = wait.until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "#cushion_num p strong"))
                )
                time_el = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#cushion_list option:first-child"))
                )
                value_text = value_el.text.strip()
                time_text = time_el.text.strip()
                body_text = driver.find_element(By.TAG_NAME, "body").text

                venue = None
                m = re.search(r"馬場情報[（(]\s*([^）)]+?)競馬場\s*[）)]", body_text)
                if not m:
                    m = re.search(r"(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)競馬場", body_text)
                if m:
                    venue = m.group(1).strip()

                turf_going = None
                dirt_going = None

                # 馬場状態も生HTMLではなく、JavaScript描画後のDOMを読む。
                # JRA側の表示構造変更で生HTMLの正規表現が別箇所を拾うことがあるため。
                for selector, target in [("#turf_info", "turf"), ("#dirt_info", "dirt")]:
                    try:
                        txt = driver.find_element(By.CSS_SELECTOR, selector).text
                        gm = re.search(r"(良|稍重|重|不良)", txt)
                        if gm:
                            if target == "turf":
                                turf_going = gm.group(1)
                            else:
                                dirt_going = gm.group(1)
                    except Exception:
                        pass

                # DOM個別要素から取れない場合のみ、描画後bodyから馬場状態部分を補完。
                if turf_going is None or dirt_going is None:
                    sm = re.search(
                        r"馬場状態.*?芝\s*(良|稍重|重|不良).*?ダート\s*(良|稍重|重|不良)",
                        body_text,
                        flags=re.S,
                    )
                    if sm:
                        turf_going = turf_going or sm.group(1)
                        dirt_going = dirt_going or sm.group(2)

                if venue and re.fullmatch(r"\d+(?:\.\d+)?", value_text):
                    rendered[venue] = {
                        "cushion": float(value_text),
                        "cushion_time": time_text or None,
                        "turf_going": turf_going,
                        "dirt_going": dirt_going,
                    }
                else:
                    errors.append(f"{url}: クッション実測値を判定できませんでした ({value_text!r})")
            except Exception as e:
                errors.append(f"{url}: ブラウザ取得失敗 - {e}")
    except Exception as e:
        errors.append(f"Chromium/Seleniumを起動できませんでした - {e}")
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    return rendered, errors


@st.cache_data(ttl=300, show_spinner=False)
def fetch_jra_track_conditions():
    """
    JRAの当日馬場情報を取得する。
    開催場の割当は index/index2/index3 に固定せず、ページタイトルから判定する。
    失敗したページはスキップして、アプリ自体は手動入力で継続できる。
    """
    results = {}
    errors = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
    }

    for url in JRA_BABA_URLS:
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=8) as resp:
                raw = resp.read()
                page_html = _decode_jra_response(raw, resp.headers.get("Content-Type", ""))
            info = _parse_jra_baba_page(page_html, url)
            if info.get("venue"):
                results[info["venue"]] = info
        except Exception as e:
            errors.append(f"{url}: {e}")

    # クッション値はJavaScript描画後の「測定時刻直下の実測値」を採用する。
    rendered_cushions, rendered_errors = _fetch_rendered_cushion_values(JRA_BABA_URLS)
    errors.extend(rendered_errors)
    for venue, rendered_info in rendered_cushions.items():
        if venue in results:
            results[venue]["cushion"] = rendered_info.get("cushion")
            results[venue]["cushion_time"] = rendered_info.get("cushion_time")
            # 芝/ダートの馬場状態も描画後DOMの値を最優先する。
            if rendered_info.get("turf_going"):
                results[venue]["turf_going"] = rendered_info.get("turf_going")
            if rendered_info.get("dirt_going"):
                results[venue]["dirt_going"] = rendered_info.get("dirt_going")

    return results, errors


# =====================================================
# Ver7.2 / JRA 単勝オッズ自動取得
# =====================================================

JRA_VENUE_CODES = {
    "札幌": "01", "函館": "02", "福島": "03", "新潟": "04", "東京": "05",
    "中山": "06", "中京": "07", "京都": "08", "阪神": "09", "小倉": "10",
}


def _normalize_yyyymmdd(value):
    """調教判定表の年月日を YYYYMMDD 8桁文字列にする。"""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    text = re.sub(r"\D", "", str(value))
    if len(text) >= 8:
        return text[:8]
    try:
        return f"{int(float(value)):08d}"
    except Exception:
        return None


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_jra_meeting_info(yyyymmdd):
    """JRA開催日程ページから「4回中山2日」の回次・日次を取得する。"""
    if not yyyymmdd or len(yyyymmdd) != 8:
        return {}, ["開催日を判定できませんでした。"]
    y, m, md = yyyymmdd[:4], int(yyyymmdd[4:6]), yyyymmdd[4:8]
    url = f"https://www.jra.go.jp/keiba/calendar{y}/{y}/{m}/{md}.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.8",
    }
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=10) as resp:
            raw = resp.read()
            page_html = _decode_jra_response(raw, resp.headers.get("Content-Type", ""))
        plain = _strip_html(page_html)
        meetings = {}
        for kai, venue, day in re.findall(
            r"(\d+)回\s*(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)\s*(\d+)日",
            plain,
        ):
            meetings[venue] = {"kai": int(kai), "day": int(day)}
        return meetings, ([] if meetings else [f"開催情報を抽出できませんでした: {url}"])
    except Exception as e:
        return {}, [f"開催情報取得失敗: {url} - {e}"]


def _make_jra_odds_urls(place, race_no, yyyymmdd, kai, day):
    """JRA出馬表URL候補。

    JRAのCNAMEキーは ``01 + 場コード + 年 + 回 + 日 + R + 年月日``。
    v10では先頭の ``01`` が欠けていたため、別ページへ遷移してオッズを取得できなかった。
    ``sw01ddd``（PC詳細出馬表）と ``sw01dde``（簡易詳細出馬表）の両方を試す。
    """
    code = JRA_VENUE_CODES.get(str(place).strip())
    if not code:
        return []
    base_key = f"01{code}{yyyymmdd[:4]}{int(kai):02d}{int(day):02d}{int(race_no):02d}{yyyymmdd}"
    return [
        f"https://app.jra.jp/JRADB/accessD.html?CNAME=sw01ddd{base_key}",
        f"https://app.jra.jp/JRADB/accessD.html?CNAME=sw01ddd{base_key}%2F00",
        f"https://app.jra.jp/JRADB/accessD.html?CNAME=sw01dde{base_key}",
        f"https://app.jra.jp/JRADB/accessD.html?CNAME=sw01dde{base_key}%2F00",
    ]


def _parse_odds_from_rendered_rows(driver, expected_horses):
    """描画後の出馬表から、調教判定表の馬名をキーに単勝・人気を拾う。"""
    from selenium.webdriver.common.by import By

    expected = []
    for h in expected_horses:
        no = to_int_or_none(h.get("horse_no"))
        name = normalize_text(h.get("horse_name", ""))
        if no is not None and name:
            expected.append((no, name, h.get("horse_name", "")))

    found = {}
    rows = driver.find_elements(By.CSS_SELECTOR, "tr")
    for row in rows:
        row_text = row.text or ""
        row_norm = normalize_text(row_text)
        if not row_norm:
            continue
        cells = row.find_elements(By.CSS_SELECTOR, "th,td")
        cell_texts = [(c.text or "").strip() for c in cells]

        for horse_no, name_norm, display_name in expected:
            if horse_no in found or name_norm not in row_norm:
                continue

            odds = None
            popularity = None

            # 最優先：JRAの「12.3 (4番人気)」形式。
            m = re.search(r"(\d{1,4}(?:\.\d+)?)\s*[（(]\s*(\d+)\s*番人気\s*[）)]", row_text)
            if m:
                odds = float(m.group(1))
                popularity = int(m.group(2))

            # 次点：馬名セルの直後にある単勝オッズ列を探す。
            if odds is None and cell_texts:
                horse_idx = None
                for i, txt in enumerate(cell_texts):
                    if name_norm and name_norm in normalize_text(txt):
                        horse_idx = i
                        break
                if horse_idx is not None:
                    for txt in cell_texts[horse_idx + 1: horse_idx + 4]:
                        pm = re.search(r"(\d+)\s*番人気", txt)
                        if pm:
                            popularity = int(pm.group(1))
                        om = re.fullmatch(r"\s*(\d{1,4}(?:\.\d+)?)\s*(?:[（(]\s*\d+\s*番人気\s*[）)])?\s*", txt)
                        if om:
                            candidate = float(om.group(1))
                            # 馬体重や斤量セルは通常 kg/記号を伴うため、純数値セルをオッズ候補にする。
                            if 1.0 <= candidate <= 9999.9:
                                odds = candidate
                                break

            # クラス名に odds を含むセルがあればさらに補完。
            if odds is None:
                for c, txt in zip(cells, cell_texts):
                    cls = (c.get_attribute("class") or "").lower()
                    if "odds" not in cls:
                        continue
                    om = re.search(r"(\d{1,4}(?:\.\d+)?)", txt)
                    if om:
                        odds = float(om.group(1))
                    pm = re.search(r"(\d+)\s*番人気", txt)
                    if pm:
                        popularity = int(pm.group(1))
                    if odds is not None:
                        break

            if odds is not None:
                found[horse_no] = {
                    "horse_no": horse_no,
                    "horse_name": display_name,
                    "odds": odds,
                    "popularity": popularity,
                }
    return found


def fetch_jra_win_odds_batch(race_requests):
    """
    複数レースの単勝オッズをChromium 1起動で取得。
    race_requests: [{date, place, race_no, horses}, ...]
    """
    results = {}
    errors = []
    if not race_requests:
        return results, errors

    driver = None
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1440,1200")
        options.add_argument("--lang=ja-JP")
        options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36")
        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 12)

        meeting_cache = {}
        for req in race_requests:
            yyyymmdd = _normalize_yyyymmdd(req.get("date"))
            place = str(req.get("place", "")).strip()
            race_no = to_int_or_none(req.get("race_no"))
            horses = req.get("horses", [])
            key = f"{yyyymmdd}_{place}_{race_no}"
            if not yyyymmdd or not place or race_no is None:
                errors.append(f"{key}: レース識別情報不足")
                continue

            if yyyymmdd not in meeting_cache:
                meeting_cache[yyyymmdd] = _fetch_jra_meeting_info(yyyymmdd)
            meetings, meet_errors = meeting_cache[yyyymmdd]
            if meet_errors:
                errors.extend(meet_errors)
            meet = meetings.get(place)
            if not meet:
                errors.append(f"{key}: {place}の回次・日次を取得できませんでした")
                continue

            success = False
            last_reason = ""
            for url in _make_jra_odds_urls(place, race_no, yyyymmdd, meet["kai"], meet["day"]):
                try:
                    driver.get(url)
                    wait.until(lambda d: d.find_element(By.TAG_NAME, "body").text.strip() != "")
                    time.sleep(1.0)
                    body_text = driver.find_element(By.TAG_NAME, "body").text
                    # 誤ページを採用しない。
                    date_ok = f"{int(yyyymmdd[4:6])}月{int(yyyymmdd[6:8])}日" in body_text
                    place_ok = place in body_text
                    race_ok = (f"{race_no}レース" in body_text) or (f"{race_no}R" in body_text)
                    if not (date_ok and place_ok and race_ok):
                        last_reason = "対象レース表示を確認できず"
                        continue
                    odds = _parse_odds_from_rendered_rows(driver, horses)

                    # 対象馬がいるのに1頭も拾えない場合は、別形式の出馬表URLも試す。
                    # v10はここで0件を「発売前」とみなして終了したため、URL/DOM不一致を見逃していた。
                    if horses and not odds:
                        if "単勝" in body_text or "オッズ" in body_text:
                            last_reason = "対象レースは開けたが単勝オッズを抽出できず"
                            continue

                    results[key] = {
                        "date": yyyymmdd,
                        "place": place,
                        "race_no": race_no,
                        "horses": odds,
                        "url": driver.current_url,
                    }
                    # 発売前など、JRAページ自体にオッズ表示が無い場合だけ0件を許容する。
                    success = True
                    break
                except Exception as e:
                    last_reason = str(e)
            if not success:
                errors.append(f"{key}: JRA出馬表取得失敗 - {last_reason}")
    except Exception as e:
        errors.append(f"単勝オッズ用Chromium/Seleniumを起動できませんでした - {e}")
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
    return results, errors


def _race_date_from_training(training_df, place, race_no):
    if training_df is None or "年月日" not in training_df.columns:
        return None
    tmp = training_df.copy()
    tmp["R_num"] = pd.to_numeric(tmp.get("R"), errors="coerce")
    hit = tmp[(tmp["場所"].astype(str).str.strip() == str(place).strip()) & (tmp["R_num"] == int(race_no))]
    if len(hit) == 0:
        return None
    return _normalize_yyyymmdd(hit.iloc[0].get("年月日"))


def _horses_for_odds_request(training_df, place, race_no):
    if training_df is None:
        return []
    tmp = training_df.copy()
    tmp["R_num"] = pd.to_numeric(tmp.get("R"), errors="coerce")
    tmp["馬番_num"] = pd.to_numeric(tmp.get("馬番"), errors="coerce")
    hit = tmp[(tmp["場所"].astype(str).str.strip() == str(place).strip()) & (tmp["R_num"] == int(race_no))]
    hit = hit.sort_values("馬番_num")
    return [
        {"horse_no": to_int_or_none(r.get("馬番")), "horse_name": r.get("馬名", "")}
        for _, r in hit.iterrows()
        if to_int_or_none(r.get("馬番")) is not None and normalize_text(r.get("馬名", ""))
    ]


def build_odds_requests(training_df, race_pairs):
    reqs = []
    seen = set()
    for place, race_no in race_pairs:
        rno = to_int_or_none(race_no)
        if rno is None:
            continue
        date = _race_date_from_training(training_df, place, rno)
        key = (date, str(place).strip(), rno)
        if not date or key in seen:
            continue
        seen.add(key)
        reqs.append({
            "date": date,
            "place": str(place).strip(),
            "race_no": rno,
            "horses": _horses_for_odds_request(training_df, place, rno),
        })
    return reqs


def get_cached_win_odds(training_df, place, race_no, horse_no):
    date = _race_date_from_training(training_df, place, race_no)
    key = f"{date}_{str(place).strip()}_{int(race_no)}"
    race = st.session_state.get("jra_win_odds_cache", {}).get(key, {})
    horse = race.get("horses", {}).get(to_int_or_none(horse_no), {})
    return horse.get("odds"), horse.get("popularity")


def merge_odds_into_result_df(df, training_df):
    if df is None or len(df) == 0:
        return df
    out = df.copy()
    odds_list, pop_list, stars, judgements = [], [], [], []
    for _, row in out.iterrows():
        odds, pop = get_cached_win_odds(training_df, row.get("場所", ""), row.get("R", 0), row.get("馬番"))
        odds_list.append("-" if odds is None else round(float(odds), 1))
        pop_list.append("-" if pop is None else int(pop))
        stars.append(value_star_with_odds(row.get("芝・ダ", ""), row.get("最終スコア"), odds))
        judgements.append(value_judgement_with_odds(row.get("芝・ダ", ""), row.get("最終スコア"), odds))
    out["単勝オッズ"] = odds_list
    out["人気"] = pop_list
    out["★"] = stars
    out["妙味条件"] = judgements
    return out


# =====================================================
# 第2ブロック / Ver7.1 Runaway's 当日ダッシュボード
# =====================================================

st.subheader("TRACK CONDITION")

# 開催場・距離・表面・Rは調教判定表から自動検出。手入力時のみ従来方式へフォールバック。
if training_df is not None and all(c in training_df.columns for c in ["場所", "R", "芝・ダ", "距離"]):
    input_mode = "調教判定表から自動取得"
    races = training_df[["場所", "R", "芝・ダ", "距離"]].copy()
    races["場所"] = races["場所"].astype(str).str.strip()
    races["芝・ダ"] = races["芝・ダ"].apply(normalize_surface)
    races["R"] = pd.to_numeric(races["R"], errors="coerce")
    races["距離"] = pd.to_numeric(races["距離"], errors="coerce")
    races = races.dropna().drop_duplicates().sort_values(["場所", "R"])

    # 調教判定表には未使用行が「0」で残る場合がある。
    # これを開催場として数えると 0 + 2場 で[:3]が埋まり、本来の3場目が消えるため先に除外する。
    place_text = races["場所"].astype(str).str.strip()
    valid_place_mask = ~place_text.isin(["", "0", "nan", "None", "NaN", "未指定"])
    valid_race_mask = pd.to_numeric(races["R"], errors="coerce").fillna(0).gt(0)
    valid_distance_mask = pd.to_numeric(races["距離"], errors="coerce").fillna(0).gt(0)
    valid_surface_mask = races["芝・ダ"].isin(["芝", "ダ"])
    races = races[valid_place_mask & valid_race_mask & valid_distance_mask & valid_surface_mask].copy()

    # JRA中央競馬は同日に最大3場開催。無効行を除外した後の実開催場を最大3場表示する。
    active_places = races["場所"].dropna().astype(str).str.strip().drop_duplicates().tolist()[:3]
    races = races[races["場所"].isin(active_places)].copy()
    st.caption("開催場・距離・芝/ダート・ZIは調教判定表から自動取得します。")

    cushion_map = dict(st.session_state.get("cushion_by_place", {}))
    going_map = dict(st.session_state.get("going_by_place", {}))

    refresh_col, source_col = st.columns([1, 3], vertical_alignment="center")
    with refresh_col:
        if st.button("🔄 JRA再取得", use_container_width=True):
            fetch_jra_track_conditions.clear()
            st.rerun()
    with source_col:
        st.caption("JRA公式馬場情報を自動取得。必要な場合だけ分析値を手動補正できます。")

    with st.spinner("JRA馬場情報を取得中..."):
        jra_conditions, jra_errors = fetch_jra_track_conditions()

    # Ver7.0と同じ配置：競馬場カードの下に共通のRACE NAVIGATIONを置く。
    venue_cols = st.columns(max(1, len(active_places)))
    for i, venue in enumerate(active_places):
        vraces = races[races["場所"] == venue]
        official = jra_conditions.get(venue, {})

        with venue_cols[i]:
            with st.container(border=True):
                st.markdown(f"### 🏇 {venue}")

                if official:
                    official_parts = []
                    if official.get("turf_going"):
                        official_parts.append(f'芝 {official["turf_going"]}')
                    if official.get("cushion") is not None:
                        official_parts.append(f'Cushion {official["cushion"]:.1f}')
                    if official.get("dirt_going"):
                        official_parts.append(f'ダ {official["dirt_going"]}')
                    if official_parts:
                        st.caption("JRA公式　" + " / ".join(official_parts))
                    time_note = official.get("cushion_time") or official.get("status_time")
                    if time_note:
                        st.caption(f"公表・測定：{time_note}")
                else:
                    st.caption("JRA公式値を取得できませんでした。手動入力で利用できます。")

                if (vraces["芝・ダ"] == "芝").any():
                    official_cushion = official.get("cushion")
                    adj_key = f"cushion_adjust_{venue}"
                    manual_key = f"cushion_manual_{venue}"

                    if official_cushion is not None:
                        if adj_key not in st.session_state:
                            st.session_state[adj_key] = 0.0
                        adjustment = st.number_input(
                            "芝 クッション補正",
                            min_value=-1.0,
                            max_value=1.0,
                            step=0.1,
                            format="%.1f",
                            key=adj_key,
                            help="例：雨で実質的に軟化したと見る場合は -0.1 ～ -0.3 など。",
                        )
                        cushion_map[venue] = round(float(official_cushion) + float(adjustment), 1)
                        st.metric(
                            "分析使用クッション値",
                            f'{cushion_map[venue]:.1f}',
                            delta=f'{adjustment:+.1f}' if abs(float(adjustment)) > 0.0001 else None,
                        )
                        if st.button("芝を公式値に戻す", key=f"reset_cushion_{venue}", use_container_width=True):
                            st.session_state[adj_key] = 0.0
                            st.rerun()
                    else:
                        old = cushion_map.get(venue, "")
                        cv = st.text_input(
                            "芝 クッション値（手動）",
                            value=str(old) if old is not None else "",
                            key=manual_key,
                            placeholder="例 9.3",
                        )
                        try:
                            cushion_map[venue] = float(cv) if str(cv).strip() else None
                        except ValueError:
                            cushion_map[venue] = None
                            st.warning("クッション値は数値で入力してください。")
                else:
                    cushion_map[venue] = None

                if (vraces["芝・ダ"] == "ダ").any():
                    opts = ["未指定", "良", "稍重", "重", "不良"]
                    official_going = official.get("dirt_going")
                    going_key = f"going_{venue}"
                    init_key = f"going_initialized_{venue}"

                    # 初回だけJRA公式値を採用。その後はユーザーの手動変更を維持する。
                    if not st.session_state.get(init_key, False):
                        initial = official_going or going_map.get(venue) or "未指定"
                        st.session_state[going_key] = initial if initial in opts else "未指定"
                        st.session_state[init_key] = True

                    gv = st.selectbox(
                        "ダート 馬場状態（分析使用）",
                        opts,
                        key=going_key,
                    )
                    going_map[venue] = None if gv == "未指定" else gv

                    if official_going and gv != official_going:
                        st.caption(f"手動補正中：JRA公式 {official_going} → 分析 {gv}")

                    if st.button("ダートを公式値に戻す", key=f"reset_going_{venue}", use_container_width=True):
                        if official_going in opts:
                            st.session_state[going_key] = official_going
                            going_map[venue] = official_going
                        st.rerun()
                else:
                    going_map[venue] = None

    if not jra_conditions and jra_errors:
        with st.expander("JRA自動取得エラー", expanded=False):
            st.caption("自動取得に失敗しても、従来どおり手動入力で分析できます。")
            for err in jra_errors:
                st.code(err)

    st.session_state["cushion_by_place"] = cushion_map
    st.session_state["going_by_place"] = going_map

    st.markdown("#### RACE NAVIGATION")
    race_options = []
    race_map = {}
    for _, rr0 in races.iterrows():
        label = f'{rr0["場所"]} {int(rr0["R"])}R  {rr0["芝・ダ"]}{int(rr0["距離"])}m'
        race_options.append(label)
        race_map[label] = rr0

    if not race_options:
        st.error("分析できるレースが調教判定表に見つかりません。")
        st.stop()

    selected_race = st.selectbox(
        "分析するレース",
        race_options,
        key="race_navigation",
        label_visibility="collapsed",
    )
    rr = race_map[selected_race]
    place = str(rr["場所"])
    race_no = int(rr["R"])
    distance = int(rr["距離"])
    surface = "芝" if normalize_surface(rr["芝・ダ"]) == "芝" else "ダート"
    cushion = cushion_map.get(place) if surface == "芝" else None
    going = going_map.get(place) if surface == "ダート" else None
    sex = None
else:
    input_mode = "手入力"
    cushion_map, going_map = {}, {}
    surface = st.radio("馬場", ["芝", "ダート"], horizontal=True)
    place = st.selectbox("競馬場", ["札幌","函館","福島","新潟","東京","中山","中京","京都","阪神","小倉"])
    race_no = None
    course_tmp = course_df.copy(); surface_code = "芝" if surface == "芝" else "ダ"
    course_tmp = course_tmp[course_tmp["芝・ダ"].astype(str).str.strip() == surface_code]
    course_tmp = course_tmp[course_tmp["場所"].astype(str).str.strip() == place]
    distance_options = sorted(pd.to_numeric(course_tmp["距離"], errors="coerce").dropna().astype(int).unique())
    distance = st.selectbox("距離", distance_options)
    sex = None
    going = st.selectbox("馬場状態", ["未指定","良","稍重","重","不良"])
    going = None if going == "未指定" else going
    cushion = None
    if surface == "芝":
        ct = st.text_input("当日クッション値", value="")
        try: cushion = float(ct) if ct.strip() else None
        except ValueError: st.warning("クッション値は数値で入力してください。")

race_df = data["turf"] if surface == "芝" else data["dirt"]
lucky_df = data["turf_lucky"] if surface == "芝" else data["dirt_lucky"]
analyzer = SireAnalyzer(race_df=race_df, course_df=course_df, lucky_df=lucky_df)

# Ver6.1: prevent stale analysis results after race-condition changes.
current_condition_signature = (
    surface,
    place,
    int(distance) if distance is not None else None,
    race_no if "race_no" in globals() else None,
    None if cushion is None else round(float(cushion), 3),
    going,
    sex,
)

# =====================================================
# RACE NAVIGATION直下：注目レース一覧
# =====================================================

if training_df is not None:
    st.subheader("🏆 注目レース")

    st.caption("S評価の馬がいるレースのみを表示しています。ZIは能力・相手候補の独立軸です。")

    target_place_list = active_places if "active_places" in locals() else []

    with st.spinner("注目レースを分析中です..."):
        # 芝・ダートを分離したまま両方を走査し、開催全体のS評価レースを集約
        summaries = []
        for summary_surface in ["芝", "ダート"]:
            summary_analyzer = SireAnalyzer(
                race_df=data["turf"] if summary_surface == "芝" else data["dirt"],
                course_df=course_df,
                lucky_df=data["turf_lucky"] if summary_surface == "芝" else data["dirt_lucky"],
            )
            part = create_top_race_summary_by_full_analysis(
                training_df=training_df, analyzer=summary_analyzer, surface=summary_surface,
                place_list=target_place_list, cushion_map=cushion_map, going_map=going_map,
            )
            if len(part) > 0:
                summaries.append(part)
        top_summary_df = pd.concat(summaries, ignore_index=True) if summaries else pd.DataFrame()

    if len(top_summary_df) > 0:
        race_pairs = list(top_summary_df[["場所", "R"]].drop_duplicates().itertuples(index=False, name=None))
        odds_requests = build_odds_requests(training_df, race_pairs)
        odds_cache = dict(st.session_state.get("jra_win_odds_cache", {}))
        request_keys = {f'{r["date"]}_{r["place"]}_{r["race_no"]}' for r in odds_requests}
        missing_requests = [r for r in odds_requests if f'{r["date"]}_{r["place"]}_{r["race_no"]}' not in odds_cache]

        # 初回だけ注目レースの単勝を自動取得。以後はボタン操作時だけ更新する。
        if missing_requests:
            with st.spinner("JRA単勝オッズを取得中です..."):
                new_odds, odds_errors = fetch_jra_win_odds_batch(missing_requests)
            odds_cache.update(new_odds)
            st.session_state["jra_win_odds_cache"] = odds_cache
            if odds_errors:
                st.session_state["jra_win_odds_errors"] = odds_errors

        odds_col, odds_note_col = st.columns([1, 3], vertical_alignment="center")
        with odds_col:
            if st.button("🔄 オッズ再取得", key="refresh_top_odds", use_container_width=True):
                with st.spinner("JRA単勝オッズを更新中です..."):
                    refreshed, odds_errors = fetch_jra_win_odds_batch(odds_requests)
                odds_cache.update(refreshed)
                st.session_state["jra_win_odds_cache"] = odds_cache
                st.session_state["jra_win_odds_errors"] = odds_errors
                st.rerun()
        with odds_note_col:
            st.caption("単勝オッズはJRA公式から取得。★は最終スコア＋現在オッズが妙味条件に入った時だけ表示します。")

        top_summary_df = merge_odds_into_result_df(top_summary_df, training_df)
        st.dataframe(
            top_summary_df,
            use_container_width=True,
            hide_index=True,
        )
        odds_errors = st.session_state.get("jra_win_odds_errors", [])
        if odds_errors:
            with st.expander("JRAオッズ取得メモ", expanded=False):
                st.caption("発売前は単勝オッズが「-」になります。取得失敗時も分析自体は継続します。")
                for err in odds_errors[-20:]:
                    st.code(err)
    else:
        st.info(
            "最終評価Sの注目レースは見つかりませんでした。"
        )
# =====================================================
# 出走馬データ作成
# =====================================================

horses = []

if input_mode == "調教判定表から自動取得":
    st.subheader("出馬表入力")
    st.info("調教判定表から自動取得します。出馬表の貼り付けは不要です。")

    if place == "すべて":
        st.warning("自動取得モードでは競馬場を指定してください。")

    elif training_df is None:
        st.warning("調教判定表が読み込まれていません。")

    else:
        horses = create_horses_from_training_df(
            training_df=training_df,
            place=place,
            race_no=race_no,
            surface=surface,
            distance=distance,
        )

        if len(horses) > 0:
            st.success(
                f"{len(horses)}頭を調教判定表から読み込みました。"
            )

            preview_df = make_preview_df_from_horses(horses)

            st.dataframe(
                preview_df,
                use_container_width=True,
                hide_index=True,
            )

        else:
            st.warning(
                "指定条件に一致する出走馬が調教判定表に見つかりません。"
            )


else:
    st.subheader("出馬表入力")

    st.caption(
        "手入力では父だけ必須です。馬名・性別・枠番・馬番は未入力でも分析できます。"
    )

    race_text = st.text_area(
        "出馬表",
        height=320,
        placeholder=(
            "父\n"
            "ハービンジャー\n"
            "キズナ\n"
            "ドゥラメンテ"
        ),
    )

    if race_text.strip():
        try:
            horses, horse_df = parse_horses_from_manual_text(race_text)

            st.success(
                f"{len(horses)}頭読み込みました。"
            )

            preview_df = make_preview_df_from_horses(horses)

            st.dataframe(
                preview_df,
                use_container_width=True,
                hide_index=True,
            )

        except Exception as e:
            st.error(str(e))
            st.stop()

    else:
        st.info("出馬表を貼り付けてください。")


# =====================================================
# 分析開始
# =====================================================

run = st.button(
    "🔍 分析開始",
    use_container_width=True,
)


# =====================================================
# 第4ブロック
# 分析実行
# =====================================================

if run:
    if len(horses) == 0:
        if input_mode == "調教判定表から自動取得":
            st.warning("出走馬データがありません。競馬場・レース番号・距離・調教判定表を確認してください。")
        else:
            st.warning("出走馬データがありません。手入力欄に少なくとも父を入力してください。")
        st.stop()

    results = []

    progress_text = st.empty()

    for i, horse in enumerate(horses):
        progress_text.caption(f"分析中… {i + 1}/{len(horses)}頭")
        surface_code = "芝" if surface == "芝" else "ダ"

        if place == "すべて":
            course_id = None
        else:
            course_id = f"{place}{surface_code}{int(distance)}"

        result = analyzer.analyze_all(
            horse_name=horse["horse_name"],
            sire_name=horse["sire"],
            sex=horse["sex"],
            frame=horse["frame"],
            horse_no=horse["horse_no"],
            place=place,
            distance=distance,
            course_id=course_id,
            cushion=cushion,
            going=going,
        )

        if result is not None:
            result = apply_live_cushion_override(
                result=result,
                race_df=analyzer.race_df,
                cushion=cushion,
                target_surface=surface,
            )
            results.append(result)
        else:
            st.warning(
                f'{horse["horse_name"]} の分析結果が作成できませんでした。'
            )

    progress_text.empty()

    st.session_state["results"] = results
    st.session_state["analysis_condition_signature"] = current_condition_signature

    st.success("分析が完了しました。")


# =====================================================
# 第5ブロック
# 結果一覧作成
# =====================================================

# Ver6.1: 条件変更後に前回結果を残さない
if (
    "results" in st.session_state
    and st.session_state.get("analysis_condition_signature") is not None
    and st.session_state.get("analysis_condition_signature") != current_condition_signature
):
    st.session_state.pop("results", None)

if "results" in st.session_state:
    st.subheader("分析結果")

    results = st.session_state["results"]

    results = [
        r for r in results
        if r is not None
    ]

    if len(results) == 0:
        st.warning("分析結果が空です。条件または入力データを確認してください。")
        st.stop()

    result_df = pd.DataFrame()

    # -----------------------------
    # 基本情報
    # -----------------------------

    result_df["馬番"] = [
        "-"
        if r.get("horse_no") is None
        else int(r.get("horse_no"))
        for r in results
    ]

    result_df["馬名"] = [
        r["horse_name"]
        for r in results
    ]

    result_df["父"] = [
        r["sire"]
        for r in results
    ]

    # -----------------------------
    # 父馬適性
    # -----------------------------

    result_df["競馬場×距離"] = [
        r["father"]["course_distance"]["grade"]
        for r in results
    ]

    result_df["枠適性"] = [
        safe_get_grade(r["father"].get("frame"))
        for r in results
    ]

    result_df["馬番適性"] = [
        safe_get_grade(r["father"].get("horse_no"))
        for r in results
    ]

    result_df["左右"] = [
        safe_get_grade(r["father"].get("right_left"))
        for r in results
    ]

    result_df["坂"] = [
        safe_get_grade(r["father"].get("slope"))
        for r in results
    ]

    result_df["距離区分"] = [
        safe_get_grade(r["father"].get("distance_type"))
        for r in results
    ]

    result_df["コーナー"] = [
        safe_get_grade(r["father"].get("corner_count"))
        for r in results
    ]

    result_df["適性効果"] = [
        r.get("aptitude_effect", {}).get("display", "±0.0pt（100）")
        for r in results
    ]

    result_df["好転条件"] = [
        "-"
        if r["father"].get("core_distance") is None
        else r["father"]["core_distance"].get("label", "-")
        for r in results
    ]

    # -----------------------------
    # 調教判定表との連携
    # -----------------------------

    training_df = None

    if "training_df" in st.session_state:
        training_df = st.session_state["training_df"]

    training_records = []

    for r in results:
        course_id = None

        if r.get("course") is not None:
            course_id = r["course"].get("コースID")

        if course_id is None:
            surface_code = "芝" if surface == "芝" else "ダ"

            if place != "すべて":
                course_id = f"{place}{surface_code}{int(distance)}"

        record = get_training_record(
            training_df=training_df,
            horse_name=r["horse_name"],
            course_id=course_id,
            race_no=race_no if "race_no" in globals() else None,
        )

        training_records.append(record)

    result_df["調教師"] = [
        "-" if record is None else record.get("調教師", "-")
        for record in training_records
    ]

    result_df["騎手"] = [
        "-" if record is None else record.get("騎手", "-")
        for record in training_records
    ]

    result_df["調教本命"] = [
        "-"
        if record is None
        else record.get("調教本命", "-")
        for record in training_records
    ]

    result_df["調教相手"] = [
        "-"
        if record is None
        else record.get("調教相手", "-")
        for record in training_records
    ]

    result_df["調教師判定"] = [
        "-"
        if record is None
        else record.get("調教師判定", "-")
        for record in training_records
    ]

    result_df["A3高勝率Lap"] = [
        "-"
        if record is None
        else format_a3_high_win_lap(record.get("A3高勝率Lap", "-"))
        for record in training_records
    ]

    result_df["調教コース判定"] = [
        "-"
        if record is None
        else record.get("調教コース判定", "-")
        for record in training_records
    ]

    result_df["地雷ラップ判定"] = [
        "-"
        if record is None
        else record.get("地雷ラップ判定", "-")
        for record in training_records
    ]

    result_df["ZI"] = [
        "-"
        if record is None
        else record.get("ZI", "-")
        for record in training_records
    ]

    result_df = add_zi_partner_columns(result_df)

    result_df["脚質"] = [
        "-"
        if record is None
        else record.get("脚質", "-")
        for record in training_records
    ]

    # -----------------------------
    # コースバイアス
    # -----------------------------

    result_df["枠バイアス"] = [
        safe_get_grade(r["bias"].get("frame"))
        for r in results
    ]

    result_df["Lucky"] = [
        "-"
        if r["bias"].get("lucky") is None
        else r["bias"].get("lucky")
        for r in results
    ]

    # -----------------------------
    # 芝・ダート専用項目
    # -----------------------------

    if surface == "芝":
        result_df["当日クッション値"] = [
            "-" if cushion is None else float(cushion)
            for _ in results
        ]
        result_df["父馬クッション適性"] = [
            safe_get_grade(r["father"].get("cushion")) for r in results
        ]
        result_df["クッション幅"] = [
            "-" if not r["father"].get("cushion") or r["father"]["cushion"].get("width") is None
            else f"±{float(r['father']['cushion'].get('width')):.1f}"
            for r in results
        ]
        result_df["クッション母数"] = [
            int((r["father"].get("cushion") or {}).get("stats", {}).get("sample", 0) or 0)
            for r in results
        ]
        result_df["クッション信頼度"] = [
            (r["father"].get("cushion") or {}).get("confidence_label", "評価不可")
            for r in results
        ]
        result_df["クッション判定範囲"] = [
            (r["father"].get("cushion") or {}).get("stats", {}).get("selected_scope", "-")
            for r in results
        ]
        result_df["クッション方式"] = [
            (r["father"].get("cushion") or {}).get("method", "実数±幅方式")
            for r in results
        ]
        result_df["本人クッション"] = [r.get("own_cushion", {}).get("judgement", "評価なし") for r in results]
        result_df["本人クッション母数"] = [r.get("own_cushion", {}).get("sample", 0) for r in results]
        result_df["本人クッション幅"] = [
            "-" if r.get("own_cushion", {}).get("width") is None
            else f"±{float(r.get('own_cushion', {}).get('width')):.1f}"
            for r in results
        ]
    else:
        result_df["馬場状態"] = [safe_get_grade(r["father"].get("going")) for r in results]

    # -----------------------------
    # 適性一致数・不安材料数
    # -----------------------------

    result_df["適性一致数"] = result_df.apply(
        count_effective_good_grades,
        axis=1,
    )

    result_df["不安材料数"] = result_df.apply(
        count_effective_bad_grades,
        axis=1,
    )

    # -----------------------------
    # 最終判定
    # -----------------------------

    final_grades = []
    final_scores = []
    final_reasons = []
    jirai_memos = []

    for idx, row in result_df.iterrows():
        r = results[idx]
        rec = training_records[idx] if idx < len(training_records) else None
        vr = final_rating.calculate(r, rec, surface)
        final_grades.append(vr["grade"])
        final_scores.append(vr["score"])
        final_reasons.append(vr["reason"])
        jirai_memos.append("地雷ラップ：強制降格" if vr["grade"] == "降格" else "-")

    result_df["最終評価"] = final_grades
    result_df["最終スコア"] = final_scores
    result_df["表面確認"] = [normalize_surface_label(surface) for _ in final_scores]

    # Ver7.2: 選択レースの単勝オッズがまだなければ初回だけ取得。
    selected_date = _race_date_from_training(training_df, place, race_no) if training_df is not None and race_no is not None else None
    selected_key = f"{selected_date}_{place}_{race_no}" if selected_date and race_no is not None else None
    odds_cache = dict(st.session_state.get("jra_win_odds_cache", {}))
    if selected_key and selected_key not in odds_cache:
        reqs = build_odds_requests(training_df, [(place, race_no)])
        if reqs:
            with st.spinner("選択レースのJRA単勝オッズを取得中です..."):
                fetched, odds_errors = fetch_jra_win_odds_batch(reqs)
            odds_cache.update(fetched)
            st.session_state["jra_win_odds_cache"] = odds_cache
            if odds_errors:
                st.session_state["jra_win_odds_errors"] = odds_errors

    current_odds = []
    current_pop = []
    actual_stars = []
    actual_judgements = []
    for horse_no, score in zip(result_df.get("馬番", [None] * len(result_df)), final_scores):
        odds, pop = get_cached_win_odds(training_df, place, race_no, horse_no) if training_df is not None and race_no is not None else (None, None)
        current_odds.append("-" if odds is None else round(float(odds), 1))
        current_pop.append("-" if pop is None else int(pop))
        actual_stars.append(value_star_with_odds(surface, score, odds))
        actual_judgements.append(value_judgement_with_odds(surface, score, odds))

    result_df["単勝オッズ"] = current_odds
    result_df["人気"] = current_pop
    result_df["★"] = actual_stars
    result_df["妙味条件"] = actual_judgements
    result_df["評価理由"] = final_reasons

    # -----------------------------
    # Ver6.9: 前日坂路時計（調教判定表の表示値をそのまま参照）
    # 評価・最終スコアには使用しない。
    # -----------------------------
    result_df["前日坂路時計"] = [
        "-"
        if rec is None
        else (
            "-"
            if pd.isna(rec.get("前日坂路時計", None))
            or str(rec.get("前日坂路時計", "")).strip() in {"", "nan", "None"}
            else rec.get("前日坂路時計")
        )
        for rec in training_records
    ]

    # -----------------------------
    # Ver6.8: 騎手参考情報（最終スコアには加減点しない）
    # -----------------------------
    result_df["騎手条件"] = [
        jockey_reference.evaluate_jockey_condition(
            place=place,
            surface=surface,
            distance=distance,
            jockey=("-" if rec is None else rec.get("騎手", "-")),
        )
        for rec in training_records
    ]

    result_df["父×騎手相性"] = [
        jockey_reference.evaluate_sire_jockey(
            surface=surface,
            sire=r.get("sire", ""),
            jockey=("-" if rec is None else rec.get("騎手", "-")),
        )
        for r, rec in zip(results, training_records)
    ]

    result_df["地雷補正"] = jirai_memos

    # Ver6.3: 予想履歴・検証機能は廃止

    # Ver6.1: 旧評価列は画面から除外
    result_df = result_df.drop(
        columns=[
            "旧最終判定", "統計評価", "StatScore", "推奨度",
            "クッション母数", "クッション信頼度",
            "クッション判定範囲", "クッション方式",
        ],
        errors="ignore",
    )

    # -----------------------------
    # Ver6: S/A/B/C/降格 → 同ランク内は最終スコア順
    # -----------------------------
    rank_order = {"S":0, "A":1, "B":2, "C":3, "降格":4}
    result_df["_評価順"] = result_df["最終評価"].map(rank_order).fillna(9)
    result_df = result_df.sort_values(
        ["_評価順", "最終スコア"], ascending=[True, False]
    ).drop(columns=["_評価順"]).reset_index(drop=True)

    # -----------------------------
    # 順位
    # -----------------------------

    result_df.insert(
        0,
        "順位",
        range(1, len(result_df) + 1),
    )

    # -----------------------------
    # 馬番を最左列へ移動
    # -----------------------------

    if "馬番" in result_df.columns:
        result_df.insert(
            0,
            "馬番",
            result_df.pop("馬番"),
        )

    # -----------------------------
    # 主要列を前方へ移動
    # -----------------------------

    front_columns = [
        "馬番",
        "順位",
        "馬名",
        "調教師",
        "騎手",
        "最終評価",
        "最終スコア",
        "単勝オッズ",
        "人気",
        "★",
        "ZI",
        "ZI順位",
        "ZI差",
        "ZI相手判定",
        "妙味条件",
        "評価理由",
        "前日坂路時計",
        "調教本命",
        "調教相手",
        "調教師判定",
        "A3高勝率Lap",
        "地雷ラップ判定",
        "枠バイアス",
        "Lucky",
        "適性効果",
        "父",
        "騎手条件",
        "父×騎手相性",
        "地雷補正",
        "当日クッション値",
        "父馬クッション適性",
        "クッション幅",
        "本人クッション",
        "本人クッション母数",
        "本人クッション幅",
        "馬場状態",
        "調教コース判定",
        "脚質",
    ]

    front_columns = [
        col for col in front_columns
        if col in result_df.columns
    ]

    other_columns = [
        col for col in result_df.columns
        if col not in front_columns
    ]

    result_df = result_df[front_columns + other_columns]

    # =================================================
    # カラー表示
    # =================================================

    def color_grade(val):
        if val == "◎":
            return "background-color:#4CAF50;color:white;font-weight:bold"
        elif val == "○":
            return "background-color:#2196F3;color:white;font-weight:bold"
        elif val == "△":
            return "background-color:#FF9800;color:white;font-weight:bold"
        elif val == "×":
            return "background-color:#F44336;color:white;font-weight:bold"
        elif val == "★":
            return "background-color:#FFD700;color:black;font-weight:bold"

        return ""

    def color_total(val):
        try:
            if val >= 4.0:
                return "background-color:#FFD700;font-weight:bold"
            elif val >= 2.5:
                return "background-color:#FFF59D"
            elif val >= 1.0:
                return "background-color:#E8F5E9"
        except Exception:
            pass

        return ""

    def color_recommend(val):
        if val == "★★★★★":
            return "background-color:#FFD700;font-weight:bold"
        elif val == "★★★★☆":
            return "background-color:#FFF59D;font-weight:bold"
        elif val == "★★★☆☆":
            return "background-color:#E8F5E9"

        return ""

    def color_final_judgement(val):
        if val == "本命継続":
            return "background-color:#FFD700;color:black;font-weight:bold"
        elif val == "本命注意":
            return "background-color:#FF9800;color:white;font-weight:bold"
        elif val == "相手昇格":
            return "background-color:#2196F3;color:white;font-weight:bold"
        elif val == "相手候補":
            return "background-color:#E8F5E9;color:black"
        elif val == "穴候補":
            return "background-color:#9C27B0;color:white;font-weight:bold"
        elif val == "様子見":
            return "background-color:#EEEEEE;color:black"
        elif val == "評価下げ":
            return "background-color:#F44336;color:white;font-weight:bold"

        return ""

    def color_final_grade(val):
        if val == "S":
            return "background-color:#FFD700;color:black;font-weight:bold"
        if val == "A":
            return "background-color:#4CAF50;color:white;font-weight:bold"
        if val == "B":
            return "background-color:#2196F3;color:white;font-weight:bold"
        if val == "C":
            return "background-color:#EEEEEE;color:black"
        if val == "降格":
            return "background-color:#F44336;color:white;font-weight:bold"
        return ""

    def color_jirai(val):
        if has_jirai_lap(val):
            return "background-color:#F44336;color:white;font-weight:bold"

        return ""

    def color_positive_mark(val):
        if is_positive_mark(val):
            return "background-color:#E8F5E9;font-weight:bold"

        return ""

    style_obj = result_df.style

    grade_cols = [
        "競馬場×距離",
        "左右",
        "坂",
        "コーナー",
        "枠適性",
        "馬番適性",
        "距離区分",
        "枠バイアス",
        "Lucky",
        "父馬クッション適性",
        "馬場状態",
        "騎手条件",
        "父×騎手相性",
    ]

    grade_cols = [
        col for col in grade_cols
        if col in result_df.columns
    ]

    if len(grade_cols) > 0:
        style_obj = style_obj.map(
            color_grade,
            subset=grade_cols,
        )

    if "最終評価" in result_df.columns:
        style_obj = style_obj.map(color_final_grade, subset=["最終評価"])

    if "★" in result_df.columns:
        style_obj = style_obj.map(color_score_star, subset=["★"])

    if "妙味条件" in result_df.columns:
        style_obj = style_obj.map(color_value_condition, subset=["妙味条件"])

    jirai_cols = [
        col for col in ["地雷ラップ判定", "地雷補正"]
        if col in result_df.columns
    ]

    if len(jirai_cols) > 0:
        style_obj = style_obj.map(
            color_jirai,
            subset=jirai_cols,
        )

    positive_cols = [
        col for col in ["調教本命", "調教相手"]
        if col in result_df.columns
    ]

    if len(positive_cols) > 0:
        style_obj = style_obj.map(
            color_positive_mark,
            subset=positive_cols,
        )

    st.dataframe(
        style_obj,
        use_container_width=True,
        hide_index=True,
    )

# =====================================================
# Ver7.1 最下部：データ読み込み / 判定表使用設定
# =====================================================

with st.container(border=True):
    data_title_col, data_check_col = st.columns([2.2, 1.8], vertical_alignment="center")
    with data_title_col:
        st.markdown("### 🗄️ データ読み込み")
    with data_check_col:
        st.checkbox(
            "調教判定CSV / Excelを使用する",
            key="use_training_data",
            help="オフにすると、dataフォルダの調教判定CSVを使用せず、手入力モードで分析します。",
        )

    if training_load_status:
        with st.expander("調教判定データの読み込み状態", expanded=False):
            for status_kind, status_message in training_load_status:
                if status_kind == "success":
                    st.success(status_message)
                elif status_kind == "warning":
                    st.warning(status_message)
                else:
                    st.info(status_message)

st.markdown(
    '<div class="rw-footer"><div><strong>Runaway’s</strong> — Race Analysis System &nbsp; Ver7.1</div>'
    '<div class="gold">Analyze &nbsp; Find the Odds &nbsp; Run to the Future</div></div>',
    unsafe_allow_html=True,
)
