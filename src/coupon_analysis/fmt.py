"""Number formatting shared by the appendix, the report and the tables. One place, so '3,810' is always written the same way."""
from __future__ import annotations

import math


def num(x, nd=0, sign=False):
    """1234.5 -> '1,235'; negative numbers get a true minus sign; sign=True adds '+' to positive ones."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    body = f"{abs(x):,.{nd}f}"
    if round(x, nd) == 0:
        return body
    return ("\u2212" if x < 0 else ("+" if sign else "")) + body


def pval(p):
    if p is None:
        return "n/a"
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}" if p < 0.1 else f"{p:.2f}"


def pct(x, nd=0):
    return f"{100 * x:.{nd}f}%"


def mil(x, nd=1):
    return f"{x / 1e6:,.{nd}f}"


def ci(lo, hi, nd=0):
    return f"[{num(lo, nd)}, {num(hi, nd)}]"


FILTERS = {
    "int": lambda v: num(v, 0),
    "signed": lambda v: num(v, 0, sign=True),
    "f1": lambda v: num(v, 1),
    "f2": lambda v: num(v, 2),
    "f3": lambda v: num(v, 3),
    "sf2": lambda v: num(v, 2, sign=True),
    "sf3": lambda v: num(v, 3, sign=True),
    "p": pval,
    "pct0": lambda v: pct(v, 0),
    "pct1": lambda v: pct(v, 1),
    "mil1": lambda v: mil(v, 1),
    "mil2": lambda v: mil(v, 2),
    "x1": lambda v: f"{v:.1f}",
    "x2": lambda v: f"{v:.2f}",
    "str": str,
    "abs": lambda v: num(abs(v), 0),
    "sci": lambda v: f"{v:.1e}",
}
