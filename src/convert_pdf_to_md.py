#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Batch convert PDFs to Markdown via MinerU API.

支持两种模式：
1. 直接上传模式（默认）：直接上传 PDF 文件到 MinerU API
2. OSS 模式：先上传到 OSS，然后通过 URL 提交任务

Usage (直接上传模式):
  python convert_pdf_to_md.py -i /path/to/pdfs -o md_out \
    --server https://mineru.net/api/v4/extract/task \
    --api-key YOUR_API_KEY \
    --lang ch --backend pipeline --parse-method auto \
    --formula-enable true --table-enable true \
    --workers 4 --timeout 120 --retries 3

Usage (OSS 模式):
  python convert_pdf_to_md.py -i /path/to/pdfs -o md_out \
    --use-oss --oss-bucket epi-flow --oss-prefix pdfs \
    --server https://mineru.net/api/v4/extract/task \
    --api-key YOUR_API_KEY \
    --model-version vlm \
    --poll-interval 5 --max-wait-time 600
"""

import argparse
import json
import os
import sys
import glob
import time
import mimetypes
import subprocess
import zipfile
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


def get_ossutil_path() -> str:
    """
    获取 ossutil 命令路径。
    优先级：环境变量 OSS_UTILS_PATH > .env 文件 > 系统 PATH 中的 ossutil
    
    Returns:
        ossutil 命令路径
    """
    # 1. 从环境变量读取
    ossutil_path = os.environ.get("OSS_UTILS_PATH")
    if ossutil_path and Path(ossutil_path).exists():
        return ossutil_path
    
    # 2. 从 .env 文件读取
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('OSS_UTILS_PATH='):
                        ossutil_path = line.split('=', 1)[1].strip()
                        # 移除引号
                        if ossutil_path.startswith('"') and ossutil_path.endswith('"'):
                            ossutil_path = ossutil_path[1:-1]
                        elif ossutil_path.startswith("'") and ossutil_path.endswith("'"):
                            ossutil_path = ossutil_path[1:-1]
                        if ossutil_path and Path(ossutil_path).exists():
                            return ossutil_path
        except Exception:
            pass
    
    # 3. 使用系统 PATH 中的 ossutil
    return "ossutil"


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


def upload_to_oss(pdf_path: str, oss_path: str, opts: argparse.Namespace) -> tuple[bool, str]:
    """
    使用 ossutil 上传文件到 OSS。
    返回：(success, message)
    """
    timeout = 300  # 默认超时时间
    try:
        # 根据文件大小动态调整超时时间（每MB约2秒，最少60秒，最多1800秒）
        file_size = os.path.getsize(pdf_path)
        file_size_mb = file_size / (1024 * 1024)
        timeout = max(60, min(int(file_size_mb * 2) + 60, 1800))  # 至少60秒，最多30分钟
        
        ossutil_cmd = get_ossutil_path()
        cmd = [ossutil_cmd, "cp", pdf_path, oss_path]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return (True, "uploaded")
        # 输出更详细的错误信息
        error_msg = result.stderr.strip() or result.stdout.strip()
        if not error_msg:
            error_msg = f"exit code {result.returncode}"
        return (False, f"ossutil error: {error_msg[:500]}")
    except subprocess.TimeoutExpired:
        return (False, f"upload timeout (>{timeout}s)")
    except FileNotFoundError:
        ossutil_path = get_ossutil_path()
        return (False, f"ossutil command not found at: {ossutil_path}. Please check OSS_UTILS_PATH in .env file or install ossutil")
    except Exception as e:
        return (False, f"upload failed: {e}")


def sign_oss_url(oss_path: str, expires: int = 3600, opts: argparse.Namespace = None) -> tuple[bool, str]:
    """
    使用 ossutil 生成 OSS 签名 URL。
    注意：ossutil sign 命令不支持 --timeout 参数，默认过期时间为 900 秒。
    返回：(success, signed_url)
    """
    try:
        # ossutil sign 不支持自定义过期时间，使用默认值（通常是 900 秒）
        ossutil_cmd = get_ossutil_path()
        cmd = [ossutil_cmd, "sign", oss_path]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # 移除可能的警告信息，只保留 URL
            for line in url.split("\n"):
                if line.startswith("http"):
                    return (True, line.strip())
            return (True, url)
        return (False, f"ossutil sign error: {result.stderr[:200]}")
    except FileNotFoundError:
        ossutil_path = get_ossutil_path()
        return (False, f"ossutil command not found at: {ossutil_path}. Please check OSS_UTILS_PATH in .env file or install ossutil")
    except Exception as e:
        return (False, f"sign failed: {e}")


def submit_mineru_task(
    session: requests.Session,
    server: str,
    pdf_url: str,
    opts: argparse.Namespace,
) -> tuple[Optional[str], bool, str]:
    """
    提交任务到 MinerU API（URL 方式）。
    返回：(task_id, success, message)
    """
    server = server.rstrip("/")
    if not server.endswith("/extract/task"):
        if server.endswith("/task"):
            url = server
        else:
            url = f"{server}/extract/task" if "/api/" in server else f"{server}/api/v4/extract/task"
    else:
        url = server

    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
    }
    if opts.api_key:
        headers["Authorization"] = f"Bearer {opts.api_key}"

    payload = {
        "url": pdf_url,
    }
    if opts.model_version:
        payload["model_version"] = opts.model_version

    try:
        resp = session.post(url, json=payload, headers=headers, timeout=opts.timeout)
        if not (200 <= resp.status_code < 300):
            return (None, False, f"HTTP {resp.status_code}: {resp.text[:200]}")

        j = resp.json()
        if j.get("code") == 0:
            task_id = j.get("data", {}).get("task_id")
            if task_id:
                return (task_id, True, "task submitted")
            return (None, False, "no task_id in response")
        return (None, False, f"API error: {j.get('msg', 'unknown')}")
    except Exception as e:
        return (None, False, f"submit failed: {e}")


def query_mineru_task(
    session: requests.Session,
    server: str,
    task_id: str,
    opts: argparse.Namespace,
) -> tuple[bool, Optional[Dict[str, Any]], str]:
    """
    查询 MinerU 任务状态。
    返回：(success, task_data, message)
    """
    server = server.rstrip("/")
    if not server.endswith("/extract/task"):
        if server.endswith("/task"):
            base_url = server
        else:
            base_url = f"{server}/extract/task" if "/api/" in server else f"{server}/api/v4/extract/task"
    else:
        base_url = server

    url = f"{base_url}/{task_id}"

    headers = {"Accept": "*/*"}
    if opts.api_key:
        headers["Authorization"] = f"Bearer {opts.api_key}"

    try:
        resp = session.get(url, headers=headers, timeout=opts.timeout)
        if not (200 <= resp.status_code < 300):
            return (False, None, f"HTTP {resp.status_code}: {resp.text[:200]}")

        j = resp.json()
        if j.get("code") == 0:
            data = j.get("data", {})
            return (True, data, "ok")
        return (False, None, f"API error: {j.get('msg', 'unknown')}")
    except Exception as e:
        return (False, None, f"query failed: {e}")


def wait_for_task_completion(
    session: requests.Session,
    server: str,
    task_id: str,
    opts: argparse.Namespace,
    poll_interval: int = 5,
    max_wait: int = 600,
) -> tuple[bool, Optional[Dict[str, Any]], str]:
    """
    轮询任务直到完成。
    返回：(success, task_data, message)
    """
    start_time = time.time()
    poll_count = 0
    while time.time() - start_time < max_wait:
        poll_count += 1
        success, data, msg = query_mineru_task(session, server, task_id, opts)
        if not success:
            return (False, None, msg)

        state = data.get("state", "").lower()
        elapsed = int(time.time() - start_time)
        print(f"[DEBUG] 轮询 #{poll_count} (已等待 {elapsed}s): state={state}")
        
        if state == "done":
            return (True, data, "task completed")
        elif state in ("failed", "error"):
            err_msg = data.get("err_msg", "unknown error")
            return (False, data, f"task failed: {err_msg}")

        time.sleep(poll_interval)

    return (False, None, f"timeout after {max_wait}s")


def download_and_extract_result(
    zip_url: str,
    out_dir: Path,
    pdf_stem: str,
    session: requests.Session,
    opts: argparse.Namespace,
) -> tuple[str, bool, str]:
    """
    下载并解压 MinerU 结果 zip 文件，提取 full.md。
    返回：(输出路径, success, message)
    """
    out_md_path = out_dir / (pdf_stem + ".md")

    headers = {"Accept": "*/*"}
    if opts.api_key:
        headers["Authorization"] = f"Bearer {opts.api_key}"

    try:
        # 下载 zip
        print(f"[DEBUG] 开始下载 ZIP 文件...")
        resp = session.get(zip_url, headers=headers, timeout=opts.timeout * 2, stream=True)
        if not (200 <= resp.status_code < 300):
            return (str(out_md_path), False, f"download failed: HTTP {resp.status_code}")

        # 保存到临时文件
        temp_zip = out_dir / f"{pdf_stem}_temp.zip"
        total_size = 0
        with open(temp_zip, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                total_size += len(chunk)
        print(f"[DEBUG] ZIP 下载完成 ({total_size / 1024 / 1024:.2f} MB)")

        # 解压并提取 full.md
        print(f"[DEBUG] 开始解压 ZIP 文件...")
        with zipfile.ZipFile(temp_zip, "r") as zf:
            file_list = zf.namelist()
            print(f"[DEBUG] ZIP 包含 {len(file_list)} 个文件")
            if "full.md" in file_list:
                zf.extract("full.md", out_dir)
                extracted_md = out_dir / "full.md"
                if extracted_md.exists():
                    shutil.move(str(extracted_md), str(out_md_path))
                    print(f"[DEBUG] 提取 full.md 成功")
            else:
                # 如果没有 full.md，尝试找其他 .md 文件
                md_files = [f for f in file_list if f.endswith(".md")]
                if md_files:
                    print(f"[DEBUG] 未找到 full.md，使用 {md_files[0]}")
                    zf.extract(md_files[0], out_dir)
                    extracted_md = out_dir / md_files[0]
                    if extracted_md.exists():
                        shutil.move(str(extracted_md), str(out_md_path))
                else:
                    return (str(out_md_path), False, f"no .md file in zip. Files: {file_list[:10]}")

        # 清理临时文件
        temp_zip.unlink()
        print(f"[DEBUG] 清理临时文件完成")

        if out_md_path.exists():
            md_size = out_md_path.stat().st_size
            print(f"[DEBUG] Markdown 文件已保存: {out_md_path} ({md_size / 1024:.2f} KB)")
            return (str(out_md_path), True, "ok")
        return (str(out_md_path), False, "md file not found after extraction")

    except Exception as e:
        return (str(out_md_path), False, f"download/extract failed: {e}")


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


def process_pdf_via_oss(
    session: requests.Session,
    server: str,
    pdf_path: str,
    opts: argparse.Namespace,
) -> tuple[str, bool, str]:
    """
    通过 OSS 上传并提交到 MinerU API 处理单个 PDF。
    返回：(输出路径, success, message)
    """
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
    pdf_stem = Path(pdf_path).stem
    out_md_path = out_dir / (pdf_stem + ".md")

    # 1. 上传到 OSS
    pdf_name = Path(pdf_path).name
    if opts.oss_prefix:
        oss_path = f"{opts.oss_bucket}/{opts.oss_prefix}/{pdf_name}"
    else:
        oss_path = f"{opts.oss_bucket}/{pdf_name}"
    # 确保路径格式正确（移除多余斜杠）
    oss_path = "/".join(filter(None, oss_path.split("/")))
    
    oss_full_path = f"oss://{oss_path}"
    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    print(f"[DEBUG] 准备上传: {pdf_name} ({file_size_mb:.2f} MB) -> {oss_full_path}")

    upload_ok, upload_msg = upload_to_oss(pdf_path, oss_full_path, opts)
    if not upload_ok:
        return (str(out_md_path), False, f"OSS upload failed: {upload_msg}")
    print(f"[DEBUG] OSS 上传成功: {oss_full_path}")

    # 2. 生成签名 URL
    print(f"[DEBUG] 生成签名 URL: oss://{oss_path}")
    sign_ok, signed_url = sign_oss_url(f"oss://{oss_path}", opts.oss_url_expires, opts)
    if not sign_ok:
        return (str(out_md_path), False, f"OSS sign failed: {signed_url}")
    print(f"[DEBUG] 签名 URL 生成成功 (长度: {len(signed_url)})")

    # 3. 提交任务
    print(f"[DEBUG] 提交任务到 MinerU API: {server}")
    task_id, submit_ok, submit_msg = submit_mineru_task(session, server, signed_url, opts)
    if not submit_ok:
        return (str(out_md_path), False, f"submit failed: {submit_msg}")
    print(f"[DEBUG] 任务提交成功, task_id: {task_id}")

    # 4. 等待任务完成
    print(f"[DEBUG] 开始轮询任务状态 (间隔: {opts.poll_interval}s, 最大等待: {opts.max_wait_time}s)")
    complete_ok, task_data, complete_msg = wait_for_task_completion(
        session, server, task_id, opts, poll_interval=opts.poll_interval, max_wait=opts.max_wait_time
    )
    if not complete_ok:
        return (str(out_md_path), False, f"task completion failed: {complete_msg}")
    print(f"[DEBUG] 任务完成, 准备下载结果")

    # 5. 下载结果
    zip_url = task_data.get("full_zip_url")
    if not zip_url:
        return (str(out_md_path), False, f"no full_zip_url in task data. Available keys: {list(task_data.keys())}")
    print(f"[DEBUG] 下载结果 ZIP: {zip_url}")

    return download_and_extract_result(zip_url, out_dir, pdf_stem, session, opts)


def post_file(
    session: requests.Session,
    server: str,
    pdf_path: str,
    opts: argparse.Namespace,
) -> tuple[str, bool, str]:
    """
    向 MinerU 发送单个 PDF（直接上传方式，保留作为备选）。
    返回：(输出路径, success, message)
    """
    # 如果启用了 OSS 模式，使用 OSS 流程
    if opts.use_oss:
        return process_pdf_via_oss(session, server, pdf_path, opts)

    server = server.rstrip("/")
    # 兼容两类传参：
    # 1) 传入根地址（如 http://host:port 或 https://mineru.net），则拼接 /file_parse
    # 2) 传入完整端点（如 https://mineru.net/api/v4/extract/task 或 .../file_parse），则直接使用
    if server.endswith("/file_parse") or server.endswith("/extract/task") or "/api/" in server:
        url = server
    else:
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
    ap.add_argument("-i", "--input", help="PDF 文件或目录或通配符（如 './pdf/*.pdf'）")
    ap.add_argument("-o", "--out", default="md_out", help="本地输出目录，默认 md_out")
    ap.add_argument("--server", default=os.environ.get("MINERU_API", "https://mineru.net/api/v4/extract/task"),
                    help="MinerU 服务根地址，默认 https://mineru.net/api/v4/extract/task")
    ap.add_argument("--api-key", default=os.environ.get("MINERU_API_KEY", ""),
                    help="如需鉴权，传入 Bearer token（可留空）")

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

    # OSS 相关参数（OSS 模式）
    ap.add_argument("--use-oss", action="store_true", help="启用 OSS 模式：先上传到 OSS，再通过 URL 提交任务")
    ap.add_argument("-b", "--oss-bucket", default=os.environ.get("OSS_BUCKET", ""),
                    help="OSS bucket 名称（OSS 模式必需），也可通过环境变量 OSS_BUCKET 设置")
    ap.add_argument("--oss-prefix", default=os.environ.get("OSS_PREFIX", ""),
                    help="OSS 路径前缀（可选），如 'pdfs'，也可通过环境变量 OSS_PREFIX 设置")
    ap.add_argument("--oss-url-expires", type=int, default=3600,
                    help="OSS 签名 URL 过期时间（秒），默认 3600")
    
    # MinerU API 任务模式参数
    ap.add_argument("--model-version", default="vlm",
                    help="MinerU 模型版本（OSS 模式），默认 vlm，可选 vlm 或 pipeline")
    ap.add_argument("--poll-interval", type=int, default=5,
                    help="任务状态轮询间隔（秒），默认 5")
    ap.add_argument("--max-wait-time", type=int, default=600,
                    help="任务最大等待时间（秒），默认 600")

    # 通用控制
    ap.add_argument("--workers", type=int, default=4, help="并发线程数，默认 4")
    ap.add_argument("--timeout", type=int, default=120, help="单个请求超时秒，默认 120")
    ap.add_argument("--retries", type=int, default=3, help="失败重试次数，默认 3")

    opts = ap.parse_args()

    # 验证 OSS 模式参数
    if opts.use_oss:
        if not opts.oss_bucket:
            print("错误：OSS 模式需要指定 --oss-bucket 或设置环境变量 OSS_BUCKET", file=sys.stderr)
            sys.exit(2)

    pdfs = list_pdfs(opts.input)
    if not pdfs:
        print("未找到任何 PDF。", file=sys.stderr)
        sys.exit(2)

    base = common_base(pdfs)
    opts._base_dir = str(base)

    Path(opts.out).mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"Accept": "application/json, text/markdown;q=0.9, */*;q=0.5"})

    mode_str = "OSS 模式" if opts.use_oss else "直接上传模式"
    print(f"[INFO] 模式={mode_str}  server={opts.server}  files={len(pdfs)}  out={opts.out}")
    if opts.use_oss:
        print(f"[INFO] OSS bucket={opts.oss_bucket}  prefix={opts.oss_prefix or '(无)'}  "
              f"model_version={opts.model_version}")
    else:
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
    # url = "/data/ykx/covid19/get_data/cn_cdc_data/update/2025-10-27/pdf/t20251106_313312.pdf"
    main()