import pytest

from coupon_analysis import bunching, did, rdd
from coupon_analysis.data import build_customers


@pytest.fixture(scope="module")
def cust(raw):
    return build_customers(raw)


def test_rd_at_1000_reproducible_and_positive(cust):
    a = rdd.effects(cust, 1000, 1)["s34"]
    b = rdd.effects(cust, 1000, 1)["s34"]
    assert a == b
    assert 800 < a["effect"] < 1100 and a["ci_lo"] > 0


def test_rd_at_3000_is_null(cust):
    e = rdd.effects(cust, 3000, -1)["s34"]
    assert e["ci_lo"] < 0 < e["ci_hi"]


def test_density_rejects_only_at_10000(cust):
    assert rdd.density_test(cust.s33, 10000)["p"] < 0.001
    assert rdd.density_test(cust.s33, 1000)["p"] > 0.05


def test_did_main_estimate(cust):
    t, c = did._masks(cust)
    m = did.did_2x2(cust, t, c)
    assert m["estimate"] == pytest.approx(3810.4, abs=1.0)
    assert m["ci_lo"] < m["estimate"] < m["ci_hi"]


def test_placebo_did_small(cust):
    assert abs(did.placebo_did(cust)["estimate"]) < 300


def test_bunching_finds_missing_mass_and_placebo_does_not(cust):
    b = bunching.run(cust)
    assert 300 < b["week33"]["missing_mass"] < 470
    assert b["week32_placebo"]["missing_mass"] < 60
