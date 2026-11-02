"""Markdown tables for the appendix and the report. Each builder takes the results dict and returns a string."""
from __future__ import annotations

from . import config as C
from .fmt import ci, mil, num, pct, pval


def _md(header: list[str], rows: list[list[str]], align: str | None = None) -> str:
    align = align or ("l" + "r" * (len(header) - 1))
    sep = ["---:" if a == "r" else ":---" for a in align]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(sep) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def groups(R) -> str:
    t = R["descriptives"]["group_table"]
    rows = []
    for g in C.GROUP_ORDER:
        r = t[g]
        rows.append([g, num(r["n"]), num(r["pre"]), num(r["s33"]), num(r["s34"]), pct(r["is_member"]), pct(r["male"]), pct(r["age_18_39"])])
    return _md(["Group (by week-33 spending)", "Customers", "Mean wk 30-32", "Week 33", "Week 34", "Member", "Male", "Age 18-39"], rows)


def naive(R) -> str:
    n = R["descriptives"]["naive"]
    rows = [
        ["3000 coupon vs 3,000-9,999", num(n["w34_3000_vs_mid"]), num(n["pre_3000_vs_mid"]), pct(n["pre_3000_vs_mid"] / n["w34_3000_vs_mid"])],
        ["500 coupon vs <1,000", num(n["w34_500_vs_below"]), num(n["pre_500_vs_below"]), pct(n["pre_500_vs_below"] / n["w34_500_vs_below"])],
        ["Any coupon vs no coupon", num(n["w34_any_vs_none"]), num(n["pre_any_vs_none"]), pct(n["pre_any_vs_none"] / n["w34_any_vs_none"])],
    ]
    return _md(["Comparison", "Difference in week 34", "Same difference, weeks 30-32", "Share already there before"], rows)


def _rd_row(label, e):
    return [label, num(e["effect"], 0, True), ci(e["ci_lo"], e["ci_hi"]), pval(e["p"]), num(e["h"]), f"{e['n_left']} / {e['n_right']}"]


def rd_effects(R) -> str:
    r = R["rd"]
    rows = [
        _rd_row("1,000 (500 coupon above): week 34", r["at1000"]["effects"]["s34"]),
        _rd_row("1,000: week 34 minus baseline", r["at1000"]["effects"]["d34_pre"]),
        _rd_row("3,000 (500 coupon below): week 34", r["at3000"]["effects"]["s34"]),
        _rd_row("3,000: week 34 minus baseline", r["at3000"]["effects"]["d34_pre"]),
        _rd_row("10,000 (3000 coupon above): week 34, not valid", r["at10000"]["effects"]["s34"]),
        _rd_row("10,000: week 34 minus baseline, not valid", r["at10000"]["effects"]["d34_pre"]),
    ]
    return _md(["Cutoff and outcome", "Effect (yen)", "Robust 95% CI", "p", "h (yen)", "Effective n left / right"], rows)


def density(R) -> str:
    r = R["rd"]
    rows = []
    for key, c in (("at1000", 1000), ("at3000", 3000), ("at10000", 10000)):
        d33, d32 = r[key]["density_w33"], r[key]["density_w32"]
        rows.append([f"{c:,}", num(d32["t"], 2), pval(d32["p"]), num(d33["t"], 2), pval(d33["p"])])
    return _md(["Cutoff", "Week 32: T", "Week 32: p", "Week 33: T", "Week 33: p"], rows)


def balance(R) -> str:
    """Balance and placebo tests with raw and Holm-adjusted p-values (Lecture 2, deck 03). A dagger marks a covariate that is
    nearly constant inside the bandwidth, so the test cannot say much."""
    from .rdd import LABELS
    names = {"is_member": "Member", "male": "Male", "age_18_39": "Age 18-39", "age_40_59": "Age 40-59", "age_60p": "Age 60+",
             "s30": "Spending wk 30", "s31": "Spending wk 31", "s32": "Spending wk 32", "pre": "Mean wk 30-32",
             "lag1": "Lag placebo (R wk 32, Y wk 33)", "lag2": "Lag placebo (R wk 31, Y wk 32)"}
    keys = ("at1000", "at3000")
    holm = {key: {t["name"]: t for t in R["rd"][key]["multiple_testing"]["tests"]} for key in keys}
    rows = []
    for k, label in names.items():
        cells = [label]
        for key in keys:
            e = R["rd"][key]["balance"].get(k) or R["rd"][key]["placebo"].get(k)
            if e is None:
                cells += ["n/a", "n/a", "n/a"]
                continue
            nd = 3 if k in R["rd"][key]["balance"] else 0
            t = holm[key][LABELS[k]]
            mark = "" if t["informative"] else " \u2020"
            cells += [num(e["effect"], nd, True), pval(e["p"]) + mark, pval(t["p_holm"]) + mark]
        rows.append(cells)
    mt = {key: R["rd"][key]["multiple_testing"] for key in keys}
    rows.append(["Tests run"] + sum(([str(mt[k]["n_tests"]), "", ""] for k in keys), []))
    rows.append(["Rejected at 5% (raw p / after Holm)"] + sum((["", str(mt[k]["n_reject_5pct"]), str(mt[k]["n_reject_holm"])] for k in keys), []))
    rows.append(["Smallest p (raw / after Holm)"] + sum((["", pval(mt[k]["min_p"]), pval(mt[k]["min_p_holm"])] for k in keys), []))
    return _md(["Variable", "1,000: jump", "p", "Holm p", "3,000: jump", "p", "Holm p"], rows)


