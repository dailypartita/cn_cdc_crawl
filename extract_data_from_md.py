#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, re, argparse, concurrent.futures, io
from io import StringIO
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dateutil import parser as dateparser
import pandas as pd
from bs4 import BeautifulSoup
from tqdm import tqdm
import re
from datetime import date

# ===== 可选：LLM（OpenRouter DeepSeek） =====
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import Runnable

# ----------------- Schema -----------------

WEEK_CN_RE = re.compile(r"^\s*(\d{4})\s*年\s*第?\s*(\d{1,2})\s*周\s*$")

class Table1Row(BaseModel):
    pathogen: str
    ili_cases: Optional[int] = None
    ili_percent: Optional[float] = None
    sari_cases: Optional[int] = None
    sari_percent: Optional[float] = None
    notes: Optional[str] = None

class CDCWeeklyPayload(BaseModel):
    report_date: Optional[str] = None
    report_week: Optional[str] = None
    rows: List[Table1Row] = Field(default_factory=list)

# ----------------- LLM 链（可选） -----------------
def build_llm_chain(model: str, api_key: str) -> Runnable:
    parser = PydanticOutputParser(pydantic_object=CDCWeeklyPayload)
    sys_msg = (
        "你是严谨的数据抽取助手。输入是一份中国CDC周报Markdown。"
        "任务：识别‘报告时间/周次’与‘表1’，提取每个病原体在门急诊流感样病例（ILI）与住院严重急性呼吸道感染（SARI）的数据。"
        "规则：优先抽取‘表1’；若只有百分比、人数字段留空；report_date尽量YYYY-MM-DD；输出严格JSON。"
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", sys_msg),
        ("human", "从以下Markdown中抽取数据为JSON：\n\n{md_text}\n\n" + parser.get_format_instructions())
    ])
    llm = ChatOpenAI(
        model=model, api_key=api_key, base_url="https://openrouter.ai/api/v1",
        temperature=0, timeout=120,
        default_headers={"HTTP-Referer":"http://localhost","X-Title":"cdc-md-table1-extractor"}
    )
    return prompt | llm | parser

# ----------------- 工具与常量 -----------------
PATHOGEN_KEYS = ["病原体","病原","病原学","Pathogen"]
ILI_KEYS = ["门急诊","流感样","ILI","门诊"]
SARI_KEYS = ["住院","严重急性","SARI"]

DATE_PATS = [
    r"发布\s*日(?:期)?[:：]?\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)",
    r"更新\s*日(?:期)?[:：]?\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)",
    r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)",
]
WEEK_PAT = r"(\d{4})\s*年\s*第?\s*(\d{1,2})\s*周"
FILENAME_DATE_PAT = r"t(\d{4})(\d{2})(\d{2})_\d+"

def all_pipe_tables(md: str) -> List[Tuple[int,int,str]]:
    out = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            j = i; buf = []
            while j < len(lines) and lines[j].strip().startswith("|"):
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
    cols = [str(c) for c in df.columns]
    score = 0
    # 允许两行表头（此时列名可能是0,1,2...，给基础分）
    if any(any(k in " ".join(map(str, df.iloc[0].values)) for k in PATHOGEN_KEYS) for _ in [0]):
        score += 2
    if any(any(k in " ".join(map(str, df.iloc[0].values)) for k in ILI_KEYS) for _ in [0]):
        score += 2
    if any(any(k in " ".join(map(str, df.iloc[0].values)) for k in SARI_KEYS) for _ in [0]):
        score += 2
    # 有真实列名也加分
    if any(any(k in c for k in PATHOGEN_KEYS) for c in cols): score += 3
    if any(any(k in c for k in ILI_KEYS) for c in cols): score += 2
    if any(any(k in c for k in SARI_KEYS) for c in cols): score += 2
    score += min(len(df), 10)
    return score

def normalize_two_row_header(df: pd.DataFrame) -> pd.DataFrame:
    """
    适配如下形态：
      行0: 病原体 | 门急诊流感样病例 | 门急诊流感样病例 | 住院严重急性... | 住院严重急性...
      行1: 病原体 | 第31周          | 较上周*         | 第31周          | 较上周*
    合并成：
      病原体 | 门急诊流感样病例|第31周 | 门急诊流感样病例|较上周* | 住院严重急性...|第31周 | 住院严重急性...|较上周*
    """
    if df.shape[0] >= 2:
        row0 = [str(x).strip() for x in df.iloc[0].tolist()]
        row1 = [str(x).strip() for x in df.iloc[1].tolist()]
        # 条件：两行首列都像“病原体”
        if any(k in row0[0] for k in PATHOGEN_KEYS) and any(k in row1[0] for k in PATHOGEN_KEYS):
            new_cols = []
            for a, b in zip(row0, row1):
                a1 = re.sub(r"\s+", "", a)
                b1 = re.sub(r"\s+", "", b)
                if b1 and b1 != a1:
                    new_cols.append(f"{a1}|{b1}")
                else:
                    new_cols.append(a1)
            df2 = df.iloc[2:].reset_index(drop=True).copy()
            df2.columns = new_cols
            return df2
    return df

