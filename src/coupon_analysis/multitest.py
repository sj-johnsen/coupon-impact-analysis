"""Multiple-testing correction (Lecture 2, deck 03: FWER, Bonferroni, Holm).

Holm's step-down method: sort the m p-values, multiply the i-th smallest by (m - i + 1), make the sequence
non-decreasing and cap it at 1. It controls the family-wise error rate at alpha without any assumption on
how the tests depend on each other, and it is never less powerful than Bonferroni.
"""
from __future__ import annotations

import math


def holm_adjust(pvals: list[float]) -> list[float]:
    """Holm-adjusted p-values, in the order of the input."""
    p = list(pvals)
    for x in p:
        if x is None or not isinstance(x, (int, float)) or math.isnan(x) or not 0.0 <= x <= 1.0:
            raise ValueError(f"holm_adjust needs p-values between 0 and 1, got {x!r}. Fix: drop tests that were not run before adjusting.")
    m = len(p)
    order = sorted(range(m), key=lambda i: p[i])
    adj = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[i]))
        adj[i] = running
    return adj
