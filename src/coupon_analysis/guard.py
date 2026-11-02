"""Stale-text guard: every estimate quoted in text.md must still exist in results.json.

text.md is edited by hand and only rebuilt with --regen-report. If the data or the analysis change afterwards,
numbers in the text can silently go out of date. This check reads the numbers in text.md and looks each one up in
results.json (allowing for rounding, millions and percent). Design constants such as 500 or 10,000 are ignored.
"""
from __future__ import annotations

import re

from . import config as C

NUM = re.compile(r"(?<![\w.])[-−+]?\d[\d,]*(?:\.\d+)?%?")
CONSTANTS = {9999, 2999, 11999, 7999, 500, 1000, 3000, 10000, 8000, 12000, 2500, 2000, 4000, 1500, 100, 200, 300, 400, 600, 800, 962, 2026, 2022}


def _leaves(o, out):
    if isinstance(o, dict):
        for v in o.values():
            _leaves(v, out)
    elif isinstance(o, list):
        for v in o:
            _leaves(v, out)
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        out.append(float(o))


def _body(text: str) -> str:
    """Text after the frontmatter and before the reference list."""
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    return text.split("\n## References", 1)[0]


def _tokens(text: str):
    for m in NUM.finditer(text):
        raw = m.group(0)
        pct = raw.endswith("%")
        clean = raw.rstrip("%").replace(",", "").replace("−", "-").lstrip("+")
        dec = len(clean.split(".")[1]) if "." in clean else 0
        val = abs(float(clean))
        if not pct and dec == 0 and "," not in raw and 1900 <= val <= 2100:
            continue          # a year in a citation
        if (pct and val in (5, 25, 50, 75, 95, 100)) or (not pct and dec == 0 and (val < 100 or int(val) in CONSTANTS)):
            continue          # week numbers, panel letters, design constants
        yield raw, val, dec, pct


def stale_numbers(text: str, results: dict) -> list[str]:
    leaves: list[float] = []
    _leaves(results, leaves)
    pool = [abs(v) for v in leaves]
    pool += [abs(v) * 100 for v in leaves if abs(v) <= 5]      # shares as percent
    pool += [abs(v) / 1e6 for v in leaves if abs(v) >= 1e5]    # million yen
    bad = []
    for raw, val, dec, pct in _tokens(_body(text)):
        tol = 0.5 * 10 ** (-dec) + 1e-9
        if not any(abs(p - val) <= tol for p in pool):
            bad.append(raw)
    return sorted(set(bad))


def stale_details(text: str, results: dict) -> list[dict]:
    """Like stale_numbers, but with line number and context for every stale number (line counted in the whole file)."""
    bad = set(stale_numbers(text, results))
    lines = text.splitlines()
    found = []
    for i, line in enumerate(lines, 1):
        for m in NUM.finditer(line):
            if m.group(0) in bad and not any(f["number"] == m.group(0) and f["line"] == i for f in found):
                found.append({"number": m.group(0), "line": i, "context": line[max(0, m.start() - 40): m.end() + 30].strip()})
    return found