def bandwidth(R) -> str:
    rows = []
    for key, c in (("at1000", 1000), ("at3000", 3000)):
        for var, lab in (("s34", "week 34"), ("d34_pre", "change vs baseline")):
            for e in R["rd"][key]["bandwidth_sensitivity"][var]:
                rows.append([f"{c:,}, {lab}", f"{e['multiple']:.2f} x h", num(e["h"]), num(e["effect"], 0, True), ci(e["ci_lo"], e["ci_hi"]), pval(e["p"])])
    return _md(["Cutoff, outcome", "Bandwidth", "h (yen)", "Effect (yen)", "Robust 95% CI", "p"], rows)


def robustness(R) -> str:
    """Headline RD estimate under other bandwidths, kernel, polynomial order and bandwidth selector (Lecture 4)."""
    rows = []
    for key, c in (("at1000", "1,000"), ("at3000", "3,000")):
        rb = R["rd"][key]["robustness"]
        rows.append([f"**{c} yen edge**", "", "", "", "", "", ""])
        for lv, ch in zip(rb["s34"], rb["d34_pre"]):
            rows.append([lv["label"], num(lv["effect"], 0, True), ci(lv["ci_lo"], lv["ci_hi"]), pval(lv["p"]),
                         num(ch["effect"], 0, True), ci(ch["ci_lo"], ch["ci_hi"]), pval(ch["p"])])
    return _md(["Specification", "Level: effect", "Robust 95% CI", "p", "Change vs baseline: effect", "Robust 95% CI", "p"], rows)


def did_means(R) -> str:
    """Card-Krueger 2x2 table in the notation of Lecture 5: four cell means, the two changes, the two gaps, alpha."""
    k, m = R["did"]["card_krueger"], R["did"]["main"]
    rows = [
        ["Coupon group (G = 1)", num(k["treated_pre"]), num(k["treated_post"]), num(k["change_treated"], 0, True)],
        ["Comparison group (G = 0)", num(k["control_pre"]), num(k["control_post"]), num(k["change_control"], 0, True)],
        ["Coupon minus comparison", num(k["gap_pre"], 0, True), num(k["gap_post"], 0, True),
         f"**{num(k['did'], 0, True)}** = alpha (ATT), regression {num(m['estimate'], 0, True)} {ci(m['ci_lo'], m['ci_hi'])}"],
    ]
    return _md(["Mean weekly spending (yen)", "Before, T = 0 (mean wk 30-32)", "After, T = 1 (week 34)", "After minus before"], rows)


def ck_naive(R) -> str:
    """The two naive comparisons that the 2x2 table makes visible, and the bias each one contains."""
    k = R["did"]["card_krueger"]
    rows = [
        ["Before-after, coupon group (T = 1 minus T = 0 for G = 1)", num(k["naive_before_after"], 0, True), "time change of the comparison group", num(k["bias_time"], 0, True), "time effect"],
        ["Coupon group against comparison group after the coupon (G = 1 minus G = 0 at T = 1)", num(k["naive_cross_section"], 0, True), "gap that existed before the coupon", num(k["bias_selection"], 0, True), "selection bias term"],
        ["Difference-in-differences alpha (ATT)", num(k["did"], 0, True), "nothing: both biases drop out under parallel trends", num(0), "none"],
    ]
    return _md(["Comparison", "Estimate (yen)", "Estimate = alpha plus the", "Bias (yen)", "Term in Lecture 5"], rows, align="lrlrl")


