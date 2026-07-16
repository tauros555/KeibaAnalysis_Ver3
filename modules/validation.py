"""Join predictions and results and produce validation summaries."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import config


def create_validation_history(predictions: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    if predictions.empty or results.empty: return pd.DataFrame()
    p = predictions.copy(); r = results.copy()
    p["レースID"] = p["レースID"].astype(str).str.strip()
    r["レースID"] = r["レースID"].astype(str).str.strip()
    p["馬番"] = pd.to_numeric(p["馬番"], errors="coerce").astype("Int64")
    r["馬番"] = pd.to_numeric(r["馬番"], errors="coerce").astype("Int64")
    merged = p.merge(r, on=["レースID","馬番"], how="inner", suffixes=("", "_結果"))
    path = Path(config.VALIDATION_HISTORY); path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try: old = pd.read_csv(path, encoding="utf-8-sig")
        except Exception: old = pd.DataFrame()
        merged = pd.concat([old, merged], ignore_index=True, sort=False)
        merged = merged.drop_duplicates(subset=["レースID","馬番"], keep="last")
    merged.to_csv(path, index=False, encoding="utf-8-sig")
    return merged


def summarize_by(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if df.empty or column not in df.columns: return pd.DataFrame()
    work = df[df.get("検証対象", True).astype(str).str.lower().isin(["true","1"])].copy() if "検証対象" in df.columns else df.copy()
    for c in ["勝利","連対","複勝"]:
        work[c] = work[c].astype(str).str.lower().isin(["true","1"])
    work["単勝払戻"] = pd.to_numeric(work.get("単勝払戻",0), errors="coerce").fillna(0)
    work["複勝払戻"] = pd.to_numeric(work.get("複勝払戻",0), errors="coerce").fillna(0)
    rows=[]
    for key,g in work.groupby(column, dropna=False):
        n=len(g)
        rows.append({column:key,"件数":n,"勝率":round(g["勝利"].mean()*100,1),"連対率":round(g["連対"].mean()*100,1),"複勝率":round(g["複勝"].mean()*100,1),"単回収率":round(g["単勝払戻"].sum()/(n*100)*100,1) if n else 0,"複回収率":round(g["複勝払戻"].sum()/(n*100)*100,1) if n else 0})
    return pd.DataFrame(rows).sort_values("件数",ascending=False)
