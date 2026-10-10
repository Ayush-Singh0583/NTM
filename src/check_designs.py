"""Check that each study's runs have the structure of its stated experimental design.

Orthogonal arrays (Taguchi L9, L18, and the 3 x L9 electrode blocks) must be balanced
for every pair of factors: each combination of levels of two factors appears equally
often. The face-centred central composite design of P01 must have 16 factorial,
8 axial and 6 centre runs. Exit status is non-zero if any check fails.
"""
import itertools
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

# raw table -> factors varied by the design
ARRAYS = {
    "P06_fatatit2021.csv": ["electrode", "ip_a", "ton_us", "toff_us"],
    "P10_akincioglu2022.csv": ["ton_us", "toff_us", "ip_a"],
    "P12_reddy2016.csv": ["ip_a", "ton_us", "toff_us"],
    "P13_ram2025.csv": ["ip_a", "ton_us", "toff_us", "shape"],
    "P21_bahgat2019.csv": ["electrode", "ip_a", "ton_us"],
    "H04_chandrashekarappa2021.csv": ["dielectric", "ip_a", "ton_us", "electrode"],
    "H05_jagdale2025.csv": ["electrode", "ton_us", "toff_us", "ip_a"],
    "H17_surani2025.csv": ["ip_a", "ton_us", "duty_pct", "vg_v"],
    "H18_hassan2023.csv": ["ip_a", "vg_v", "ton_us", "duty_pct"],
}


def pairwise_balanced(d, factors):
    for a, b in itertools.combinations(factors, 2):
        counts = d.groupby([a, b]).size()
        full = d[a].nunique() * d[b].nunique()
        if len(counts) != full or counts.nunique() != 1:
            return False, f"{a} x {b}: {len(counts)}/{full} combinations, counts {sorted(set(counts))}"
    return True, ", ".join(f"{f}: {d[f].nunique()} levels" for f in factors)


def ccd_counts(d, factors):
    lo_hi = {f: (d[f].min(), d[f].max()) for f in factors}
    mid = {f: sorted(d[f].unique())[1] for f in factors}
    n_extreme = sum((d[f].isin(lo_hi[f])).astype(int) for f in factors)
    return {"factorial": int((n_extreme == len(factors)).sum()),
            "axial": int((n_extreme == 1).sum()),
            "centre": int((n_extreme == 0).sum() if all((d.loc[n_extreme == 0, f] == mid[f]).all()
                                                         for f in factors) else -1)}


def main():
    ok = True
    for table, factors in ARRAYS.items():
        d = pd.read_csv(RAW / table)
        passed, info = pairwise_balanced(d, factors)
        ok &= passed
        print(f"{table}: {'balanced' if passed else 'NOT BALANCED'} ({len(d)} runs; {info})")
    d = pd.read_csv(RAW / "P01_soundhar2019.csv")
    c = ccd_counts(d, ["vg_v", "ip_a", "ton_us", "toff_us"])
    passed = c == {"factorial": 16, "axial": 8, "centre": 6}
    ok &= passed
    print(f"P01_soundhar2019.csv: {'face-centred CCD' if passed else 'NOT A CCD'} ({c})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
