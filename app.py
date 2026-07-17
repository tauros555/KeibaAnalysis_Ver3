# =====================================================
# app.py Ver5.0
# 調教判定CSV自動取得 + 手入力安全読込 + 注目レース一覧 対応版
# =====================================================

import streamlit as st
import pandas as pd

from io import StringIO
from pathlib import Path

import config

from modules import loader
from modules.analyzer import SireAnalyzer
from modules import result_loader, result_transformer, prediction_history, validation

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODULES_DIR = BASE_DIR / "modules"



# =====================================================
# パス設定
# =====================================================

TRAINING_CSV_PATH = DATA_DIR / "調教判定表.csv"


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

    # 枠番
    if "枠番" not in df.columns and "枠" in df.columns:
        rename_dict["枠"] = "枠番"

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
    1. 調教本命〇 または A3高勝率Lap★ → 本命継続
       ただし、地雷ラップ〇・クッション値×・競馬場×距離×・枠バイアス×の
       いずれかがあれば本命注意
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

    caution_factors = []
    if cushion_grade == "×":
        caution_factors.append("クッション値×")
    if course_distance_grade == "×":
        caution_factors.append("競馬場・距離×")
    if frame_bias_grade == "×":
        caution_factors.append("枠バイアス×")

    # 調教本命〇またはA3高勝率Lap★でも、
    # 地雷ラップまたは指定された×評価があれば本命注意。
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

        result = analyzer.analyze_all(
            horse_name=record.get("馬名", ""),
            sire_name=record.get("父", ""),
            sex=record.get("性別", ""),
            frame=frame,
            horse_no=horse_no,
            course_id=course_id,
            place=place,
            distance=int(distance),
            cushion=cushion,
            going=going,
        )

        if result is None:
            continue

        training_record = record.to_dict()

        row_for_judge = build_judgement_row_from_result(
            result=result,
            training_record=training_record,
            target_surface=target_surface,
        )

        final_judgement, jirai_memo = judge_final_result(row_for_judge)

        if not is_final_judgement_target(final_judgement):
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
                "父": record.get("父", ""),
                "調教本命": record.get("調教本命", "-"),
                "調教相手": record.get("調教相手", "-"),
                "StatScore": row_for_judge["StatScore"],
                "適性一致数": row_for_judge["適性一致数"],
                "不安材料数": row_for_judge["不安材料数"],
                "最終判定": final_judgement,
                "地雷補正": jirai_memo,
                "ZI": record.get("ZI", "-"),
                "脚質": record.get("脚質", "-"),
            }
        )

    if len(rows) == 0:
        return pd.DataFrame()

    result_df = pd.DataFrame(rows)

    result_df = result_df.sort_values(
        ["場所", "R", "StatScore"],
        ascending=[True, True, False],
    ).reset_index(drop=True)

    return result_df

# =====================================================
# ページ設定
# =====================================================

st.set_page_config(
    page_title="競馬分析アプリ Ver5",
    layout="wide",
)

st.title("🏇 競馬分析アプリ Ver5")


# =====================================================
# データ読込
# =====================================================

data = loader.load_data()

course_df = data["course"]


# =====================================================
# 調教判定表読み込み
# =====================================================

st.subheader("調教判定表")

training_df = None

use_training_data = st.checkbox(
    "調教判定CSV / Excelを使用する",
    value=True,
    help="オフにすると、CSVがdataフォルダにあっても読み込まず、手入力だけで分析できます。",
)

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

        st.success(
            f"調教判定表CSVを読み込みました：{TRAINING_CSV_PATH}"
        )

    else:
        st.info(
            f"事前配置CSVが見つかりません：{TRAINING_CSV_PATH}"
        )

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

                st.success(
                    f"調教判定表を読み込みました。読み込みシート：{actual_sheet_name}"
                )

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
        st.success("調教判定に必要な列を確認できました。")


# =====================================================
# 第2ブロック
# 分析条件入力
# =====================================================

surface = st.radio(
    "馬場",
    ["芝", "ダート"],
    horizontal=True,
)

if surface == "芝":
    race_df = data["turf"]
    lucky_df = data["turf_lucky"]
else:
    race_df = data["dirt"]
    lucky_df = data["dirt_lucky"]

analyzer = SireAnalyzer(
    race_df=race_df,
    course_df=course_df,
    lucky_df=lucky_df,
)

# =====================================================
# 出走馬入力方式
# =====================================================

if training_df is not None:
    input_mode = st.radio(
        "出走馬の入力方式",
        [
            "調教判定表から自動取得",
            "手入力",
        ],
        horizontal=True,
    )
