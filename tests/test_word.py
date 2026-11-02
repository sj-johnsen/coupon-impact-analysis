import json
import shutil
import zipfile
from pathlib import Path

import pytest
from docx import Document

from coupon_analysis import config as C
from coupon_analysis import guard, word
from coupon_analysis.__main__ import main


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("word")
    shutil.copy(C.project_root() / C.DATA_FILENAME, root / C.DATA_FILENAME)
    assert main(["--root", str(root), "--no-pdf", "--docx", "-q"]) == 0
    return root


def _headings(path):
    return [p.text for p in Document(str(path)).paragraphs if p.style.name == "Heading 1"]


def test_docx_exists_with_sections_cover_and_references(built):
    path = built / C.REPORT_DOCX
    assert path.stat().st_size > 20_000
    assert _headings(path) == ["Executive Summary", "Evidences", "Diagnostics", "References"]
    texts = [p.text for p in Document(str(path)).paragraphs]
    assert "Causal Impact of Coupon Interventions" in texts[0] or any("Causal Impact" in t for t in texts[:8])
    assert any(t.startswith("Student ID:") for t in texts[:12])
    assert len(Document(str(path)).inline_shapes) == 2


def test_metadata_is_simons_and_clean(built):
    path = built / C.REPORT_DOCX
    cp = Document(str(path)).core_properties
    assert cp.author == cp.last_modified_by == "Simon Jensen"
    assert cp.title == "Causal Impact of Coupon Interventions"
    assert cp.comments == ""
    assert cp.created.year >= 2026 and cp.modified.year >= 2026
    with zipfile.ZipFile(path) as z:
        for name in ("docProps/core.xml", "docProps/app.xml"):
            assert "python-docx" not in z.read(name).decode("utf-8", "ignore"), name


def test_all_text_is_at_least_12_pt(built):
    doc = Document(str(built / C.REPORT_DOCX))
    for p in doc.paragraphs:
        for r in p.runs:
            if r.text.strip():
                assert r.font.size is None or r.font.size.pt >= 12, (r.text[:30], r.font.size.pt)
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                for r in c.paragraphs[0].runs:
                    assert r.font.size.pt >= 12


def test_every_number_in_the_docx_is_in_results(built):
    res = json.loads((built / C.RESULTS_FILENAME).read_text())
    assert guard.stale_numbers(word.docx_body_text(built / C.REPORT_DOCX), res) == []


def test_docx_guard_catches_a_wrong_number(built, tmp_path):
    res = json.loads((built / C.RESULTS_FILENAME).read_text())
    md = (built / C.REPORT_SOURCE).read_text()
    est = f"{round(res['did']['main']['estimate']):,}"
    out = word.build(md.replace(est, "9,876", 1), built, tmp_path / "x.docx")
    assert "9,876" in guard.stale_numbers(word.docx_body_text(out), res)


def test_cover_and_references_flags(built, tmp_path):
    md = (built / C.REPORT_SOURCE).read_text()
    bare = word.build(md, built, tmp_path / "bare.docx", include_cover=False, include_references=False)
    assert _headings(bare) == ["Executive Summary", "Evidences", "Diagnostics"]
    assert not any(p.text.startswith("Student ID:") and p.style.name == "Normal" and p.text.startswith("Student ID: ") and len(p.text) < 25
                   for p in Document(str(bare)).paragraphs)
    full = word.build(md, built, tmp_path / "full.docx", include_cover=True, include_references=True)
    assert _headings(full)[-1] == "References"


@pytest.mark.skip(reason="Word route is opt-in (--docx) and does not typeset formulas; the page limit is checked on the LaTeX PDF")
def test_page_estimate_within_budget(built):
    est = word.estimate_pages(built / C.REPORT_DOCX)
    assert est["ok"], est
    assert est["pages"] <= 3 and est["fill"] <= word.MAX_FILL


def test_no_old_html_pdf_needed(built):
    assert not (built / C.REPORT_PDF).exists()
