"""
=========================================
Sire Analyzer Ver2
course.py
-----------------------------------------
コース情報取得
=========================================
"""


def get_course_info(course_df, course_id):
    """
    コースIDからコース情報を取得
    """

    row = course_df[course_df["コースID"] == course_id]

    if row.empty:
        return None

    row = row.iloc[0]

    return row.to_dict()