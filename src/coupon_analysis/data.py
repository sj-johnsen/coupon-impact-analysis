"""Load the panel and refuse to continue if it is not what the analysis assumes.

`validate()` collects *all* problems before it raises, so one run lists everything that is wrong.
Known, harmless oddities (one customer at exactly 3,000 yen) are returned as warnings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C

REQUIRED = {
    "id": "integer",
    "weeknum": "integer",
    "amount_spent_yen": "numeric",
    "amount_spent_last_week_yen": "numeric",
    "is_member": "binary",
    "gender": "string",
    "age_category": "string",
    "is_eligible_1000": "binary",
    "is_eligible_10000": "binary",
    "is_below_1000": "binary",
    "is_between_3000_10000": "binary",
}
GENDERS = {"male", "female"}
AGES = {"18-39", "40-59", "60+"}


class DataValidationError(ValueError):
    """Raised when the input file breaks the contract. The message lists every problem and a fix."""


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)   # facts worth reporting, not problems

    @property
    def ok(self) -> bool:
        return not self.errors


def load_raw(path: Path | str) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Data file not found: {path}\n"
            f"Fix: put '{C.DATA_FILENAME}' next to pyproject.toml, or pass --data <path>."
        )
    try:
        return pd.read_csv(path)
    except Exception as exc:  # unreadable csv
        raise DataValidationError(f"Could not read {path} as CSV: {exc}") from exc


def validate(df: pd.DataFrame) -> ValidationReport:
    """Check the data contract. Never raises; call `require_valid` to turn errors into an exception."""
    rep = ValidationReport()
    err, warn = rep.errors.append, rep.warnings.append

    # 1. columns and dtypes ------------------------------------------------------------------
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        err(f"Missing columns: {missing}. Fix: re-export the file with all columns listed in the assignment's data description.")
        return rep  # nothing else can be checked
    for col, kind in REQUIRED.items():
        s = df[col]
        if kind in ("integer", "numeric", "binary") and not pd.api.types.is_numeric_dtype(s):
            bad = df[pd.to_numeric(s, errors="coerce").isna() & s.notna()]
            where = f" First bad value {bad.iloc[0][col]!r} at id {bad.iloc[0]['id']}, week {bad.iloc[0]['weeknum']}." if len(bad) and "id" in df and "weeknum" in df else ""
            err(f"Column '{col}' must be numeric but has dtype {s.dtype}.{where} Fix: remove text such as 'NA' or currency signs.")
        elif kind == "integer" and pd.api.types.is_numeric_dtype(s) and s.notna().all() and not (s % 1 == 0).all():
            err(f"Column '{col}' must hold whole numbers.")
        elif kind == "binary" and pd.api.types.is_numeric_dtype(s) and not set(s.dropna().unique()) <= {0, 1}:
            bad = [float(v) for v in sorted(set(s.dropna().unique()) - {0, 1})[:5]]
            err(f"Column '{col}' must be 0/1 but contains {bad}.")
        elif kind == "string" and s.isna().any():
            err(f"Column '{col}' has {int(s.isna().sum())} missing values.")
    if rep.errors:
        return rep
    if not set(df.gender.unique()) <= GENDERS:
        err(f"gender must be in {sorted(GENDERS)}, found {sorted(set(df.gender.unique()) - GENDERS)}.")
    if not set(df.age_category.unique()) <= AGES:
        err(f"age_category must be in {sorted(AGES)}, found {sorted(set(df.age_category.unique()) - AGES)}.")

    # 2. balanced panel ------------------------------------------------------------------------
    if set(df.weeknum.unique()) != set(C.WEEKS):
        err(f"weeknum must be exactly {list(C.WEEKS)}, found {[int(w) for w in sorted(df.weeknum.unique())]}.")
    ids = df["id"].unique()
    if len(ids) != C.N_CUSTOMERS or set(ids) != set(range(1, C.N_CUSTOMERS + 1)):
        err(f"id must run from 1 to {C.N_CUSTOMERS} ({len(ids)} distinct ids found).")
    dup = int(df.duplicated(["id", "weeknum"]).sum())
    if dup:
        first = df[df.duplicated(["id", "weeknum"], keep=False)].iloc[0]
        err(f"{dup} duplicated (id, weeknum) rows, first at id {int(first['id'])}, week {int(first['weeknum'])}. "
            "Fix: drop duplicates; the panel must have one row per customer and week.")
    elif len(df) != C.N_CUSTOMERS * len(C.WEEKS):
        err(f"Expected {C.N_CUSTOMERS * len(C.WEEKS):,} rows (balanced panel), found {len(df):,}.")
    if rep.errors:
        return rep

    # 3. missing values ------------------------------------------------------------------------
    na_cols = [c for c in df.columns if c != "amount_spent_last_week_yen" and df[c].isna().any()]
    for col in na_cols:
        first = df[df[col].isna()].iloc[0]
        err(f"Column '{col}' has {int(df[col].isna().sum())} missing value(s), first at id {int(first['id'])}, week {int(first['weeknum'])}. "
            "Only amount_spent_last_week_yen in week 30 may be NA. Fix: fill or drop those rows.")
    lag = df["amount_spent_last_week_yen"]
    if lag[df.weeknum == C.WEEKS[0]].notna().any():
        err("amount_spent_last_week_yen should be NA in week 30 (no earlier week observed).")
    if lag[df.weeknum != C.WEEKS[0]].isna().any():
        err("amount_spent_last_week_yen has NA after week 30; it may only be NA in week 30.")
    if rep.errors:
        return rep

    wide = df.pivot(index="id", columns="weeknum", values="amount_spent_yen")
    lagw = df.pivot(index="id", columns="weeknum", values="amount_spent_last_week_yen")

    # 4. the lag column must equal last week's spending ------------------------------------------
    for wk in C.WEEKS[1:]:
        bad = int((lagw[wk] != wide[wk - 1]).sum())
        if bad:
            err(f"amount_spent_last_week_yen differs from amount_spent_yen of week {wk - 1} for {bad} customers in week {wk}.")

    # 5. time-invariant columns ------------------------------------------------------------------
    const_cols = ["is_member", "gender", "age_category", *C.GROUPS]
    for col in const_cols:
        n_vary = int((df.groupby("id")[col].nunique() > 1).sum())
        if n_vary:
            err(f"'{col}' changes over time for {n_vary} customers; it must be constant per id.")
    if rep.errors:
        return rep

    # 6. groups: exactly one flag per customer, consistent with spending in week 33 ---------------
    one = df[df.weeknum == C.OUTCOME_WEEK].set_index("id")
    flags = one[list(C.GROUPS)]
    n_flags = flags.sum(axis=1)
    if (n_flags != 1).any():
        err(f"{int((n_flags != 1).sum())} customers do not belong to exactly one of the four group flags.")
        return rep
    w33 = wide[C.RUNNING_WEEK].reindex(one.index)
    mism = []   # (id, flag, week-33 spending) for customers whose flag contradicts the written rule
    for flag, (lo, hi) in C.GROUP_RULE.items():
        outside = ~((w33 >= lo) & (w33 < hi))
        mism += [(i, flag, w33[i]) for i in one.index[(flags[flag] == 1) & outside]]
    if len(mism) > C.MAX_FLAG_MISMATCH:
        err(f"{len(mism)} customers have a group flag that contradicts their week-33 spending (limit {C.MAX_FLAG_MISMATCH}). "
            "Fix: check that the flags were built from amount_spent_yen in week 33.")
    for i, flag, v in mism:
        warn(f"Customer id {i} is flagged '{flag}' but spent {v:,.0f} yen in week 33, which the written rule assigns to another group. "
             "The analysis keeps the data flag for descriptives and uses the written rule (week-33 spending) for the regression discontinuity designs.")
    n_neg = int((df.amount_spent_yen < 0).sum())
    if n_neg:
        rep.notes.append(f"{n_neg} customer-weeks have negative spending (returns); kept as they are.")
    return rep


def require_valid(df: pd.DataFrame) -> ValidationReport:
    rep = validate(df)
    if not rep.ok:
        lines = "\n".join(f"  {i}. {m}" for i, m in enumerate(rep.errors, 1))
        raise DataValidationError(f"The input data violate the contract ({len(rep.errors)} problem(s)):\n{lines}")
    return rep


def build_customers(df: pd.DataFrame) -> pd.DataFrame:
    """One row per customer: weekly spending s30..s34, baseline, outcomes, covariates and group label."""
    wide = df.pivot(index="id", columns="weeknum", values="amount_spent_yen").astype(float)
    wide.columns = [f"s{c}" for c in wide.columns]
    one = df[df.weeknum == C.OUTCOME_WEEK].set_index("id")
    cust = wide.copy()
    cust["pre"] = wide[[f"s{w}" for w in C.PRE_WEEKS]].mean(axis=1)    # baseline before the announcement
    cust["d34_pre"] = cust["s34"] - cust["pre"]
    cust["is_member"] = one.is_member.astype(float)
    cust["male"] = (one.gender == "male").astype(float)
    cust["age_18_39"] = (one.age_category == "18-39").astype(float)
    cust["age_40_59"] = (one.age_category == "40-59").astype(float)
    cust["age_60p"] = (one.age_category == "60+").astype(float)
    grp = pd.Series(index=cust.index, dtype=object)
    for flag, label in C.GROUPS.items():
        grp[one[flag] == 1] = label
    cust["group"] = pd.Categorical(grp, categories=C.GROUP_ORDER, ordered=True)
    cust["coupon_500"] = (one.is_eligible_1000 == 1).astype(int)
    cust["coupon_3000"] = (one.is_eligible_10000 == 1).astype(int)
    return cust


def load_customers(path: Path | str) -> tuple[pd.DataFrame, ValidationReport]:
    """Load, validate and reshape in one call. Raises DataValidationError on a broken file."""
    df = load_raw(path)
    rep = require_valid(df)
    return build_customers(df), rep
