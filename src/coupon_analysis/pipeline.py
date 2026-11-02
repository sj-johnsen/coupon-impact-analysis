"""The whole run, in order. `python -m coupon_analysis` calls `run()`."""
from __future__ import annotations

import json
from pathlib import Path

from . import config as C
import os

from . import doc, guard, latex, plots, render, results, word
from .data import DataValidationError, load_raw, validate

TEMPLATES = Path(__file__).resolve().parent / "templates"
MAX_REPORT_PAGES = 3


def _log(msg: str, quiet: bool) -> None:
    if not quiet:
        print(msg, flush=True)


def check_only(data_path: Path) -> int:
    rep = validate(load_raw(data_path))
    for m in rep.errors:
        print("ERROR  ", m)
    for m in rep.warnings:
        print("WARNING", m)
    for m in rep.notes:
        print("NOTE   ", m)
    print("Data contract:", "FAILED" if rep.errors else "satisfied")
    return 1 if rep.errors else 0


def build_docx(root: Path, res: dict, include_cover, include_references, quiet: bool, out: dict) -> None:
    """text.md -> Word. The text is checked against results.json first (stale numbers); with COUPON_WORD_EXPORT=1 Word also
    exports the PDF, and the page count is reported (body must stay within three pages)."""
    md = (root / C.REPORT_SOURCE).read_text(encoding="utf-8")
    path = word.build(md, root, root / C.REPORT_DOCX, include_cover, include_references)
    bad = guard.stale_numbers(word.docx_body_text(path), res)
    if bad:
        out["stale_numbers"] = sorted(set(out.get("stale_numbers", [])) | set(bad))
        _log(f"WARNING: {path.name}: numbers not in results.json: {', '.join(bad)}", quiet)
    _log(f"      Word report written: {path.name}", quiet)
    est = word.estimate_pages(path)
    out["docx_estimate"] = est
    _log(f"      page estimate (body, conservative): {est['pages']} page(s), {est['fill']:.0%} of three pages; per page "
         + ", ".join(f"{x:.0%}" for x in est["per_page"]), quiet)
    if not est["ok"]:
        msg = f"The Word body is estimated at {est['fill']:.0%} of three pages over {est['pages']} pages (limit: 3 pages, {word.MAX_FILL:.0%}). Shorten text.md or the figures."
        out["warnings"].append(msg)
        _log("WARNING: " + msg, quiet)
    if os.environ.get("COUPON_WORD_EXPORT"):
        pages = word.export_pdf_with_word(path, root / C.REPORT_PDF)
        out["docx_pages"] = pages
        _log(f"      Word export: {pages} page(s) in total (cover and reference page included if switched on)", quiet)


def build_latex(root: Path, res: dict, quiet: bool, out: dict) -> None:
    """text.md -> .tex -> PDF (tectonic). The numbers in the text are checked against results.json first; the PDF must have
    at most three text pages (cover page and reference page are not counted)."""
    md = (root / C.REPORT_SOURCE).read_text(encoding="utf-8")
    pdf, pages = latex.build(md, root, Path(C.REPORT_PDF).stem)
    out["report_pages"] = pages
    _log(f"      LaTeX report written: {pdf.name}, {pages} page(s)", quiet)
    if pages > MAX_REPORT_PAGES:
        msg = f"The report has {pages} pages (limit {MAX_REPORT_PAGES}). Shorten text.md or the figures."
        out["warnings"].append(msg)
        _log("WARNING: " + msg, quiet)


