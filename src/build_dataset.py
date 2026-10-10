"""Combine the raw per-study tables into data/twr_dataset.csv.

Every conversion applied here is listed in data/studies.csv. Run order and values
are otherwise left exactly as published.
"""
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

# densities used only where a study does not report its own (median of the reported values, data/materials.csv)
NOMINAL_DENSITY = {"Graphite": 1.77, "Copper": 8.92}
ZERO_FILL = 0.0025  # a quarter of the printed step (0.01 mm3/min) for values printed as 0
ELECTRODE_NAMES = {"Cu": "Copper", "CuCrZr": "CuCrZr", "CuCo1Ni1Be": "CuCo1Ni1Be"}


def duty(ton, toff):
    return 100 * ton / (ton + toff)


def p01():
    d = pd.read_csv(RAW / "P01_soundhar2019.csv")
    return pd.DataFrame({
        "run": d.run, "electrode": "Graphite", "ip_a": d.ip_a, "ton_us": d.ton_us, "toff_us": d.toff_us,
        "gap_voltage_v": d.vg_v, "twr_mm3min": d.ewr_gmin / NOMINAL_DENSITY["Graphite"] * 1000})


def p06():
    d = pd.read_csv(RAW / "P06_fatatit2021.csv")
    return pd.DataFrame({
        "run": d.run, "electrode": d.electrode.map(ELECTRODE_NAMES), "ip_a": d.ip_a, "ton_us": d.ton_us,
        "toff_us": d.toff_us, "twr_mm3min": d.twr_mm3min, "printed_zero": d.twr_mm3min == 0})


def p10():
    d = pd.read_csv(RAW / "P10_akincioglu2022.csv")
    return pd.DataFrame({
        "run": d.run, "electrode": "Copper", "ip_a": d.ip_a, "ton_us": d.ton_us, "toff_us": d.toff_us,
        "twr_mm3min": d.twr_gmin / 8.9 * 1000})


def p12():
    d = pd.read_csv(RAW / "P12_reddy2016.csv")
    return pd.DataFrame({
        "run": d.run, "electrode": "Copper", "ip_a": d.ip_a, "ton_us": d.ton_us, "toff_us": d.toff_us,
        "twr_mm3min": d.twr_mm3min})


def p13():
    d = pd.read_csv(RAW / "P13_ram2025.csv")
    return pd.DataFrame({
        "run": d.run, "electrode": "Copper", "ip_a": d.ip_a, "ton_us": d.ton_us, "toff_us": d.toff_us,
        "tool_shape": d["shape"], "twr_mm3min": d.twr_mm3min})


def p21():
    d = pd.read_csv(RAW / "P21_bahgat2019.csv")
    return pd.DataFrame({
        "run": d.run, "electrode": d.electrode, "ip_a": d.ip_a, "ton_us": d.ton_us, "duty_pct": 50.0,
        "twr_mm3min": d.ewr_pct * d.mrr_mm3min / 100, "twr_derived": True})


def h04():
    d = pd.read_csv(RAW / "H04_chandrashekarappa2021.csv")
    rho = d.electrode.map({"Graphite": 1.77, "Copper": 8.904, "Brass": 8.55})
    return pd.DataFrame({
        "run": d.run, "electrode": d.electrode, "ip_a": d.ip_a, "ton_us": d.ton_us, "toff_us": 50.0,
        "dielectric": d.dielectric.str.lower(), "twr_mm3min": d.twr_gmin / rho * 1000})


def h05():
    d = pd.read_csv(RAW / "H05_jagdale2025.csv")
    return pd.DataFrame({
        "run": d.run, "electrode": d.electrode, "ip_a": d.ip_a, "ton_us": d.ton_us, "toff_us": d.toff_us,
        "twr_mm3min": d.twr_mm3min})


def h17():
    d = pd.read_csv(RAW / "H17_surani2025.csv")
    return pd.DataFrame({
        "run": d.run, "electrode": "Copper", "ip_a": d.ip_a, "ton_us": d.ton_us, "duty_pct": d.duty_pct,
        "gap_voltage_v": d.vg_v, "twr_mm3min": d.twr_mm3min})


def h18():
    d = pd.read_csv(RAW / "H18_hassan2023.csv")
    return pd.DataFrame({
        "run": d.run, "electrode": "Copper", "ip_a": d.ip_a, "ton_us": d.ton_us, "duty_pct": d.duty_pct,
        "gap_voltage_v": d.vg_v, "twr_mm3min": d.ewr_gmin / NOMINAL_DENSITY["Copper"] * 1000})


BUILDERS = {"P01": p01, "P06": p06, "P10": p10, "P12": p12, "P13": p13, "P21": p21,
            "H04": h04, "H05": h05, "H17": h17, "H18": h18}


def build():
    studies = pd.read_csv(ROOT / "data" / "studies.csv").set_index("study")
    materials = pd.read_csv(ROOT / "data" / "materials.csv").set_index("electrode")
    parts = []
    for sid, fn in BUILDERS.items():
        d = fn()
        meta = studies.loc[sid]
        d.insert(0, "study", sid)
        d["workpiece"] = meta.workpiece
        d["workpiece_class"] = meta.workpiece_class
        if "dielectric" not in d:
            d["dielectric"] = meta.dielectric
        d["special_process"] = meta.special_process != "none"
        d["polarity"] = meta.polarity
        parts.append(d)
    df = pd.concat(parts, ignore_index=True)

    for col in ["toff_us", "duty_pct", "gap_voltage_v", "tool_shape"]:
        if col not in df:
            df[col] = np.nan
    df["duty_pct"] = df.duty_pct.fillna(duty(df.ton_us, df.toff_us))
    df["printed_zero"] = df.get("printed_zero", False).fillna(False).astype(bool)
    df["twr_derived"] = df.get("twr_derived", False).fillna(False).astype(bool)
    df.loc[df.printed_zero, "twr_mm3min"] = ZERO_FILL
    df["charge_uc"] = df.ip_a * df.ton_us  # A x us = uC
    for col, src in [("el_melting_c", "melting_point_c"), ("el_conductivity_wmk", "thermal_conductivity_wmk"),
                     ("el_density_gcm3", "density_gcm3")]:
        df[col] = df.electrode.map(materials[src])
    df["el_thermal_index"] = (df.el_melting_c + 273.15) * df.el_conductivity_wmk
    df["log10_twr"] = np.log10(df.twr_mm3min)
    df["twr_mm3min"] = df.twr_mm3min.round(6)

    cols = ["study", "run", "workpiece", "workpiece_class", "electrode", "ip_a", "ton_us", "toff_us", "duty_pct",
            "charge_uc", "gap_voltage_v", "dielectric", "special_process", "tool_shape", "polarity",
            "el_melting_c", "el_conductivity_wmk", "el_density_gcm3", "el_thermal_index",
            "twr_mm3min", "log10_twr", "printed_zero", "twr_derived"]
    return df[cols]


if __name__ == "__main__":
    df = build()
    df.to_csv(ROOT / "data" / "twr_dataset.csv", index=False)
    print(f"{len(df)} runs from {df.study.nunique()} studies")
    print(df.groupby("study").agg(n=("run", "size"), electrodes=("electrode", lambda s: ", ".join(sorted(set(s)))),
                                  twr_min=("twr_mm3min", "min"), twr_max=("twr_mm3min", "max")).to_string())
