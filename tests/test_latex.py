import shutil
from pathlib import Path

import pytest

from coupon_analysis import config as C
from coupon_analysis import latex

MD = """---
titel: Test Title
untertitel: Sub
name: Simon Jensen
matrikel: 2226237U
dozent: Masayuki Sawada
datum: 2026-10-15
---

## Section

A share of 76% with $\\alpha = 4,459 - 649$, p <0.001, 3,000-9,999 yen, a_b & c, **bold**.

$$m^{*} = \\frac{r N f}{\\Delta R}.$$

**Table 1.** Caption.
{: .tcap }

| Coupon | Effect |
| :--- | ---: |
| A | +634 [257, 1,012] |

## References

Smith, J. (2020). Title. *Journal, 1*(2), 3-4. https://doi.org/10.1/x_y
"""


def test_markdown_becomes_latex():
    tex = latex.to_tex(MD)
    assert r"\begin{equation*}" in tex and r"\frac{r N f}{\Delta R}" in tex
    assert r"76\%" in tex                       # percent escaped in text
    assert r"$\alpha = 4{,}459 - 649$" in tex   # thousands comma kept out of math spacing
    assert "3,000--9,999" in tex                # range gets an en dash
    assert r"$<$\,0.001" in tex                 # "p <0.001" gets proper spacing
    assert r"a\_b \& c" in tex                  # specials escaped
    assert r"\textbf{bold}" in tex
    assert r"\url{https://doi.org/10.1/x_y}" in tex
    assert r"\begin{tabular}{@{}lr@{}}" in tex and r"\toprule" in tex
    assert tex.count(r"\sect{") == 2
    assert r"\textbf{Name:} Simon Jensen" in tex and "Masayuki Sawada" in tex


def test_em_dash_in_text_is_rejected():
    with pytest.raises(latex.LatexError):
        latex.to_tex(MD.replace("yen,", "yen \u2014 and"))


def test_table_without_caption_line_fails_clearly():
    bad = MD.replace("{: .tcap }\n", "")
    with pytest.raises(latex.LatexError):
        latex.to_tex(bad)


@pytest.mark.skipif(not (shutil.which("tectonic") or (Path.home() / ".local/bin/tectonic").exists()), reason="tectonic not installed")
def test_report_pdf_has_at_most_three_text_pages(tmp_path):
    root = C.project_root()
    shutil.copytree(root / "figures", tmp_path / "figures")
    pdf, pages = latex.build((root / C.REPORT_SOURCE).read_text(encoding="utf-8"), tmp_path, "report")
    assert pdf.exists() and pages <= 3
