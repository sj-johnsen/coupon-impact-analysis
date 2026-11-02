# Causal impact of the 500 yen and 3000 yen coupons

Assignment 1, *Topics in Econometrics B* (Prof. Masayuki Sawada), Hitotsubashi University, Autumn 2026.
Author: Simon Jensen (student ID 2226237U).

This repository is the replication package for the three-page report
[`assignment_2226237U_simon_jensen.pdf`](assignment_2226237U_simon_jensen.pdf). It holds the analysis code, the tests,
all estimates (`results.json`), the figures and the full appendix
([`appendix_2226237U_simon_jensen.pdf`](appendix_2226237U_simon_jensen.pdf)) with every robustness table the report
refers to.

## The data are not included

The customer panel (`assignment_data_panel_obs.csv`, 10,000 customers, weeks 30 to 34) is course material and is
**not published here on purpose**. To check or reproduce the results, put your own copy of the file next to
`pyproject.toml`. Without it the pipeline stops with a message saying where the file belongs, and the tests that need
the data are skipped.

## Where to find what

| Report | Appendix |
| :--- | :--- |
| Regression discontinuity at 3,000 yen ("finds nothing") | Section D, Figure A3 |
| The four group means behind the difference-in-differences (Card-Krueger table) | Section E, Tables A8 and A9 |
| Robustness of the headline RD estimate (bandwidth, kernel, polynomial, selectors) | Section F, Table A17 |
| Why the RD at 10,000 yen is not valid | Section E, Figure A4 |
| Balance and placebo tests with Holm correction | Section F, Table A15 |
| Break-even margins at other redemption rates | Section G |

## Headline results

Effects in yen per customer, 95% confidence intervals; all values come from `results.json`.

| Quantity | Estimate | 95% CI |
| :--- | ---: | :--- |
| 500 yen coupon, RD at 1,000, change vs. own baseline (weeks 30 to 32) | +634 | +257 to +1,012 |
| 500 yen coupon, RD at 1,000, week-34 level | +932 | +461 to +1,403 |
| 500 yen coupon, RD at 3,000, week-34 level | −204 | −524 to +115 |
| 3000 yen coupon, difference-in-differences | +3,810 | +3,751 to +3,870 |

## Running it

```bash
# install uv once: https://docs.astral.sh/uv/
uv sync                                    # creates .venv with the pinned packages
uv run python -m coupon_analysis --check   # validates the data file only
uv run python -m coupon_analysis --no-pdf  # all estimates, figures and the appendix (Markdown/HTML)
uv run pytest                              # tests
```

Building the PDFs additionally needs [tectonic](https://tectonic-typesetting.github.io/) (report) and Chrome
(appendix). The run is deterministic: running it twice gives an identical `results.json`. Section A of the appendix is
the full user manual, Section B explains the code module by module.

## Layout

```text
src/coupon_analysis/   pipeline: data checks, RD, DiD, bunching, cost-benefit, plots, report and appendix rendering
tests/                 pytest suite (validation, estimators, simulation with a known effect, page and number checks)
figures/               all figures
results.json           every number used in the report and the appendix
text.md                source of the report
appendix.md            source of the appendix
```
