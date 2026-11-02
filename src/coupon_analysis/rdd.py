"""Sections D and F: regression discontinuity designs (Lecture 4 notation).

Running variable R = spending in week 33, cutoff c. Sharp design D = 1{R >= c}, so the estimand is
    tau = lim_{r down c} E[Y | R = r] - lim_{r up c} E[Y | R = r].
At the 3,000 yen edge the coupon is on the *left*, so the coupon effect is -tau (`sign=-1`).
Estimates: local linear (p = 1), triangular kernel, MSE-optimal bandwidth, bias-corrected estimate with
robust confidence interval (Calonico, Cattaneo and Titiunik, 2014), via `rdrobust`.
"""
from __future__ import annotations

import contextlib
import io
import warnings

import numpy as np
import pandas as pd
from rddensity import rddensity
from rdrobust import rdrobust

from . import config as C
from .multitest import holm_adjust

COVARIATES = C.COVARIATES
PLACEBO_OUTCOMES = ["s30", "s31", "s32", "pre"]
LABELS = {"is_member": "member share", "male": "male share", "age_18_39": "share aged 18-39", "age_40_59": "share aged 40-59",
          "age_60p": "share aged 60+", "s30": "spending in week 30", "s31": "spending in week 31", "s32": "spending in week 32",
          "pre": "baseline spending (weeks 30-32)", "lag1": "lag placebo (week 32 to 33)", "lag2": "lag placebo (week 31 to 32)"}


MESSAGES: dict[str, int] = {}   # warnings and notices printed by rdrobust/rddensity, with counts; written to results.json


