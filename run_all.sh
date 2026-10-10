#!/usr/bin/env bash
# Rebuild everything from the source articles: data -> experiments -> tables -> figures -> paper.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python}

$PY src/fetch_sources.py          # download sources, verify checksums
$PY src/extract_xml.py            # parse the four XML tables into data/raw/
$PY src/verify_raw.py             # check the six typed tables against the PDFs
$PY src/check_designs.py          # check each design has its stated structure
$PY src/build_dataset.py          # data/twr_dataset.csv

$PY src/run_experiments.py        # random CV + LOPO, all models
for subset in no_P01_run13 no_derived_P21 no_printed_zero no_H04 no_P12 no_P13_pmedm no_borrowed_density; do
  $PY src/run_experiments.py --exclude "$subset" --schemes lopo
done
$PY src/run_experiments.py --exclude original_6_studies

$PY src/evaluate.py | tee results/evaluate_log.txt
$PY src/within_study.py | tee results/within_study_log.txt
$PY src/figures.py
$PY paper/build_paper.py