def run(root: Path, data_path: Path | None = None, render_pdf: bool = True, render_docs: bool = True,
        regen_report: bool = False, quiet: bool = False, html_pdf: bool = False,
        include_cover: bool | None = None, include_references: bool | None = None, docx: bool = False) -> dict:
    root = Path(root)
    data_path = Path(data_path) if data_path else root / C.DATA_FILENAME
    out = {"warnings": []}

    _log(f"[1/6] Reading and validating {data_path.name}", quiet)
    res, cust, rep = results.compute(data_path)
    for w in rep.warnings:
        _log(f"      warning: {w}", quiet)
    out["warnings"] += rep.warnings

    _log("[2/6] Estimates done; writing results.json", quiet)
    results.write_json(res, root / C.RESULTS_FILENAME)

    _log("[3/6] Drawing figures", quiet)
    figs = plots.make_all(cust, res, root / C.FIGURES_DIRNAME)

    _log("[4/6] Filling the appendix from results.json", quiet)
    app_tmpl = (TEMPLATES / "appendix.md.tmpl").read_text(encoding="utf-8")
    appendix_md = doc.render(app_tmpl, res, figs, "A")
    (root / f"{C.APPENDIX_BASENAME}.md").write_text(appendix_md, encoding="utf-8")

    report_path = root / C.REPORT_SOURCE
    if regen_report or not report_path.exists():
        _log(f"      writing {C.REPORT_SOURCE} from its template (existing edits are overwritten)", quiet)
        rep_tmpl = (TEMPLATES / "text.md.tmpl").read_text(encoding="utf-8")
        report_path.write_text(doc.render(rep_tmpl, res, figs, "", doc.scan(app_tmpl, "A")), encoding="utf-8")
    else:
        _log(f"      keeping the existing {C.REPORT_SOURCE} (use --regen-report to rebuild it from the template)", quiet)

    stale = guard.stale_details(report_path.read_text(encoding="utf-8"), res)
    if stale:
        out["stale_numbers"] = [s["number"] for s in stale]
        for s in stale:
            msg = f"{C.REPORT_SOURCE} line {s['line']}: {s['number']} is not in results.json ({s['context']!r})"
            out["warnings"].append(msg)
            _log("WARNING: " + msg, quiet)
        _log("         Fix: edit the number in text.md, or run --regen-report (this discards your manual edits).", quiet)

    if render_docs:
        _log("[5/6] Rendering the appendix", quiet)
        pdf = (root / C.APPENDIX_PDF) if render_pdf else None
        pages = render.render_file(root / f"{C.APPENDIX_BASENAME}.md", "appendix", root / f"{C.APPENDIX_BASENAME}.html", pdf,
                                   "Appendix: reproducible analysis of the coupon interventions", "Assignment 1, Topics in Econometrics B", root)
        out["appendix_pages"] = pages
        _log("[6/6] Building the report (LaTeX)", quiet)
        if render_pdf:
            build_latex(root, res, quiet, out)
        if docx:
            build_docx(root, res, include_cover, include_references, quiet, out)
        if html_pdf:
            build = root / "build"
            build.mkdir(exist_ok=True)
            pages = render.render_file(report_path, "report", build / "report.html", root / C.REPORT_HTML_PDF,
                                       "Causal Impact of Coupon Interventions", "Assignment 1, Topics in Econometrics B", root)
            out["report_pages"] = pages
            _log(f"      HTML route: {pages} page(s)", quiet)
    else:
        _log("[5/6, 6/6] Rendering skipped", quiet)
    out["results"] = res
    return out


def run_only(root: Path, which: str, data_path: Path | None = None, quiet: bool = False,
             include_cover: bool | None = None, include_references: bool | None = None, docx: bool = False) -> dict:
    """Redo one part from the existing results.json: 'figures' (needs the data) or 'report' (text.md -> Word only)."""
    root = Path(root)
    if not (root / C.RESULTS_FILENAME).exists():
        raise FileNotFoundError(f"{C.RESULTS_FILENAME} not found in {root}. Fix: run the full pipeline first (uv run python -m coupon_analysis).")
    res = json.loads((root / C.RESULTS_FILENAME).read_text(encoding="utf-8"))
    out = {"warnings": []}
    if which == "figures":
        from .data import load_customers
        cust, _ = load_customers(Path(data_path) if data_path else root / C.DATA_FILENAME)
        plots.make_all(cust, res, root / C.FIGURES_DIRNAME)
        _log("Figures redrawn.", quiet)
    else:
        text = (root / C.REPORT_SOURCE).read_text(encoding="utf-8")
        stale = guard.stale_details(text, res)
        if stale:
            out["stale_numbers"] = [s["number"] for s in stale]
            for s in stale:
                _log(f"WARNING: {C.REPORT_SOURCE} line {s['line']}: {s['number']} is not in results.json ({s['context']!r})", quiet)
        build_latex(root, res, quiet, out)
        if docx:
            build_docx(root, res, include_cover, include_references, quiet, out)
    return out
