# Transfer of tool wear rate models in die-sinking EDM

Data and code for the paper *How Well Do Tool Wear Rate Models for Die-Sinking EDM Transfer to a New
Laboratory? A Leave-One-Paper-Out Evaluation on Data from Ten Published Studies*
(Adithya D, Billava Srujan Macha, Ayush Singh; RV Institute of Technology and Management).

**Main result.** On 156 runs from 10 published studies, random 5-fold cross-validation gives R² ≈ 0.6 on
log10(TWR), but no model transfers reliably to a held-out study. Every nonlinear model (RF, XGBoost, ANN,
SVR, stacked) falls below zero; ridge regression stays barely positive (R² = 0.12), and only as long as
studies P01 and H18 are included. More than half of the held-out error is the overall wear level of each
study. A within-study model of peak current, with the level set from a few runs of the new study, beats
the mean of those runs by 9–10%.

| | Random CV R² | Leave-one-paper-out R² | Median ρ within held-out study |
|---|---|---|---|
| Mean baseline | −0.01 | −0.22 | – |
| Ridge, base inputs | 0.42 | **0.12** | 0.17 |
| RF, physics features | **0.61** | −0.25 | 0.03 |
| Within-study ridge (base) | – | – | **0.57** |
| Within-study peak current only | – | – | 0.55 |

All numbers in the paper are computed from `results/` by `paper/build_paper.py`, which also checks every
qualitative claim in the text and stops if one no longer holds.

## Layout

```
data/
  raw/                 per-study tables exactly as published (one CSV per study)
  studies.csv          workpiece, dielectric, polarity, design, unit conversion and known problems per study
  materials.csv        electrode properties used as features, with their sources
  twr_dataset.csv      combined dataset (156 runs), built by src/build_dataset.py
  sources.sha256       checksums of the source articles used
  sources/             source articles (downloaded, not committed)
src/
  fetch_sources.py     download the source articles and verify checksums
  extract_xml.py       parse the four XML tables (Europe PMC) into data/raw/
  verify_raw.py        check every typed table row against the text of its source PDF
  check_designs.py     check each study's runs have the structure of its stated design
  build_dataset.py     unit conversion, features, combined dataset
  models.py            feature sets, models and hyperparameter grids
  run_experiments.py   random CV and leave-one-paper-out predictions (+ data-subset runs)
  evaluate.py          metrics, per-study diagnostics, few-run calibration
  within_study.py      within-study (level-free) models and calibration
  figures.py           paper figures
results/               predictions and summary tables (CSV)
figures/               figures (PNG, PDF)
paper/
  build_paper.py       builds the paper (.docx) from results/ and figures/
  references.py        reference list (checked against Crossref)
  EDM_TWR_paper.docx   the paper
run_all.sh             reruns everything end to end
```

## Reproduce

```bash
python -m venv .venv && source .venv/bin/activate
pip install --no-deps xgboost==3.4.1        # CPU build without the 200 MB GPU dependency
pip install -r requirements.txt
sudo apt install poppler-utils              # pdftotext, used by verify_raw.py
./run_all.sh                                # about 6 minutes on a 28-core machine; longer on a laptop
```

All models are seeded, so a rerun reproduces the numbers in `results/` exactly.

## How the data were extracted

* **P01, P21, H05, H17**: tables parsed by script from the publisher JATS XML (Europe PMC), so they are exact copies.
* **P06, P10, P12, P13, H04, H18**: tables typed from the PDF, then `src/verify_raw.py` checks that every row
  appears value by value, in order, on one line of the PDF text layer (81/81 rows pass; a deliberately altered
  value is caught).
* `src/check_designs.py` confirms every orthogonal array is balanced for every pair of factors and that the
  P01 central composite design has 16 factorial, 8 axial and 6 centre runs.
* Every unit conversion is listed in `data/studies.csv`. Problems found in the sources are kept visible there
  rather than silently fixed (for example, a pulse-on misprint in P06, a balance too coarse for the wear rates in
  P12, and tool mass loss above workpiece mass loss in H04). `results/sensitivity.csv` shows that removing any of
  them does not change the conclusions.

Two further studies with usable tables (Sultan et al. 2014; Agrawal et al. 2026) could not be downloaded and are
not yet included.

## Dataset columns (`data/twr_dataset.csv`)

| Column | Meaning |
|---|---|
| `study`, `run` | study ID (see `data/studies.csv`) and run number as published |
| `workpiece`, `workpiece_class` | workpiece material; steel / titanium / nickel |
| `electrode` | Copper, Graphite, Brass, CuCrZr, CuCo1Ni1Be |
| `ip_a`, `ton_us`, `toff_us` | peak current (A), pulse-on and pulse-off time (µs) |
| `duty_pct` | duty factor (%), as reported or 100·Ton/(Ton+Toff) |
| `charge_uc` | Ip·Ton (µC) |
| `gap_voltage_v`, `polarity`, `dielectric`, `tool_shape` | as reported (often missing; not used as inputs if < 80% known) |
| `special_process` | powder-mixed dielectric (P13) |
| `el_*` | electrode melting point (°C), thermal conductivity (W/m K), density (g/cm³), thermal index |
| `twr_mm3min`, `log10_twr` | tool wear rate (mm³/min) and the model target |
| `printed_zero` | TWR printed as 0 in the source; set to 0.0025 mm³/min |
| `twr_derived` | TWR computed as EWR% × MRR / 100 (P21) |

## Notes

* The source articles are third-party publications and are not redistributed; `src/fetch_sources.py`
  downloads them (all are open access) and verifies them against `data/sources.sha256`.
