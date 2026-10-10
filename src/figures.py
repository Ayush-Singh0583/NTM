"""Figures for the paper (PNG at 300 dpi and PDF) in figures/."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
FIG = ROOT / "figures"

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
GREY, INK, INK2, GRID = "#8a8985", "#0b0b0b", "#52514e", "#e4e3df"
COL = 3.5  # IEEE single-column width, inches

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Liberation Serif", "DejaVu Serif"],
    "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "xtick.labelsize": 7, "ytick.labelsize": 7,
    "legend.fontsize": 7, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
    "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True, "legend.frameon": False,
    "savefig.dpi": 300, "savefig.bbox": "tight", "lines.linewidth": 1.5,
})

STUDY_ORDER = ["P01", "P06", "P10", "P12", "P13", "P21", "H04", "H05", "H17", "H18"]


def save(fig, name):
    FIG.mkdir(exist_ok=True)
    fig.savefig(FIG / f"{name}.png")
    fig.savefig(FIG / f"{name}.pdf")
    plt.close(fig)


def fig_workflow():
    steps = ["Search and\nscreening", "Table\nextraction", "Check against\nsource text",
             "Units and\nfeatures", "Random CV\nand LOPO", "Within-study\nmodels, k-run\ncalibration"]
    fig, ax = plt.subplots(figsize=(COL, 1.45))
    ax.set_axis_off()
    w, h, gx, gy = 0.9, 0.5, 0.3, 0.28
    pos = [(i * (w + gx), h + gy) for i in range(3)] + [((2 - i) * (w + gx), 0) for i in range(3)]
    for (x, y), s in zip(pos, steps):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.05",
                                    fc="#f3f2ee", ec=INK2, lw=0.8))
        ax.text(x + w / 2, y + h / 2, s, ha="center", va="center", fontsize=6.5, color=INK)
    arrow = dict(arrowstyle="-|>", color=INK2, lw=0.8)
    for i in range(5):
        (x0, y0), (x1, y1) = pos[i], pos[i + 1]
        if y0 == y1:
            start = (x0 + w + 0.03, y0 + h / 2) if x1 > x0 else (x0 - 0.03, y0 + h / 2)
            end = (x1 - 0.03, y1 + h / 2) if x1 > x0 else (x1 + w + 0.03, y1 + h / 2)
        else:
            start, end = (x0 + w / 2, y0 - 0.03), (x1 + w / 2, y1 + h + 0.03)
        ax.annotate("", xy=end, xytext=start, arrowprops=arrow)
    ax.set_xlim(-0.05, 3 * w + 2 * gx + 0.05)
    ax.set_ylim(-0.05, 2 * h + gy + 0.05)
    save(fig, "fig1_workflow")


def fig_twr_by_study():
    d = pd.read_csv(ROOT / "data" / "twr_dataset.csv")
    fig, ax = plt.subplots(figsize=(COL, 2.4))
    rng = np.random.default_rng(0)
    for i, s in enumerate(STUDY_ORDER):
        g = d[d.study == s]
        y = i + rng.uniform(-0.18, 0.18, len(g))
        z = g.printed_zero.values
        ax.scatter(g.twr_mm3min[~z], y[~z], s=12, color=BLUE, edgecolor="white", linewidth=0.4, zorder=3)
        ax.scatter(g.twr_mm3min[z], y[z], s=12, facecolor="white", edgecolor=BLUE, linewidth=0.8, zorder=3)
    ax.set_xscale("log")
    ax.set_yticks(range(len(STUDY_ORDER)), STUDY_ORDER)
    ax.invert_yaxis()
    ax.set_xlabel("TWR (mm³/min, log scale)")
    ax.grid(axis="y", visible=False)
    save(fig, "fig2_twr_by_study")


def fig_r2():
    s = pd.read_csv(RES / "summary.csv")
    models = ["Mean baseline", "Ridge", "RF", "XGBoost", "ANN", "SVR", "Stacked"]
    fig, axes = plt.subplots(2, 1, figsize=(COL, 3.6), sharex=True)
    for ax, (col, title) in zip(axes, [("random_r2", "Random 5-fold CV"), ("lopo_r2", "Leave-one-paper-out")]):
        y = np.arange(len(models))
        for k, (fs, color, label) in enumerate([("base", BLUE, "Base inputs"), ("physics", ORANGE, "Physics features")]):
            v = [s[(s.model == m) & (s.features == fs)][col].iloc[0] for m in models]
            ax.barh(y + (k - 0.5) * 0.38, v, height=0.34, color=color, label=label, edgecolor="white", linewidth=0.6)
        ax.axvline(0, color=INK2, lw=0.8)
        ax.set_yticks(y, models)
        ax.invert_yaxis()
        ax.set_title(title, loc="left", color=INK)
        ax.grid(axis="y", visible=False)
    axes[1].set_xlabel("R² on log10(TWR)")
    axes[1].set_xlim(-0.6, 0.75)
    axes[0].legend(loc="lower left", bbox_to_anchor=(0, 1.08), ncol=2)
    save(fig, "fig3_r2")


def fig_rank():
    ab = pd.read_csv(RES / "lopo_per_study.csv")
    ab = ab[ab.model == ab.model.iloc[0]]  # best absolute model on base inputs
    ws = pd.read_csv(RES / "within_study_rho.csv")
    series = [
        (ab.set_index("study").rho, f"{ab.model.iloc[0]}, absolute", GREY, "s"),
        (ws[ws.model == "Ridge (base)"].set_index("study").rho, "Ridge (base), within-study", BLUE, "o"),
        (ws[ws.model == "Peak current only (ridge)"].set_index("study").rho, "Peak current only", ORANGE, "D"),
    ]
    fig, ax = plt.subplots(figsize=(COL, 2.6))
    y = np.arange(len(STUDY_ORDER))
    for k, (v, label, color, mk) in enumerate(series):
        ax.scatter([v[s] for s in STUDY_ORDER], y + (k - 1) * 0.22, s=18, marker=mk, color=color,
                   edgecolor="white", linewidth=0.5, label=f"{label} (median {v.median():.2f})", zorder=3)
    ax.axvline(0, color=INK2, lw=0.8)
    ax.set_yticks(y, STUDY_ORDER)
    ax.invert_yaxis()
    ax.set_xlim(-1, 1)
    ax.set_xlabel("Spearman ρ within the held-out study")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=1)
    save(fig, "fig4_rank")


def fig_calibration():
    cal = pd.read_csv(RES / "calibration.csv")
    ws = pd.read_csv(RES / "within_study.csv")
    fig, ax = plt.subplots(figsize=(COL, 2.3))
    km = ws[ws.model == "Peak current only (ridge)"]
    ax.plot(km.k, km.error_factor_kmean, color=GREY, ls="--", marker="s", ms=4, label="Mean of the k runs (no model)")
    a = cal[(cal.model == "Ridge") & (cal.features == "base") & (cal.k > 0)]
    ax.plot(a.k, a.error_factor_model, color=AQUA, marker="^", ms=4, label="Absolute ridge + offset")
    for name, color, mk in [("Ridge (base)", BLUE, "o"), ("Peak current only (ridge)", ORANGE, "D")]:
        g = ws[ws.model == name]
        ax.plot(g.k, g.error_factor_model, color=color, marker=mk, ms=4,
                label=f"Within-study {name.replace(' (ridge)', '')}")
    ax.set_xlabel("Runs k from the new study used for calibration")
    ax.set_ylabel("Typical error factor (×)")
    ax.set_xticks([1, 2, 3, 5])
    ax.legend(loc="upper right")
    save(fig, "fig5_calibration")


if __name__ == "__main__":
    fig_workflow()
    fig_twr_by_study()
    fig_r2()
    fig_rank()
    fig_calibration()
    print("figures written to", FIG)
