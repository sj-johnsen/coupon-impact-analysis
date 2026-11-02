"""Constants and paths. Everything that is a design choice lives here, nowhere else."""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------- paths
def project_root() -> Path:
    """Folder that holds pyproject.toml. Override with the COUPON_PROJECT_ROOT environment variable."""
    env = os.environ.get("COUPON_PROJECT_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


DATA_FILENAME = "assignment_data_panel_obs.csv"
FIGURES_DIRNAME = "figures"
RESULTS_FILENAME = "results.json"
APPENDIX_BASENAME = "appendix"
APPENDIX_PDF = "appendix_2226237U_simon_jensen.pdf"
REPORT_SOURCE = "text.md"
REPORT_PDF = "assignment_2226237U_simon_jensen.pdf"      # the submission: compiled from LaTeX (assignment_..._lastname.tex)
REPORT_DOCX = "assignment_2226237U_simon_jensen.docx"
REPORT_HTML_PDF = "build/report_html.pdf"                 # old HTML route, only with --html-pdf
INCLUDE_COVER = True              # cover page (not part of the three pages); switch off with --no-cover
INCLUDE_REFERENCES = True         # references on their own final page; switch off with --no-references
COURSE = "Topics in Econometrics B"
LECTURER = "Masayuki Sawada"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

AUTHOR = "Simon Jensen"
STUDENT_ID = "2226237U"

# ---------------------------------------------------------------- data contract
N_CUSTOMERS = 10_000
WEEKS = (30, 31, 32, 33, 34)
PRE_WEEKS = (30, 31, 32)          # before the 3000 yen coupon was announced (start of week 33)
RUNNING_WEEK = 33                 # eligibility is decided on spending in this week
OUTCOME_WEEK = 34                 # coupons are valid in this week
MAX_FLAG_MISMATCH = 5             # customers whose flag disagrees with the written rule: warn up to this many, fail above

GROUPS = {                        # flag column -> short label (order = low to high spending)
    "is_below_1000": "<1,000",
    "is_eligible_1000": "500 yen coupon",
    "is_between_3000_10000": "3,000-9,999",
    "is_eligible_10000": "3000 yen coupon",
}
GROUP_ORDER = list(GROUPS.values())
# rule for the running variable (spending in week 33): lower bound inclusive, upper bound exclusive
GROUP_RULE = {
    "is_below_1000": (float("-inf"), 1000),
    "is_eligible_1000": (1000, 3000),
    "is_between_3000_10000": (3000, 10000),
    "is_eligible_10000": (10000, float("inf")),
}
COUPON_FACE = {"500": 500.0, "3000": 3000.0}   # yen

# ---------------------------------------------------------------- estimation choices
CUTOFFS = (1000, 3000, 10000)
ALPHA = 0.05                      # significance level used for 'rejects' counts and red markers
RD_DESIGNS = {"at1000": (1000, +1), "at3000": (3000, -1)}   # valid designs: cutoff, sign of the coupon effect (-1: coupon on the left)
RD_INVALID = ("at10000", 10000)   # the 3000 yen threshold: estimated only to show that it fails
DENSITY_SPANS = {1000: 1500, 3000: 1500, 10000: 2000}      # half-width of the histograms in the density figure
DID_TREATED_MIN = 10000           # 3000 yen coupon: week-33 spending at or above this
DID_CONTROL_MIN = 3000            # comparison group: from here up to DID_TREATED_MIN (exclusive)
DID_BAND = (8000, 12000)          # robustness: drop everyone whose week-33 spending lies in this band
RD_NEAR = 1500                    # balance test is skipped if a covariate has no variation within this distance of the cutoff
COVARIATES = ["is_member", "male", "age_18_39", "age_40_59", "age_60p"]
DID_COVARIATES = ["is_member", "male", "age_40_59", "age_60p"]   # age_18_39 is the reference category
RD_KERNEL = "tri"                 # triangular, as in Lecture 4
RD_BWSELECT = "mserd"             # same MSE-optimal bandwidth on both sides, as in the Lecture 4 example
RD_VCE = "nn"                     # nearest-neighbour variance, as in the Lecture 4 example
RD_P = 1                          # local linear
BW_MULTIPLES = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
# Robustness of the headline RD estimate beyond the bandwidth multiples (Lecture 4: kernel, polynomial order, bandwidth selector).
# (key, label, overrides for run_rd). The reference row (key 'main') uses RD_KERNEL, RD_P and RD_BWSELECT.
RD_ROBUSTNESS = (
    ("uniform", "uniform kernel", {"kernel": "uni"}),
    ("p2", "local quadratic (p = 2)", {"p": 2}),
    ("msetwo", "MSE-optimal, separate bandwidth per side (msetwo)", {"bwselect": "msetwo"}),
    ("cerrd", "coverage-error-optimal bandwidth (cerrd)", {"bwselect": "cerrd"}),
)
RD_OVERRIDABLE = ("kernel", "p", "bwselect")   # run_rd arguments that a robustness row may change
MIN_RARE_OBS = 10                 # a binary covariate with fewer observations of its rarer value inside the bandwidth cannot be tested
HOLM_ALPHA = ALPHA                # family-wise error rate for the Holm correction
DONUTS = (200, 400, 600)          # yen cut out on each side of 10,000
SEED = 20261102                   # used by the bunching bootstrap only
BOOT_REPS = 500

BUNCH_BIN = 200                   # yen
BUNCH_RANGE = (4000, 16000)       # histogram range; the counts outside the response region fix the scale
BUNCH_HALF_WIDTH = 2500           # response region: 10,000 -/+ this many yen
BUNCH_WIDTHS_SENS = (2000, 2500, 3000)
BUNCH_REFERENCE = (31, 32)        # weeks before the announcement that give the counterfactual shape

REDEMPTION_GRID = (1.0, 0.75, 0.5, 0.25)
