"""Run every analysis and write results.json. All numbers in the appendix and the report come from this file."""
from __future__ import annotations

import json
from importlib import metadata
import platform
from pathlib import Path

import numpy as np
import pandas as pd

from . import bunching, costbenefit, descriptives, did, rdd
from . import config as C
from .data import ValidationReport, load_customers


def _plain(o):
    """numpy -> plain python so json can write it."""
    if isinstance(o, dict):
        return {str(k): _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def compute(data_path: Path) -> tuple[dict, pd.DataFrame, ValidationReport]:
    cust, rep = load_customers(data_path)
    rd_res = rdd.run(cust)
    did_res = did.run(cust)
    bunch_res = bunching.run(cust)
    results = {
        "meta": {"n_customers": len(cust), "weeks": list(C.WEEKS), "seed": C.SEED, "python": platform.python_version(),
                 "packages": {p: metadata.version(p) for p in ("numpy", "pandas", "statsmodels", "matplotlib", "rdrobust", "rddensity")},
                 "validation_warnings": rep.warnings, "validation_notes": rep.notes,
                 "validation_warning_text": " ".join(rep.warnings) or "None.",
                 "validation_note_text": " ".join(rep.notes) or "None."},
        "descriptives": descriptives.run(cust),
        "rd": rd_res,
        "did": did_res,
        "bunching": bunch_res,
    }
    results["meta"]["estimator_messages"] = dict(rdd.MESSAGES)
    results["meta"]["estimator_message_text"] = "; ".join(f"{m} (x{n})" for m, n in rdd.MESSAGES.items()) or "none"
    results["costbenefit"] = costbenefit.run(cust, rd_res, did_res, bunch_res)
    return _plain(results), cust, rep


def write_json(results: dict, path: Path) -> None:
    path.write_text(json.dumps(results, indent=1, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8")