else:
    input_mode = "手入力"
    st.info(
        "調教判定表を使用しないため、出走馬の入力方式は手入力になります。"
    )

st.subheader("レース条件")

col1, col2, col3 = st.columns(3)

with col1:
    place = st.selectbox(
        "競馬場",
        [
            "すべて",
            "札幌",
            "函館",
            "福島",
            "新潟",
            "東京",
            "中山",
            "中京",
            "京都",
            "阪神",
            "小倉",
        ],
    )

with col2:
    course_tmp = course_df.copy()

    course_tmp.columns = [
        str(col).strip()
        for col in course_tmp.columns
    ]

    surface_code = "芝" if surface == "芝" else "ダ"

    if "芝・ダ" in course_tmp.columns:
        course_tmp = course_tmp[
            course_tmp["芝・ダ"].astype(str).str.strip() == surface_code
        ]

    if place != "すべて":
        course_tmp = course_tmp[
            course_tmp["場所"].astype(str).str.strip() == place
        ]

    distance_options = sorted(
        pd.to_numeric(
            course_tmp["距離"],
            errors="coerce",
        ).dropna().astype(int).unique()
    )

    if len(distance_options) == 0:
        st.warning("選択条件に一致する距離がありません。")
        st.stop()

    distance = st.selectbox(
        "距離",
        distance_options,
    )

with col3:
    if input_mode == "調教判定表から自動取得":
        race_no = st.selectbox(
            "レース番号",
            list(range(1, 13)),
        )
    else:
        race_no = None
        st.info(
            "手入力モードではレース番号は不要です。"
        )


sex = st.selectbox(
    "対象性別",
    [
        "すべて",
        "牡",
        "牝",
        "せん",
    ],
)

if sex == "すべて":
    sex = None


going = st.selectbox(
    "馬場状態",
    [
        "未指定",
        "良",
        "稍重",
        "重",
        "不良",
    ],
)

if going == "未指定":
    going = None


cushion = None

if surface == "芝":
    cushion = st.selectbox(
        "クッション値",
        [
            "未指定",
            "8未満",
            "8.0～8.5",
            "8.6～9.0",
            "9.1～9.5",
            "9.6～10.0",
            "10.1～10.5",
            "10.6～11.0",
            "11.1～11.5",
            "11.6以上",
        ],
    )

    if cushion == "未指定":
        cushion = None




# =====================================================
# トップページ：相手候補以上レース一覧
# =====================================================

