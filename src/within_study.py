"""Within-study ("level-free") models under leave-one-paper-out validation.

Each model is fitted to within-study variation only: the inputs and log10(TWR) are both
centred on the mean of their own study (the fixed-effects, or "within", estimator), so
the model learns how wear changes with the settings inside a study and nothing about
the level of a study. For a held-out study, the inputs are centred on that study's own
settings (known before any run is made) and the level is set from k measured runs:

    prediction = mean(y over the k runs) + f(x) - mean(f(x) over the k runs)

Errors are measured on the remaining runs and compared, on the same draws, with the
k-run mean on its own. Writes results/within_study.csv and results/within_study_rho.csv.
"""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.stats import spearmanr
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import GridSearchCV, LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from evaluate import K_SHOTS, calibrated_errors, calibration_draws, summarize_calibration
from models import FEATURES, SEED, add_derived, rf, svr

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def design(df, fs):
    """Numeric inputs plus one-hot categories (fixed category lists), not yet centred."""
    f = FEATURES[fs]
    X = df[f["num"]].astype(float)
    for c in f["cat"]:
        X = X.join(pd.get_dummies(df[c], prefix=c, dtype=float))
    return X


def centre(X, groups):
    return X - X.groupby(groups).transform("mean")


def ridge():
    return Pipeline([("scale", StandardScaler()), ("m", RidgeCV(alphas=np.logspace(-3, 3, 13)))])


def tuned(est, grid):
    return GridSearchCV(Pipeline([("scale", StandardScaler()), ("m", est)]), grid, cv=LeaveOneGroupOut(),
                        scoring="neg_mean_squared_error", n_jobs=1)


def xgb_monotone(n_features):
    # wear may only rise with peak current, the first input of every feature set
    cons = "(" + ",".join(["1"] + ["0"] * (n_features - 1)) + ")"
    return tuned(XGBRegressor(n_estimators=200, subsample=0.8, colsample_bytree=0.8, min_child_weight=2,
                              max_depth=2, random_state=SEED, n_jobs=1, verbosity=0, monotone_constraints=cons),
                 {"m__learning_rate": [0.05, 0.1]})


MODELS = {  # name -> (feature set, estimator factory taking the number of inputs, needs groups)
    "Peak current only (ridge)": ("ip_only", lambda n: ridge(), False),
    "Ridge (base)": ("base", lambda n: ridge(), False),
    "Ridge (physics)": ("physics", lambda n: ridge(), False),
    "RF (physics)": ("physics", lambda n: tuned(rf(), {"m__max_depth": [None, 5], "m__min_samples_leaf": [1, 3]}),
                     True),
    "SVR (physics)": ("physics", lambda n: tuned(svr(), {"m__C": [1, 3, 10], "m__gamma": ["scale", 0.1]}), True),
    "XGBoost, monotone in Ip (physics)": ("physics", xgb_monotone, True),
}


def lopo_within_predictions(df, name):
    warnings.filterwarnings("ignore")
    fs, factory, needs_groups = MODELS[name]
    X = centre(design(df, fs), df.study.values)
    y = df.log10_twr - df.groupby("study").log10_twr.transform("mean")
    out = []
    for tr, te in LeaveOneGroupOut().split(df, groups=df.study):
        est = factory(X.shape[1])
        # each study is centred on its own runs only, so no information crosses between studies
        if needs_groups:
            est.fit(X.iloc[tr], y.iloc[tr], groups=df.study.values[tr])
        else:
            est.fit(X.iloc[tr], y.iloc[tr])
        out.append(df.iloc[te].assign(f=est.predict(X.iloc[te])))
    return name, pd.concat(out)


def main():
    df = add_derived(pd.read_csv(ROOT / "data" / "twr_dataset.csv"))
    res = Parallel(n_jobs=-1)(delayed(lopo_within_predictions)(df, n) for n in MODELS)
    rows, rho_rows = [], []
    for name, p in res:
        for s, st in p.groupby("study"):
            rho_rows.append({"model": name, "study": s, "rho": spearmanr(st.log10_twr, st.f).statistic})
            for k in K_SHOTS:
                em, eb = calibrated_errors(st.log10_twr.values, st.f.values, k, calibration_draws(s, len(st), k))
                rows.append({"model": name, "features": MODELS[name][0], "k": k, "study": s,
                             "err_model": em, "err_kmean": eb})
    cal = summarize_calibration(rows)
    rho = pd.DataFrame(rho_rows)
    cal.to_csv(RESULTS / "within_study.csv", index=False)
    rho.to_csv(RESULTS / "within_study_rho.csv", index=False)
    print(rho.pivot(index="study", columns="model", values="rho").round(2).to_string())
    print("median rho:\n", rho.groupby("model", sort=False).rho.median().round(2).to_string())
    print(cal.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