def did_robust(R) -> str:
    d = R["did"]
    rows = [
        ["Baseline: DiD, mean of weeks 30-32 (main)", num(d["main"]["estimate"], 0, True), ci(d["main"]["ci_lo"], d["main"]["ci_hi"])],
        ["Baseline: week 32 only", num(d["baseline_week32"]["estimate"], 0, True), ci(d["baseline_week32"]["ci_lo"], d["baseline_week32"]["ci_hi"])],
        ["With covariates (member, gender, age; interacted with T)", num(d["covariates"]["estimate"], 0, True), ci(d["covariates"]["ci_lo"], d["covariates"]["ci_hi"])],
        ["Linear pre-trend of the gap extended to week 34", num(d["trend_adjusted"]["estimate"], 0, True), "n/a"],
        ["Proportional DiD (week 34 / own baseline - 1), in yen at the treated baseline", num(d["proportional"]["att_yen"], 0, True), ci(d["proportional"]["ci_lo_yen"], d["proportional"]["ci_hi_yen"])],
        ["Without everyone with 8,000-11,999 yen in week 33 (treated 12,000 or more; control 3,000-7,999)", num(d["band_dropped"]["estimate"], 0, True), ci(d["band_dropped"]["ci_lo"], d["band_dropped"]["ci_hi"])],
        ["All treated, but only controls with 3,000-7,999 yen (none just below 10,000)", num(d["control_far"]["estimate"], 0, True), ci(d["control_far"]["ci_lo"], d["control_far"]["ci_hi"])],
        ["Placebo DiD (groups by week 31, baseline week 30, outcome week 32)", num(d["placebo"]["estimate"], 0, True), ci(d["placebo"]["ci_lo"], d["placebo"]["ci_hi"])],
        ["Main estimate minus placebo", num(d["placebo_adjusted"], 0, True), "n/a"],
    ]
    return _md(["Specification", "Estimate (yen)", "95% CI (cluster-robust)"], rows)


def event_study(R) -> str:
    es = R["did"]["event_study"]["coefficients"]
    rows = []
    for w in C.WEEKS:
        e = es[str(w)]
        note = {"32": "reference", "33": "group defined by this week (mechanical)", "34": "coupon valid"}.get(str(w), "before announcement")
        rows.append([str(w), num(e["estimate"], 0, True) if w != 32 else "0", ci(e["ci_lo"], e["ci_hi"]) if w != 32 else "-", note])
    rows.append(["Joint test, weeks 30 and 31 = 0", "", f"p {pval(R['did']['event_study']['pretrend_joint_p'])}", ""])
    return _md(["Week", "Gap relative to week 32 (yen)", "95% CI", "Note"], rows)


def donut(R) -> str:
    rows = []
    for d in R["rd"]["at10000"]["donut"]:
        rows.append([("none" if d["donut"] == 0 else f"{d['donut']}"), num(d["n"]),
                     num(d["pre"]["effect"], 0, True), num(d["d34_pre"]["effect"], 0, True), ci(d["d34_pre"]["ci_lo"], d["d34_pre"]["ci_hi"]),
                     num(d["s34"]["effect"], 0, True), ci(d["s34"]["ci_lo"], d["s34"]["ci_hi"])])
    return _md(["Donut (yen each side)", "n", "Jump in baseline", "Change vs baseline", "Robust 95% CI", "Week 34", "Robust 95% CI"], rows)


def bunching(R) -> str:
    b = R["bunching"]
    w = b["week33"]
    rows = [
        ["Missing mass below 10,000 (customers)", num(w["missing_mass"]), ci(*b["missing_mass_ci"])],
        ["Excess mass above 10,000 (customers)", num(w["excess_mass"]), ""],
        ["Mean origin of the missing mass (yen)", num(w["origin"]), ""],
        ["Mean landing point of the excess mass (yen)", num(w["landing"]), ""],
        ["Stretch (yen per customer)", num(w["stretch"]), ci(*b["stretch_ci"])],
        ["Week-33 spending added by the announcement (yen)", num(w["effect_total"]), ci(*b["effect_total_ci"])],
        ["Same, per eligible customer (yen)", num(b["effect_per_eligible"], 0), ""],
        ["Placebo (week 32 against weeks 30-31): missing mass", num(b["week32_placebo"]["missing_mass"]), ""],
    ]
    for s in b["sensitivity"]:
        rows.append([f"Sensitivity: response region +/- {num(s['half_width'])}: missing mass / total yen", num(s["missing_mass"]), num(s["effect_total"])])
    return _md(["Quantity", "Estimate", "95% bootstrap CI / second value"], rows)