if training_df is not None:
    st.subheader("本日の注目レース")

    st.caption(
        "調教判定で本命または相手の馬だけを対象に、血統・適性・バイアスまで分析し、相手候補以上の馬がいるレースを表示します。"
    )

    show_top_summary = st.checkbox(
        "注目レース一覧を表示する",
        value=True,
    )

    if show_top_summary:
        target_place_list = st.multiselect(
            "注目レース表示対象の競馬場",
            [
                "札幌",
                "函館",
                "福島",
                "新潟",
                "東京",
                "中山",
                "中京",
                "京都",
                "阪神",
                "小倉",
            ],
            default=[],
            help="未選択の場合は全競馬場を対象にします。",
        )

        with st.spinner("注目レースを分析中です..."):
            top_summary_df = create_top_race_summary_by_full_analysis(
                training_df=training_df,
                analyzer=analyzer,
                surface=surface,
                place_list=target_place_list,
                cushion=cushion,
                going=going,
            )

        if len(top_summary_df) > 0:
            st.dataframe(
                top_summary_df,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info(
                "相手候補以上の馬がいるレースは見つかりませんでした。"
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

    progress = st.progress(0)

    for i, horse in enumerate(horses):
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
            results.append(result)
        else:
            st.warning(
                f'{horse["horse_name"]} の分析結果が作成できませんでした。'
            )

        progress.progress((i + 1) / len(horses))

    progress.empty()

    st.session_state["results"] = results

    st.success("分析が完了しました。")


# =====================================================
# 第5ブロック
# 結果一覧作成
# =====================================================

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

    result_df["統計評価"] = [
        r["grade"]
        for r in results
    ]

    result_df["StatScore"] = [
        r["total_score"]
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
        result_df["クッション"] = [
            safe_get_grade(r["father"].get("cushion"))
            for r in results
        ]
    else:
        result_df["馬場状態"] = [
            safe_get_grade(r["father"].get("going"))
            for r in results
        ]

    # -----------------------------
    # Ver5: analyzerの連続StatScoreを使用
    # -----------------------------
    result_df["StatScore"] = pd.to_numeric(result_df["StatScore"], errors="coerce").fillna(0).round(3)

    # -----------------------------
    # 推奨度
    # -----------------------------

    recommend = []

    for score in result_df["StatScore"]:
        if score >= 4.0:
            recommend.append("★★★★★")
        elif score >= 2.5:
            recommend.append("★★★★☆")
        elif score >= 1.0:
            recommend.append("★★★☆☆")
        elif score >= 0.0:
            recommend.append("★★☆☆☆")
        else:
            recommend.append("★☆☆☆☆")

    result_df["推奨度"] = recommend

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

    final_results = []
    jirai_memos = []

    for _, row in result_df.iterrows():
        final_judgement, jirai_memo = judge_final_result(row)

        final_results.append(final_judgement)
        jirai_memos.append(jirai_memo)

    result_df["最終判定"] = final_results
    result_df["地雷補正"] = jirai_memos

    # -----------------------------
    # Ver5: 予想履歴を自動保存
    # -----------------------------
    history_df = result_df.copy()
    history_df["場所"] = place
    history_df["R"] = race_no if "race_no" in globals() else ""
    history_df["芝・ダ"] = surface
    history_df["距離"] = distance
    history_df["レースID"] = [
        "" if rec is None else rec.get("レースID", "") for rec in training_records
    ]
    history_df["血統登録番号"] = [
        "" if rec is None else rec.get("血統登録番号", "") for rec in training_records
    ]
    history_df["年月日"] = [
        "" if rec is None else rec.get("年月日", "") for rec in training_records
    ]
    if history_df["レースID"].astype(str).str.strip().ne("").any():
        try:
            prediction_history.save_predictions(history_df)
        except Exception as history_error:
            st.warning(f"予想履歴の保存に失敗しました: {history_error}")

    # -----------------------------
    # StatScore順ソート
    # -----------------------------

    result_df = result_df.sort_values(
        "StatScore",
        ascending=False,
    ).reset_index(drop=True)

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
        "最終判定",
        "統計評価",
        "調教本命",
        "調教相手",
        "調教師判定",
        "A3高勝率Lap",
        "地雷ラップ判定",
        "枠バイアス",
        "Lucky",
        "StatScore",
        "適性効果",
        "父",
        "推奨度",
        "地雷補正",
        "調教コース判定",
        "ZI",
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
        "統計評価",
        "競馬場×距離",
        "左右",
        "坂",
        "コーナー",
        "枠適性",
        "馬番適性",
        "距離区分",
        "枠バイアス",
        "Lucky",
        "クッション",
        "馬場状態",
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

    if "StatScore" in result_df.columns:
        style_obj = style_obj.map(
            color_total,
            subset=["StatScore"],
        )

    if "推奨度" in result_df.columns:
        style_obj = style_obj.map(
            color_recommend,
            subset=["推奨度"],
        )

    if "最終判定" in result_df.columns:
        style_obj = style_obj.map(
            color_final_judgement,
            subset=["最終判定"],
        )

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
# Ver5 検証機能
# =====================================================
st.divider()
st.header("Ver5 検証")
st.caption("TARGETのヘッダーなし『オッズ成績データA』をそのままアップロードしてください。")
result_upload = st.file_uploader("TARGET結果CSV", type=["csv"], key="ver5_result_upload")
if result_upload is not None:
    try:
        race_result_df = result_loader.load_target_result_csv(result_upload)
        horse_result_df = result_transformer.transform_results(race_result_df)
        prediction_df = prediction_history.load_predictions()
        validation_df = validation.create_validation_history(prediction_df, horse_result_df)
        st.success(f"{len(validation_df)}頭分の検証履歴を更新しました。")
        if not validation_df.empty:
            tab1, tab2, tab3 = st.tabs(["最終判定別", "適性項目別", "検証履歴"])
            with tab1:
                st.dataframe(validation.summarize_by(validation_df, "最終判定"), use_container_width=True, hide_index=True)
            with tab2:
                target_col = st.selectbox("検証項目", [c for c in ["競馬場×距離","左右","坂","コーナー","距離区分","枠適性","馬番適性","クッション","馬場状態","枠バイアス"] if c in validation_df.columns])
                st.dataframe(validation.summarize_by(validation_df, target_col), use_container_width=True, hide_index=True)
            with tab3:
                st.dataframe(validation_df, use_container_width=True, hide_index=True)
                st.download_button("検証履歴CSVをダウンロード", validation_df.to_csv(index=False).encode("utf-8-sig"), "validation_history.csv", "text/csv")
    except Exception as validation_error:
        st.error(f"結果CSVの検証処理でエラーが発生しました: {validation_error}")
