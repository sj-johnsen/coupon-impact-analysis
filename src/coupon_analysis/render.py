"""Markdown -> HTML -> PDF, for the appendix and the report.

HTML: Python-Markdown (tables, toc, fenced code, pygments highlighting) with a print stylesheet; images are
embedded, so the HTML file is self-contained. PDF: headless Google Chrome. Metadata: pypdf.
"""
from __future__ import annotations

import base64
import html
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import markdown
from pygments.formatters import HtmlFormatter
import logging
from pypdf import PdfReader, PdfWriter

from . import config as C


logging.getLogger('pypdf').setLevel(logging.ERROR)


class RenderError(RuntimeError):
    pass


# ------------------------------------------------------------------------------------------ css
COMMON_CSS = """
:root { --ink:#1b1b1b; --muted:#555; --rule:#d9d9d9; --accent:#1f3a5f; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: var(--ink); margin: 0; }
h1, h2, h3, h4 { color: var(--accent); line-height: 1.2; break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 0.4em 0 0.9em; break-inside: avoid; }
th { text-align: left; border-bottom: 1.5px solid var(--ink); }
td { border-bottom: 0.5px solid var(--rule); vertical-align: top; }
td, th { padding: 2px 6px; }
figure { margin: 0.8em 0 1em; break-inside: avoid; text-align: center; }
figure img { max-width: 100%; height: auto; }
figcaption { text-align: left; color: var(--muted); }
p.tcap { margin: 1em 0 0.2em; color: var(--muted); break-after: avoid; }
p.tcap strong { color: var(--ink); }
code { font-family: Menlo, "DejaVu Sans Mono", monospace; }
.codehilite { background: #f6f8fa; border: 0.5px solid var(--rule); border-radius: 3px; padding: 6px 8px; margin: 0.5em 0 1em; overflow-x: hidden; }
.codehilite pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: Menlo, "DejaVu Sans Mono", monospace; line-height: 1.35; }
pre { white-space: pre-wrap; }
""" + HtmlFormatter(style="friendly").get_style_defs(".codehilite")

APPENDIX_CSS = """
@page { size: A4; margin: 20mm 18mm 20mm 18mm; @bottom-center { content: counter(page); font-size: 9pt; color: #777; } }
body { font-size: 10pt; line-height: 1.42; }
h1 { font-size: 22pt; margin: 0 0 0.2em; }
h2 { font-size: 16pt; margin: 0 0 0.5em; padding-bottom: 3px; border-bottom: 1px solid var(--accent); break-before: page; }
h2.first { break-before: auto; }
h3 { font-size: 12pt; margin: 1.3em 0 0.4em; }
h4 { font-size: 10.5pt; margin: 1em 0 0.3em; }
table { font-size: 8.5pt; }
figcaption, p.tcap { font-size: 9pt; }
.codehilite pre { font-size: 7.6pt; }
code { font-size: 9pt; }
.codehilite code { font-size: inherit; }
p.byline { color: var(--muted); margin: 0 0 1.2em; }
.toc { font-size: 9.5pt; columns: 2; column-gap: 24px; }
.toc ul { list-style: none; padding-left: 0.9em; margin: 0.1em 0; }
.toc > ul { padding-left: 0; }
.toc a { color: var(--ink); text-decoration: none; }
"""

REPORT_CSS = """
@page { size: A4; margin: 15mm 17mm 15mm 17mm; }
body { font-size: 12pt; line-height: 1.5; }
h1 { font-size: 15pt; margin: 0 0 0.1em; }
h2 { font-size: 13pt; margin: 0.75em 0 0.2em; }
p { margin: 0 0 0.5em; }
table { font-size: 12pt; margin: 0.15em 0 0.5em; }
td, th { padding: 1px 5px; }
td { white-space: nowrap; }
figcaption, p.tcap { font-size: 12pt; line-height: 1.2; }
figure { margin: 0.3em 0 0.5em; }
figure img { max-height: none; }
p.tcap { margin: 0.4em 0 0.1em; }
.byline { font-size: 12pt; margin: 0 0 0.3em; color: var(--muted); }
ul { margin: 0.1em 0 0.5em; padding-left: 1.3em; }
li { margin-bottom: 0.15em; }
"""


# ------------------------------------------------------------------------------------------ markdown
def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta, m.group(2).lstrip("\n")


