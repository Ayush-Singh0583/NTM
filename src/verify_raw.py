"""Check every hand-entered raw table against the text of its source PDF.

For each row, the numbers in the CSV must appear in the same order on one line of
`pdftotext -layout` output (the value printed in the paper, as written). Rows whose
settings had to be decoded from level codes (P06) are checked on the response columns
and the level code. Exit status is non-zero if any row fails.
"""
import csv
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "sources"
RAW = ROOT / "data" / "raw"

# raw table -> (source pdf, columns that must appear on the row's line, in order)
CHECKS = {
    "P06_fatatit2021.csv": ("P06_fatatit2021.pdf", ["run", "code", "mrr_mm3min", "twr_mm3min", "ra_um"]),
    "P10_akincioglu2022.csv": ("P10_akincioglu2022.pdf",
                               ["run", "ton_us", "toff_us", "ip_a", "mrr_gmin", "twr_gmin", "depth_mmmin", "ra_um"]),
    "P12_reddy2016.csv": ("P12_reddy2016.pdf",
                          ["run", "ip_a", "ton_us", "toff_us", "mrr_mm3min", "twr_mm3min", "ra_um"]),
    "P13_ram2025.csv": ("P13_ram2025.pdf",
                        ["run", "ip_a", "ton_us", "toff_us", "shape", "mrr_mm3min", "twr_mm3min", "ra_um"]),
    "H04_chandrashekarappa2021.csv": ("H04_chandrashekarappa2021.pdf",
                                      ["run", "dielectric", "ip_a", "ton_us", "electrode", "mrr_gmin", "ra_um", "twr_gmin"]),
    "H18_hassan2023.csv": ("H18_hassan2023.pdf",
                           ["ip_a", "vg_v", "ton_us", "duty_pct", "mrr_gmin", "ewr_gmin", "roc_mm"]),
}


def contains_in_order(line_tokens, wanted):
    it = iter(line_tokens)
    return all(any(t == w for t in it) for w in wanted)


def main():
    failures = 0
    for table, (pdf, cols) in CHECKS.items():
        text = subprocess.run(["pdftotext", "-layout", str(SRC / pdf), "-"],
                              capture_output=True, text=True, check=True).stdout
        lines = [re.findall(r"[^\s]+", ln) for ln in text.splitlines()]
        with open(RAW / table) as f:
            rows = list(csv.DictReader(f))
        ok = 0
        for r in rows:
            wanted = []
            for c in cols:
                wanted += r[c].split()  # "Distilled water" -> two tokens
            if any(contains_in_order(ln, wanted) for ln in lines):
                ok += 1
            else:
                failures += 1
                print(f"  NOT FOUND {table} run {r.get('run')}: {wanted}")
        print(f"{table}: {ok}/{len(rows)} rows found in {pdf}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
