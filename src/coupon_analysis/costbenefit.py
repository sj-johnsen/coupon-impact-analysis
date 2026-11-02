"""Section G: coupon cost against incremental spending, and the margin that makes the coupon break even.

Revenue is not profit. A coupon pays for itself only if  margin * incremental_spending >= coupon_cost.
We therefore report the break-even margin  m* = cost / incremental_spending  and never assume a margin.
Cost scenarios: every eligible customer redeems (stated assumption) and lower redemption rates.
"""
from __future__ import annotations

from . import config as C


F500, F3000 = C.COUPON_FACE["500"], C.COUPON_FACE["3000"]
SCOPE_500 = "Assumes the effect at 1,000 holds for all eligible customers (upper bound); the estimate at 3,000 is about zero."


def _row(label, n, face, effect_per_cust, extra_revenue=0.0, note=""):
    revenue = n * effect_per_cust + extra_revenue
    cost_full = n * face
    return {
        "label": label, "n_eligible": n, "face": face, "note": note,
        "effect_per_customer": effect_per_cust, "incremental_revenue": revenue,
        "cost_full_redemption": cost_full,
        "by_redemption": {str(int(round(r * 100))): {"cost": r * cost_full,
                                   "break_even_margin": (r * cost_full / revenue) if revenue > 0 else None}
                          for r in C.REDEMPTION_GRID},
    }


def run(cust, rd_res, did_res, bunch_res) -> dict:
    n500, n3000 = int(cust.coupon_500.sum()), int(cust.coupon_3000.sum())
    lo = rd_res["at1000"]["effects"]["s34"]
    lo_d = rd_res["at1000"]["effects"]["d34_pre"]
    up = rd_res["at3000"]["effects"]["s34"]
    att, att_prop = did_res["main"], did_res["proportional"]
    ann = bunch_res["week33"]["effect_total"]
    naive_diff = cust.loc[cust.coupon_3000 == 1, "s34"].mean() - cust.loc[cust.group == "3,000-9,999", "s34"].mean()
    return {
        "coupon_500": {
            "at_lower_edge": _row("500 yen, effect on week-34 spending at 1,000", n500, F500, lo["effect"], note=SCOPE_500),
            "at_lower_edge_diff": _row("500 yen, effect on change vs baseline at 1,000", n500, F500, lo_d["effect"], note=SCOPE_500),
            "at_lower_edge_ci_low": _row("500 yen, lower end of robust CI at 1,000", n500, F500, lo["ci_lo"], note=SCOPE_500),
            "at_upper_edge": {"effect_per_customer": up["effect"], "ci": [up["ci_lo"], up["ci_hi"]],
                              "note": "Effect at 3,000 is indistinguishable from zero."},
        },
        "coupon_3000": {
            "did_levels": _row("3000 yen: DiD in levels, plus week-33 announcement effect", n3000, F3000, att["estimate"], ann),
            "did_proportional": _row("3000 yen: DiD in proportions, plus week-33 announcement effect", n3000, F3000, att_prop["att_yen"], ann),
            "did_levels_ci_low": _row("3000 yen: lower end of DiD CI, no announcement effect", n3000, F3000, att["ci_lo"]),
            "announcement_effect": ann,
        },
        "naive_view": {
            "incremental_revenue": n3000 * naive_diff,
            "cost_full_redemption": n3000 * F3000,
            "overstatement_factor": naive_diff / att["estimate"],
        },
        "assumptions": [
            "Eligible customers redeem the full face value (cost scenario); lower redemption rates are shown.",
            "amount_spent_yen is read as spending before the coupon is deducted.",
            "Incremental revenue is spending, not profit; the break-even margin is the share of an extra yen of spending that must be margin.",
        ],
    }
