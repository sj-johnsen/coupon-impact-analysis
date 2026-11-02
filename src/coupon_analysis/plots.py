"""Figures. Every function takes already-computed results and writes one PNG; none estimates anything itself,
except the drawn local-linear lines, which repeat the estimator inside the bandwidth chosen by rdrobust."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config as C

COL = {"<1,000": "#7a7a7a", "500 yen coupon": "#e08a00", "3,000-9,999": "#1f6fb4", "3000 yen coupon": "#b0233c"}
DPI = 200


def _style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 8.5, "axes.titlesize": 9, "axes.labelsize": 8.5,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#e6e6e6",
        "grid.linewidth": 0.6, "legend.frameon": False, "legend.fontsize": 8, "figure.dpi": 100,
        "savefig.bbox": "tight", "savefig.pad_inches": 0.05,
    })


def _save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, metadata={"Software": ""})
    plt.close(fig)


def _yen(x, _=None):
    return f"{x:,.0f}"


def _trend_ax(ax, cust, groups, annotate=True):
    m = cust.groupby("group", observed=True)[[f"s{w}" for w in C.WEEKS]].mean()
    for g in groups:
        ax.plot(C.WEEKS, m.loc[g].values, marker="o", ms=3.5, lw=1.6, color=COL[g], label=g)
    ax.axvspan(32.5, 33.5, color="#f2e6b8", alpha=0.55, lw=0)
    ax.axvspan(33.5, 34.5, color="#d9ecd0", alpha=0.6, lw=0)
    ax.set_xticks(C.WEEKS)
    ax.set_xlabel("Week")
    ax.yaxis.set_major_formatter(_yen)
    if annotate:
        top = ax.get_ylim()[1]
        ax.text(33, top, "3000 coupon\nannounced", ha="center", va="top", fontsize=7)
        ax.text(34, top, "coupons\nvalid", ha="center", va="top", fontsize=7)
    return m


def fig_trends(cust, path: Path, panels: str = "both"):
    _style()
    if panels == "both":
        fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.7), gridspec_kw={"width_ratios": [1.15, 1]})
        _trend_ax(axes[0], cust, C.GROUP_ORDER)
        axes[0].set_ylabel("Mean spending (yen)")
        axes[0].set_title("(a) All four groups")
        axes[0].legend(loc="center left", bbox_to_anchor=(0.0, 0.52), fontsize=7)
        _trend_ax(axes[1], cust, C.GROUP_ORDER[:2], annotate=False)
        axes[1].set_title("(b) The two low-spending groups")
        axes[1].legend(loc="center left", bbox_to_anchor=(0.0, 0.6), fontsize=7)
    else:
        fig, ax = plt.subplots(figsize=(4.2, 2.8))
        _trend_ax(ax, cust, C.GROUP_ORDER)
        ax.legend()
    _save(fig, path)


def _hist(ax, v, lo, hi, bin_w, **kw):
    edges = np.arange(lo, hi + bin_w, bin_w)
    cnt, _ = np.histogram(v, edges)
    ax.stairs(cnt, edges, baseline=None, **kw)
    return cnt


def fig_density(cust, rd_res, path: Path):
    _style()
    fig, axes = plt.subplots(1, 3, figsize=(7.4, 2.6))
    for ax, (c, key, span) in zip(axes, [(c, f"at{c}", C.DENSITY_SPANS[c]) for c in C.CUTOFFS]):
        _hist(ax, cust.s32, c - span, c + span, 100, color="#9aa7b4", lw=1.2, label="week 32")
        _hist(ax, cust.s33, c - span, c + span, 100, color="#b0233c", lw=1.4, label="week 33")
        ax.axvline(c, color="k", lw=0.8, ls="--")
        p33, p32 = rd_res[key]["density_w33"]["p"], rd_res[key]["density_w32"]["p"]
        ax.set_title(f"Cutoff {c:,}\nrddensity p = {p33:.2g} (wk 33), {p32:.2f} (wk 32)", fontsize=7.5)
        ax.set_xlabel("Spending (yen)")
        ax.xaxis.set_major_formatter(_yen)
        ax.tick_params(axis="x", labelsize=7, rotation=30)
    axes[0].set_ylabel("Customers per 100 yen")
    axes[0].legend(loc="upper left", fontsize=7)
    fig.tight_layout()
    _save(fig, path)


def _local_linear(r, y, c, h, side):
    """WLS line with triangular weights on one side of c; returns a function of r."""
    m = (r >= c - h) & (r < c) if side == "left" else (r >= c) & (r <= c + h)
    x, yy = r[m] - c, y[m]
    w = 1 - np.abs(x) / h
    X = np.column_stack([np.ones_like(x), x])
    beta = np.linalg.solve(X.T @ (X * w[:, None]), X.T @ (yy * w))
    return lambda rr: beta[0] + beta[1] * (rr - c)


def rd_plot(ax, cust, c, var, est, ylabel, span_mult=2.0, nbins=14, color="#1f6fb4"):
    r, y = cust.s33.values.astype(float), cust[var].values.astype(float)
    h = est["h"]
    span = span_mult * h
    for side, sl in (("left", (c - span, c)), ("right", (c, c + span))):
        m = (r >= sl[0]) & (r < sl[1]) if side == "left" else (r >= sl[0]) & (r <= sl[1])
        edges = np.linspace(sl[0], sl[1], nbins + 1)
        idx = np.digitize(r[m], edges[1:-1])
        xs = np.array([r[m][idx == k].mean() for k in range(nbins) if (idx == k).sum() > 0])
        ys = np.array([y[m][idx == k].mean() for k in range(nbins) if (idx == k).sum() > 0])
        ax.scatter(xs, ys, s=14, color="#444", alpha=0.85, zorder=3)
        f = _local_linear(r, y, c, h, side)
        grid = np.linspace(c - h, c, 20) if side == "left" else np.linspace(c, c + h, 20)
        ax.plot(grid, f(grid), color=color, lw=2)
    ax.axvline(c, color="k", lw=0.8, ls="--")
    ax.set_xlabel("Spending in week 33 (yen)")
    ax.set_ylabel(ylabel)
    ax.xaxis.set_major_formatter(_yen)
    ax.yaxis.set_major_formatter(_yen)
    ax.tick_params(axis="x", labelsize=7)


def _rd_title(est, sign_note=""):
    return f"{sign_note}effect {est['effect']:+,.0f} yen, 95% CI [{est['ci_lo']:,.0f}, {est['ci_hi']:,.0f}], h = {est['h']:,.0f}"


def fig_rd(cust, rd_suite, c, path: Path, coupon_title: str):
    _style()
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9))
    e = rd_suite["effects"]
    rd_plot(axes[0], cust, c, "s34", e["s34"], "Spending in week 34 (yen)")
    axes[0].set_title("(a) Level\n" + _rd_title(e["s34"]), fontsize=7.5)
    rd_plot(axes[1], cust, c, "d34_pre", e["d34_pre"], "Week 34 minus mean of weeks 30-32 (yen)")
    axes[1].set_title("(b) Change vs baseline\n" + _rd_title(e["d34_pre"]), fontsize=7.5)
    fig.suptitle(coupon_title, fontsize=9, y=1.02)
    fig.tight_layout()
    _save(fig, path)


def fig_rd_invalid(cust, rd10, path: Path):
    _style()
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9))
    pre = rd10["placebo"]["pre"]
    rd_plot(axes[0], cust, 10000, "pre", pre, "Mean spending, weeks 30-32 (yen)", color="#b0233c")
    axes[0].set_title(f"(a) Before the announcement: jump of {pre['effect']:+,.0f} yen\n(p = {pre['p']:.1g}; should be zero)", fontsize=7.5)
    s34 = rd10["effects"]["s34"]
    rd_plot(axes[1], cust, 10000, "s34", s34, "Spending in week 34 (yen)", color="#b0233c")
    axes[1].set_title(f"(b) Week 34: naive RD {s34['effect']:+,.0f} yen\n(not interpretable)", fontsize=7.5)
    fig.tight_layout()
    _save(fig, path)


def _forest(ax, items, title, xlabel, fmt="{:,.0f}"):
    ys = np.arange(len(items))[::-1]
    for y, (name, e) in zip(ys, items):
        if e is None:
            ax.text(0, y, "no variation", va="center", ha="center", fontsize=7, color="#888")
            continue
        sig = e["p"] < C.ALPHA
        ax.plot([e["ci_lo"], e["ci_hi"]], [y, y], color="#b0233c" if sig else "#1f6fb4", lw=1.6)
        ax.plot(e["effect"], y, "o", ms=4, color="#b0233c" if sig else "#1f6fb4")
    ax.axvline(0, color="k", lw=0.8)
    ax.set_yticks(ys)
    ax.set_yticklabels([n for n, _ in items], fontsize=7.5)
    ax.set_title(title, fontsize=8.5)
    ax.set_xlabel(xlabel, fontsize=8)
    ax.grid(axis="y", visible=False)


COV_LABELS = {"is_member": "member", "male": "male", "age_18_39": "age 18-39", "age_40_59": "age 40-59", "age_60p": "age 60+"}
PLC_LABELS = {"s30": "week 30", "s31": "week 31", "s32": "week 32", "pre": "mean wk 30-32",
              "lag1": "R = wk 32, Y = wk 33", "lag2": "R = wk 31, Y = wk 32"}


def fig_balance_placebo(rd_res, path: Path):
    _style()
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.0))
    for j, (key, c) in enumerate((("at1000", 1000), ("at3000", 3000))):
        s = rd_res[key]
        _forest(axes[0, j], [(COV_LABELS[k], s["balance"][k]) for k in COV_LABELS],
                f"Covariate balance at {c:,}", "Jump in share (robust 95% CI)")
        _forest(axes[1, j], [(PLC_LABELS[k], s["placebo"][k]) for k in PLC_LABELS],
                f"Placebo outcomes at {c:,}", "Jump in yen (robust 95% CI)")
    fig.tight_layout()
    _save(fig, path)


def fig_bandwidth(rd_res, path: Path):
    _style()
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8), sharey=False)
    for ax, (key, c) in zip(axes, (("at1000", 1000), ("at3000", 3000))):
        for var, col, lab in (("s34", "#1f6fb4", "Week 34 level"), ("d34_pre", "#e08a00", "Change vs baseline")):
            rows = rd_res[key]["bandwidth_sensitivity"][var]
            xs = [r["multiple"] for r in rows]
            ax.plot(xs, [r["effect"] for r in rows], marker="o", ms=3.5, color=col, label=lab)
            ax.fill_between(xs, [r["ci_lo"] for r in rows], [r["ci_hi"] for r in rows], color=col, alpha=0.15, lw=0)
        ax.axhline(0, color="k", lw=0.8)
        ax.set_title(f"Coupon effect at {c:,}")
        ax.set_xlabel("Bandwidth as a multiple of the MSE-optimal h")
        ax.yaxis.set_major_formatter(_yen)
    axes[0].set_ylabel("Effect (yen), robust 95% CI")
    axes[0].legend(loc="upper left")
    fig.tight_layout()
    _save(fig, path)


def _event_ax(ax, did_res, small=False):
    co = did_res["event_study"]["coefficients"]
    fs = 7 if small else 8
    for w in C.WEEKS:
        e = co[str(w)]
        yerr = [[e["estimate"] - e["ci_lo"]], [e["ci_hi"] - e["estimate"]]]
        if w == 33:
            ax.errorbar(w, e["estimate"], yerr=yerr, fmt="o", mfc="white", color="#888", capsize=3, ms=5)
        else:
            ax.errorbar(w, e["estimate"], yerr=yerr, fmt="o", color="#b0233c" if w == 34 else "#1f6fb4", capsize=3, ms=5)
    ax.axhline(0, color="k", lw=0.8)
    ax.axvspan(32.5, 33.5, color="#f2e6b8", alpha=0.55, lw=0)
    ax.axvspan(33.5, 34.5, color="#d9ecd0", alpha=0.6, lw=0)
    ax.text(33, 1800, "group set by\nweek-33 spending", ha="center", fontsize=fs - 1, color="#666")
    ax.set_xticks(C.WEEKS)
    ax.set_xlabel("Week (reference: week 32)")
    ax.set_ylabel("Gap to 3,000-9,999 group,\nrelative to week 32 (yen)")
    ax.yaxis.set_major_formatter(_yen)
    ax.annotate(f"{co['34']['estimate']:+,.0f}", (34, co["34"]["estimate"]), xytext=(-9, -3), textcoords="offset points", ha="right", fontsize=fs + 2, color="#b0233c")
    ax.set_title(f"Week 34: {co['34']['estimate']:+,.0f} yen; week 30: {co['30']['estimate']:+,.0f}", fontsize=fs)


def fig_event_study(did_res, path: Path, compact: bool = False):
    _style()
    fig, ax = plt.subplots(figsize=(3.6, 2.7) if compact else (4.6, 3.0))
    _event_ax(ax, did_res, small=compact)
    _save(fig, path)


# ---------------------------------------------------------------- report figures (Word, group-memo style)
BLUE = "#2a6fdb"
GREY = "#9aa3ad"
DARK = "#2b2f33"
REPORT_W = 6.69         # inches = 17 cm, the text width of the Word page
REPORT_DPI = 300


def _report_style():
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 9.5, "axes.labelsize": 9.5, "xtick.labelsize": 9, "ytick.labelsize": 9,
        "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#b5bbc2",
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": "#e6e8eb", "grid.linewidth": 0.7,
        "axes.axisbelow": True, "legend.frameon": False, "xtick.color": "#555", "ytick.color": "#555",
        "axes.labelcolor": "#444", "text.color": DARK, "savefig.bbox": "tight", "savefig.pad_inches": 0.04,
    })


def _panel_title(ax, text):
    ax.set_title(text, loc="left", fontweight="bold", fontsize=10.5, pad=8, color=DARK)


def _rd_report_panel(ax, cust, var, est, ylabel, note_x, label):
    """Binned means and local linear lines on both sides of 1,000; the jump is drawn and labelled at the cutoff."""
    c, h = 1000, est["h"]
    r, y = cust.s33.values.astype(float), cust[var].values.astype(float)
    span = 2.0 * h
    for side in ("left", "right"):
        lo, hi = (c - span, c) if side == "left" else (c, c + span)
        m = (r >= lo) & (r < hi) if side == "left" else (r >= lo) & (r <= hi)
        edges = np.linspace(lo, hi, 13)
        idx = np.digitize(r[m], edges[1:-1])
        ks = [k for k in range(12) if (idx == k).sum() > 0]
        ax.scatter([r[m][idx == k].mean() for k in ks], [y[m][idx == k].mean() for k in ks], s=16, color=GREY, zorder=3, lw=0)
        f = _local_linear(r, y, c, h, side)
        grid = np.linspace(c - h, c, 20) if side == "left" else np.linspace(c, c + h, 20)
        ax.plot(grid, f(grid), color=BLUE, lw=2.2, zorder=4)
    lo_v, hi_v = _local_linear(r, y, c, h, "left")(c), _local_linear(r, y, c, h, "right")(c)
    ax.axvline(c, color="#777", lw=0.8, ls=(0, (3, 3)), zorder=2)
    ax.annotate("", xy=(c + 0.04 * span, hi_v), xytext=(c + 0.04 * span, lo_v), arrowprops=dict(arrowstyle="<->", color=DARK, lw=1.1, shrinkA=0, shrinkB=0), zorder=5)
    ax.text(c - 0.07 * span, (lo_v + hi_v) / 2 + (0.0 if abs(hi_v - lo_v) > 0.1 * (ax.get_ylim()[1] - ax.get_ylim()[0]) else 0.0), label, va="center", ha="right", fontsize=10, fontweight="bold", color=BLUE)
    ax.set_xlabel("Spending in week 33 (yen)")
    ax.set_ylabel(ylabel)
    ax.xaxis.set_major_formatter(_yen)
    ax.yaxis.set_major_formatter(_yen)
    ax.set_xlim(c - span, c + span)
    ax.set_xticks([0, 1000, 2000])


def fig_report_rd(cust, res, path: Path):
    """Figure 1: the regression discontinuity at 1,000 yen. A: week-34 level. B: the same customers before any coupon existed."""
    _report_style()
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(REPORT_W, 1.95), gridspec_kw={"wspace": 0.38})
    r1 = res["rd"]["at1000"]
    e = r1["effects"]["s34"]
    _rd_report_panel(ax_a, cust, "s34", e, "Spending in week 34 (yen)", 0, f"{e['effect']:+,.0f}")
    _panel_title(ax_a, "A  After the coupon")
    pre = r1["placebo"]["pre"]
    _rd_report_panel(ax_b, cust, "pre", pre, "Mean of weeks 30 to 32 (yen)", 0, f"{pre['effect']:+,.0f}")
    _panel_title(ax_b, "B  Before the coupon")
    _save_report(fig, path)


def _save_report(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=REPORT_DPI, metadata={"Software": ""})
    plt.close(fig)


def fig_report_did(cust, res, path: Path):
    """Figure 2: the 3000 yen coupon. A: mean spending by group, the coupon group in blue. B: event-study gaps."""
    _report_style()
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(REPORT_W, 1.95), gridspec_kw={"wspace": 0.42, "width_ratios": [1.2, 1]})
    m = cust.groupby("group", observed=True)[[f"s{w}" for w in C.WEEKS]].mean()
    ax_a.axvspan(32.5, 33.5, color="#eef0f3", lw=0, zorder=0)
    ax_a.text(33, 9500, "announced", ha="center", va="center", fontsize=8.5, color="#6b737b")
    labels = {"3000 yen coupon": "3000 yen\ncoupon", "3,000-9,999": "3,000-9,999", "500 yen coupon": "500 yen coupon", "<1,000": "<1,000"}
    nudge = {"500 yen coupon": 700, "<1,000": -750}
    for g in C.GROUP_ORDER:
        hot = g == "3000 yen coupon"
        ax_a.plot(C.WEEKS, m.loc[g].values, color=BLUE if hot else GREY, lw=2.6 if hot else 1.7, marker="o", ms=5 if hot else 3.5, zorder=4 if hot else 3)
        ax_a.text(34.12, m.loc[g].values[-1] + nudge.get(g, 0), labels[g], va="center", ha="left", fontsize=9, fontweight="bold" if hot else "normal", color=BLUE if hot else "#6b737b", linespacing=1.1)
    ax_a.set_xlim(29.7, 36.9)
    ax_a.set_ylim(0, 19000)
    ax_a.set_xticks(C.WEEKS)
    ax_a.set_xlabel("Week")
    ax_a.set_ylabel("Mean spending (yen)")
    ax_a.yaxis.set_major_formatter(_yen)
    _panel_title(ax_a, "A  Mean spending by group")
    co = res["did"]["event_study"]["coefficients"]
    ws = list(C.WEEKS)
    est = np.array([co[str(w)]["estimate"] for w in ws])
    lo = np.array([co[str(w)]["ci_lo"] for w in ws])
    hi = np.array([co[str(w)]["ci_hi"] for w in ws])
    ax_b.axhline(0, color="#777", lw=0.9)
    ax_b.axvspan(32.5, 33.5, color="#eef0f3", lw=0, zorder=0)
    ax_b.plot(ws, est, color=GREY, lw=1.6, zorder=2)
    for w, e_, l_, h_ in zip(ws, est, lo, hi):
        col = BLUE if w == 34 else GREY
        ax_b.vlines(w, l_, h_, color=col, lw=1.6, zorder=3)
        ax_b.plot(w, e_, "o", ms=6.5 if w == 34 else 5, color="white" if w == 33 else col, mec=col, mew=1.4, zorder=4)
    ax_b.annotate(f"{est[-1]:+,.0f}", (34, est[-1]), xytext=(-8, -4), textcoords="offset points", ha="right", va="top", fontsize=10, fontweight="bold", color=BLUE)
    ax_b.annotate("groups set by\nweek-33 spending", (32.95, 650), xytext=(31.3, 1700), ha="center", va="center", fontsize=8.5, color="#6b737b", linespacing=1.15, arrowprops={"arrowstyle": "-", "color": "#9aa1a8", "lw": 0.8})
    ax_b.set_xticks(ws)
    ax_b.set_xlim(29.6, 34.5)
    ax_b.set_xlabel("Week (reference: week 32)")
    ax_b.set_ylabel("Change in gap since week 32 (yen)")
    ax_b.yaxis.set_major_formatter(_yen)
    _panel_title(ax_b, "B  Gap to comparison group")
    _save_report(fig, path)


def fig_bunching(b, path: Path):
    _style()
    p = b["plot"]
    mids, obs, cf, inside = map(np.array, (p["mids"], p["observed"], p["counterfactual"], p["inside"]))
    fig, ax = plt.subplots(figsize=(6.6, 3.0))
    sel = (mids > 5000) & (mids < 15000)
    ax.bar(mids[sel], obs[sel], width=C.BUNCH_BIN * 0.9, color=np.where(inside[sel], "#e7a8b3", "#b9c4cf"), label="observed, week 33")
    ax.plot(mids[sel], cf[sel], color="#1f2d3d", lw=1.6, label="counterfactual (weeks 31-32, rescaled)")
    ax.axvline(10000, color="k", ls="--", lw=0.8)
    m = b["week33"]
    ax.set_title(f"About {m['missing_mass']:.0f} customers moved from below 10,000 to above it, a stretch of roughly {m['stretch']:,.0f} yen", fontsize=8)
    ax.set_xlabel("Spending in week 33 (yen); shaded: response region")
    ax.set_ylabel(f"Customers per {C.BUNCH_BIN} yen")
    ax.xaxis.set_major_formatter(_yen)
    ax.set_ylim(0, 290)
    ax.legend(loc="upper right")
    _save(fig, path)


def make_all(cust, res, fig_dir: Path) -> dict[str, str]:
    """Write every figure. Returns {key: filename} for the appendix and report."""
    names = {
        "trends": "trends.png", "density": "density.png", "rd1000": "rd_1000.png", "rd3000": "rd_3000.png",
        "diagnostics": "balance_placebo.png", "bandwidth": "bandwidth.png", "event": "event_study.png",
        "bunching": "bunching.png", "rd10000": "rd_10000_invalid.png", "report_rd": "report_fig1_rd.png", "report_did": "report_fig2_did.png",
    }
    fig_trends(cust, fig_dir / names["trends"])
    fig_density(cust, res["rd"], fig_dir / names["density"])
    fig_rd(cust, res["rd"]["at1000"], 1000, fig_dir / names["rd1000"], "500 yen coupon, lower edge (customers just above 1,000 yen receive it)")
    fig_rd(cust, res["rd"]["at3000"], 3000, fig_dir / names["rd3000"], "500 yen coupon, upper edge (customers just below 3,000 yen receive it; effect = minus the jump)")
    fig_balance_placebo(res["rd"], fig_dir / names["diagnostics"])
    fig_bandwidth(res["rd"], fig_dir / names["bandwidth"])
    fig_event_study(res["did"], fig_dir / names["event"])
    fig_bunching(res["bunching"], fig_dir / names["bunching"])
    fig_rd_invalid(cust, res["rd"]["at10000"], fig_dir / names["rd10000"])
    fig_report_rd(cust, res, fig_dir / names["report_rd"])
    fig_report_did(cust, res, fig_dir / names["report_did"])
    return names