def _cb_row(label, row, extra=""):
    be = row["by_redemption"]
    return [label, num(row["n_eligible"]), num(row["effect_per_customer"]), mil(row["incremental_revenue"], 2), mil(row["cost_full_redemption"], 2),
            pct(be["100"]["break_even_margin"]) if be["100"]["break_even_margin"] else "n/a",
            pct(be["50"]["break_even_margin"]) if be["50"]["break_even_margin"] else "n/a",
            pct(be["25"]["break_even_margin"]) if be["25"]["break_even_margin"] else "n/a"]


def costbenefit(R) -> str:
    cb = R["costbenefit"]
    c5, c3 = cb["coupon_500"], cb["coupon_3000"]
    rows = [
        _cb_row("500 yen: RD at 1,000, week 34 level", c5["at_lower_edge"]),
        _cb_row("500 yen: RD at 1,000, change vs baseline", c5["at_lower_edge_diff"]),
        _cb_row("500 yen: lower end of CI at 1,000", c5["at_lower_edge_ci_low"]),
        _cb_row("3000 yen: DiD in levels + week-33 effect", c3["did_levels"]),
        _cb_row("3000 yen: DiD in proportions + week-33 effect", c3["did_proportional"]),
        _cb_row("3000 yen: lower end of DiD CI", c3["did_levels_ci_low"]),
    ]
    return _md(["Scenario", "Eligible", "Effect per customer (yen)", "Incremental spending (m yen)", "Cost at full redemption (m yen)",
                "Break-even margin, 100% redemption", "50% redemption", "25% redemption"], rows)


def summary(R) -> str:
    """Report Table 1."""
    r, d, cb = R["rd"], R["did"], R["costbenefit"]
    e1, e1d, e3 = r["at1000"]["effects"]["s34"], r["at1000"]["effects"]["d34_pre"], r["at3000"]["effects"]["s34"]
    m, prop = d["main"], d["proportional"]
    c5, c3 = cb["coupon_500"], cb["coupon_3000"]
    be = lambda row: pct(row["by_redemption"]["100"]["break_even_margin"])
    est = lambda e, lo="ci_lo", hi="ci_hi", k="effect": f"{num(e[k], 0, True)} {ci(e[lo], e[hi])}"
    rows = [
        ["500 yen at 1,000, vs baseline", "RD", est(e1d), be(c5["at_lower_edge_diff"])],
        ["500 yen at 1,000, level", "RD", est(e1), be(c5["at_lower_edge"])],
        ["500 yen at 3,000, level", "RD", est(e3), "no effect"],
        ["3000 yen, levels", "DiD", est(m, k="estimate"), be(c3["did_levels"])],
        ["3000 yen, proportional", "DiD", est(prop, "ci_lo_yen", "ci_hi_yen", "att_yen"), be(c3["did_proportional"])],
    ]
    return _md(["Coupon and estimate", "Design", "Effect, yen [95% CI]", "Break-even margin"], rows, align="llrr")


def options(R) -> str:
    rows = [
        ["(none)", "Everything: validate, estimate, draw, write results.json and appendix.md, render appendix and report to HTML and PDF."],
        ["`--check`", "Only validate the data file and print errors, warnings and notes. Writes nothing. Exit code 1 if the data break the contract."],
        ["`--no-pdf`", "Write results, figures, appendix.md and appendix.html but skip the PDFs (no Chrome needed; the page check of the report is skipped too)."],
        ["`--no-render`", "Write results.json, figures and appendix.md only."],
        ["`--regen-report`", "Rebuild text.md from its template. Without it, an existing text.md is never overwritten, because it is the file that gets edited by hand."],
        ["`--only figures`", "Redraw the figures from the existing `results.json` and the data."],
        ["`--only report`", "Render only `assignment_2226237U_simon_jensen.pdf` from the current `text.md` (fast; use after editing the text). Needs an existing `results.json`."],
        ["`--data PATH`", "Read another CSV with the same columns (for example a corrected export)."],
        ["`--root DIR`", "Write all outputs into DIR instead of the project folder."],
        ["`-q`", "Quiet: print only warnings and errors."],
    ]
    return _md(["Option", "Effect"], rows, align="ll")


def outputs(R) -> str:
    rows = [
        ["`results.json`", "Every estimate, standard error, p-value and table entry. The single source of every number below and in the report."],
        ["`figures/*.png`", "All figures, 200 dpi."],
        ["`appendix.md`", "This document as Markdown, filled from `results.json`."],
        ["`appendix.html`", "This document as one self-contained HTML file (figures embedded)."],
        ["`appendix_2226237U_simon_jensen.pdf`", "This document as a PDF."],
        ["`text.md`", "Source of the report. Created from its template on the first run; edited by hand afterwards."],
        ["`assignment_2226237U_simon_jensen.pdf`", "The report, at most three pages."],
        ["`build/`", "Intermediate HTML of the report. Can be deleted."],
    ]
    return _md(["File", "What it contains"], rows, align="ll")


