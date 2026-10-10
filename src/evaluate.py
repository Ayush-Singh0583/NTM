"""Metrics, per-study diagnostics and the few-shot calibration experiment.

Reads results/predictions*.csv and writes the tables used in the paper to results/.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
K_SHOTS = [1, 2, 3, 5]
N_DRAWS = 1000
SEED = 0


def metrics(y, p):
    err = y - p
    ss_res, ss_tot = np.sum(err ** 2), np.sum((y - y.mean()) ** 2)
    mae = np.mean(np.abs(err))
    return {"r2": 1 - ss_res / ss_tot, "rmse": np.sqrt(np.mean(err ** 2)), "mae": mae, "error_factor": 10 ** mae}


def per_study(d):
    rows = []
    for s, g in d.groupby("study"):
        rho = spearmanr(g.log10_twr, g.pred).statistic if g.pred.nunique() > 1 else np.nan
        rows.append({"study": s, "n": len(g), "error_factor": 10 ** np.mean(np.abs(g.log10_twr - g.pred)),
                     "rho": rho, "bias": np.mean(g.pred - g.log10_twr)})
    return pd.DataFrame(rows)


def summary(pred):
    rows = []
    for (m, fs), g in pred.groupby(["model", "features"], sort=False):
        r = {"model": m, "features": fs}
        rnd = g[g.scheme == "random"]
        reps = [metrics(x.log10_twr.values, x.pred.values) for _, x in rnd.groupby("repeat")]
        for k in ("r2", "error_factor"):
            vals = [x[k] for x in reps]
            r[f"random_{k}"], r[f"random_{k}_sd"] = np.mean(vals), np.std(vals)
        lopo = g[g.scheme == "lopo"]
        lm = metrics(lopo.log10_twr.values, lopo.pred.values)
        ps = per_study(lopo)
        r.update({"lopo_r2": lm["r2"], "lopo_error_factor": lm["error_factor"],
                  "lopo_median_rho": ps.rho.median(), "lopo_median_abs_bias": ps.bias.abs().median(),
                  "lopo_mm3_r2": metrics(10 ** lopo.log10_twr.values, 10 ** lopo.pred.values)["r2"]})
        rows.append(r)
    return pd.DataFrame(rows)


def calibration_draws(study, n, k):
    """Random orders of a study's n runs; the first k are the calibration runs.

    Seeded by study and k only, so every method is scored on the same draws and the
    comparisons between methods are paired.
    """
    rng = np.random.default_rng([SEED, k, sum(ord(c) * 31 ** i for i, c in enumerate(study))])
    return [rng.permutation(n) for _ in range(N_DRAWS)]


def calibrated_errors(y, f, k, draws):
    """Absolute log errors on the runs not used for calibration, per draw.

    method:     mean(y over the k runs) + f(x) - mean(f over the k runs)
    k-run mean: mean(y over the k runs) for every remaining run
    """
    em, eb = [], []
    for idx in draws:
        cal, ev = idx[:k], idx[k:]
        em.append(np.abs(y[ev] - (y[cal].mean() + f[ev] - f[cal].mean())))
        eb.append(np.abs(y[ev] - y[cal].mean()))
    return em, eb


def summarize_calibration(rows):
    """rows: dicts with model, features, k, err_model (list of arrays), err_kmean (list of arrays)."""
    out = []
    for (m, fs, k), g in pd.DataFrame(rows).groupby(["model", "features", "k"], sort=False):
        em = [e for lst in g.err_model for e in lst]
        eb = [e for lst in g.err_kmean for e in lst]
        em_all, eb_all = np.concatenate(em), np.concatenate(eb)
        # paired: share of draws (all studies) in which the method beats the k-run mean
        wins = np.mean([a.mean() < b.mean() for a, b in zip(em, eb)])
        out.append({"model": m, "features": fs, "k": k, "error_factor_model": 10 ** em_all.mean(),
                    "error_factor_kmean": 10 ** eb_all.mean(), "improvement_pct": 100 * (1 - 10 ** (em_all.mean() - eb_all.mean())),
                    "frac_within_x2_model": np.mean(em_all < np.log10(2)),
                    "frac_within_x2_kmean": np.mean(eb_all < np.log10(2)), "win_rate": wins})
    return pd.DataFrame(out)


def calibration(pred, models):
    """Offset calibration of the absolute LOPO predictions from k runs of the held-out study."""
    rows = []
    lopo = pred[pred.scheme == "lopo"]
    for (m, fs), g in lopo.groupby(["model", "features"], sort=False):
        if (m, fs) not in models:
            continue
        for k in K_SHOTS:
            for s, st in g.groupby("study"):
                em, eb = calibrated_errors(st.log10_twr.values, st.pred.values, k, calibration_draws(s, len(st), k))
                rows.append({"model": m, "features": fs, "k": k, "study": s, "err_model": em, "err_kmean": eb})
    return summarize_calibration(rows)


def main():
    pred = pd.read_csv(RESULTS / "predictions.csv")
    s = summary(pred)
    s.to_csv(RESULTS / "summary.csv", index=False)
    print(s.round(3).to_string(index=False))

    lopo = pred[pred.scheme == "lopo"]
    best = {}
    for fs in ("base", "physics"):
        cand = s[(s.features == fs) & (s.model != "Mean baseline")]
        best[fs] = cand.sort_values("lopo_r2", ascending=False).iloc[0].model
    tabs = []
    for fs, m in best.items():
        ps = per_study(lopo[(lopo.model == m) & (lopo.features == fs)])
        ps.insert(0, "model", f"{m} ({fs})")
        tabs.append(ps)
    per = pd.concat(tabs)
    per.to_csv(RESULTS / "lopo_per_study.csv", index=False)
    print("\nbest LOPO models:", best)
    print(per.round(2).to_string(index=False))

    cal = calibration(pred, {(best["base"], "base"), (best["physics"], "physics"),
                             ("Stacked", "physics"), ("Ridge", "physics")})
    cal.to_csv(RESULTS / "calibration.csv", index=False)
    print("\n", cal.round(3).to_string(index=False))

    rows = []
    for f in sorted(RESULTS.glob("predictions_*.csv")):
        p = pd.read_csv(f)
        for (m, fs), g in p[p.scheme == "lopo"].groupby(["model", "features"], sort=False):
            lm = metrics(g.log10_twr.values, g.pred.values)
            rows.append({"subset": f.stem.replace("predictions_", ""), "model": m, "features": fs,
                         "n_runs": len(g), "n_studies": g.study.nunique(), "lopo_r2": lm["r2"],
                         "lopo_error_factor": lm["error_factor"],
                         "lopo_median_rho": per_study(g).rho.median()})
    if rows:
        sens = pd.DataFrame(rows)
        sens.to_csv(RESULTS / "sensitivity.csv", index=False)
        print("\n", sens.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
