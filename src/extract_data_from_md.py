#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, argparse, concurrent.futures, io
from io import StringIO
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import pandas as pd
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from datetime import date
from tqdm import tqdm

# ------------ 关键字 ------------
PATHOGEN_KEYS = ["病原体","病原","病原学","Pathogen"]
ILI_KEYS = ["门急诊","流感样","ILI","门诊"]
SARI_KEYS = ["住院","严重急性","SARI"]

# ------------ 表格读取与选择 ------------
def all_pipe_tables(md: str) -> List[Tuple[int,int,str]]:
    out = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            j = i; buf = []
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                buf.append(lines[j]); j += 1
            if len(buf) >= 2:
                out.append((i, j, "\n".join(buf)))
            i = j
        else:
            i += 1
    return out

def to_dataframe_from_pipe(table_text: str) -> Optional[pd.DataFrame]:
    lines = []
    for ln in table_text.splitlines():
        s = ln.strip()
        if not s: continue
        if s.startswith("|"): s = s[1:]
        if s.endswith("|"): s = s[:-1]
        lines.append(s)
    if len(lines) < 2: return None
    txt = "\n".join(lines)
    try:
        return pd.read_csv(io.StringIO(txt), sep=r"\s*\|\s*", engine="python")
    except Exception:
        return None

def html_tables_from_md(md: str) -> List[pd.DataFrame]:
    soup = BeautifulSoup(md, "lxml")
    dfs = []
    for tbl in soup.find_all("table"):
        try:
            for df in pd.read_html(StringIO(str(tbl))):
                dfs.append(df)
        except Exception:
            continue
    return dfs

def score_table(df: pd.DataFrame) -> int:
    score = 0
    cols = [str(c) for c in df.columns]
    if any(any(k in c for k in PATHOGEN_KEYS) for c in cols): score += 4
    if any(any(k in c for k in ILI_KEYS) for c in cols): score += 3
    if any(any(k in c for k in SARI_KEYS) for c in cols): score += 3
    if df.shape[0] >= 2:
        top0 = " ".join(map(str, df.iloc[0].tolist()))
        top1 = " ".join(map(str, df.iloc[1].tolist()))
        if any(k in top0 for k in PATHOGEN_KEYS) or any(k in top1 for k in PATHOGEN_KEYS): score += 2
        if any(k in top0 for k in ILI_KEYS) or any(k in top1 for k in ILI_KEYS): score += 2
        if any(k in top0 for k in SARI_KEYS) or any(k in top1 for k in SARI_KEYS): score += 2
    score += min(len(df), 10)
    return score

