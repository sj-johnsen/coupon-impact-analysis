import pytest

from coupon_analysis import config as C
from coupon_analysis.data import DataValidationError, build_customers, require_valid, validate


def test_real_data_passes_with_one_warning(df):
    rep = validate(df)
    assert rep.ok
    assert len(rep.warnings) == 1 and "1387" in rep.warnings[0]


def test_missing_column_is_error(df):
    rep = validate(df.drop(columns=["is_member"]))
    assert not rep.ok and "Missing columns" in rep.errors[0]


def test_duplicate_rows_are_error(df):
    rep = validate(__import__("pandas").concat([df, df.iloc[[0]]]))
    assert any("duplicated" in e for e in rep.errors)


def test_wrong_weeks_are_error(df):
    df.loc[df.weeknum == 34, "weeknum"] = 35
    assert not validate(df).ok


def test_unexpected_na_is_error(df):
    df.loc[10, "amount_spent_yen"] = None
    assert any("missing value" in e for e in validate(df).errors)


def test_lag_column_must_match(df):
    i = df.index[df.weeknum == 33][0]
    df.loc[i, "amount_spent_last_week_yen"] += 1
    assert any("differs from amount_spent_yen" in e for e in validate(df).errors)


def test_group_flag_not_constant_is_error(df):
    i = df.index[df.weeknum == 31][0]
    df.loc[i, "is_member"] = 1 - df.loc[i, "is_member"]
    assert any("changes over time" in e for e in validate(df).errors)


def test_many_flag_mismatches_stop_the_run(df):
    ids = df[(df.weeknum == 34) & (df.is_eligible_10000 == 1)].id.iloc[: C.MAX_FLAG_MISMATCH + 3]
    m = df.id.isin(ids)
    df.loc[m, ["is_eligible_10000", "is_below_1000"]] = [0, 1]
    assert any("contradicts" in e for e in validate(df).errors)


def test_require_valid_raises_with_list(df):
    with pytest.raises(DataValidationError, match="1\\."):
        require_valid(df.drop(columns=["gender"]))


def test_customer_table_shape(df):
    cust = build_customers(df)
    assert len(cust) == C.N_CUSTOMERS
    assert cust.group.value_counts().sum() == C.N_CUSTOMERS
    assert (cust.pre == cust[["s30", "s31", "s32"]].mean(axis=1)).all()
