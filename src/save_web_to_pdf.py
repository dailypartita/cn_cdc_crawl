import asyncio
import argparse
import re
import time
from pathlib import Path
from urllib.parse import urlparse, unquote

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ---------- 文件名工具：取 URL 最后段 ----------
def filename_from_url(url: str) -> str:
    p = urlparse(url)
    last = unquote(p.path.split("/")[-1]) or "index.html"
    # 去掉查询/片段，保留基名
    base = last.split("?")[0].split("#")[0]
    # 去掉原扩展名，换成 .pdf
    if base.lower().endswith(".html") or base.lower().endswith(".htm"):
        base = base.rsplit(".", 1)[0]
    if not base:
        base = "page"
    return base

# ---------- 合法化并避免重名 ----------
def unique_pdf_path(out_dir: Path, base: str) -> Path:
    # 替换非法字符，避免过长
    safe = re.sub(r'[\\/:*?"<>|]+', "_", base).strip()[:180] or "page"
    path = out_dir / f"{safe}.pdf"
    i = 1
    while path.exists():
        path = out_dir / f"{safe}-{i}.pdf"
        i += 1
    return path

# ---------- 渲染单页 ----------
async def render_one(context, url: str, out_dir: Path, args, sem: asyncio.Semaphore):
    async with sem:
        page = await context.new_page()
        page.set_default_timeout(args.timeout * 1000)

        # 给中文环境/字体一点“友好度”
        await page.add_init_script("""document.documentElement.lang = document.documentElement.lang || 'zh-CN';""")

        try:
            # 第一次尝试：等待 load；如失败改用 networkidle 再试
            for attempt, wait_until in enumerate([args.wait_until, "networkidle"], start=1):
                try:
                    await page.goto(url, wait_until=wait_until)
                    break
                except PWTimeout:
                    if attempt == 2:
                        raise

            # 注入样式：打印配色、中文字体优先、去粘性头
            await page.add_style_tag(content=r"""
                :root { -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }
                /* 中文字体回退链：按平台常见字体排列 */
                * {
                  font-family: system-ui, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
                                "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", sans-serif !important;
                }
                @media print {
                  * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
                }
                header, nav, footer { z-index: 0 !important; }
                .sticky, .fixed, [style*="position:sticky"], [style*="position:fixed"] { position: static !important; }
            """)

            # 等待页面自带 @font-face 字体真正就绪（关键）
            try:
                await page.evaluate("await document.fonts.ready")
            except Exception:
                pass  # 个别站点不支持也无妨

            await page.emulate_media(media="print")

            base = filename_from_url(url)
            pdf_path = unique_pdf_path(out_dir, base)

            await page.pdf(
                path=str(pdf_path),
                format=args.format,               # A4/Letter...
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": args.margin, "right": args.margin, "bottom": args.margin, "left": args.margin},
                scale=args.scale
            )
            print(f"[OK] {url} -> {pdf_path.name}")
        except Exception as e:
            print(f"[FAIL] {url} ({type(e).__name__}: {e})")
        finally:
            await page.close()
            if args.delay > 0:
                await asyncio.sleep(args.delay)

async def main():
    parser = argparse.ArgumentParser(description="Batch save webpages to PDF with good Chinese support (Playwright+Chromium).")
    parser.add_argument("input", help="每行一个 URL 的文本文件，或逗号分隔 URL 字符串")
    parser.add_argument("-o", "--output", default="pdf_out", help="输出目录，默认 pdf_out")
    parser.add_argument("--format", default="A4", help="纸型（A4/Letter/Legal）")
    parser.add_argument("--margin", default="10mm", help="页边距，默认 10mm")
    parser.add_argument("--scale", type=float, default=1.0, help="缩放 0.1~2.0，默认 1.0")
    parser.add_argument("-c", "--concurrency", type=int, default=4, help="并发数，默认 4")
    parser.add_argument("-t", "--timeout", type=int, default=45, help="单页超时秒，默认 45")
    parser.add_argument("--wait-until", dest="wait_until", default="load",
                        choices=["domcontentloaded", "load", "networkidle"],
                        help="初次等待策略，默认 load；失败会再用 networkidle 重试一次")
    parser.add_argument("--delay", type=float, default=0.0, help="每页导出后的间隔秒，默认 0")
    parser.add_argument("--user-agent", default="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
                        help="自定义 UA，默认常见 Chrome UA")
    args = parser.parse_args()

    # 读 URL 列表
    in_path = Path(args.input)
    if in_path.exists():
        urls = [line.strip() for line in in_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        urls = [u.strip() for u in args.input.split(",") if u.strip()]
    if not urls:
        raise SystemExit("未读取到 URL")

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-gpu"])
        context = await browser.new_context(locale="zh-CN", user_agent=args.user_agent)
        sem = asyncio.Semaphore(args.concurrency)

        tasks = [render_one(context, u, out_dir, args, sem) for u in urls]
        await asyncio.gather(*tasks, return_exceptions=True)
        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
