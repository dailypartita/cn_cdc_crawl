# web2pdf_util.py
# -*- coding: utf-8 -*-

"""
Importable utility to save web pages as PDF (Playwright + Chromium).

Public APIs
----------
1) async save_webpages_to_pdf(urls, *, output="pdf_out", format="A4", margin="10mm",
                              scale=1.0, concurrency=4, timeout=45, wait_until="load",
                              delay=0.0, user_agent=DEFAULT_UA, headless=True,
                              browser_args=None) -> list[dict]
   - Core async function. Returns a list of dicts (one per URL):
     { "url": str, "ok": bool, "path": pathlib.Path|None, "error": str|None }

2) web_to_pdf(urls, **same_kwargs) -> list[dict]
   - Synchronous wrapper around the async function. Handy for quick use.

Notes
-----
- Requires: playwright >= 1.44  (and Chromium installed: `playwright install chromium`)
- Adds CSS to improve print color fidelity and Chinese font fallbacks.
- Sanitizes filenames and avoids collisions.
- Retries navigation: first with `wait_until`, then with `networkidle` if needed.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Iterable, List, Dict, Any, Optional
from urllib.parse import urlparse, unquote

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124 Safari/537.36"
)

# --------------------- Filename helpers --------------------- #

def _filename_from_url(url: str) -> str:
    """
    Derive a base filename from URL path (without extension); fallback 'page'.
    """
    p = urlparse(url)
    last = unquote(p.path.split("/")[-1]) or "index.html"
    base = last.split("?")[0].split("#")[0]
    if base.lower().endswith((".html", ".htm")):
        base = base.rsplit(".", 1)[0]
    return base or "page"


def _unique_pdf_path(out_dir: Path, base: str) -> Path:
    """
    Produce a unique, sanitized PDF path in the output directory.
    """
    safe = re.sub(r'[\\/:*?"<>|]+', "_", base).strip()[:180] or "page"
    path = out_dir / f"{safe}.pdf"
    i = 1
    while path.exists():
        path = out_dir / f"{safe}-{i}.pdf"
        i += 1
    return path

# --------------------- Core rendering routine --------------------- #

async def _render_one(context, url: str, out_dir: Path, *,
                      format: str, margin: str, scale: float,
                      timeout: int, wait_until: str, delay: float) -> Dict[str, Any]:
    """
    Render a single URL to PDF; returns a result dict.
    """
    page = await context.new_page()
    page.set_default_timeout(timeout * 1000)

    # Prefer Chinese fonts and exact print colors
    await page.add_init_script(
        "document.documentElement.lang = document.documentElement.lang || 'zh-CN';"
    )

    try:
        # Try initial wait strategy, then fallback to networkidle
        for attempt, wu in enumerate([wait_until, "networkidle"], start=1):
            try:
                await page.goto(url, wait_until=wu)
                break
            except PWTimeout:
                if attempt == 2:
                    raise

        # Style injection: better print fidelity and remove sticky overlays
        await page.add_style_tag(content=r"""
            :root { -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
            * {
              font-family: system-ui, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
                           "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei",
                           "Segoe UI", Arial, sans-serif !important;
            }
            @media print {
              * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
            }
            header, nav, footer { z-index: 0 !important; }
            .sticky, .fixed, [style*="position:sticky"], [style*="position:fixed"] { position: static !important; }
        """)

        # Ensure @font-face finished loading (best-effort)
        try:
            await page.evaluate("await document.fonts.ready")
        except Exception:
            pass

        await page.emulate_media(media="print")

        base = _filename_from_url(url)
        pdf_path = _unique_pdf_path(out_dir, base)

        await page.pdf(
            path=str(pdf_path),
            format=format,                    # e.g., "A4", "Letter"
            print_background=True,
            prefer_css_page_size=True,
            margin={"top": margin, "right": margin, "bottom": margin, "left": margin},
            scale=scale,
        )

        ok = True
        err = None
        return {"url": url, "ok": ok, "path": pdf_path, "error": err}

    except Exception as e:
        return {"url": url, "ok": False, "path": None, "error": f"{type(e).__name__}: {e}"}

    finally:
        await page.close()
        if delay > 0:
            await asyncio.sleep(delay)

# --------------------- Public async API --------------------- #

async def save_webpages_to_pdf(
    urls: Iterable[str],
    *,
    output: str | Path = "pdf_out",
    format: str = "A4",
    margin: str = "10mm",
    scale: float = 1.0,
    concurrency: int = 4,
    timeout: int = 45,
    wait_until: str = "load",            # "domcontentloaded" | "load" | "networkidle"
    delay: float = 0.0,
    user_agent: str = DEFAULT_UA,
    headless: bool = True,
    browser_args: Optional[list[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Save multiple web pages to PDFs concurrently.

    Parameters
    ----------
    urls : Iterable[str]
        One or more HTTP/HTTPS URLs.
    output : str | Path
        Output directory. Will be created if missing.
    format : str
        Paper size (e.g., "A4", "Letter", "Legal").
    margin : str
        CSS units accepted by Chromium ("10mm", "0.5in", etc.).
    scale : float
        Page scale, 0.1–2.0 (default 1.0).
    concurrency : int
        Max concurrent pages to render.
    timeout : int
        Per-page timeout in seconds.
    wait_until : str
        Initial wait strategy; will auto-fallback to "networkidle" on retry.
    delay : float
        Delay (seconds) after each page export (helps rate-limit).
    user_agent : str
        Custom User-Agent for the browsing context.
    headless : bool
        Launch Chromium in headless mode.
    browser_args : list[str] | None
        Extra args passed to Chromium (e.g., ["--disable-gpu"]).

    Returns
    -------
    List[Dict[str, Any]]
        For each URL: {url, ok, path, error}
    """
    # Normalize & validate inputs
    url_list = [u.strip() for u in urls if str(u).strip()]
    if not url_list:
        return []

    out_dir = Path(output).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    sem = asyncio.Semaphore(max(1, int(concurrency)))
    if browser_args is None:
        browser_args = ["--disable-gpu"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=browser_args)
        context = await browser.new_context(locale="zh-CN", user_agent=user_agent)

        async def _worker(u: str) -> None:
            async with sem:
                res = await _render_one(
                    context, u, out_dir,
                    format=format, margin=margin, scale=scale,
                    timeout=timeout, wait_until=wait_until, delay=delay
                )
                results.append(res)

        # Fire tasks and wait (collect exceptions inside worker for per-URL reporting)
        tasks = [asyncio.create_task(_worker(u)) for u in url_list]
        await asyncio.gather(*tasks, return_exceptions=True)

        await context.close()
        await browser.close()

    return results

# --------------------- Synchronous convenience wrapper --------------------- #

def web_to_pdf(
    urls: Iterable[str] | str,
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    Run the async exporter in a blocking fashion.

    Usage
    -----
    from web2pdf_util import web_to_pdf
    res = web_to_pdf(["https://example.com", "https://paddle.org"], output="pdf_out")
    for r in res:
        print(r["ok"], r["url"], r["path"], r["error"])
    """
    if isinstance(urls, str):
        urls = [urls]
    return asyncio.run(save_webpages_to_pdf(urls, **kwargs))
