"""Feature sets, model definitions and hyperparameter grids."""
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor, StackingRegressor
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import SVR
from xgboost import XGBRegressor

SEED = 0

FEATURES = {
    "ip_only": {
        "num": ["ip_a"],
        "cat": [],
    },
    "base": {
        "num": ["ip_a", "ton_us", "duty_pct"],
        "cat": ["electrode"],
    },
    "physics": {
        "num": ["ip_a", "log_ton", "duty_pct", "log_charge", "el_melting_c", "el_conductivity_wmk",
                "el_density_gcm3", "el_thermal_index", "special_process"],
        "cat": ["workpiece_class", "dielectric"],
    },
}


def add_derived(df):
    df = df.copy()
    df["log_ton"] = np.log10(df.ton_us)
    df["log_charge"] = np.log10(df.charge_uc)
    df["special_process"] = df.special_process.astype(float)
    return df


def preprocessor(feature_set):
    f = FEATURES[feature_set]
    return ColumnTransformer([
        ("num", StandardScaler(), f["num"]),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), f["cat"]),
    ])


def columns(feature_set):
    f = FEATURES[feature_set]
    return f["num"] + f["cat"]


def rf(**kw):
    return RandomForestRegressor(n_estimators=200, max_features=0.7, random_state=SEED, n_jobs=1, **kw)


def xgb(**kw):
    return XGBRegressor(n_estimators=200, subsample=0.8, colsample_bytree=0.8, min_child_weight=2,
                        random_state=SEED, n_jobs=1, verbosity=0, **kw)


def ann(**kw):
    return MLPRegressor(solver="lbfgs", max_iter=5000, random_state=SEED, **kw)


def svr(**kw):
    return SVR(kernel="rbf", epsilon=0.1, **kw)


def stacked():
    return StackingRegressor(
        estimators=[("rf", rf(min_samples_leaf=2)), ("xgb", xgb(max_depth=3, learning_rate=0.05)),
                    ("svr", svr(C=3)), ("ann", ann(hidden_layer_sizes=(16,), alpha=1.0))],
        final_estimator=LinearRegression(positive=True), cv=5, n_jobs=1)


# name -> (estimator factory, grid over the final step "m")
MODELS = {
    "Mean baseline": (lambda: DummyRegressor(), {}),
    "Ridge": (lambda: RidgeCV(alphas=np.logspace(-3, 3, 13)), {}),
    "RF": (rf, {"m__max_depth": [None, 5], "m__min_samples_leaf": [1, 3]}),
    "XGBoost": (xgb, {"m__max_depth": [2, 4], "m__learning_rate": [0.05, 0.1]}),
    "ANN": (ann, {"m__hidden_layer_sizes": [(8,), (16, 8)], "m__alpha": [0.1, 1.0]}),
    "SVR": (svr, {"m__C": [1, 3, 10, 30], "m__gamma": ["scale", 0.1]}),
    "Stacked": (stacked, {}),
}


def pipeline(model_name, feature_set):
    factory, _ = MODELS[model_name]
    return Pipeline([("prep", preprocessor(feature_set)), ("m", factory())])


def grid(model_name):
    return MODELS[model_name][1]