def pick_table1(md_text: str) -> Optional[pd.DataFrame]:
    candidates: List[pd.DataFrame] = []

    m = re.search(r"表\s*1[^\n]*", md_text, flags=re.IGNORECASE)
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

    if not candidates: return None

    # 先挑最像的，再做两行表头归一化
    best_df = None; best_score = -1
    for df in candidates:
        sc = score_table(df)
        if sc > best_score:
            best_df, best_score = df, sc

    best_df = normalize_two_row_header(best_df)
    return best_df

def extract_date_and_week(md_text: str, filename: str) -> Tuple[Optional[str], Optional[str]]:
    report_date = None; report_week = None
    for pat in DATE_PATS:
        m = re.search(pat, md_text)
        if m:
            try:
                report_date = dateparser.parse(m.group(1).replace(" ", "")).date().isoformat()
                break
            except: pass
    m2 = re.search(WEEK_PAT, md_text)
    if m2:
        report_week = f"{m2.group(1)}年第{int(m2.group(2))}周"
    if not report_date:
        m3 = re.search(FILENAME_DATE_PAT, filename)
        if m3:
            y, mo, d = m3.groups()
            try:
                report_date = dateparser.parse(f"{y}-{mo}-{d}").date().isoformat()
            except: pass
    return report_date, report_week

def flatten_rows(df: pd.DataFrame) -> List[Dict[str, Any]]:
    cols = [str(c) for c in df.columns]

    # 找“病原体”列
    def find_col(keys):
        for c in cols:
            if any(k in c for k in keys):
                return c
        return cols[0]  # 兜底：第一列

    c_pathogen = find_col(PATHOGEN_KEYS)

    # 选择 ILI/SARI 的“周百分比列”（优先 |第X周），以及“较上周*”列作为备注
    def pick_percent_and_delta(keys):
        c_percent = None; c_delta = None; c_cases = None
        for c in cols:
            if any(k in c for k in keys):
                if re.search(r"\|?第?\d+周", c) or ("阳性率" in c) or ("% " in c) or c.endswith("%"):
                    if c_percent is None: c_percent = c
                if "较上周" in c or "较上期" in c or "较上周*" in c:
                    if c_delta is None: c_delta = c
                if any(k in c for k in ["例数","人数","阳性数","数（例）","数(例)"]):
                    if c_cases is None: c_cases = c
        # 如果没找到显式百分比列，但只剩一个候选列，就把它当百分比
        if c_percent is None:
            candidates = [c for c in cols if any(k in c for k in keys)]
            if len(candidates) == 1:
                c_percent = candidates[0]
        return c_percent, c_delta, c_cases

    ili_percent_col, ili_delta_col, ili_cases_col = pick_percent_and_delta(ILI_KEYS)
    sari_percent_col, sari_delta_col, sari_cases_col = pick_percent_and_delta(SARI_KEYS)

    out = []
    for _, r in df.iterrows():
        name = str(r.get(c_pathogen, "")).strip()
        if name == "" or name in ["合计","总计"]:
            continue

        def to_float(x):
            if x is None or (isinstance(x, float) and pd.isna(x)): return None
            s = str(x).replace(",", "").replace("，","").replace("％","%").strip()
            s = s.replace("%","")  # 即使没写%，这里也当数值
            s = re.sub(r"[^\d\.\-]", "", s)
            if s in ["","-"]: return None
            try: return float(s)
            except: return None

        def to_int(x):
            f = to_float(x)
            if f is None: return None
            return int(round(f))

        ili_cases   = to_int(r.get(ili_cases_col))   if ili_cases_col else None
        ili_percent = to_float(r.get(ili_percent_col)) if ili_percent_col else None
        sari_cases   = to_int(r.get(sari_cases_col))   if sari_cases_col else None
        sari_percent = to_float(r.get(sari_percent_col)) if sari_percent_col else None

        notes_bits = []
        if ili_delta_col:
            v = r.get(ili_delta_col)
            if v not in [None, "", "-"]:
                notes_bits.append(f"ILI较上周:{str(v).strip()}")
        if sari_delta_col:
            v = r.get(sari_delta_col)
            if v not in [None, "", "-"]:
                notes_bits.append(f"SARI较上周:{str(v).strip()}")

        out.append({
            "pathogen": name,
            "ili_cases": ili_cases,
            "ili_percent": ili_percent,
            "sari_cases": sari_cases,
            "sari_percent": sari_percent,
            "notes": "; ".join(notes_bits) if notes_bits else None
        })
    return out

# ----------------- 主流程 -----------------
def find_md_files(inp: str) -> List[Path]:
    p = Path(inp)
    if p.is_file() and p.suffix.lower() in [".md",".markdown"]:
        return [p]
    if p.is_dir():
        return sorted([x for x in p.rglob("*.md")])
    return sorted([Path(x) for x in Path().glob(inp) if str(x).endswith(".md")])

