"""Holm correction, the Card-Krueger 2x2 identity and the RD robustness table."""
import numpy as np
import pandas as pd
import pytest

from coupon_analysis import config as C
from coupon_analysis import did, rdd
from coupon_analysis.data import build_customers
from coupon_analysis.multitest import holm_adjust


def test_holm_known_example():
    # sorted p: .005 .01 .03 .04 -> times 4,3,2,1 = .02 .03 .06 .04 -> running maximum .02 .03 .06 .06
    assert holm_adjust([0.01, 0.04, 0.03, 0.005]) == pytest.approx([0.03, 0.06, 0.06, 0.02])


def test_holm_caps_at_one_and_never_lowers_a_p():
    p = [0.9, 0.5, 0.0004, 0.2]
    adj = holm_adjust(p)
    assert max(adj) <= 1.0
    assert all(a >= x for a, x in zip(adj, p))
    assert adj[2] == pytest.approx(0.0016)


def test_holm_rejects_bad_input():
    with pytest.raises(ValueError, match="between 0 and 1"):
        holm_adjust([0.2, 1.4])
    with pytest.raises(ValueError):
        holm_adjust([0.2, float("nan")])
    assert holm_adjust([]) == []


def test_multiple_testing_counts_raw_and_adjusted_rejections():
    named = {"a": {"p": 0.01, "informative": True}, "b": {"p": 0.04}, "c": {"p": 0.6, "informative": False}, "skipped": None}
    mt = rdd.multiple_testing(named)
    assert mt["n_tests"] == 3 and mt["n_reject_5pct"] == 2
    assert mt["n_reject_holm"] == 1                       # 0.01 * 3 = 0.03 still rejects, 0.04 * 2 = 0.08 does not
    assert mt["n_uninformative"] == 1 and mt["uninformative_text"] == "c"
    assert mt["min_p_holm"] == pytest.approx(0.03)


@pytest.fixture(scope="module")
def cust(raw):
    return build_customers(raw)


def test_card_krueger_did_equals_regression_alpha_on_real_data(cust):
    t, c = did._masks(cust)
    ck = did.card_krueger(cust, t, c)
    assert ck["did"] == pytest.approx(did.did_2x2(cust, t, c)["estimate"], abs=1e-6)
    assert ck["identity_before_after"] == pytest.approx(0, abs=1e-8)
    assert ck["identity_cross_section"] == pytest.approx(0, abs=1e-8)


def test_card_krueger_identity_on_unbalanced_synthetic_data():
    rng = np.random.default_rng(7)
    n = 3000
    s33 = rng.uniform(3000, 14000, n)
    cust = pd.DataFrame({"s33": s33})
    treated = pd.Series(s33 >= 10000)
    for w in (30, 31, 32):
        cust[f"s{w}"] = 0.7 * s33 + rng.normal(0, 300, n)
    cust["s34"] = 0.7 * s33 + 800 * treated + 150 * (s33 / 10000) + rng.normal(0, 300, n)
    for col in ("is_member", "male", "age_40_59", "age_60p"):
        cust[col] = rng.integers(0, 2, n).astype(float)
    t, c = did._masks(cust)
    ck = did.card_krueger(cust, t, c)
    assert ck["did"] == pytest.approx(did.did_2x2(cust, t, c)["estimate"], abs=1e-6)
    assert ck["naive_cross_section"] == pytest.approx(ck["did"] + ck["bias_selection"])
    assert ck["naive_before_after"] == pytest.approx(ck["did"] + ck["bias_time"])


def test_robustness_table_has_expected_rows(cust):
    eff = rdd.effects(cust, 1000, 1)
    bw = rdd.bandwidth_sensitivity(cust, 1000, 1, eff)
    rb = rdd.robustness(cust, 1000, 1, eff, bw)
    expected = ["main"] + [f"bw_{round(100 * m):03d}" for m in C.BW_MULTIPLES if m != 1.0] + [k for k, _, _ in C.RD_ROBUSTNESS]
    for var in ("s34", "d34_pre"):
        assert [r["key"] for r in rb[var]] == expected
        assert rb["summary"][var]["n_specs"] == len(expected)
        assert rb["summary"][var]["n_ci_excludes_zero"] + rb["summary"][var]["n_ci_includes_zero"] == len(expected)
    assert rb["by_key"]["s34"]["main"]["effect"] == pytest.approx(eff["s34"]["effect"])
    assert {"uniform", "p2", "msetwo", "cerrd"} <= set(rb["by_key"]["d34_pre"])


def test_run_rd_rejects_unknown_override():
    with pytest.raises(ValueError, match="cannot override"):
        rdd.run_rd([1.0, 2.0], [1.0, 2.0], 1.5, vce="hc1")
