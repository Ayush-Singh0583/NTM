"""Random CV and leave-one-paper-out (LOPO) evaluation of every model and feature set.

Writes out-of-fold predictions to results/predictions.csv. Hyperparameters are tuned
by grid search inside each training split only (5-fold for random CV, leave-one-study-out
over the training studies for LOPO), so no test run influences model selection.

Usage: python src/run_experiments.py [--exclude NAME] [--tag TAG]
"""
import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.model_selection import GridSearchCV, KFold, LeaveOneGroupOut

from models import MODELS, SEED, add_derived, columns, grid, pipeline

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
N_REPEATS = 3  # repeats of random 5-fold CV (different shuffles)

EXCLUSIONS = {
    "none": lambda d: d,
    "no_P01_run13": lambda d: d[~((d.study == "P01") & (d.run.astype(str) == "13"))],
    "no_derived_P21": lambda d: d[~d.twr_derived],
    "no_printed_zero": lambda d: d[~d.printed_zero],
    "no_H04": lambda d: d[d.study != "H04"],
    "no_P12": lambda d: d[d.study != "P12"],
    "no_P13_pmedm": lambda d: d[d.study != "P13"],
    "no_borrowed_density": lambda d: d[~d.study.isin(["P01", "H18"])],
    "original_6_studies": lambda d: d[d.study.isin(["P01", "P06", "P10", "P12", "P13", "P21"])],
}


def fit_predict(model, fs, train, test, inner_cv, inner_groups):
    est = pipeline(model, fs)
    g = grid(model)
    X_tr, y_tr = train[columns(fs)], train.log10_twr.values
    if g:
        est = GridSearchCV(est, g, cv=inner_cv, scoring="neg_mean_squared_error", n_jobs=1)
        est.fit(X_tr, y_tr, groups=inner_groups)
        params = est.best_params_
    else:
        est.fit(X_tr, y_tr)
        params = {}
    return est.predict(test[columns(fs)]), params


def run_one(df, model, fs, scheme):
    warnings.filterwarnings("ignore")
    rows = []
    if scheme == "random":
        for rep in range(N_REPEATS):
            for fold, (tr, te) in enumerate(KFold(5, shuffle=True, random_state=SEED + rep).split(df)):
                train, test = df.iloc[tr], df.iloc[te]
                inner = KFold(5, shuffle=True, random_state=SEED)
                pred, params = fit_predict(model, fs, train, test, inner, None)
                rows.append(test.assign(pred=pred, fold=f"{rep}-{fold}", repeat=rep, params=str(params)))
    else:
        for tr, te in LeaveOneGroupOut().split(df, groups=df.study):
            train, test = df.iloc[tr], df.iloc[te]
            pred, params = fit_predict(model, fs, train, test, LeaveOneGroupOut(), train.study.values)
            rows.append(test.assign(pred=pred, fold=test.study.iloc[0], repeat=0, params=str(params)))
    out = pd.concat(rows)
    out["model"], out["features"], out["scheme"] = model, fs, scheme
    return out[["study", "run", "electrode", "log10_twr", "pred", "fold", "repeat", "model", "features",
                "scheme", "params"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exclude", default="none", choices=EXCLUSIONS)
    ap.add_argument("--schemes", default="random,lopo")
    ap.add_argument("--models", default=",".join(MODELS))
    args = ap.parse_args()

    df = add_derived(pd.read_csv(ROOT / "data" / "twr_dataset.csv"))
    df = EXCLUSIONS[args.exclude](df).reset_index(drop=True)
    jobs = [(m, fs, s) for s in args.schemes.split(",") for m in args.models.split(",")
            for fs in ("base", "physics")]
    print(f"{len(df)} runs, {df.study.nunique()} studies, {len(jobs)} jobs")
    outs = Parallel(n_jobs=-1, verbose=5)(delayed(run_one)(df, m, fs, s) for m, fs, s in jobs)
    pred = pd.concat(outs, ignore_index=True)
    RESULTS.mkdir(exist_ok=True)
    name = "predictions.csv" if args.exclude == "none" else f"predictions_{args.exclude}.csv"
    pred.to_csv(RESULTS / name, index=False)
    print("wrote", RESULTS / name)


if __name__ == "__main__":
    main()