def normalize_two_row_header_flexible(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """两行表头归一化：允许第一行首格为 NaN、第二行首格为'病原体'的情况。"""
    header_lines: List[str] = []
    if df.shape[0] >= 2:
        row0 = [("" if (isinstance(x, float) and pd.isna(x)) else str(x)).strip() for x in df.iloc[0].tolist()]
        row1 = [("" if (isinstance(x, float) and pd.isna(x)) else str(x)).strip() for x in df.iloc[1].tolist()]
        header_lines = [" ".join(row0), " ".join(row1)]
        has_week = any(re.search(r"第?\s*\d{1,2}\s*周", c) for c in row0+row1)
        row1_has_pathogen = bool(row1 and any(k in row1[0] for k in PATHOGEN_KEYS))
        if has_week and (row1_has_pathogen or (row0 and any(k in row0[0] for k in PATHOGEN_KEYS))):
            new_cols = []
            for a,b in zip(row0, row1):
                a1 = re.sub(r"\s+","", a)
                b1 = re.sub(r"\s+","", b)
                if a1 == "" and (("病原" in b1) or ("Pathogen" in b1)):
                    new_cols.append("病原体")
                elif b1 and a1 and b1 != a1:
                    new_cols.append(f"{a1}|{b1}")
                elif a1:
                    new_cols.append(a1)
                else:
                    new_cols.append(b1)
            df2 = df.iloc[2:].reset_index(drop=True).copy()
            df2.columns = new_cols
            return df2, header_lines
    return df, header_lines

def pick_table1(md_text: str) -> Tuple[Optional[pd.DataFrame], List[str]]:
    candidates: List[pd.DataFrame] = []
    m = re.search(r"表\s*[1一I][^\n]*", md_text)
    if m:
        tail = md_text[m.end():]
        blocks = all_pipe_tables(tail)
        if blocks:
            df = to_dataframe_from_pipe(blocks[0][2])
            if df is not None:
                candidates.append(df)
    for _, _, txt in all_pipe_tables(md_text):
        df = to_dataframe_from_pipe(txt)
        if df is not None:
            candidates.append(df)
    for df in html_tables_from_md(md_text):
        candidates.append(df)
    if not candidates:
        return None, []
    best_df = None; best_score = -1
    for df in candidates:
        sc = score_table(df)
        if sc > best_score:
            best_df, best_score = df, sc
    best_df, header_lines = normalize_two_row_header_flexible(best_df)
    return best_df, header_lines

# ------------ 日期/周次 ------------
FILENAME_DATE_PAT = re.compile(r"t(\d{4})(\d{2})(\d{2})_")
def parse_report_date(md_text: str, filename: str) -> Optional[str]:
    # 形如：时间：2025-05-08
    m = re.search(r"时间[:：]\s*(\d{4}-\d{2}-\d{2})", md_text)
    if m: return m.group(1)
    # 中文日期
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", md_text)
    if m:
        y, mo, d = map(int, m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"
    # 文件名兜底
    m = FILENAME_DATE_PAT.search(filename)
    if m: return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None

def week_iso(y: int, w: int) -> str:
    return f"{y}-{w:02d}"

def week_to_monday(week_str: Optional[str]):
    if not week_str or "-" not in str(week_str): return pd.NaT
    try:
        y, w = map(int, str(week_str).split("-"))
        return pd.to_datetime(date.fromisocalendar(y, w, 1))
    except Exception:
        return pd.NaT

# ------------ 行展开（取“最大周”那一列） ------------
WEEK_NUMS = re.compile(r"第?\s*(\d{1,2})\s*周")
def extract_latest_week_data(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    cols = [str(c) for c in df.columns]

    def find_pathogen_col():
        for c in cols:
            if any(k in c for k in PATHOGEN_KEYS): return c
        return cols[0]

    def pick_latest_col(keys):
        best_col, best_week = None, None
        for c in cols:
            if any(k in c for k in keys):
                ws = [int(x) for x in WEEK_NUMS.findall(c)]
                if ws:
                    w = max(ws)
                    if (best_week is None) or (w > best_week):
                        best_col, best_week = c, w
                elif best_col is None:
                    best_col = c  # 没有周号也保留候选
        return best_col, best_week

    c_path  = find_pathogen_col()
    c_ili,  w_ili  = pick_latest_col(ILI_KEYS)
    c_sari, w_sari = pick_latest_col(SARI_KEYS)
    max_week = None
    for w in [w_ili, w_sari]:
        if w is not None:
            max_week = w if max_week is None else max(max_week, w)

    def to_float(x):
        if x is None or (isinstance(x, float) and pd.isna(x)): return None
        s = str(x).replace(",", "").replace("，","").replace("％","%").strip()
        s = s.replace("%","")
        s = re.sub(r"[^\d\.\-]", "", s)
        if s in ["","-"]: return None
        try: return float(s)
        except: return None

    rows = []
    for _, r in df.iterrows():
        name = str(r.get(c_path, "")).strip()
        if not name or name in ["合计","总计"]: continue
        rows.append({
            "pathogen": name,
            "ili_percent": to_float(r.get(c_ili)) if c_ili else None,
            "sari_percent": to_float(r.get(c_sari)) if c_sari else None
        })
    return rows, max_week

# ------------ 驱动 ------------
def find_md_files(inp: str) -> List[Path]:
    p = Path(inp)
    if p.is_file() and p.suffix.lower() in [".md",".markdown"]:
        return [p]
    if p.is_dir():
        return sorted([x for x in p.rglob("*.md")])
    return sorted([Path(x) for x in Path().glob(inp) if str(x).endswith(".md")])

def process_one(md_path: Path, debug=False) -> List[Dict[str, Any]]:
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    df, header_lines = pick_table1(text)
    if df is None:
        if debug: print(f"[debug] no table detected in {md_path.name}")
        return []

    rows, week_from_cols = extract_latest_week_data(df)
    if not rows: return []

    report_date = parse_report_date(text, md_path.name)

    # 优先：用列名里解析出的“最大周”；否则回退到正文/文件名（这里就不再从正文识别周号了）
    report_week = None
    if week_from_cols is not None:
        try:
            year = int((report_date or md_path.name)[:4])
            report_week = week_iso(year, int(week_from_cols))
        except Exception:
            report_week = None

    for r in rows:
        r.update({"report_date": report_date, "report_week": report_week})
    return rows

def main():
    ap = argparse.ArgumentParser(description="Extract (ILI/SARI) choosing latest week column from monthly/weekly tables")
    ap.add_argument("input", help="单个.md、目录或通配符（如 'md_out/*.md'）")
    ap.add_argument("-o","--out", default="cdc_table1.csv", help="输出CSV路径")
    ap.add_argument("--max-workers", type=int, default=4)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    files = find_md_files(args.input)
    if not files: raise SystemExit("未找到任何 .md 文件")

    all_rows: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futs = [ex.submit(process_one, p, args.debug) for p in files]
        for fut in tqdm(concurrent.futures.as_completed(futs), total=len(futs), desc="processing"):
            all_rows.extend(fut.result())

    if not all_rows:
        print("没有抽取到任何数据。")
        return

    df = pd.DataFrame(all_rows)

    # 只保留 5 列
    need = ["report_date","report_week","pathogen","ili_percent","sari_percent"]
    for c in need:
        if c not in df.columns: df[c] = None
    df = df[need].copy()

    # 数值列
    for c in ["ili_percent","sari_percent"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # 排序（新 -> 旧）：优先用 report_date，否则用周一
    df["_sort_date"] = pd.to_datetime(df["report_date"], errors="coerce")
    mask = df["_sort_date"].isna()
    df.loc[mask, "_sort_date"] = df.loc[mask, "report_week"].apply(
        lambda s: pd.to_datetime(date.fromisocalendar(*map(int, str(s).split("-")), 1)) if isinstance(s,str) and "-" in s else pd.NaT
    )
    df = df.sort_values("_sort_date", ascending=False, kind="mergesort").drop(columns=["_sort_date"])

    # 确保输出目录存在
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    df.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"✅ Done. {len(df)} rows -> {args.out}")

if __name__ == "__main__":
    main()