def _quiet(fn, *args, **kwargs):
    """rdrobust and rddensity print to stdout and raise warnings. Keep the log clean, but collect every message."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = fn(*args, **kwargs)
    for line in [ln.strip() for ln in buf.getvalue().splitlines() if ln.strip()] + [str(w.message) for w in caught]:
        MESSAGES[line] = MESSAGES.get(line, 0) + 1
    return out


def run_rd(y, r, c: float, sign: int = 1, h: float | None = None, b: float | None = None, **override) -> dict:
    """One RD estimate. Returns the bias-corrected effect with the robust 95% CI.
    `override` may change kernel, p or bwselect (robustness rows); everything else is fixed in config.py."""
    bad = set(override) - set(C.RD_OVERRIDABLE)
    if bad:
        raise ValueError(f"run_rd cannot override {sorted(bad)}. Fix: only {list(C.RD_OVERRIDABLE)} may differ from config.py.")
    y = np.asarray(y, dtype=float)
    r = np.asarray(r, dtype=float)
    kw = dict(c=c, p=C.RD_P, kernel=C.RD_KERNEL, bwselect=C.RD_BWSELECT, vce=C.RD_VCE)
    kw.update(override)
    if h is not None:
        kw.update(h=h, b=b if b is not None else h)
    o = _quiet(rdrobust, y, r, **kw)
    coef, se, ci, pv = o.coef.iloc[:, 0], o.se.iloc[:, 0], o.ci, o.pv.iloc[:, 0]
    lo, hi = float(ci.iloc[2, 0]), float(ci.iloc[2, 1])
    if sign < 0:
        lo, hi = -hi, -lo
    return {
        "effect": sign * float(coef.iloc[1]),          # bias-corrected
        "effect_conventional": sign * float(coef.iloc[0]),
        "se_robust": float(se.iloc[2]),
        "ci_lo": lo,
        "ci_hi": hi,
        "p": float(pv.iloc[2]),
        "h": float(o.bws.loc["h", "left"]),
        "h_right": float(o.bws.loc["h", "right"]),
        "b": float(o.bws.loc["b", "left"]),
        "n_left": int(o.N_h[0]),
        "n_right": int(o.N_h[1]),
    }


def density_test(values, c: float) -> dict:
    """Manipulation test of Cattaneo, Jansson and Ma (2019): H0 = the density of R is continuous at c."""
    x = np.asarray(values, dtype=float)
    d = _quiet(rddensity, x, c=c)
    return {
        "t": float(d.test["t_jk"]),
        "p": float(d.test["p_jk"]),
        "h_left": float(d.h["left"]),
        "h_right": float(d.h["right"]),
        "n_eff_left": int(d.n["eff_left"]),
        "n_eff_right": int(d.n["eff_right"]),
    }


def effects(cust: pd.DataFrame, c: float, sign: int) -> dict:
    r = cust.s33.values
    return {k: run_rd(cust[k].values, r, c, sign) for k in ("s34", "d34_pre")}


def balance(cust: pd.DataFrame, c: float) -> dict:
    """Covariates measured before the coupon should not jump at the cutoff (sign = +1: a plain jump)."""
    out = {}
    for k in COVARIATES:
        if cust.loc[(cust.s33 - c).abs() < C.RD_NEAR, k].nunique() < 2:
            out[k] = None            # no variation near the cutoff, nothing to test
            continue
        out[k] = run_rd(cust[k].values, cust.s33.values, c)
        inside = cust.loc[(cust.s33 - c).abs() <= out[k]["h"], k]
        out[k]["n_rare_in_h"] = int(min(inside.sum(), len(inside) - inside.sum()))   # observations of the rarer value inside the bandwidth
        out[k]["informative"] = out[k]["n_rare_in_h"] >= C.MIN_RARE_OBS
    return out


def placebo(cust: pd.DataFrame, c: float) -> dict:
    """Outcomes the coupon cannot have changed: spending in weeks 30-32, and lagged-design placebos."""
    out = {k: run_rd(cust[k].values, cust.s33.values, c) for k in PLACEBO_OUTCOMES}
    out["lag1"] = run_rd(cust.s33.values, cust.s32.values, c)   # R = week 32, Y = week 33
    out["lag2"] = run_rd(cust.s32.values, cust.s31.values, c)   # R = week 31, Y = week 32
    return out


def bandwidth_sensitivity(cust: pd.DataFrame, c: float, sign: int, base: dict) -> dict:
    """Re-estimate with h and b scaled by a common factor around the MSE-optimal pair."""
    out = {}
    for var in ("s34", "d34_pre"):
        b0 = base[var]
        rows = []
        for m in C.BW_MULTIPLES:
            est = run_rd(cust[var].values, cust.s33.values, c, sign, h=b0["h"] * m, b=b0["b"] * m)
            rows.append({"multiple": m, **est})
        out[var] = rows
    out["summary"] = {var: {"min_effect": min(r["effect"] for r in out[var]), "max_effect": max(r["effect"] for r in out[var]),
                            "n_ci_excludes_zero": sum(not (r["ci_lo"] <= 0 <= r["ci_hi"]) for r in out[var]), "n_bandwidths": len(out[var])}
                      for var in ("s34", "d34_pre")}
    return out


def robustness(cust: pd.DataFrame, c: float, sign: int, base: dict, bw: dict) -> dict:
    """Headline estimate under other choices (Lecture 4: bandwidth, kernel, polynomial order, selector).
    Rows: the reference (`main`), the bandwidth multiples already computed in `bw`, then one row per entry of config.RD_ROBUSTNESS."""
    out = {}
    for var in ("s34", "d34_pre"):
        rows = [{"key": "main", "label": "reference: triangular, p = 1, mserd", **base[var]}]
        for e in bw[var]:
            if e["multiple"] != 1.0:
                rows.append({"key": f"bw_{round(100 * e['multiple']):03d}", "label": f"{e['multiple']:.2f} x h (triangular, p = 1)", **e})
        for key, label, over in C.RD_ROBUSTNESS:
            rows.append({"key": key, "label": label, **run_rd(cust[var].values, cust.s33.values, c, sign, **over)})
        out[var] = rows
    out["by_key"] = {var: {r["key"]: r for r in out[var]} for var in ("s34", "d34_pre")}
    out["summary"] = {var: {"n_specs": len(out[var]),
                            "min_effect": min(r["effect"] for r in out[var]), "max_effect": max(r["effect"] for r in out[var]),
                            "n_ci_excludes_zero": sum(not (r["ci_lo"] <= 0 <= r["ci_hi"]) for r in out[var]),
                            "n_ci_includes_zero": sum(r["ci_lo"] <= 0 <= r["ci_hi"] for r in out[var]),
                            "all_positive": all(r["effect"] > 0 for r in out[var])}
                      for var in ("s34", "d34_pre")}
    return out


def multiple_testing(named: dict) -> dict:
    """Raw and Holm-adjusted p-values over all balance and placebo tests of one cutoff (Lecture 2, deck 03, slide 10)."""
    tests = [(k, v) for k, v in named.items() if v is not None]
    raw = [v["p"] for _, v in tests]
    adj = holm_adjust(raw)
    rows = [{"name": k, "p": p, "p_holm": a, "informative": v.get("informative", True)} for (k, v), p, a in zip(tests, raw, adj)]
    thin = [r for r in rows if not r["informative"]]
    good = [r for r in rows if r["informative"]]
    good_adj = holm_adjust([r["p"] for r in good])
    return {
        "n_tests": len(rows),
        "n_reject_5pct": sum(r["p"] < C.ALPHA for r in rows),
        "n_reject_holm": sum(r["p_holm"] < C.HOLM_ALPHA for r in rows),
        "min_p": float(min(raw)),
        "min_p_holm": float(min(adj)),
        "rejected_text": ", ".join(r["name"] for r in rows if r["p"] < C.ALPHA) or "none",
        "uninformative_text": ", ".join(r["name"] for r in thin) or "none",
        "n_uninformative": len(thin),
        "n_tests_informative": len(good),
        "n_reject_holm_informative": sum(a < C.HOLM_ALPHA for a in good_adj),
        "min_p_holm_informative": float(min(good_adj)),
        "tests": rows,
    }


def suite(cust: pd.DataFrame, c: float, sign: int) -> dict:
    eff = effects(cust, c, sign)
    bal, plc = balance(cust, c), placebo(cust, c)
    named = {**{LABELS[k]: v for k, v in bal.items()}, **{LABELS[k]: v for k, v in plc.items()}}
    pre_p = [plc[k]["p"] for k in PLACEBO_OUTCOMES]
    bw = bandwidth_sensitivity(cust, c, sign, eff)
    return {
        "cutoff": c,
        "sign": sign,
        "effects": eff,
        "balance": bal,
        "placebo": plc,
        "bandwidth_sensitivity": bw,
        "robustness": robustness(cust, c, sign, eff, bw),
        "density_w33": density_test(cust.s33, c),
        "density_w32": density_test(cust.s32, c),
        "multiple_testing": multiple_testing(named),
        "placebo_pre_p_range": [float(min(pre_p)), float(max(pre_p))],
        "placebo_pre_effect_range": [float(min(plc[k]["effect"] for k in PLACEBO_OUTCOMES)), float(max(plc[k]["effect"] for k in PLACEBO_OUTCOMES))],
    }


def donut(cust: pd.DataFrame, c: float, widths=C.DONUTS) -> list[dict]:
    """Drop customers within `w` yen of the cutoff, where the bunching sits, and estimate again."""
    rows = []
    for w in (0, *widths):
        sub = cust[(cust.s33 - c).abs() >= w]
        row = {"donut": w, "n": len(sub)}
        for var in ("s34", "d34_pre", "pre"):
            row[var] = run_rd(sub[var].values, sub.s33.values, c)
        rows.append(row)
    return rows


def run(cust: pd.DataFrame) -> dict:
    MESSAGES.clear()
    return {
        "n_density_tests": 2 * len(C.CUTOFFS),
        **{key: suite(cust, c, sign) for key, (c, sign) in C.RD_DESIGNS.items()},
        C.RD_INVALID[0]: {
            "effects": effects(cust, C.RD_INVALID[1], +1),
            "placebo": placebo(cust, C.RD_INVALID[1]),
            "density_w33": density_test(cust.s33, C.RD_INVALID[1]),
            "density_w32": density_test(cust.s32, C.RD_INVALID[1]),
            "donut": donut(cust, C.RD_INVALID[1]),
        },
    }
