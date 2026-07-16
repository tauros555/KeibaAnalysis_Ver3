"""
=========================================
Sire Analyzer Ver2
loader.py
-----------------------------------------
CSV読込モジュール
=========================================
"""

from pathlib import Path

import pandas as pd
import streamlit as st

import config


# ==========================================
# CSV読込
# ==========================================

def read_csv(file_path: Path) -> pd.DataFrame:
    """
    CSVをエンコード自動判定で読み込む
    """

    last_error = None

    for enc in config.ENCODINGS:

        try:
            df = pd.read_csv(file_path, encoding=enc)
            df.columns = df.columns.str.strip()
            return df

        except Exception as e:
            last_error = e

    raise Exception(
        f"{file_path.name} を読み込めません。\n{last_error}"
    )


# ==========================================
# 必須列チェック
# ==========================================

def check_columns(df: pd.DataFrame,
                  required_columns: list,
                  csv_name: str):

    missing = []

    for col in required_columns:

        if col not in df.columns:

            missing.append(col)

    if missing:

        st.error(f"{csv_name} に不足列があります。")

        st.write("不足列")

        st.write(missing)

        st.stop()


# ==========================================
# データ整形
# ==========================================

def clean_dataframe(df: pd.DataFrame):

    numeric_columns = [

        config.COL_DISTANCE,

        config.COL_FINISH,

        config.COL_FRAME,

        config.COL_HORSE_NO,
        getattr(config, "COL_CORNER_COUNT", "コーナー回数")

    ]

    for col in numeric_columns:

        if col in df.columns:

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

    return df


# ==========================================
# コースマスタ結合
# ==========================================

def merge_course(master_df, course_df):

    # マスタ側に既にある列はコースマスタから除外
    drop_cols = [
        config.COL_PLACE,
        config.COL_DISTANCE
    ]

    course = course_df.drop(
        columns=drop_cols,
        errors="ignore"
    )

    return master_df.merge(
        course,
        on=config.COL_COURSE_ID,
        how="left"
    )


# ==========================================
# 全CSV読込
# ==========================================

@st.cache_data(show_spinner=False)

def load_data():

    turf = read_csv(config.TURF_MASTER)

    dirt = read_csv(config.DIRT_MASTER)

    turf_lucky = read_csv(config.TURF_LUCKY)

    dirt_lucky = read_csv(config.DIRT_LUCKY)

    course = read_csv(config.COURSE_MASTER)

    check_columns(

        turf,

        config.REQUIRED_COLUMNS["芝マスタ"],

        "芝マスタ"

    )

    check_columns(

        dirt,

        config.REQUIRED_COLUMNS["ダートマスタ"],

        "ダートマスタ"

    )

    check_columns(

        course,

        config.REQUIRED_COLUMNS["コースマスタ"],

        "コースマスタ"

    )

    turf = clean_dataframe(turf)

    dirt = clean_dataframe(dirt)

    turf = merge_course(

        turf,

        course

    )

    dirt = merge_course(

        dirt,

        course

    )

    return {

        "turf": turf,

        "dirt": dirt,

        "course": course,

        "turf_lucky": turf_lucky,

        "dirt_lucky": dirt_lucky

    }