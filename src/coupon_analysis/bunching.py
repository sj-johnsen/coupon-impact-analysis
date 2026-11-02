"""Section E: how much did the announcement itself move spending in week 33?

Customers who stretched to reach 10,000 yen leave a hole below the threshold and a pile above it.
Counterfactual histogram for week 33 = average histogram of weeks 31 and 32 (before the announcement; the
two weeks look alike), rescaled so that both have the same count outside the response region.
    missing mass M = customers missing below 10,000   = sum of max(counterfactual - observed, 0) over the bins below
    excess mass  B = customers in surplus above 10,000
    stretch s      = mean position of the excess mass - mean position of the missing mass
    announcement effect on week-33 spending = M * s   (yen)
"""
from __future__ import annotations

import numpy as np

from . import config as C


def _counts(values, edges):
    return np.histogram(np.asarray(values, dtype=float), edges)[0].astype(float)


def estimate(obs, ref_list, c: float = 10000, half_width: float = C.BUNCH_HALF_WIDTH) -> dict:
    """obs: week-33 spending; ref_list: spending in the reference weeks (same customers, same order)."""
    lo, hi = C.BUNCH_RANGE
    edges = np.arange(lo, hi + C.BUNCH_BIN, C.BUNCH_BIN)
    mids = edges[:-1] + C.BUNCH_BIN / 2
    observed = _counts(obs, edges)
    reference = np.mean([_counts(r, edges) for r in ref_list], axis=0)
    inside = (mids > c - half_width) & (mids < c + half_width)
    scale = observed[~inside].sum() / reference[~inside].sum()
    cf = reference * scale
    below, above = inside & (mids < c), inside & (mids > c)
    miss = np.clip(cf - observed, 0, None) * below
    exc = np.clip(observed - cf, 0, None) * above
    M, B = float(miss.sum()), float(exc.sum())
    origin, landing = float((mids * miss).sum() / M), float((mids * exc).sum() / B)
    return {"missing_mass": M, "excess_mass": B, "origin": origin, "landing": landing,
            "stretch": landing - origin, "stretch_min": c - origin,
            "effect_total": M * (landing - origin), "effect_total_min": M * (c - origin),
            "share_of_eligible": B / max(1.0, float((np.asarray(obs) >= c).sum())),
            "_plot": (mids, observed, cf, inside)}


def _strip(e: dict) -> dict:
    return {k: v for k, v in e.items() if k != "_plot"}


def run(cust) -> dict:
    ref = [cust[f"s{w}"].values for w in C.BUNCH_REFERENCE]
    main = estimate(cust.s33.values, ref)
    # placebo: week 32 against weeks 30 and 31, when nothing was announced
    plc = estimate(cust.s32.values, [cust.s30.values, cust.s31.values])
    rng = np.random.default_rng(C.SEED)
    n = len(cust)
    boots = []
    arr = [cust.s33.values, *ref]
    for _ in range(C.BOOT_REPS):
        idx = rng.integers(0, n, n)                   # resample customers, keeping their weeks together
        e = estimate(arr[0][idx], [a[idx] for a in arr[1:]])
        boots.append((e["missing_mass"], e["stretch"], e["effect_total"]))
    b = np.array(boots)
    ci = lambda col: [float(np.percentile(b[:, col], 2.5)), float(np.percentile(b[:, col], 97.5))]
    mids, observed, cf, inside = main["_plot"]
    n_elig = int(cust.coupon_3000.sum())
    return {
        "week33": _strip(main),
        "week32_placebo": _strip(plc),
        "n_boot": C.BOOT_REPS,
        "missing_mass_ci": ci(0), "stretch_ci": ci(1), "effect_total_ci": ci(2),
        "sensitivity": [{"half_width": w, **_strip(estimate(cust.s33.values, ref, half_width=w))} for w in C.BUNCH_WIDTHS_SENS],
        "effect_per_eligible": main["effect_total"] / n_elig,
        "plot": {"mids": mids.tolist(), "observed": observed.tolist(), "counterfactual": cf.tolist(), "inside": inside.tolist()},
    }
