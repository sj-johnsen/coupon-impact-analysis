"""Known-effect checks: the estimators must recover an effect that we put into simulated data."""
import numpy as np
import pandas as pd
import pytest

from coupon_analysis import costbenefit, did, guard, rdd


def test_rd_recovers_known_jump():
    rng = np.random.default_rng(1)
    r = rng.uniform(0, 5000, 20000).round()
    y = 0.4 * r + 300 * (r >= 1000) + rng.normal(0, 150, r.size)
    est = rdd.run_rd(y, r, 1000)
    assert est["ci_lo"] < 300 < est["ci_hi"]
    assert est["effect"] == pytest.approx(300, abs=60)


def test_rd_sign_flip_for_upper_edge():
    rng = np.random.default_rng(2)
    r = rng.uniform(1000, 5000, 20000).round()
    y = 0.2 * r + 200 * (r < 3000) + rng.normal(0, 100, r.size)      # coupon on the left of the cutoff
    est = rdd.run_rd(y, r, 3000, sign=-1)
    assert est["effect"] == pytest.approx(200, abs=50)
    assert est["ci_lo"] < est["effect"] < est["ci_hi"]


def test_did_recovers_known_effect():
    rng = np.random.default_rng(3)
    n = 6000
    s33 = rng.uniform(3000, 16000, n)
    level = 0.8 * s33
    cust = pd.DataFrame({"s33": s33})
    for w in (30, 31, 32):
        cust[f"s{w}"] = level + rng.normal(0, 200, n)
    treated = pd.Series(s33 >= 10000)
    cust["s34"] = level + 1000 * treated + rng.normal(0, 200, n)
    for c in ("is_member", "male", "age_40_59", "age_60p"):
        cust[c] = rng.integers(0, 2, n).astype(float)
    cust["pre"] = cust[["s30", "s31", "s32"]].mean(axis=1)
    t, c = did._masks(cust)
    est = did.did_2x2(cust, t, c)
    assert est["estimate"] == pytest.approx(1000, abs=40)
    assert est["ci_lo"] < 1000 < est["ci_hi"]
    assert abs(did.event_study(cust, t, c)["coefficients"]["30"]["estimate"]) < 60


def test_break_even_arithmetic():
    row = costbenefit._row("x", n=100, face=3000.0, effect_per_cust=1500.0)
    assert row["incremental_revenue"] == 150_000
    assert row["cost_full_redemption"] == 300_000
    assert row["by_redemption"]["100"]["break_even_margin"] == pytest.approx(2.0)
    assert row["by_redemption"]["50"]["break_even_margin"] == pytest.approx(1.0)
    assert row["by_redemption"]["25"]["cost"] == 75_000
    row0 = costbenefit._row("x", 100, 500.0, -10.0)
    assert row0["by_redemption"]["100"]["break_even_margin"] is None     # no incremental spending: no margin can pay


def test_text_guard_flags_a_changed_number():
    res = {"did": {"main": {"estimate": 3810.4}}, "share": 0.66}
    ok = "---\nx: 1\n---\nThe estimate is +3,810 yen and 66% of the gap."
    assert guard.stale_numbers(ok, res) == []
    stale = ok.replace("3,810", "3,910")
    assert guard.stale_numbers(stale, res) == ["+3,910"]


def test_bunching_recovers_known_number_of_movers():
    from coupon_analysis import bunching
    rng = np.random.default_rng(4)
    n = 20000
    ref = [rng.gamma(4, 2500, n) for _ in range(2)]            # smooth spending in two earlier weeks
    obs = ref[0].copy()
    movers = np.where((obs >= 9000) & (obs < 10000))[0][:300]
    obs[movers] = rng.uniform(10000, 10800, movers.size)         # 300 customers stretch over the threshold
    est = bunching.estimate(obs, ref)
    assert 230 < est["missing_mass"] < 380
    assert est["landing"] > 10000 > est["origin"]
