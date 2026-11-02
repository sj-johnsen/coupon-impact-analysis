"""Section E: difference-in-differences for the 3000 yen coupon (Lecture 5 notation).

    Y_it = b0 + b1 T_t + b2 G_i + alpha D_it + e_it,   D_it = T_t * G_i
G = 1 for customers with week-33 spending >= 10,000 (coupon), G = 0 for 3,000-9,999 (no coupon).
T = 1 in week 34 (coupon valid), T = 0 in the baseline weeks 30-32 (before the announcement).
alpha is the ATT under parallel trends. Standard errors are clustered by customer.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from . import config as C

COV = C.DID_COVARIATES


def _masks(cust: pd.DataFrame, week: int = C.RUNNING_WEEK):
    s = cust[f"s{week}"]
    return s >= C.DID_TREATED_MIN, (s >= C.DID_CONTROL_MIN) & (s < C.DID_TREATED_MIN)


def _fit(model, groups):
    return model.fit(cov_type="cluster", cov_kwds={"groups": groups})


def _pack(m, name="D", extra=None) -> dict:
    ci = m.conf_int().loc[name]
    out = {"estimate": float(m.params[name]), "se": float(m.bse[name]),
           "ci_lo": float(ci[0]), "ci_hi": float(ci[1]), "p": float(m.pvalues[name])}
    out.update(extra or {})
    return out


def _long(cust: pd.DataFrame, treated: pd.Series, control: pd.Series, pre_weeks, post_week) -> pd.DataFrame:
    """Two rows per customer: baseline (mean of pre weeks) and post. Same point estimate as the 4-week panel."""
    keep = treated | control
    base = cust.loc[keep]
    pre = base[[f"s{w}" for w in pre_weeks]].mean(axis=1)
    frames = []
    for t, y in ((0, pre), (1, base[f"s{post_week}"])):
        f = base[["is_member", "male", "age_40_59", "age_60p"]].copy()
        f["y"], f["T"], f["G"] = y, t, treated[keep].astype(int)
        f["id"] = base.index
        frames.append(f)
    out = pd.concat(frames)
    out["D"] = out["T"] * out["G"]
    return out


def did_2x2(cust, treated, control, pre_weeks=C.PRE_WEEKS, post_week=C.OUTCOME_WEEK, covariates=False) -> dict:
    df = _long(cust, treated, control, pre_weeks, post_week)
    if covariates:
        for c in COV:                                    # centre at the treated mean: alpha stays the ATT
            df[c] = df[c] - df.loc[df.G == 1, c].mean()
        rhs = "T + G + D + " + " + ".join(COV) + " + " + " + ".join(f"{c}:T" for c in COV)
    else:
        rhs = "T + G + D"
    m = _fit(smf.ols(f"y ~ {rhs}", df), df["id"])
    means = df.groupby(["G", "T"]).y.mean()
    return _pack(m, extra={
        "n_treated": int(treated.sum()), "n_control": int(control.sum()),
        "mean_treated_pre": float(means[1, 0]), "mean_treated_post": float(means[1, 1]),
        "mean_control_pre": float(means[0, 0]), "mean_control_post": float(means[0, 1]),
    })


def card_krueger(cust, treated, control, pre_weeks=C.PRE_WEEKS, post_week=C.OUTCOME_WEEK) -> dict:
    """The 2x2 table of Card and Krueger (Lecture 5, slides 8-17), computed from the raw cell means.

    Cells: mean spending of G = 1 and G = 0 in the baseline (T = 0) and in the post week (T = 1).
    Two naive comparisons and the bias each one contains:
      before-after for G = 1:   (treated post - treated pre)  = alpha + time change of the comparison group
      treated vs comparison after: (treated post - comparison post) = alpha + gap that existed before (selection term)
    alpha = difference of the two changes = the OLS coefficient on D in did_2x2 (the regression is saturated).
    """
    pre = cust[[f"s{w}" for w in pre_weeks]].mean(axis=1)
    post = cust[f"s{post_week}"]
    cell = {"treated_pre": float(pre[treated].mean()), "treated_post": float(post[treated].mean()),
            "control_pre": float(pre[control].mean()), "control_post": float(post[control].mean())}
    change_t = cell["treated_post"] - cell["treated_pre"]
    change_c = cell["control_post"] - cell["control_pre"]
    gap_pre = cell["treated_pre"] - cell["control_pre"]
    gap_post = cell["treated_post"] - cell["control_post"]
    did = change_t - change_c
    return {
        **cell,
        "change_treated": change_t, "change_control": change_c,
        "gap_pre": gap_pre, "gap_post": gap_post,
        "did": did,
        "naive_before_after": change_t, "bias_time": change_c,
        "naive_cross_section": gap_post, "bias_selection": gap_pre,
        "identity_before_after": change_t - (did + change_c),     # both identities hold exactly; stored so a test can see it
        "identity_cross_section": gap_post - (did + gap_pre),
    }


def did_proportional(cust, treated, control) -> dict:
    """Parallel trends in proportions: outcome = week-34 spending / own baseline - 1, then back to yen."""
    keep = (treated | control) & (cust.pre > 0)
    d = cust.loc[keep].copy()
    d["rel"] = d.s34 / d.pre - 1
    d["G"] = treated[keep].astype(int)
    m = smf.ols("rel ~ G", d).fit(cov_type="HC1")
    base = float(d.loc[d.G == 1, "pre"].mean())
    return {"att_pct": float(m.params["G"]), "se_pct": float(m.bse["G"]), "baseline_treated": base,
            "att_yen": float(m.params["G"]) * base,
            "ci_lo_yen": float(m.conf_int().loc["G", 0]) * base, "ci_hi_yen": float(m.conf_int().loc["G", 1]) * base,
            "mean_growth_treated": float(d.loc[d.G == 1, "rel"].mean()), "mean_growth_control": float(d.loc[d.G == 0, "rel"].mean())}


def event_study(cust, treated, control, ref_week: int = 32) -> dict:
    """Difference between the groups in week t, relative to the reference week (customer fixed effects)."""
    keep = treated | control
    base = cust.loc[keep]
    G = treated[keep].astype(int)
    weeks = [w for w in C.WEEKS if w != ref_week]
    rows = []
    for w in weeks:
        rows.append(pd.DataFrame({"d": base[f"s{w}"] - base[f"s{ref_week}"], "week": w, "G": G, "id": base.index}))
    df = pd.concat(rows)
    for w in weeks:
        df[f"t{w}"] = (df.week == w).astype(int)
        df[f"G{w}"] = df[f"t{w}"] * df.G
    rhs = " + ".join(f"t{w}" for w in weeks) + " + " + " + ".join(f"G{w}" for w in weeks)
    m = _fit(smf.ols(f"d ~ 0 + {rhs}", df), df["id"])
    coefs = {str(w): _pack(m, f"G{w}") for w in weeks}
    coefs[str(ref_week)] = {"estimate": 0.0, "se": 0.0, "ci_lo": 0.0, "ci_hi": 0.0, "p": 1.0}
    pre = [f"G{w}" for w in weeks if w < ref_week]
    wald = m.wald_test(", ".join(f"{p} = 0" for p in pre), scalar=True)
    return {"reference_week": ref_week, "coefficients": coefs,
            "pretrend_joint_p": float(wald.pvalue), "pretrend_weeks": [w for w in weeks if w < ref_week]}


def did_band(cust, drop_band: bool) -> dict:
    """Robustness to selection on the manipulated week: keep only customers well away from 10,000 yen.
    drop_band=True: treated >= upper end of the band, control below the lower end of the band.
    drop_band=False: all treated, but only controls below the lower end of the band (no controls just under 10,000)."""
    lo, hi = C.DID_BAND
    s = cust.s33
    t = (s >= hi) if drop_band else (s >= C.DID_TREATED_MIN)
    c = (s >= C.DID_CONTROL_MIN) & (s < lo)
    return did_2x2(cust, t, c)


def placebo_did(cust) -> dict:
    """Same design, one step back: groups by week-31 spending, baseline week 30, outcome week 32. No coupon exists."""
    t, c = _masks(cust, 31)
    return did_2x2(cust, t, c, pre_weeks=(30,), post_week=32)


def trend_adjusted(gap: dict) -> dict:
    """Extend the pre-announcement trend of the group gap (weeks 30-32) to week 34 and subtract it."""
    slope = (gap["32"] - gap["30"]) / 2.0
    predicted = gap["32"] + 2 * slope
    return {"slope_per_week": slope, "predicted_gap_w34": predicted, "estimate": gap["34"] - predicted}


def run(cust: pd.DataFrame) -> dict:
    t, c = _masks(cust)
    main = did_2x2(cust, t, c)
    plc = placebo_did(cust)
    gap = {str(w): float(cust.loc[t, f"s{w}"].mean() - cust.loc[c, f"s{w}"].mean()) for w in C.WEEKS}
    return {
        "main": main,
        "card_krueger": card_krueger(cust, t, c),
        "covariates": did_2x2(cust, t, c, covariates=True),
        "baseline_week32": did_2x2(cust, t, c, pre_weeks=(32,)),
        "proportional": did_proportional(cust, t, c),
        "event_study": event_study(cust, t, c),
        "placebo": plc,
        "placebo_share_of_main": plc["estimate"] / main["estimate"],
        "band_dropped": did_band(cust, True),
        "control_far": did_band(cust, False),
        "pretrend_w30_share_of_gap": abs(float(cust.loc[t, "s30"].mean() - cust.loc[c, "s30"].mean()
                                               - (cust.loc[t, "s32"].mean() - cust.loc[c, "s32"].mean()))) / abs(float(cust.loc[t, "s32"].mean() - cust.loc[c, "s32"].mean())),
        "placebo_adjusted": main["estimate"] - plc["estimate"],
        "gap_by_week": gap,
        "trend_adjusted": {**trend_adjusted(gap), "shift_vs_main": main["estimate"] - trend_adjusted(gap)["estimate"]},
    }