def _figures(html_body: str) -> str:
    def repl(m: re.Match) -> str:
        alt, src = html.unescape(m.group(1)), m.group(2)
        head, _, rest = alt.partition(". ")
        cap = f"<strong>{html.escape(head)}.</strong> {html.escape(rest)}" if rest else html.escape(alt)
        return f'<figure><img alt="{html.escape(head)}" src="{src}"><figcaption>{cap}</figcaption></figure>'
    return re.sub(r'<p><img alt="(.*?)" src="(.*?)"\s*/?></p>', repl, html_body, flags=re.S)


def _embed_images(html_body: str, base: Path) -> str:
    def repl(m: re.Match) -> str:
        p = base / m.group(1)
        if not p.exists():
            raise RenderError(f"Image not found: {p}. Fix: run the full pipeline so that figures/ is regenerated.")
        return 'src="data:image/png;base64,' + base64.b64encode(p.read_bytes()).decode() + '"'
    return re.sub(r'src="(figures/[^"]+)"', repl, html_body)


def to_html(md_text: str, kind: str, base: Path, title: str) -> str:
    meta, body_md = split_frontmatter(md_text)
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "codehilite", "toc", "attr_list", "sane_lists"],
        extension_configs={"codehilite": {"guess_lang": False, "css_class": "codehilite"},
                           "toc": {"toc_depth": "2-3", "permalink": False}},
    )
    body = md.convert(body_md)
    body = _figures(body)
    body = _embed_images(body, base)
    header = ""
    if kind == "report":
        title = meta.get("titel", title)
        header = (f"<h1>{html.escape(title)}</h1>"
                  f'<p class="byline">{html.escape(meta.get("name", C.AUTHOR))} &middot; Student ID {html.escape(meta.get("matrikel", C.STUDENT_ID))}'
                  f' &middot; Topics in Econometrics B &middot; Assignment 1</p>')
    css = COMMON_CSS + (REPORT_CSS if kind == "report" else APPENDIX_CSS)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f'<meta name="author" content="{C.AUTHOR}"><style>{css}</style></head><body>{header}{body}</body></html>')


# ------------------------------------------------------------------------------------------ pdf
def chrome_path() -> str:
    path = os.environ.get("COUPON_CHROME")
    if not path:
        path = C.CHROME if Path(C.CHROME).exists() else next(
            (p for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome") if (p := shutil.which(n))), C.CHROME)
    if not Path(path).exists():
        raise RenderError(
            f"Google Chrome not found at '{path}'. Fix: install Chrome, or set COUPON_CHROME to the browser binary, "
            "or run with --no-pdf to write only the HTML."
        )
    return path


def _print_with_chrome(html_path: Path, pdf_path: Path, timeout: float = 150.0) -> None:
    """Run headless Chrome and wait until the PDF is written.

    Chrome sometimes keeps running after it has written the file (when another Chrome is open), so the PDF
    appearing and its size staying the same is treated as done, and the process is stopped.
    """
    pdf_path.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as profile:
        cmd = [chrome_path(), "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={profile}",
               f"--print-to-pdf={pdf_path}", f"file://{html_path}"]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        start, last_size, stable_since = time.time(), -1, None
        try:
            while time.time() - start < timeout:
                if proc.poll() is not None:
                    break
                size = pdf_path.stat().st_size if pdf_path.exists() else -1
                if size > 0 and size == last_size:
                    stable_since = stable_since or time.time()
                    if time.time() - stable_since > 2.0:
                        break
                else:
                    stable_since = None
                last_size = size
                time.sleep(0.5)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(10)
                except subprocess.TimeoutExpired:
                    proc.kill()
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise RenderError("Chrome did not produce the PDF. Fix: close other headless Chrome processes and run again, or use --no-pdf.")


def html_to_pdf(html_path: Path, pdf_path: Path, title: str, subject: str) -> int:
    """Print with headless Chrome, then set metadata and strip tool names. Returns the page count."""
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    _print_with_chrome(html_path.resolve(), pdf_path.resolve())
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter(clone_from=reader)
    writer.add_metadata({"/Title": title, "/Author": C.AUTHOR, "/Subject": subject, "/Producer": "", "/Creator": "", "/Keywords": ""})
    with open(pdf_path, "wb") as fh:
        writer.write(fh)
    return len(PdfReader(str(pdf_path)).pages)


def render_file(md_path: Path, kind: str, html_path: Path, pdf_path: Path | None, title: str, subject: str, base: Path) -> int | None:
    html_text = to_html(md_path.read_text(encoding="utf-8"), kind, base, title)
    html_path.write_text(html_text, encoding="utf-8")
    if pdf_path is None:
        return None
    return html_to_pdf(html_path, pdf_path, title, subject)
