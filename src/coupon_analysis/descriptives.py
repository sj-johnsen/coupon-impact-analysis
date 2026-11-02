"""Section C: what the Executive saw, and why it misleads (selection and mean reversion)."""
from __future__ import annotations

import pandas as pd

from . import config as C

WEEK_COLS = [f"s{w}" for w in C.WEEKS]


def group_table(cust: pd.DataFrame) -> pd.DataFrame:
    """Mean spending by group and week, plus size and covariate shares (Table A1)."""
    g = cust.groupby("group", observed=True)
    out = g[WEEK_COLS + ["pre"]].mean()
    out.insert(0, "n", g.size())
    for col in ("is_member", "male", "age_18_39", "age_40_59", "age_60p"):
        out[col] = g[col].mean()
    return out


def naive_comparisons(cust: pd.DataFrame) -> dict[str, float]:
    """Mean differences in week 34 that a summary table invites, next to the same difference before the coupons."""
    m = cust.groupby("group", observed=True)[WEEK_COLS + ["pre"]].mean()
    hi, mid, lo, c5 = "3000 yen coupon", "3,000-9,999", "<1,000", "500 yen coupon"
    any_coupon = cust.coupon_500.astype(bool) | cust.coupon_3000.astype(bool)
    return {
        "w34_3000_vs_mid": m.loc[hi, "s34"] - m.loc[mid, "s34"],
        "pre_3000_vs_mid": m.loc[hi, "pre"] - m.loc[mid, "pre"],
        "w34_500_vs_below": m.loc[c5, "s34"] - m.loc[lo, "s34"],
        "pre_500_vs_below": m.loc[c5, "pre"] - m.loc[lo, "pre"],
        "w34_any_vs_none": cust.loc[any_coupon, "s34"].mean() - cust.loc[~any_coupon, "s34"].mean(),
        "pre_any_vs_none": cust.loc[any_coupon, "pre"].mean() - cust.loc[~any_coupon, "pre"].mean(),
        "share_selection_3000": (m.loc[hi, "pre"] - m.loc[mid, "pre"]) / (m.loc[hi, "s34"] - m.loc[mid, "s34"]),
    }


def mean_reversion(cust: pd.DataFrame) -> dict[str, float]:
    """The group below 1,000 collapses in week 33 and returns by itself in week 34."""
    m = cust.loc[cust.group == "<1,000", ["pre", "s33", "s34"]].mean()
    return {"pre": m.pre, "w33": m.s33, "w34": m.s34, "rebound": m.s34 - m.s33}


def run(cust: pd.DataFrame) -> dict:
    gt = group_table(cust)
    return {
        "group_table": {str(k): {c: float(v) for c, v in row.items()} for k, row in gt.iterrows()},
        "naive": naive_comparisons(cust),
        "mean_reversion": mean_reversion(cust),
        "n_negative_customer_weeks": int((cust[WEEK_COLS] < 0).sum().sum()),
    }
