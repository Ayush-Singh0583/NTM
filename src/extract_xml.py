"""Write the per-run tables of the studies available as JATS XML (Europe PMC) to data/raw/.

These tables are parsed from the publisher XML, not typed, so they are exact copies
of the published values. Run src/fetch_sources.py first.
"""
import csv
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "sources"
RAW = ROOT / "data" / "raw"


def text(e):
    return re.sub(r"\s+", " ", "".join(e.itertext())).strip()


def table_rows(xml_file, label):
    """Return the body rows (lists of cell strings) of the table with this label."""
    root = ET.parse(xml_file).getroot()
    for tw in root.iter("table-wrap"):
        lab = tw.find("label")
        if lab is not None and text(lab) == label:
            rows = []
            for tr in tw.iter("tr"):
                rows.append([text(c) for c in tr if c.tag in ("td", "th")])
            return rows
    raise ValueError(f"{label} not found in {xml_file}")


def numeric_rows(rows, first_col_is_int=True):
    out = []
    for r in rows:
        if r and (r[0].isdigit() if first_col_is_int else True):
            out.append(r)
    return out


def write(name, header, rows):
    RAW.mkdir(parents=True, exist_ok=True)
    with open(RAW / name, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"{name}: {len(rows)} runs")


def main():
    # P01 Soundhar et al. 2019, Table 5 (EWR in g/min)
    rows = numeric_rows(table_rows(SRC / "P01_soundhar2019.xml", "Table 5"))
    write("P01_soundhar2019.csv",
          ["run", "vg_v", "ip_a", "ton_us", "toff_us", "mrr_gmin", "ewr_gmin", "ra_um"], rows)

    # P21 Bahgat et al. 2019, Table 7 (MRR in mm3/min, EWR in %)
    rows = numeric_rows(table_rows(SRC / "P21_bahgat2019.xml", "Table 7"))
    rows = [[r[0], r[1], r[2], r[3], r[4], r[6], r[8]] for r in rows]
    write("P21_bahgat2019.csv",
          ["run", "electrode", "ip_a", "ton_us", "mrr_mm3min", "ewr_pct", "ra_um"], rows)

    # H05 Jagdale et al. 2025, Table 4 (wide: one block of MRR, SR, TWR, DD per electrode)
    rows = numeric_rows(table_rows(SRC / "H05_jagdale2025.xml", "Table 4"))
    long = []
    for r in rows:
        run, ton, toff, ip = r[0:4]
        for k, electrode in enumerate(["Copper", "Brass", "Graphite"]):
            mrr, sr, twr, dd = r[4 + 4 * k: 8 + 4 * k]
            long.append([f"{electrode[0]}{run}", electrode, ton, toff, ip, mrr, sr, twr])
    write("H05_jagdale2025.csv",
          ["run", "electrode", "ton_us", "toff_us", "ip_a", "mrr_mm3min", "ra_um", "twr_mm3min"], long)

    # H17 Surani et al. 2025: settings from Table 5, TWR from Table 9 (same run order)
    settings = numeric_rows(table_rows(SRC / "H17_surani2025.xml", "Table 5"))
    twr = [r for r in table_rows(SRC / "H17_surani2025.xml", "Table 9") if r and r[0].startswith("IP")]
    assert len(settings) == len(twr) == 9
    rows = []
    for s, t in zip(settings, twr):
        cond = dict(re.findall(r"(IP|TON|DC|Vg) = ([\d.]+)", t[0]))
        assert [cond["IP"], cond["TON"], cond["DC"], cond["Vg"]] == s[1:5], (s, t)
        rows.append(s + [t[1]])
    write("H17_surani2025.csv", ["run", "ip_a", "ton_us", "duty_pct", "vg_v", "twr_mm3min"], rows)


if __name__ == "__main__":
    main()