def checks(R) -> str:
    rows = [
        ["Columns and types", "All eleven columns exist; numeric columns are numbers; flags are 0/1; gender and age_category take only the documented values.", "Error"],
        ["Balanced panel", "10,000 ids (1 to 10,000), weeks 30 to 34, one row per id and week, 50,000 rows.", "Error"],
        ["Missing values", "Only amount_spent_last_week_yen in week 30 is missing, and all of it is.", "Error"],
        ["Lag column", "amount_spent_last_week_yen equals amount_spent_yen of the previous week for every customer.", "Error"],
        ["Constant per customer", "is_member, gender, age_category and the four group flags do not change across weeks.", "Error"],
        ["One group per customer", "Exactly one of the four group flags is 1.", "Error"],
        ["Flags against the written rule", "A flag must agree with week-33 spending: below 1,000; 1,000 to 2,999; 3,000 to 9,999; 10,000 or more. Up to five disagreements are reported, more than five stop the run.", "Warning, then error"],
        ["Negative spending", "Returns appear as negative amounts. They are counted and kept.", "Note"],
    ]
    return _md(["Check", "What must hold", "If violated"], rows, align="lll")


def errors(R) -> str:
    rows = [
        ["`FileNotFoundError: Data file not found`", "The CSV is not next to `pyproject.toml`.", "Copy `assignment_data_panel_obs.csv` there, or pass `--data PATH`."],
        ["`The input data violate the contract (n problem(s))`", "The file differs from the documented panel; the message lists every problem with the first id and week.", "Fix the listed items; run `--check` to test without running the analysis."],
        ["`Google Chrome not found`", "Chrome is not at the default macOS path or on the PATH.", "Set `COUPON_CHROME` to the browser binary, or use `--no-pdf`."],
        ["`Could not find a version that satisfies the requirement`", "uv cannot reach the package index.", "Check the network and run `uv sync` again; the versions are fixed in `uv.lock`."],
        ["`ModuleNotFoundError: coupon_analysis`", "The command was run outside the project folder or without `uv run`.", "`cd` into the folder with `pyproject.toml` and use `uv run python -m coupon_analysis`."],
        ["`results.json not found` with `--only`", "The full pipeline has not run yet.", "Run `uv run python -m coupon_analysis` once."],
        ["`text.md line n: x is not in results.json` (exit code 3)", "A number in the hand-edited text is stale or mistyped.", "Edit the number in `text.md`, or run `--regen-report` (discards manual edits)."],
        ["Report has more than three pages (warning, exit code 3)", "`text.md` was edited and became longer.", "Shorten the text; the page count is printed after every run."],
        ["`Unknown results path` while filling a template", "A placeholder in a template names a key that is not in `results.json`.", "Open `results.json`, find the right key, fix the template."],
    ]
    return _md(["Message", "Cause", "Fix"], rows, align="lll")


def _reading(dens_p: float, n_reject_holm: int) -> str:
    if dens_p < 0.01 or n_reject_holm > 0:
        return "invalid"
    return "valid, density borderline" if dens_p < 0.05 else "valid"


def diagnostics(R) -> str:
    """Report Table 2: validity checks per design."""
    r, d = R["rd"], R["did"]
    def rd_row(key, cutoff):
        t = r[key]["multiple_testing"]
        return [cutoff, pval(r[key]["density_w33"]["p"]), f"{t['n_reject_5pct']} of {t['n_tests']} / {t['n_reject_holm']}", _reading(r[key]['density_w33']['p'], t['n_reject_holm'])]
    p10 = r["at10000"]
    rows = [
        rd_row("at1000", "RD at 1,000"),
        rd_row("at3000", "RD at 3,000"),
        ["RD at 10,000", pval(p10["density_w33"]["p"]), "n/a", f"invalid, baseline {num(p10['placebo']['pre']['effect'], 0, True)} yen"],
        ["DiD, 3000 yen", "n/a", "n/a", f"pre-trend p {pval(d['event_study']['pretrend_joint_p'])}, placebo {num(d['placebo']['estimate'], 0, True)} yen"],
    ]
    return _md(["Design", "Density p", "Tests rejected, raw / Holm", "Reading"], rows, align="lrrl")


BUILDERS = {k: v for k, v in globals().items() if callable(v) and not k.startswith("_") and k not in ("ci", "mil", "num", "pct", "pval")}
