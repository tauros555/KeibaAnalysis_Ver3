"""Prediction history persistence."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import pandas as pd
import config


def save_predictions(df: pd.DataFrame, path: Path | None = None) -> tuple[int,int]:
    path = Path(path or config.PREDICTION_HISTORY)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = df.copy()
    if new.empty: return 0,0
    new["保存日時"] = datetime.now().isoformat(timespec="seconds")
    for col in ["レースID","馬番"]:
        if col not in new.columns: new[col] = ""
    new["照合キー"] = new["レースID"].astype(str).str.strip() + "_" + new["馬番"].astype(str).str.replace(r"\.0$","",regex=True)
    if path.exists():
        try: old = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
        except Exception: old = pd.DataFrame()
    else: old = pd.DataFrame()
    before = len(old)
    combined = pd.concat([old, new], ignore_index=True, sort=False)
    combined = combined.drop_duplicates(subset=["照合キー"], keep="last")
    combined.to_csv(path, index=False, encoding="utf-8-sig")
    return len(new), len(combined)-before


def load_predictions(path: Path | None = None) -> pd.DataFrame:
    path = Path(path or config.PREDICTION_HISTORY)
    if not path.exists(): return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str)
