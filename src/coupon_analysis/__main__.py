"""Command line: `uv run python -m coupon_analysis [options]` from the project folder."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config as C
from .data import DataValidationError
from .pipeline import check_only, run, run_only
from .render import RenderError


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="coupon_analysis", description="Regenerate every result, figure and document of Assignment 1.")
    ap.add_argument("--data", type=Path, help=f"path to the panel CSV (default: <project>/{C.DATA_FILENAME})")
    ap.add_argument("--root", type=Path, help="project folder where outputs are written (default: the folder with pyproject.toml)")
    ap.add_argument("--check", action="store_true", help="only validate the data and exit")
    ap.add_argument("--no-pdf", action="store_true", help="write HTML but skip the PDFs (no Chrome needed)")
    ap.add_argument("--no-render", action="store_true", help="compute results, figures and appendix.md only")
    ap.add_argument("--regen-report", action="store_true", help="rebuild text.md from its template (overwrites manual edits)")
    ap.add_argument("--only", choices=["figures", "report"], help="redo only the figures, or only the report PDF from the current text.md (uses the existing results.json)")
    ap.add_argument("--docx", action="store_true", help="also build the old Word report (it does not typeset formulas)")
    ap.add_argument("--no-cover", action="store_true", help="Word report without the cover page")
    ap.add_argument("--no-references", action="store_true", help="Word report without the reference page")
    ap.add_argument("--html-pdf", action="store_true", help="also build the old HTML -> Chrome PDF of the report (build/report_html.pdf)")
    ap.add_argument("-q", "--quiet", action="store_true")
    a = ap.parse_args(argv)
    root = (a.root or C.project_root()).resolve()
    data = a.data or root / C.DATA_FILENAME
    try:
        if a.check:
            return check_only(data)
        if a.only:
            out = run_only(root, a.only, data, quiet=a.quiet, include_cover=False if a.no_cover else None, include_references=False if a.no_references else None, docx=a.docx)
            return 3 if out.get("stale_numbers") or (out.get("report_pages") or 0) > 3 else 0
        out = run(root, data, render_pdf=not a.no_pdf, render_docs=not a.no_render, regen_report=a.regen_report, quiet=a.quiet, html_pdf=a.html_pdf,
                  include_cover=False if a.no_cover else None, include_references=False if a.no_references else None, docx=a.docx)
    except (DataValidationError, FileNotFoundError, RenderError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 2
    return 3 if out.get("stale_numbers") or (out.get("report_pages") or 0) > 3 else 0   # 3 = finished, but check the warnings


if __name__ == "__main__":
    sys.exit(main())