def process_one(md_path: Path, chain: Optional[Runnable], debug=False) -> List[Dict[str, Any]]:
    text = md_path.read_text(encoding="utf-8", errors="ignore")

    if chain is not None:
        try:
            payload: CDCWeeklyPayload = chain.invoke({"md_text": text})
            if payload.rows:
                rd, rw = payload.report_date, payload.report_week
                return [{
                    "source_file": str(md_path),
                    "report_date": rd, "report_week": rw,
                    "pathogen": r.pathogen,
                    "ili_cases": r.ili_cases, "ili_percent": r.ili_percent,
                    "sari_cases": r.sari_cases, "sari_percent": r.sari_percent,
                    "notes": r.notes
                } for r in payload.rows]
        except Exception as e:
            if debug: print(f"[debug] LLM failed: {md_path.name}: {e}")

    df = pick_table1(text)
    if df is None:
        if debug: print(f"[debug] no table detected in {md_path.name}")
        return []

    if debug:
        print(f"[debug] chosen table shape={df.shape} in {md_path.name}")
        print(f"[debug] head:\n{df.head(3)}")

    rows = flatten_rows(df)
    rd, rw = extract_date_and_week(text, md_path.name)
    out = [{
        "source_file": str(md_path),
        "report_date": rd, "report_week": rw,
        "pathogen": r["pathogen"],
        "ili_cases": r["ili_cases"], "ili_percent": r["ili_percent"],
        "sari_cases": r["sari_cases"], "sari_percent": r["sari_percent"],
        "notes": r.get("notes")
    } for r in rows]
    return out

def main():
    ap = argparse.ArgumentParser(description="Extract CDC weekly Table 1 (ILI/SARI) from Markdown into CSV")
    ap.add_argument("input", help="单个.md、目录或通配符（如 'md_out/*.md'）")
    ap.add_argument("-o","--out", default="cdc_table1.csv", help="输出CSV路径")
    ap.add_argument("--model", default="deepseek/deepseek-chat", help="OpenRouter模型名")
    ap.add_argument("--no-llm", action="store_true", help="仅用本地解析")
    ap.add_argument("--max-workers", type=int, default=4)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    api_key = os.getenv("OPENROUTER_API_KEY","")
    if not api_key and not args.no_llm:
        print("WARN: 未检测到 OPENROUTER_API_KEY，自动切到 --no-llm 本地解析。")
        args.no_llm = True

    files = find_md_files(args.input)
    if not files: raise SystemExit("未找到任何 .md 文件")

    chain = None if args.no_llm else build_llm_chain(args.model, api_key)

    all_rows: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futs = [ex.submit(process_one, p, chain, args.debug) for p in files]
        for fut in tqdm(concurrent.futures.as_completed(futs), total=len(futs), desc="processing"):
            all_rows.extend(fut.result())

    if not all_rows:
        print("没有抽取到任何数据。可加 --debug 查看解析细节。")
        return

    def normalize_week_str(s: str | None) -> str | None:
        """把 '2024年第48周' -> '2024-48'；其余返回原值或 None"""
        if not s:
            return None
        m = WEEK_CN_RE.match(str(s))
        if not m:
            return s.strip() if isinstance(s, str) else None
        y, w = int(m.group(1)), int(m.group(2))
        return f"{y}-{w:02d}"

    def week_to_monday_date(week_str: str | None):
        """把 'YYYY-ww' 转为该周周一的日期（datetime.date），用于排序"""
        if not week_str or "-" not in str(week_str):
            return None
        try:
            y, w = map(int, str(week_str).split("-"))
            # ISO 周 -> 周一
            return date.fromisocalendar(y, w, 1)
        except Exception:
            return None

    if not all_rows:
        print("没有抽取到任何数据。可加 --debug 查看解析细节。")
        return

    df = pd.DataFrame(all_rows)

    # 只保留并重排 5 列
    need_cols = ["report_date", "report_week", "pathogen", "ili_percent", "sari_percent"]
    for c in need_cols:
        if c not in df.columns:
            df[c] = None
    df = df[need_cols].copy()

    # 规范周字符串 'YYYY年第W周' -> 'YYYY-WW'
    df["report_week"] = df["report_week"].apply(normalize_week_str)

    # 数值列转为浮点
    for c in ["ili_percent", "sari_percent"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # 构造排序键：优先用 report_date，否则用 report_week 对应周一
    df["_sort_date"] = pd.to_datetime(df["report_date"], errors="coerce")
    wk_sort = df["_sort_date"].isna()
    df.loc[wk_sort, "_sort_date"] = df.loc[wk_sort, "report_week"].apply(week_to_monday_date)
    df["_sort_date"] = pd.to_datetime(df["_sort_date"], errors="coerce")

    # 按从新到旧排序
    df = df.sort_values("_sort_date", ascending=False, kind="mergesort").drop(columns=["_sort_date"])

    # 落盘（UTF-8 带 BOM，方便 Excel）
    df.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"✅ Done. {len(df)} rows -> {args.out}")

if __name__ == "__main__":
    main()
