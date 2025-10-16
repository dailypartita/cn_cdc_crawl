#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Batch convert PDFs to Markdown via MinerU API (/file_parse).
Tested with a local MinerU at http://10.22.16.132:8011

Usage:
  python convert_pdf_to_md.py /path/to/pdfs -o md_out \
    --server http://10.22.16.132:8011 \
    --lang ch --backend pipeline --parse-method auto \
    --formula-enable true --table-enable true \
    --workers 4 --timeout 120 --retries 3
"""

import argparse
import json
import os
import sys
import glob
import time
import mimetypes
from pathlib import Path
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


def list_pdfs(input_path: str) -> List[str]:
    p = Path(input_path)
    if p.is_file() and p.suffix.lower() == ".pdf":
        return [str(p)]
    if p.is_dir():
        return [str(x) for x in p.rglob("*.pdf")]
    # treat as glob pattern
    return [str(x) for x in map(Path, glob.glob(input_path)) if x.suffix.lower() == ".pdf"]


def common_base(paths: List[str]) -> Path:
    if not paths:
        return Path(".").resolve()
    try:
        return Path(os.path.commonpath([str(Path(p).resolve()) for p in paths]))
    except Exception:
        return Path(".").resolve()


def extract_markdown_from_json(obj: Any) -> str | None:
    """
    MinerU 的 JSON 结构在不同版本可能略有不同，尽量“鲁棒”地找出 markdown 文本：
    优先 'data' 下的 'md' / 'markdown' / 'content'，否则全树扫描第一个长字符串。
    """
    if obj is None:
        return None

    # 常见结构：{"code":0,"data":{"md":"..."}}
    def _get_from_data(d: Dict[str, Any]) -> str | None:
        if not isinstance(d, dict):
            return None
        data = d.get("data")
        if isinstance(data, dict):
            for k in ("md", "markdown", "content"):
                v = data.get(k)
                if isinstance(v, str) and len(v.strip()) > 0:
                    return v
        # 有些实现直接在顶层
        for k in ("md", "markdown", "content"):
            v = d.get(k)
            if isinstance(v, str) and len(v.strip()) > 0:
                return v
        return None

    md = _get_from_data(obj)
    if md:
        return md

    # 兜底：深度优先搜索第一个“像 markdown 的长字符串”
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
        elif isinstance(cur, str):
            s = cur.strip()
            if len(s) > 40:  # 容易误判，设置一个长度阈值
                return s
    return None


def post_file(
    session: requests.Session,
    server: str,
    pdf_path: str,
    opts: argparse.Namespace,
) -> tuple[str, bool, str]:
    """
    向 MinerU 发送单个 PDF。
    返回：(输出路径, success, message)
    """
    server = server.rstrip("/")
    url = f"{server}/file_parse"

    # 目标本地输出路径（保持目录结构）
    rel_dir = Path(pdf_path).resolve().parent
    base_dir = Path(opts._base_dir)  # 内部传入
    rel = Path(".")
    try:
        rel = rel_dir.relative_to(base_dir)
    except Exception:
        pass
    out_dir = Path(opts.out).joinpath(rel)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_md_path = out_dir / (Path(pdf_path).stem + ".md")

    # multipart/form-data
    with open(pdf_path, "rb") as f:
        files = [("files", (Path(pdf_path).name, f, "application/pdf"))]

        data = []
        # 与 Swagger 一致：lang_list 作为重复字段
        for lang in opts.lang:
            data.append(("lang_list", lang))
        if opts.backend:
            data.append(("backend", opts.backend))
        if opts.parse_method:
            data.append(("parse_method", opts.parse_method))
        # boolean 统一用 "true"/"false" 字符串
        data.append(("formula_enable", str(opts.formula_enable).lower()))
        data.append(("table_enable", str(opts.table_enable).lower()))
        data.append(("return_md", "true"))
        data.append(("return_images", str(opts.return_images).lower()))
        if opts.start_page_id is not None:
            data.append(("start_page_id", str(opts.start_page_id)))
        if opts.end_page_id is not None:
            data.append(("end_page_id", str(opts.end_page_id)))
        if opts.server_output_dir:
            # 仅当你希望 MinerU 在服务器容器内部写文件时使用
            data.append(("output_dir", opts.server_output_dir))

        headers = {}
        if opts.api_key:
            headers["Authorization"] = f"Bearer {opts.api_key}"

        # 重试
        backoff = 2.0
        for attempt in range(1, opts.retries + 1):
            try:
                resp = session.post(
                    url, files=files, data=data, headers=headers, timeout=opts.timeout
                )
                # 2xx 即认为成功，否则抛异常走重试
                if not (200 <= resp.status_code < 300):
                    raise requests.HTTPError(f"HTTP {resp.status_code}: {resp.text[:200]}")

                ctype = resp.headers.get("Content-Type", "")
                # 情况 A：直接返回 markdown（text/markdown 或 text/plain）
                if "text/markdown" in ctype or "text/plain" in ctype:
                    out_md_path.write_text(resp.text, encoding="utf-8")
                    return (str(out_md_path), True, "ok")

                # 情况 B：JSON 里带 md
                if "application/json" in ctype:
                    j = resp.json()
                    md = extract_markdown_from_json(j)
                    if md:
                        out_md_path.write_text(md, encoding="utf-8")
                        return (str(out_md_path), True, "ok")
                    # 如果没有 md，但返回了附件/路径信息，你也可以在这里扩展解析
                    return (str(out_md_path), False, "no markdown found in JSON")

                # 情况 C：附件（zip 或 md 文件）
                # 优先从 Content-Disposition 拿文件名
                disp = resp.headers.get("Content-Disposition", "")
                filename = None
                if "filename=" in disp:
                    filename = disp.split("filename=")[-1].strip('"; ')
                if not filename:
                    # 根据内容类型猜扩展名
                    ext = mimetypes.guess_extension(ctype) or ".bin"
                    filename = Path(pdf_path).stem + ext
                out_bin_path = out_dir / filename
                out_bin_path.write_bytes(resp.content)
                # 如果是 .md 直接返回；zip 则提示已保存附件
                if out_bin_path.suffix.lower() == ".md":
                    return (str(out_bin_path), True, "ok(md-file)")
                return (str(out_bin_path), True, f"saved attachment ({ctype})")

            except Exception as e:
                if attempt >= opts.retries:
                    return (str(out_md_path), False, f"failed after {attempt} tries: {e}")
                time.sleep(backoff)
                backoff *= 1.5


def main():
    ap = argparse.ArgumentParser(description="Convert PDFs to Markdown via MinerU /file_parse")
    ap.add_argument("input", help="PDF 文件或目录或通配符（如 './pdf/*.pdf'）")
    ap.add_argument("-o", "--out", default="md_out", help="本地输出目录，默认 md_out")
    ap.add_argument("--server", default=os.environ.get("MINERU_API", "http://10.22.16.132:8011"),
                    help="MinerU 服务根地址，默认 http://10.22.16.132:8011")
    ap.add_argument("--api-key", default="", help="如需鉴权，传入 Bearer token（可留空）")

    # 与 Swagger 对齐的解析参数
    ap.add_argument("--lang", nargs="+", default=["ch"], help="lang_list，多值可写多项，默认 ch")
    ap.add_argument("--backend", default="pipeline", help="backend，默认 pipeline")
    ap.add_argument("--parse-method", default="auto", help="parse_method，默认 auto")
    ap.add_argument("--formula-enable", type=lambda s: str(s).lower() != "false", default=True,
                    help="公式抽取：true/false，默认 true")
    ap.add_argument("--table-enable", type=lambda s: str(s).lower() != "false", default=True,
                    help="表格抽取：true/false，默认 true")
    ap.add_argument("--return-images", type=lambda s: str(s).lower() == "true", default=False,
                    help="是否让服务端一并返回图片（有的实现会打包为 zip），默认 false")
    ap.add_argument("--start-page-id", type=int, default=None, help="起始页，从 0 开始（可选）")
    ap.add_argument("--end-page-id", type=int, default=None, help="结束页（可选）")
    ap.add_argument("--server-output-dir", default="", help="让 MinerU 在服务器容器内写入的 output_dir（可选）")

    # 通用控制
    ap.add_argument("--workers", type=int, default=4, help="并发线程数，默认 4")
    ap.add_argument("--timeout", type=int, default=120, help="单个请求超时秒，默认 120")
    ap.add_argument("--retries", type=int, default=3, help="失败重试次数，默认 3")

    opts = ap.parse_args()

    pdfs = list_pdfs(opts.input)
    if not pdfs:
        print("未找到任何 PDF。", file=sys.stderr)
        sys.exit(2)

    base = common_base(pdfs)
    opts._base_dir = str(base)

    Path(opts.out).mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"Accept": "application/json, text/markdown;q=0.9, */*;q=0.5"})

    print(f"[INFO] server={opts.server}  files={len(pdfs)}  out={opts.out}")
    print(f"[INFO] lang={opts.lang} backend={opts.backend} parse_method={opts.parse_method} "
          f"formula={opts.formula_enable} table={opts.table_enable}")

    results = []
    with ThreadPoolExecutor(max_workers=opts.workers) as ex:
        futs = [ex.submit(post_file, session, opts.server, pdf, opts) for pdf in pdfs]
        for fut in as_completed(futs):
            out_path, ok, msg = fut.result()
            results.append((out_path, ok, msg))
            status = "OK" if ok else "FAIL"
            print(f"[{status}] {out_path}  {msg}")

    ok_n = sum(1 for _, ok, _ in results if ok)
    print(f"\nDone: {ok_n}/{len(results)} success. Output dir: {opts.out}")


if __name__ == "__main__":
    main()
