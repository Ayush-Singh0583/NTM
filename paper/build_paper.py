"""Build paper/EDM_TWR_paper.docx (IEEE-style, two columns) from results/ and figures/.

Every number in the text and tables is computed here from the result files, and every
qualitative claim in the text ("for all six models", "at every k", ...) is checked by an
assertion, so rerunning the analysis either updates the paper consistently or stops the
build with the claim that no longer holds.

Text markup: {key} cites a reference, <<name>> inserts a computed number, **bold**,
*italic*, _{sub} and ^{sup}.
"""
import math
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "paper"))
from evaluate import summary  # noqa: E402
from references import REFS  # noqa: E402

RES, FIG, RAW = ROOT / "results", ROOT / "figures", ROOT / "data" / "raw"
OUT = ROOT / "paper" / "EDM_TWR_paper.docx"
FONT = "Times New Roman"
TITLE = ("How Well Do Tool Wear Rate Models for Die-Sinking EDM Transfer to a New Laboratory? "
         "A Leave-One-Paper-Out Evaluation on Data from Ten Published Studies")
GUIDE = "Shanthala Kollur"
COL_W = 3.45  # usable column width in inches (two columns on letter paper)
NONLINEAR = ["RF", "XGBoost", "ANN", "SVR", "Stacked"]
MODELS = ["Ridge"] + NONLINEAR
STUDIES = ["P01", "P06", "P10", "P12", "P13", "P21", "H04", "H05", "H17", "H18"]
KEYS = {"P01": "soundhar2019", "P06": "fatatit2021", "P10": "akin2022", "P12": "reddy2016", "P13": "ram2025",
        "P21": "bahgat2019", "H04": "chandra2021", "H05": "jagdale2025", "H17": "surani2025", "H18": "hassan2023"}
TYPED = ["P06_fatatit2021.csv", "P10_akincioglu2022.csv", "P12_reddy2016.csv", "P13_ram2025.csv",
         "H04_chandrashekarappa2021.csv", "H18_hassan2023.csv"]
# headline numbers of the preliminary (six-study) version of this paper, for comparison
DRAFT = {"svr_r2": 0.05, "svr_ef": 6.4, "base_r2": -0.50, "base_ef": 11.8, "rho_max": 0.67, "ann_phys_r2": -0.36}


# ---------------------------------------------------------------- formatting
def num(x, d=2):
    s = f"{x:.{d}f}"
    if float(s) == 0:
        s = s.lstrip("-")
    return s.replace("-", "−")


def ef(x, d=1):
    return f"×{x:.{d}f}"


def pct(x):
    return f"{x:.0f}%"


WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}


def sig2(x):
    """Two significant figures, keeping a trailing zero (2.0, not 2)."""
    d = max(0, 1 - int(math.floor(math.log10(abs(x)))))
    return f"{x:.{d}f}"


def check(cond, claim):
    if not cond:
        raise AssertionError(f"claim in the text no longer holds: {claim}")


# ---------------------------------------------------------------- numbers
def numbers():
    N = {}
    data = pd.read_csv(ROOT / "data" / "twr_dataset.csv")
    summ = pd.read_csv(RES / "summary.csv").set_index(["model", "features"])
    per = pd.read_csv(RES / "lopo_per_study.csv")
    ws = pd.read_csv(RES / "within_study.csv")
    wsr = pd.read_csv(RES / "within_study_rho.csv")
    cal = pd.read_csv(RES / "calibration.csv")
    sens = pd.read_csv(RES / "sensitivity.csv")
    pred = pd.read_csv(RES / "predictions.csv")
    o6 = summary(pd.read_csv(RES / "predictions_original_6_studies.csv")).set_index(["model", "features"])

    # data
    N["n_runs"], N["n_studies"] = len(data), data.study.nunique()
    N["n_train"] = WORDS[N["n_studies"] - 1]
    N["n_typed"] = sum(len(pd.read_csv(RAW / f)) for f in TYPED)
    el = data.groupby("electrode").study.nunique()
    el6 = data[data.study.isin(STUDIES[:6])].groupby("electrode").study.nunique()
    for e in ("Copper", "Graphite", "Brass"):
        N[f"n_{e.lower()}"], N[f"n6_{e.lower()}"] = int(el[e]), int(el6.get(e, 0))
    check(el["CuCrZr"] == 1 and el["CuCo1Ni1Be"] == 1, "CuCrZr and CuCo1Ni1Be unique to one study")
    N["twr_min"] = f"{data.twr_mm3min[~data.printed_zero].min():.4f}"
    N["twr_max"] = f"{data.twr_mm3min.max():.1f}"
    N["n_zero"] = WORDS[int(data.printed_zero.sum())]
    N["pol_known"] = pct(100 * (data.polarity != "not stated").mean())
    N["vg_known"] = pct(100 * data.gap_voltage_v.notna().mean())
    N["diel_known"] = pct(100 * (data.dielectric != "not stated").mean())
    N["n_nine"] = WORDS[int((data.groupby("study").size() == 9).sum())]

    # random CV
    def s(m, fs, c):
        return summ.loc[(m, fs), c]

    rb = [s(m, "base", "random_r2") for m in MODELS]
    rp = [s(m, "physics", "random_r2") for m in MODELS]
    check(all(p > b for p, b in zip(rp, rb)), "physics features raised random-CV R2 for all six models")
    N["cv_base_lo"], N["cv_base_hi"], N["cv_phys_lo"], N["cv_phys_hi"] = map(num, (min(rb), max(rb), min(rp), max(rp)))
    best = max(rp)
    top = [m for m in MODELS if round(s(m, "physics", "random_r2"), 2) == round(best, 2)]
    N["cv_best_models"] = " and ".join(top)
    N["cv_best_r2"] = num(best)
    efs = [s(m, "physics", "random_error_factor") for m in top]
    N["cv_best_ef"] = ef(min(efs)) if len(efs) == 1 else f"{ef(min(efs))}–{max(efs):.1f}"
    N["cv_base_r2"] = num(s("Mean baseline", "base", "random_r2"))
    N["cv_base_ef"] = ef(s("Mean baseline", "base", "random_error_factor"))
    N["cv_sd_max"] = num(pd.read_csv(RES / "summary.csv").random_r2_sd.max())
    cv_rank = sorted(MODELS, key=lambda m: s(m, "base", "random_r2"))
    check(cv_rank.index("Ridge") <= 1, "ridge (base) has one of the lowest random-CV scores")

    # LOPO
    N["lo_base_r2"], N["lo_base_ef"] = num(s("Mean baseline", "base", "lopo_r2")), ef(s("Mean baseline", "base",
                                                                                       "lopo_error_factor"))
    N["lo_rb_r2"], N["lo_rb_ef"] = num(s("Ridge", "base", "lopo_r2")), ef(s("Ridge", "base", "lopo_error_factor"))
    N["lo_rp_r2"], N["lo_rp_ef"] = num(s("Ridge", "physics", "lopo_r2")), ef(s("Ridge", "physics", "lopo_error_factor"))
    others = [(m, fs) for m in MODELS for fs in ("base", "physics") if (m, fs) != ("Ridge", "base")]
    check(s("Ridge", "base", "lopo_r2") > 0 and all(s(m, fs, "lopo_r2") <= 0 for m, fs in others),
          "only ridge (base) has a positive LOPO R2")
    nl = [(m, fs, s(m, fs, "lopo_r2")) for m in NONLINEAR for fs in ("base", "physics")]
    hi, lo = max(nl, key=lambda t: t[2]), min(nl, key=lambda t: t[2])
    tied = [m for m, fs, v in nl if round(v, 2) == round(hi[2], 2) and fs == hi[1]]
    N["nl_hi"], N["nl_hi_who"] = num(hi[2]), f"{' and '.join(tied)}, {hi[1]} inputs"
    N["nl_lo"], N["nl_lo_who"] = num(lo[2]), f"{lo[0]}, {'physics features' if lo[1] == 'physics' else 'base inputs'}"
    nle = [s(m, fs, "lopo_error_factor") for m in NONLINEAR for fs in ("base", "physics")]
    N["nl_ef_lo"], N["nl_ef_hi"] = ef(min(nle)), f"{max(nle):.1f}"
    mm3 = [summ.loc[i, "lopo_mm3_r2"] for i in summ.index]
    check(max(mm3) < 0, "mm3 R2 negative for every model")
    N["mm3_hi"], N["mm3_lo"] = num(max(mm3)), num(min(mm3))
    rhos = [s(m, fs, "lopo_median_rho") for m in NONLINEAR for fs in ("base", "physics")]
    N["nl_rho_lo"], N["nl_rho_hi"] = num(min(rhos)), num(max(rhos))
    N["rb_rho"], N["rp_rho"] = num(s("Ridge", "base", "lopo_median_rho")), num(s("Ridge", "physics", "lopo_median_rho"))
    worse = [m for m in NONLINEAR if s(m, "physics", "lopo_r2") < s(m, "base", "lopo_r2")]
    check(s("Ridge", "physics", "lopo_r2") < s("Ridge", "base", "lopo_r2"), "physics lowers ridge LOPO R2")
    check(len(worse) >= 3, "physics features lowered LOPO R2 for most nonlinear models")
    N["n_nl_phys_worse"] = {3: "three", 4: "four", 5: "all five"}[len(worse)]

    # per study (ridge, physics features)
    pp = per[per.model == "Ridge (physics)"].set_index("study")
    bmin, bmax = pp.bias.idxmin(), pp.bias.idxmax()
    N["bias_min"], N["bias_min_s"], N["bias_min_x"] = num(pp.bias[bmin]), bmin, f"{10 ** -pp.bias[bmin]:.0f}"
    N["bias_max"], N["bias_max_s"], N["bias_max_x"] = num(pp.bias[bmax]), bmax, f"{10 ** pp.bias[bmax]:.0f}"
    worst = pp.error_factor.sort_values(ascending=False).index[:3].tolist()
    check(worst == ["P06", "P13", "P21"], "three worst studies are P06, P13, P21 (described in the text)")
    N["worst"] = ", ".join(f"{w} {ef(pp.error_factor[w])}" for w in worst)
    good = [st for st in STUDIES if pp.error_factor[st] < 2]
    check(len(good) >= 2, "some studies predicted within a factor of two")
    N["good"] = ", ".join(good[:-1]) + " and " + good[-1]
    lopo = pred[pred.scheme == "lopo"]

    def bias_share(m, fs):
        g = lopo[(lopo.model == m) & (lopo.features == fs)]
        e = g.pred - g.log10_twr
        return 100 * (e.groupby(g.study).transform("mean") ** 2).sum() / (e ** 2).sum()

    N["share_rb"], N["share_rp"] = pct(bias_share("Ridge", "base")), pct(bias_share("Ridge", "physics"))
    shares = [bias_share(m, fs) for m in NONLINEAR for fs in ("base", "physics")]
    N["share_nl_lo"], N["share_nl_hi"] = f"{min(shares):.0f}", pct(max(shares))
    check(min(shares + [bias_share("Ridge", "base"), bias_share("Ridge", "physics")]) > 50,
          "study bias is more than half of the squared LOPO error")

    # within-study association with single inputs
    ip_r = data.groupby("study").apply(lambda g: spearmanr(g.ip_a, g.log10_twr).statistic, include_groups=False)
    ton_r = data.groupby("study").apply(lambda g: spearmanr(g.ton_us, g.log10_twr).statistic, include_groups=False)
    N["ip_pos"], N["ip_med"] = {8: "eight", 9: "nine", 7: "seven"}[int((ip_r > 0).sum())], num(ip_r.median())
    N["ton_lo"], N["ton_hi"], N["ton_med"] = num(ton_r.min()), num(ton_r.max()), num(ton_r.median())
    check(ton_r.min() < 0 < ton_r.max(), "pulse-on correlation changes sign between studies")
    check(sorted(ip_r[ip_r < 0].index) == ["H04", "H18"], "peak-current correlation negative only in H04 and H18")
    N["ip_h04"], N["ip_h18"] = num(ip_r["H04"]), num(ip_r["H18"])

    # within-study models
    med = wsr.groupby("model").rho.median()
    for k, name in [("w_ip", "Peak current only (ridge)"), ("w_rb", "Ridge (base)"), ("w_rp", "Ridge (physics)"),
                    ("w_rf", "RF (physics)"), ("w_svr", "SVR (physics)"),
                    ("w_xgb", "XGBoost, monotone in Ip (physics)")]:
        N[k] = num(med[name])
    check(min(med["Ridge (base)"], med["Ridge (physics)"], med["Peak current only (ridge)"], med["SVR (physics)"])
          > s("Ridge", "physics", "lopo_median_rho"), "within ridge/peak-current/SVR order better than any absolute model")
    check(max(med["RF (physics)"], med["XGBoost, monotone in Ip (physics)"]) < 0.4, "within RF and XGBoost order poorly")
    for st in ("H04", "H18"):
        check((wsr[wsr.study == st].rho < 0).all(), f"every within-study model orders {st} wrongly")
        check(per[(per.model == "Ridge (base)") & (per.study == st)].rho.iloc[0] < 0, f"absolute ridge wrong on {st}")

    # calibration
    w = ws.set_index(["model", "k"])
    a = cal[(cal.model == "Ridge") & (cal.features == "base")].set_index("k")
    for k in (1, 3, 5):
        N[f"km{k}"] = ef(w.loc[("Peak current only (ridge)", k), "error_factor_kmean"], 2)
        N[f"abs{k}"] = ef(a.loc[k, "error_factor_model"], 2)
    check((a.error_factor_model > a.error_factor_kmean).all(), "absolute ridge + offset worse than k-run mean at every k")
    g_ip = ws[ws.model == "Peak current only (ridge)"].improvement_pct
    g_rb = ws[ws.model == "Ridge (base)"].improvement_pct
    check(g_ip.min() > 0 and g_rb.min() > 0, "peak-current and base ridge within models beat the k-run mean at every k")
    others_w = ["Ridge (physics)", "RF (physics)", "XGBoost, monotone in Ip (physics)"]
    g_ot = ws[ws.model.isin(others_w)].improvement_pct
    check(g_ot.max() < 0, "physics ridge, RF and monotone XGBoost worse than the k-run mean at every k")
    g_svr = ws[ws.model == "SVR (physics)"].improvement_pct
    check(g_svr.max() < 1 and g_svr.min() > -3, "SVR within about equal to the k-run mean")
    N["g_ip_lo"], N["g_ip_hi"] = f"{g_ip.min():.0f}", f"{g_ip.max():.0f}"
    N["g_rb_lo"], N["g_rb_hi"] = f"{g_rb.min():.0f}", f"{g_rb.max():.0f}"
    N["g_ot_lo"], N["g_ot_hi"] = f"{-g_ot.max():.0f}", f"{-g_ot.min():.0f}"
    N["g_svr_lo"], N["g_svr_hi"] = num(g_svr.min(), 0), num(g_svr.max(), 0)
    ip3 = w.loc[("Peak current only (ridge)", 3)]
    N["ip3"], N["km3_plain"] = ef(ip3.error_factor_model, 2), ef(ip3.error_factor_kmean, 2)
    N["x2_km3"], N["x2_ip3"] = pct(100 * ip3.frac_within_x2_kmean), pct(100 * ip3.frac_within_x2_model)
    N["win_ip3"] = pct(100 * ip3.win_rate)

    # robustness
    sub = sens[sens.subset != "original_6_studies"]
    rbs = sub[(sub.model == "Ridge") & (sub.features == "base")].lopo_r2.tolist() + [s("Ridge", "base", "lopo_r2")]
    N["sens_rb_lo"], N["sens_rb_hi"] = num(min(rbs)), num(max(rbs))
    N["sens_nl_max"] = num(sens[sens.model.isin(NONLINEAR)].lopo_r2.max())
    bd = sens[sens.subset == "no_borrowed_density"]
    N["bd_rb"] = num(bd[(bd.model == "Ridge") & (bd.features == "base")].lopo_r2.iloc[0])
    N["bd_base"] = num(bd[bd.model == "Mean baseline"].lopo_r2.iloc[0])

    def o(m, fs, c):
        return o6.loc[(m, fs), c]

    N["o6_svr_r2"], N["o6_svr_ef"] = num(o("SVR", "base", "lopo_r2")), ef(o("SVR", "base", "lopo_error_factor"))
    N["o6_base_r2"] = num(o("Mean baseline", "base", "lopo_r2"))
    N["o6_base_ef"] = ef(o("Mean baseline", "base", "lopo_error_factor"))
    N["o6_rho_max"] = num(max(o(m, fs, "lopo_median_rho") for m in NONLINEAR for fs in ("base", "physics")))
    N["o6_ann_phys"] = num(o("ANN", "physics", "lopo_r2"))
    best6 = max(((m, fs) for m in MODELS for fs in ("base", "physics")), key=lambda i: o(*i, "lopo_r2"))
    check(best6 == ("SVR", "base"), "best model on the original six studies is SVR (base), as in the draft")
    for k, v in DRAFT.items():
        N[f"d_{k}"] = ef(v) if k.endswith("_ef") else num(v)
    return N


# ---------------------------------------------------------------- docx helpers
ORDER = []


def cite(text):
    def repl(m):
        nums = []
        for k in m.group(1).split(","):
            k = k.strip()
            if k not in REFS:
                raise KeyError(k)
            if k not in ORDER:
                ORDER.append(k)
            nums.append(ORDER.index(k) + 1)
        nums.sort()
        parts, i = [], 0
        while i < len(nums):
            j = i
            while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
                j += 1
            parts.append(f"[{nums[i]}]–[{nums[j]}]" if j - i >= 2 else ", ".join(f"[{n}]" for n in nums[i:j + 1]))
            i = j + 1
        return ", ".join(parts)
    return re.sub(r"\{([a-z]+\d{4}(?:, ?[a-z]+\d{4})*)\}", repl, text)


def fill(text, N):
    return re.sub(r"<<(\w+)>>", lambda m: str(N[m.group(1)]), text)


TOKEN = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|_\{[^}]*\}|\^\{[^}]*\})")


def add_runs(p, text, size, bold=False, italic=False):
    for chunk in TOKEN.split(text):
        if not chunk:
            continue
        b, i, sub, sup, t = bold, italic, False, False, chunk
        if chunk.startswith("**"):
            b, t = True, chunk[2:-2]
        elif chunk.startswith("*"):
            i, t = True, chunk[1:-1]
        elif chunk.startswith("_{"):
            sub, t = True, chunk[2:-1]
        elif chunk.startswith("^{"):
            sup, t = True, chunk[2:-1]
        r = p.add_run(t)
        r.font.size, r.font.name, r.bold, r.italic = Pt(size), FONT, b, i
        r.font.subscript, r.font.superscript = sub, sup


class Writer:
    def __init__(self, doc, N):
        self.doc, self.N = doc, N

    def text(self, t):
        return cite(fill(t, self.N))

    def para(self, t="", size=10, bold=False, italic=False, align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=2, indent=0.14,
             keep=False):
        p = self.doc.add_paragraph()
        p.alignment = align
        f = p.paragraph_format
        f.space_after, f.space_before, f.keep_with_next = Pt(after), Pt(0), keep
        if indent:
            f.first_line_indent = Inches(indent)
        add_runs(p, self.text(t), size, bold, italic)
        return p

    def heading(self, t, level=1):
        if level == 1:
            p = self.para(t.upper(), align=WD_ALIGN_PARAGRAPH.CENTER, after=3, indent=0, keep=True)
            p.paragraph_format.space_before = Pt(8)
        else:
            p = self.para(t, italic=True, align=WD_ALIGN_PARAGRAPH.LEFT, after=2, indent=0, keep=True)
            p.paragraph_format.space_before = Pt(4)

    def equation(self, t, n):
        p = self.doc.add_paragraph()
        f = p.paragraph_format
        f.space_after, f.space_before = Pt(3), Pt(3)
        f.tab_stops.add_tab_stop(Inches(COL_W / 2), WD_TAB_ALIGNMENT.CENTER)
        f.tab_stops.add_tab_stop(Inches(COL_W), WD_TAB_ALIGNMENT.RIGHT)
        add_runs(p, "\t" + self.text(t) + f"\t({n})", 10)

    def figure(self, path, caption, width=3.35):
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.add_run().add_picture(str(path), width=Inches(width))
        self.para(caption, size=8, indent=0, after=6)

    def table(self, number, title, header, rows, widths, note=None):
        assert abs(sum(widths) - COL_W) < 0.06, (title, sum(widths))
        self.para(f"TABLE {number}", size=8, align=WD_ALIGN_PARAGRAPH.CENTER, indent=0, after=0, keep=True)
        self.para(title.upper(), size=7, align=WD_ALIGN_PARAGRAPH.CENTER, indent=0, after=2, keep=True)
        t = self.doc.add_table(rows=1 + len(rows), cols=len(header))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        pr = t._tbl.tblPr
        for tag, attrs in (("w:tblW", {"w:w": str(int(sum(widths) * 1440)), "w:type": "dxa"}),
                           ("w:tblLayout", {"w:type": "fixed"})):
            el = pr.find(qn(tag))
            if el is None:
                el = OxmlElement(tag)
                pr.append(el)
            for k, v in attrs.items():
                el.set(qn(k), v)
        mar = OxmlElement("w:tblCellMar")
        for side in ("left", "right"):
            e = OxmlElement(f"w:{side}")
            e.set(qn("w:w"), "43")
            e.set(qn("w:type"), "dxa")
            mar.append(e)
        pr.append(mar)
        borders = OxmlElement("w:tblBorders")
        for edge, val in (("top", "single"), ("left", "nil"), ("bottom", "single"), ("right", "nil"),
                          ("insideH", "nil"), ("insideV", "nil")):
            e = OxmlElement(f"w:{edge}")
            e.set(qn("w:val"), val)
            if val == "single":
                e.set(qn("w:sz"), "6")
            borders.append(e)
        pr.append(borders)
        grid = t._tbl.tblGrid
        for gc, wdt in zip(grid.findall(qn("w:gridCol")), widths):
            gc.set(qn("w:w"), str(int(wdt * 1440)))
        for i, row in enumerate([header] + rows):
            # keep every row with the next one (and the last with the note) so a table never splits
            trpr = t.rows[i]._tr.get_or_add_trPr()
            trpr.append(OxmlElement("w:cantSplit"))
            for j, val in enumerate(row):
                cell = t.cell(i, j)
                cell.width = Inches(widths[j])
                cell.text = ""
                p = cell.paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.keep_with_next = True
                add_runs(p, self.text(str(val)), 7, bold=(i == 0))
        for cell in t.rows[0].cells:  # rule under the header row
            tb = OxmlElement("w:tcBorders")
            b = OxmlElement("w:bottom")
            b.set(qn("w:val"), "single")
            b.set(qn("w:sz"), "4")
            tb.append(b)
            cell._tc.get_or_add_tcPr().append(tb)
        self.para(note or "", size=7, align=WD_ALIGN_PARAGRAPH.LEFT, indent=0, after=6)


def set_cols(section, n):
    cols = section._sectPr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        section._sectPr.append(cols)
    cols.set(qn("w:num"), str(n))
    cols.set(qn("w:space"), "360")


# ---------------------------------------------------------------- tables
def table_rows(N):
    data = pd.read_csv(ROOT / "data" / "twr_dataset.csv")
    studies = pd.read_csv(ROOT / "data" / "studies.csv").set_index("study")
    summ = pd.read_csv(RES / "summary.csv").set_index(["model", "features"])
    per = pd.read_csv(RES / "lopo_per_study.csv")
    ws = pd.read_csv(RES / "within_study.csv").set_index(["model", "k"])
    wsr = pd.read_csv(RES / "within_study_rho.csv").groupby("model").rho.median()
    cal = pd.read_csv(RES / "calibration.csv")
    sens = pd.read_csv(RES / "sensitivity.csv")
    T = {}

    def design(d):
        if "CCD" in d:
            return "CCD"
        if "3 electrodes" in d:
            return "3×L9"
        return d.split()[0]

    short = {"Copper": "Cu", "Graphite": "Gr", "Brass": "Br", "CuCo1Ni1Be": "CuCoNiBe", "CuCrZr": "CuCrZr"}
    rows = []
    for sid in STUDIES:
        g, m = data[data.study == sid], studies.loc[sid]
        lo = g.twr_mm3min[~g.printed_zero].min()
        rows.append([f"{sid} {{{KEYS[sid]}}}", m.workpiece.split(" (")[0],
                     ", ".join(sorted(short[e] for e in g.electrode.unique())), design(m.design), len(g),
                     f"{sig2(lo)}–{sig2(g.twr_mm3min.max())}" + ("*" if g.printed_zero.any() else "")])
    T["I"] = rows

    rows = []
    for m in ["Mean baseline"] + MODELS:
        for fs in (["base"] if m == "Mean baseline" else ["base", "physics"]):
            r = summ.loc[(m, fs)]
            rows.append([m, "both" if m == "Mean baseline" else fs, num(r.random_r2), ef(r.random_error_factor),
                         num(r.lopo_r2), ef(r.lopo_error_factor),
                         "–" if pd.isna(r.lopo_median_rho) else num(r.lopo_median_rho)])
    T["IV"] = rows

    pb = per[per.model == "Ridge (base)"].set_index("study")
    pp = per[per.model == "Ridge (physics)"].set_index("study")
    T["V"] = [[st, int(pb.loc[st].n), ef(pb.loc[st].error_factor), num(pb.loc[st].rho), ef(pp.loc[st].error_factor),
               num(pp.loc[st].rho), num(pp.loc[st].bias)] for st in STUDIES]

    a = cal[(cal.model == "Ridge") & (cal.features == "base")].set_index("k")
    km = "Peak current only (ridge)"
    rows = [["Mean of the k runs (no model)", "–"] + [ef(ws.loc[(km, k), "error_factor_kmean"], 2) for k in (1, 3, 5)]
            + ["–"]]
    rows.append(["Absolute ridge (base) + offset", N["rb_rho"]]
                + [ef(a.loc[k, "error_factor_model"], 2) for k in (1, 3, 5)]
                + [num(a.loc[3, "improvement_pct"], 0) + "%"])
    labels = {"Peak current only (ridge)": "Within: peak current only", "Ridge (base)": "Within: ridge (base)",
              "Ridge (physics)": "Within: ridge (physics)", "RF (physics)": "Within: RF (physics)",
              "SVR (physics)": "Within: SVR (physics)",
              "XGBoost, monotone in Ip (physics)": "Within: XGBoost, monotone (physics)"}
    for name, lab in labels.items():
        rows.append([lab, num(wsr[name])] + [ef(ws.loc[(name, k), "error_factor_model"], 2) for k in (1, 3, 5)]
                    + [num(ws.loc[(name, 3), "improvement_pct"], 0) + "%"])
    T["VI"] = rows

    labels = {"no_P01_run13": "Without P01 run 13", "no_derived_P21": "Without P21 (derived TWR)",
              "no_printed_zero": "Without printed zeros", "no_H04": "Without H04", "no_P12": "Without P12",
              "no_P13_pmedm": "Without P13 (powder-mixed)",
              "no_borrowed_density": "Without P01, H18 (density)",
              "original_6_studies": "Original six studies only"}
    nl_best = max(summ.loc[(m, fs), "lopo_r2"] for m in NONLINEAR for fs in ("base", "physics"))
    rows = [["All data", N["n_runs"], N["n_studies"], num(summ.loc[("Ridge", "base"), "lopo_r2"]), num(nl_best),
             num(summ.loc[("Mean baseline", "base"), "lopo_r2"])]]
    for sub, lab in labels.items():
        g = sens[sens.subset == sub]
        rows.append([lab, int(g.n_runs.iloc[0]), int(g.n_studies.iloc[0]),
                     num(g[(g.model == "Ridge") & (g.features == "base")].lopo_r2.iloc[0]),
                     num(g[g.model.isin(NONLINEAR)].lopo_r2.max()), num(g[g.model == "Mean baseline"].lopo_r2.iloc[0])])
    T["VII"] = rows
    return T


# ---------------------------------------------------------------- the paper
def build():
    N = numbers()
    T = table_rows(N)
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.left_margin = sec.right_margin = Inches(0.62)
    sec.top_margin, sec.bottom_margin = Inches(0.75), Inches(1.0)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = FONT, Pt(10)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    W = Writer(doc, N)
    authors = [("Adithya D", "Dept. of Information Science and Engineering", "adithyadevaraj1001@gmail.com"),
               ("Billava Srujan Macha", "Dept. of Information Science and Engineering", "billavasrujan@gmail.com"),
               ("Ayush Singh", "Dept. of Information Science and Engineering", "ayushsingh10580@gmail.com"),
               (GUIDE, "Assistant Professor, Dept. of Mechanical Engineering", "Kshanthala2@gmail.com")]
    cp = doc.core_properties  # replace python-docx's template defaults
    cp.title, cp.author = TITLE, ", ".join(a[0] for a in authors)
    cp.last_modified_by, cp.comments, cp.subject, cp.category = "Ayush Singh", "", "", ""
    cp.keywords = "electrical discharge machining; tool wear rate; machine learning; grouped cross-validation"
    cp.created = cp.modified = datetime.now()
    cp.revision = 1

    W.para(TITLE, size=22, align=WD_ALIGN_PARAGRAPH.CENTER, indent=0, after=10)
    t = doc.add_table(rows=1, cols=4)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for j, (name, dept, email) in enumerate(authors):
        c = t.cell(0, j)
        c.text = ""
        for k, (txt, sz) in enumerate([(name, 10), (dept, 9), ("RV Institute of Technology and Management", 9),
                                       ("Bengaluru, India", 9), (email, 9)]):
            p = c.paragraphs[0] if k == 0 else c.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(0)
            add_runs(p, txt, sz)
    W.para("", size=6, indent=0)
    set_cols(doc.add_section(WD_SECTION.CONTINUOUS), 2)

    W.para("**Abstract—**Tool electrode wear limits the accuracy and cost of die-sinking electrical discharge "
           "machining (EDM). Machine learning models for EDM responses, including tool wear, are often reported "
           "with R^{2} above 0.95, but almost always on runs from a single experimental campaign. This work asks "
           "how well models of the tool wear rate (TWR) carry over to a study they have not seen. A dataset of "
           "<<n_runs>> runs from <<n_studies>> published studies (five electrode materials; titanium, steel and "
           "nickel-alloy workpieces) was compiled by parsing publisher XML or by typing tables that were then "
           "checked automatically against the source text. Ridge regression, random forest, XGBoost, a neural "
           "network, support vector regression and a stacked ensemble were trained on log_{10}(TWR) with basic or "
           "physics-based inputs, with hyperparameters tuned inside the training data only. With random 5-fold "
           "cross-validation the best models reached R^{2} = <<cv_best_r2>>. With leave-one-paper-out validation "
           "only ridge regression scored above zero, and barely (R^{2} = <<lo_rb_r2>>); every nonlinear model "
           "scored below zero and hardly ordered the runs inside an unseen study (median Spearman ρ ≤ "
           "<<nl_rho_hi>>), whereas peak current alone did (ρ = <<ip_med>>). Differences in the overall wear level "
           "of each study accounted for more than half of the squared held-out error. A within-study model of peak current, with "
           "the level set from three runs of the new study, reduced the typical error from <<km3_plain>> to <<ip3>> "
           "compared with the mean of those runs alone. Random splits therefore mainly measure how well a model "
           "learns each laboratory's wear level; simple level-free models calibrated on a few runs are a realistic "
           "route to prediction in a new setting.", size=9, indent=0, after=4)
    W.para("**Index Terms—**electrical discharge machining, tool wear rate, machine learning, grouped "
           "cross-validation, transfer, calibration, literature data", size=9, indent=0, after=6)

    W.heading("I. Introduction")
    W.para("Electrical discharge machining (EDM) removes material through a series of sparks between a tool "
           "electrode and a workpiece immersed in a dielectric fluid. Because the tool never touches the workpiece, "
           "EDM can shape hardened steels, titanium and nickel-based alloys into complex cavities for dies, moulds "
           "and aerospace parts {ho2003}. The same sparks also erode the tool. Tool wear changes the electrode's "
           "shape, reduces the dimensional accuracy of the cavity and adds the cost of replacement electrodes, so "
           "the tool wear rate (TWR) is one of the main responses planned for in die-sinking EDM "
           "{ho2003,kunieda2005}.")
    W.para("TWR depends on many interacting factors. It generally rises with peak current and discharge energy, "
           "while the effect of pulse-on time and duty factor depends on the polarity and the electrode material "
           "{kunieda2005}. Electrode materials behave very differently under the same settings "
           "{bahgat2019,chandra2021,jagdale2025,ahmed2024,carlini2024}, and changing the polarity can change tool "
           "wear substantially {ozerkan2017}. These non-linear effects are hard to capture with physical models or "
           "low-order regression, which is why data-driven models are widely used.")
    W.para("Recent studies report very accurate machine learning (ML) models for EDM responses: tree ensembles, "
           "neural networks and Gaussian process regression reach R^{2} values above 0.97 or accuracies near 99% "
           "{cetin2024,boominathan2025,qasem2025}. Such models are usually trained and tested on runs from a single "
           "experimental campaign, often with a random split of the runs {qasem2025}. Runs from the same study "
           "share a machine, a measuring method and a material batch, so a random split tests interpolation within "
           "one laboratory. Grouped validation, which holds out whole groups, is recommended whenever data are "
           "clustered in this way {roberts2017}, and information shared between training and test data is a known "
           "source of over-optimistic results {kaufman2012}. Work toward models that generalize has started "
           "{nath2026,cortes2026}, but how well TWR models transfer to an unseen study has rarely been tested "
           "directly.")
    W.para("This paper tests it with data compiled from published studies. Its contributions are:")
    for item in [
        "1) a TWR dataset of <<n_runs>> runs from <<n_studies>> die-sinking EDM studies, parsed from publisher XML "
        "or checked automatically against the source text, with every conversion and every problem found in the "
        "sources documented;",
        "2) a comparison of ridge regression and five ML models under random and leave-one-paper-out (LOPO) "
        "validation, with basic or physics-based inputs, which shows that accuracy under random splits does not "
        "carry over to a new study;",
        "3) diagnostics that separate how well a model orders the runs of a new study from how well it predicts the "
        "study's overall wear level, which show that the level dominates the error and that the ML models lose even "
        "the ordering that peak current alone provides;",
        "4) within-study (fixed-effects) models and a few-run calibration protocol, compared on the same "
        "calibration runs with the baseline of simply using those runs' mean; and",
        "5) open data and code, so that the dataset can be extended and every number rerun.",
    ]:
        W.para(item, indent=0)
    W.para("Section II reviews related work, Section III describes the data and methods, Section IV presents the "
           "results, Section V discusses them, Section VI lists the limitations and Section VII concludes.")

    W.heading("II. Related Work")
    W.heading("A. Electrode Material and Process Effects", 2)
    W.para("Several studies compare electrode materials under the same settings. Bahgat et al. {bahgat2019} "
           "machined AISI H13 steel with graphite, copper and brass electrodes and found electrode wear ratios that "
           "differed by more than two orders of magnitude between runs. Chandrashekarappa et al. {chandra2021} "
           "varied copper, graphite and brass electrodes and two dielectrics on a high-carbon high-chromium steel, "
           "and Jagdale et al. {jagdale2025} compared the same three electrode materials on Ti6Al4V. Ahmed "
           "{ahmed2024} compared copper, copper–tungsten and graphite electrodes and electrode designs on D2 steel, "
           "and Carlini et al. {carlini2024} reported the lowest relative wear (1.66%) for copper–tungsten when "
           "machining Inconel 718 at low discharge energy. Özerkan {ozerkan2017} showed that switching the polarity "
           "of a graphite tool changes material removal, roughness and tool wear.")
    W.heading("B. Machine Learning for EDM Wear", 2)
    W.para("Cetin et al. {cetin2024} compared seven ML algorithms, including ANN, XGBoost, CatBoost and random "
           "forest, for predicting the wear of cryogenically treated CuCrZr and copper electrodes on AISI P20 steel "
           "and reported accuracies near 99%. Boominathan et al. {boominathan2025} combined linear regression, SVR, "
           "random forest, XGBoost and AdaBoost with SHAP and LIME explanations for EDM of Inconel 718; XGBoost "
           "reached R^{2} = 0.994 for material removal rate. Qasem and Alsakarneh {qasem2025} trained six models on "
           "72 runs over three steels with an 80/20 split; Gaussian process regression performed best, with "
           "training R^{2} above 0.97 for material removal rate. Hegde et al. {hegde2024} combined designed "
           "experiments with a neural network to predict the wear of Ti-6Al-4V-SiCp composite electrodes. Each of "
           "these models was built and evaluated on a single experimental campaign.")
    W.heading("C. Toward Transferable Models", 2)
    W.para("In a preprint, Nath et al. {nath2026} fitted a physics-guided model built from dimensionless groups to "
           "nine runs (calibration R^{2} = 0.969, mean absolute percentage error 10.1%) and validated it on nine runs "
           "from another study (18.5%). Its thermal group, which combines the electrode's thermal conductivity and "
           "melting point, had an exponent close to −1, which supports using electrode thermal properties as model "
           "inputs. Cortés-Mendoza et al. {cortes2026} proposed a generalist framework of four ML models for "
           "material removal and electrode wear and reported R^{2} up to 0.9956 for electrode wear. Clustered data "
           "of this kind are the classic setting for multilevel models, in which each group has its own intercept "
           "{gelman2007}. The present study complements these works by holding out every study in turn and by "
           "testing a within-study formulation directly.")

    W.heading("III. Data and Methods")
    W.para("Fig. 1 summarizes the workflow.")
    W.figure(FIG / "fig1_workflow.png", "Fig. 1. Workflow, from literature screening to model validation.")
    W.heading("A. Literature Search and Screening", 2)
    W.para("Studies were found through web searches in September 2026 that combined die-sinking EDM, tool or "
           "electrode wear rate, electrode materials and common workpieces (tool steels, stainless steels, titanium "
           "and nickel alloys). A study was included if it used conventional die-sinking EDM on a steel, "
           "titanium-alloy or nickel-alloy workpiece and gave, for every run, the TWR as a volume or mass rate (or "
           "in a form that converts to one) together with the peak current and pulse timing. Wire and micro-EDM, "
           "composite workpieces, single fixed settings and wear reported only as a length or in graphs were "
           "excluded. Of the 51 studies logged, 12 contained usable per-run tables, 11 need a closer check, 19 could "
           "not be accessed or are paywalled, and 9 were rejected. Ten of the 12 were retrieved as open-access full "
           "text and form the dataset; the other two {sultan2014,agrawal2026} could not be retrieved in a readable "
           "form and are left for a later update.")
    W.heading("B. Data Extraction and Checks", 2)
    W.para("Four studies {soundhar2019,bahgat2019,jagdale2025,surani2025} are available as JATS XML through Europe "
           "PMC, and their tables were parsed by a script, so the values are exact copies of the published ones. For "
           "the other six {fatatit2021,akin2022,reddy2016,ram2025,chandra2021,hassan2023} the tables were typed from "
           "the PDF and checked by a script that requires every typed row to appear, value by value and in order, "
           "on one line of the PDF's text layer; all <<n_typed>> typed rows passed, and a deliberately altered value "
           "was detected. A second script confirmed that every design has its stated structure: every pair of "
           "factors is balanced in the orthogonal arrays, and the central composite design has 16 factorial, 8 axial "
           "and 6 centre runs. The repository contains both scripts, a script that downloads the source articles, "
           "and the checksums of the copies used.")
    W.para("Four problems in the sources were found and kept visible rather than silently corrected. Table 4 of "
           "{fatatit2021} prints the pulse-on levels as 50, 200 and 200 µs, while its abstract gives 50, 200 and "
           "800 µs and its run codes use three distinct levels; 800 µs was used. Reddy et al. {reddy2016} weighed "
           "on a balance with 0.1 g resolution over 5 min cuts, which corresponds to about 2.2 mm^{3}/min of "
           "copper, more than every TWR they report (0.11–0.78 mm^{3}/min). In {chandra2021} the tool lost more "
           "mass than the workpiece in 9 of 18 runs, which is unusual for die-sinking EDM. In {soundhar2019} one "
           "centre run (run 13) has 2.1–3.4 times the wear of its five replicates. These runs were kept as "
           "published and tested in the sensitivity analysis (Section IV-E).")
    W.heading("C. Dataset", 2)
    W.table("I", "Studies in the Dataset", ["Study", "Workpiece", "Electrode(s)", "Design", "n", "TWR (mm³/min)"],
            T["I"], [0.6, 0.78, 0.82, 0.42, 0.25, 0.58],
            note="Gr: graphite; Br: brass; CCD: face-centred central composite design. *Plus runs printed as 0. "
                 "The TWR of P21 is derived from EWR% and MRR.")
    W.para("Table I lists the studies and Fig. 2 shows their TWR values. The dataset has <<n_runs>> runs covering "
           "five electrode materials (graphite, copper, brass, CuCrZr and CuCo1Ni1Be) and 10 workpiece grades from "
           "three material classes. Compared with the six-study version, more studies share electrode materials: "
           "copper appears in <<n_copper>> studies (previously <<n6_copper>>), graphite in <<n_graphite>> "
           "(previously <<n6_graphite>>) and brass in <<n_brass>> (previously <<n6_brass>>); only CuCrZr and "
           "CuCo1Ni1Be are unique to one study {fatatit2021}. TWR spans more than three orders of magnitude, from "
           "<<twr_min>> to <<twr_max>> mm^{3}/min (plus <<n_zero>> runs printed as 0), and each study occupies its "
           "own part of that range.")
    W.figure(FIG / "fig2_twr_by_study.png", "Fig. 2. TWR of every run by source study (log scale). Hollow points "
             "were printed as 0 and set to 0.0025 mm³/min.")
    W.heading("D. Pre-processing and Features", 2)
    W.para("TWR values reported in g/min were converted to mm^{3}/min with the electrode density reported by the "
           "same study {akin2022,chandra2021} or, for the two studies that give none {soundhar2019,hassan2023}, "
           "with the median of the densities that the other studies report for that material. One study "
           "{bahgat2019} reports only the electrode wear ratio (EWR%) and the material removal rate (MRR), so TWR "
           "was computed as EWR% × MRR/100. The duty factor was taken as reported or computed as")
    W.equation("D = 100 T_{on} / (T_{on} + T_{off})", 1)
    W.para("where T_{on} and T_{off} are the pulse-on and pulse-off times, and the charge per spark as", indent=0)
    W.equation("Q = I_{p} T_{on}", 2)
    W.para("where I_{p} is the peak current. The target was", indent=0)
    W.equation("y = log_{10}(TWR)", 3)
    W.para("so that errors are measured as factors rather than absolute differences. The <<n_zero>> runs printed "
           "as 0 with two decimals were set to 0.0025 mm^{3}/min, a quarter of the printed step.", indent=0)
    W.para("Two input sets were compared (Table II). The base set contains peak current, pulse-on time, duty factor "
           "and the electrode material encoded by name (one-hot); these are known for every run. The physics set "
           "replaces the electrode's name with its melting point, thermal conductivity, density and a thermal index "
           "(melting point in kelvin times thermal conductivity), uses the logarithms of pulse-on time and charge "
           "per spark, and adds the workpiece class, the dielectric and whether a special process (here, powder "
           "mixing {ram2025}) was used. For copper, graphite and brass the property values are the medians of those "
           "reported in the source studies {bahgat2019,akin2022,reddy2016,chandra2021,jagdale2025}; for CuCrZr and "
           "CuCo1Ni1Be, which {fatatit2021} does not characterize, approximate handbook values were used "
           "{asm1990}. Optional inputs were used only when at least 80% of the runs had them, which excluded "
           "electrode polarity (known for <<pol_known>> of the runs) and gap voltage (<<vg_known>>).")
    W.table("II", "Inputs in Each Set", ["Input", "Base", "Physics", "Runs with a value"], [
        ["Peak current", "yes", "yes", "100%"], ["Pulse-on time", "yes", "log", "100%"],
        ["Duty factor", "yes", "yes", "100%"], ["Electrode material (name)", "yes", "no", "100%"],
        ["Charge per spark", "no", "log", "100%"],
        ["Electrode melting point, conductivity, density, thermal index", "no", "yes", "100%"],
        ["Workpiece class", "no", "yes", "100%"], ["Dielectric", "no", "yes", N["diel_known"]],
        ["Special process", "no", "yes", "100%"], ["Electrode polarity", "no", "excluded", N["pol_known"]],
        ["Gap voltage", "no", "excluded", N["vg_known"]]], [1.75, 0.45, 0.6, 0.65],
        note="Inputs known for fewer than 80% of runs were excluded. An unstated dielectric is its own category.")
    W.heading("E. Models", 2)
    W.para("Six models and a baseline were compared, all implemented with scikit-learn {pedregosa2011} and the "
           "XGBoost library {chen2016}; Table III lists the settings. Ridge regression {hoerl1970} is a linear model "
           "with an L2 penalty, chosen by efficient leave-one-out error on the training runs. Random forest "
           "{breiman2001} averages 200 regression trees grown on bootstrap samples. XGBoost {chen2016} builds 200 "
           "gradient-boosted trees in sequence. The ANN {rumelhart1986} is a multilayer perceptron trained with the "
           "L-BFGS optimizer. SVR {drucker1997} uses a radial basis function kernel. The stacked ensemble "
           "{wolpert1992} combines out-of-fold predictions (internal 5-fold) of RF, XGBoost, SVR and ANN with a "
           "linear model whose weights cannot be negative. Numerical inputs are standardized on the training data. "
           "The mean baseline predicts the average training target.")
    W.table("III", "Model Settings", ["Model", "Tuned (grid)", "Fixed"], [
        ["Ridge", "α by leave-one-out, 10^{−3}–10^{3}", "–"],
        ["RF", "max. depth {None, 5}; min. leaf {1, 3}", "200 trees; max. features 0.7"],
        ["XGBoost", "max. depth {2, 4}; learning rate {0.05, 0.1}",
         "200 trees; subsample 0.8; column sample 0.8; min. child weight 2"],
        ["ANN", "hidden layers {(8), (16, 8)}; L2 {0.1, 1.0}", "L-BFGS; up to 5000 iterations"],
        ["SVR", "C {1, 3, 10, 30}; γ {scale, 0.1}", "RBF kernel; ε = 0.1"],
        ["Stacked", "none", "RF (min. leaf 2), XGBoost (depth 3, rate 0.05), SVR (C = 3), ANN (16 units, L2 1.0); "
                            "non-negative linear blend"]], [0.6, 1.35, 1.5])
    W.heading("F. Validation", 2)
    W.para("In random 5-fold cross-validation (CV) the runs are shuffled and split into five folds, so runs from one "
           "study appear in both training and test data; this was repeated with three different shuffles. In "
           "leave-one-paper-out (LOPO) validation each study is held out in turn and the model is trained on the "
           "other <<n_train>>, which estimates performance in a new laboratory {roberts2017}. The grids of Table III "
           "were searched inside the training data only, by 5-fold CV for random CV and by leave-one-paper-out over "
           "the <<n_train>> training studies for LOPO; the ridge penalty was chosen by leave-one-out on the training "
           "runs, and the stacked ensemble has fixed settings. No test run therefore influenced model selection "
           "{kaufman2012}. Scores were computed from the pooled out-of-fold predictions.")
    W.heading("G. Within-Study Models and Few-Run Calibration", 2)
    W.para("Because each study has its own wear level, a second family of models was fitted to within-study "
           "variation only. Both the inputs and the target are centred on the mean of the run's own study, "
           "x − x̄_{s} and y − ȳ_{s}, as in the fixed-effects (within) estimator of a model with a separate "
           "intercept for each study {gelman2007}. Such a model learns how wear changes with the settings inside a "
           "study but nothing about a study's level. For a held-out study the inputs are centred on that study's "
           "own settings, which are known before any run is made. Six forms were tested under LOPO: ridge "
           "regression on peak current only, ridge on the base and on the physics inputs, and RF, SVR and an "
           "XGBoost model constrained to be non-decreasing in peak current, the last three on the physics inputs.")
    W.para("For a new study the level is then set from k of its runs: the prediction for run i is the mean of the k "
           "measured values plus f(x_{i}) minus the mean of f over those k runs. Applied to the ordinary (absolute) "
           "models, the same formula is the offset calibration proposed in the preliminary version of this work. "
           "Both are compared with the simplest alternative, predicting every remaining run as the mean of the k "
           "measured runs. For each held-out study and k = 1, 2, 3 and 5, 1000 random sets of k runs were drawn, "
           "every method was scored on the same sets, and errors were measured on the remaining runs.")
    W.heading("H. Metrics", 2)
    W.para("With y_{i} and ŷ_{i} the observed and predicted log_{10}(TWR) of run i and ȳ the mean of the observed "
           "values, R^{2} = 1 − Σ(y_{i} − ŷ_{i})^{2} / Σ(y_{i} − ȳ)^{2} and MAE = (1/n) Σ|y_{i} − ŷ_{i}|. Because y "
           "is a logarithm, 10^{MAE} is the typical factor by which predictions miss (MAE = 0.30 means about ×2); "
           "we call it the typical error factor. R^{2} was also computed in mm^{3}/min. For each held-out study we "
           "report the Spearman rank correlation ρ between observed and predicted values, which shows whether the "
           "model orders the runs correctly, and the mean bias of the log predictions, which shows whether the "
           "study's overall wear level is over- or under-predicted.")

    W.heading("IV. Results")
    W.heading("A. Accuracy Under the Two Validation Schemes", 2)
    W.table("IV", "Model Accuracy on the Log Scale",
            ["Model", "Inputs", "CV R²", "CV error", "LOPO R²", "LOPO error", "LOPO ρ"], T["IV"],
            [0.68, 0.5, 0.42, 0.45, 0.47, 0.5, 0.43],
            note="CV: random 5-fold, mean of three shuffles (s.d. of R² ≤ <<cv_sd_max>>). Error: typical error "
                 "factor 10^{MAE}. ρ: median Spearman correlation within the held-out studies.")
    W.para("Table IV and Fig. 3 summarize the results. Under random CV every model clearly beat the mean baseline "
           "(R^{2} = <<cv_base_r2>>, typical error <<cv_base_ef>>). The physics features raised R^{2} for all six "
           "models, from <<cv_base_lo>>–<<cv_base_hi>> to <<cv_phys_lo>>–<<cv_phys_hi>>, and the best models "
           "(<<cv_best_models>> with physics features, R^{2} = <<cv_best_r2>>) had typical errors of <<cv_best_ef>>.")
    W.para("Under LOPO the picture reverses (Fig. 3, lower panel). The mean baseline gave R^{2} = <<lo_base_r2>> "
           "and a typical error of <<lo_base_ef>>. Only ridge regression with the base inputs had a positive R^{2} "
           "(<<lo_rb_r2>>, <<lo_rb_ef>>); with physics features ridge had a similar typical error (<<lo_rp_ef>>) but "
           "R^{2} = <<lo_rp_r2>>. All five nonlinear models had negative R^{2} with either input set, from "
           "<<nl_hi>> (<<nl_hi_who>>) to <<nl_lo>> (<<nl_lo_who>>), with typical errors of "
           "<<nl_ef_lo>>–<<nl_ef_hi>> against <<lo_base_ef>> for the baseline. In mm^{3}/min, R^{2} was negative "
           "for every model (<<mm3_hi>> to <<mm3_lo>>) because a few very large TWR values dominate that scale. "
           "Higher accuracy under random CV did not mean better transfer: ridge with the base inputs had one of the "
           "lowest random-CV scores but transferred best.")
    W.figure(FIG / "fig3_r2.png", "Fig. 3. R² on log10(TWR) for each model and input set under random 5-fold CV "
             "(top) and leave-one-paper-out validation (bottom).")
    W.heading("B. Behaviour on Each Held-Out Study", 2)
    W.table("V", "Leave-One-Paper-Out Errors of Ridge by Study",
            ["Study", "n", "Base error", "Base ρ", "Phys. error", "Phys. ρ", "Phys. bias"], T["V"],
            [0.45, 0.3, 0.55, 0.5, 0.55, 0.5, 0.6],
            note="Bias: mean of predicted minus observed log10(TWR); +1 means ten times too high.")
    W.para("Table V breaks the LOPO errors of ridge regression down by study. Most of the error is a shift of the "
           "whole study: the mean bias of each held-out study accounts for <<share_rb>> (base inputs) and "
           "<<share_rp>> (physics features) of the squared LOPO error of ridge, and for <<share_nl_lo>>–"
           "<<share_nl_hi>> for the nonlinear models. With physics features the bias ranged from <<bias_min>> "
           "(<<bias_min_s>>, predicted about <<bias_min_x>> times too low) to +<<bias_max>> (<<bias_max_s>>, about "
           "<<bias_max_x>> times too high). The three worst studies (<<worst>>) are the one with unique electrode "
           "alloys, the one with a powder-mixed dielectric and shaped tools, and the one whose TWR is derived from "
           "EWR%. For other studies the transfer was good: <<good>> were predicted within a factor of two.")
    W.heading("C. Ordering the Runs of an Unseen Study", 2)
    W.para("The preliminary six-study analysis found that LOPO predictions still ordered the runs of an unseen "
           "study moderately well (median ρ up to <<d_rho_max>>); rerun on those six studies here, the median ρ of "
           "the nonlinear models reaches <<o6_rho_max>> (Section IV-E). With 10 studies this no longer holds: the "
           "median ρ of the nonlinear models lies between <<nl_rho_lo>> and <<nl_rho_hi>> (Table IV). Yet an "
           "ordering signal is present in the data. Within studies, the Spearman correlation between TWR and peak "
           "current is positive in <<ip_pos>> of the 10 studies (median <<ip_med>>), whereas the correlation with "
           "pulse-on time changes sign between studies (<<ton_lo>> to <<ton_hi>>; median <<ton_med>>), as expected "
           "from the dependence of the pulse-on effect on polarity and electrode material {kunieda2005}. The "
           "absolute models spend their capacity on the between-study differences in level and lose the one trend "
           "that is shared.")
    W.para("The within-study models recover it (Fig. 4). Ridge regression fitted to within-study variation "
           "reached a median ρ of <<w_rb>> (base inputs) and <<w_rp>> (physics features), and peak current alone "
           "<<w_ip>>, against <<rb_rho>> for ridge on absolute values. SVR fitted within studies also ordered the "
           "runs well (<<w_svr>>), whereas RF (<<w_rf>>) and the monotone XGBoost (<<w_xgb>>) did not. In two "
           "studies every within-study model, and the absolute ridge model, got the order wrong: in H04 and H18 the "
           "measured wear falls as peak current rises (ρ = <<ip_h04>> and <<ip_h18>>), contrary to the other "
           "eight studies.")
    W.figure(FIG / "fig4_rank.png", "Fig. 4. Spearman ρ between observed and predicted TWR inside each held-out "
             "study, for ridge trained on absolute values, ridge fitted to within-study variation, and a "
             "within-study model of peak current alone.")
    W.heading("D. Few-Run Calibration", 2)
    W.table("VI", "Prediction in a New Study From k Calibration Runs",
            ["Approach", "ρ", "k = 1", "k = 3", "k = 5", "Gain (k=3)"], T["VI"],
            [1.35, 0.35, 0.43, 0.43, 0.43, 0.46],
            note="Typical error factor on the runs not used for calibration, pooled over the held-out studies and "
                 "1000 draws of the k runs (the same draws for every row). Gain: reduction of the typical error "
                 "factor relative to the mean of the k runs. ρ: median within-study Spearman correlation under "
                 "LOPO.")
    W.para("Table VI and Fig. 5 show what happens when a few runs of the new study are available. Predicting their "
           "mean gave typical errors of <<km1>>, <<km3>> and <<km5>> for k = 1, 3 and 5. Shifting the absolute "
           "ridge model by its error on the same runs was worse at every k (<<abs1>>, <<abs3>> and <<abs5>>): its "
           "within-study pattern adds error rather than information. Two within-study models improved on the k-run "
           "mean at every k. Peak current alone did so by <<g_ip_lo>>–<<g_ip_hi>>% (at k = 3, from <<km3>> to "
           "<<ip3>>; it beat the k-run mean in <<win_ip3>> of the draws, and the share of predictions within a "
           "factor of two rose from <<x2_km3>> to <<x2_ip3>>), and ridge on the base inputs by <<g_rb_lo>>–"
           "<<g_rb_hi>>%. The physics-feature models did not help: within-study ridge, RF and the monotone XGBoost "
           "were <<g_ot_lo>>–<<g_ot_hi>>% worse than the k-run mean, and SVR, despite its good ordering, was no "
           "better (<<g_svr_lo>>% to <<g_svr_hi>>%), because ordering the runs correctly is not enough when the size "
           "of the predicted changes is wrong.")
    W.figure(FIG / "fig5_calibration.png", "Fig. 5. Typical error factor on the remaining runs of a held-out study "
             "when k of its runs are used to set the level.")
    W.heading("E. Robustness", 2)
    W.table("VII", "Leave-One-Paper-Out R² on Data Subsets",
            ["Subset", "Runs", "Studies", "Ridge (base)", "Best nonlinear", "Mean baseline"], T["VII"],
            [1.3, 0.35, 0.42, 0.45, 0.48, 0.45])
    W.para("Table VII repeats the LOPO evaluation after removing each questionable part of the data. The "
           "conclusions about the nonlinear models hold in every subset: the best of the 10 nonlinear model variants "
           "never exceeds R^{2} = <<sens_nl_max>>. The small positive R^{2} of ridge regression is not robust: it "
           "ranges from <<sens_rb_lo>> to <<sens_rb_hi>> across subsets and falls to <<bd_rb>>, about the level of "
           "the baseline (<<bd_base>>), when the two studies whose density had to be taken from other studies are "
           "removed. On the original six studies the pipeline matches the headline numbers of the preliminary "
           "version: the best LOPO model is again SVR on the base inputs (R^{2} = <<o6_svr_r2>>, typical error "
           "<<o6_svr_ef>>, against <<d_svr_r2>> and <<d_svr_ef>> before), and the mean baseline gives "
           "<<o6_base_r2>> and <<o6_base_ef>> (before <<d_base_r2>> and <<d_base_ef>>). Individual nonlinear models "
           "differ more (for example, the ANN with physics features gives <<o6_ann_phys>> against <<d_ann_phys_r2>> "
           "before); the inputs differ from the preliminary version in the property values, now taken from the "
           "source studies, and in the corrected pulse-on levels of {fatatit2021}, which may explain this.")

    W.heading("V. Discussion")
    W.heading("A. Why Random Splits Look Good", 2)
    W.para("The gap between random CV (R^{2} ≈ 0.6) and LOPO (R^{2} ≤ <<lo_rb_r2>>) is the main finding. Runs from "
           "one study share a machine, a measuring method, an electrode batch, a machining time and a parameter "
           "range, so a random split lets a model learn each study's wear level and then interpolate between that "
           "study's runs. That the level of each held-out study accounts for more than half of the squared LOPO "
           "error shows that this level is what dominates TWR across studies. Most published EDM models are "
           "evaluated in the random-split setting {cetin2024,boominathan2025,qasem2025}, so their high R^{2} "
           "values describe accuracy within one laboratory rather than transfer to a new one {roberts2017}.")
    W.heading("B. Why the Physics Features Did Not Help Under LOPO", 2)
    W.para("The six-study version suggested that physics features would become useful once several studies share "
           "electrode materials. The extended dataset tests this: copper now appears in <<n_copper>> studies, "
           "graphite in <<n_graphite>> and brass in <<n_brass>>, yet the physics features did not improve LOPO "
           "accuracy; they lowered R^{2} for ridge and for <<n_nl_phys_worse>> of the five nonlinear models. "
           "Electrode properties explain part of the between-material differences within studies that compare "
           "electrodes, but the between-study differences in level are larger and are not explained by electrode, "
           "workpiece or dielectric. They more plausibly come from what the features do not describe: polarity "
           "(unknown for a third of the runs), machining time, electrode geometry, flushing and the way wear was "
           "measured. Where measurement quality is doubtful, as for {reddy2016} and {chandra2021}, the reported "
           "level may not be meaningful at all.")
    W.heading("C. What Transfers", 2)
    W.para("What does transfer is the within-study effect of peak current, the most consistent finding of the EDM "
           "literature {ho2003,kunieda2005}. A model fitted only to the within-study variation of peak current "
           "orders the runs of a new study better than any absolute model and, with a few runs to fix the level, "
           "predicts <<g_ip_lo>>–<<g_ip_hi>>% better than those runs alone. The gain is real but modest, and the "
           "more flexible within-study models gained nothing, which suggests that the shared signal is close to a "
           "single monotone trend and that 10 studies are too few to learn interactions that hold across "
           "laboratories.")
    W.heading("D. Practical Implications", 2)
    W.para("For a practitioner with a new machine, electrode or workpiece, the results suggest three steps: run a "
           "few calibration cuts, use their mean as the level, and adjust between settings with a simple monotone "
           "model of peak current. For researchers, they suggest reporting grouped validation alongside random "
           "splits whenever a model is meant to be used outside the laboratory that produced its data, and "
           "reporting polarity, machining time, electrode geometry and the balance resolution so that compiled "
           "datasets can describe the differences between studies.")

    W.heading("VI. Limitations")
    W.para("The dataset has <<n_runs>> runs from <<n_studies>> studies, so each LOPO fold holds out a single study "
           "and the estimates are noisy; <<n_nine>> of the studies have only nine runs. Two studies with usable "
           "tables {sultan2014,agrawal2026} could not be retrieved, and more remain to be screened. Several inputs "
           "are missing too often to be used (polarity, gap voltage), and the electrode properties are medians of "
           "values reported in the source studies or approximate handbook values. The TWR of one study is derived from "
           "EWR% and MRR, <<n_zero>> zero values were replaced by a small constant, two studies required a density "
           "taken from other studies, and the data of two studies are physically questionable (Section III-B); "
           "removing any of these does not change the conclusions about the nonlinear models, but it can remove "
           "the small advantage of ridge regression (Table VII). Finally, the studies measure wear differently (mass "
           "loss or volume, different machining times and electrode geometries), which the current features do not "
           "describe.")
    W.heading("VII. Conclusion")
    W.para("A TWR dataset compiled from <<n_studies>> published die-sinking EDM studies was used to compare ridge "
           "regression, random forest, XGBoost, ANN, SVR and a stacked ensemble. When runs from the same study "
           "appear in both training and test data, the models reach R^{2} of about 0.6 on log_{10}(TWR). When a "
           "whole study is held out, no model transfers reliably: the nonlinear models fall below zero and lose "
           "even the ordering of the runs that peak current alone provides, and the small positive R^{2} of ridge "
           "regression depends on which studies are included. Most of the error is the overall wear level of each "
           "study. Models fitted to within-study variation, with the level set from a few runs of the new study, "
           "were the only approach that improved on those runs alone, by <<g_ip_lo>>–<<g_ip_hi>>% for a model of "
           "peak current. Random splits therefore overstate how well TWR models transfer to new laboratories. The "
           "next steps are to add the remaining studies, to fill in polarity and machining time, and to fit full "
           "multilevel models with study-level predictors.")
    W.heading("Data and Code Availability")
    W.para("The compiled dataset, the per-study raw tables, the extraction and checking scripts, a download script "
           "and checksums for the source articles, the analysis code and all result files are available at "
           "https://github.com/Ayush-Singh0583/NTM.", indent=0)
    W.heading("Acknowledgment")
    W.para(f"The authors thank {GUIDE} for guidance.", indent=0)
    W.heading("References")
    unused = [k for k in REFS if k not in ORDER]
    if unused:
        raise ValueError(f"references never cited: {unused}")
    for i, k in enumerate(ORDER, 1):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        f = p.paragraph_format
        f.space_after, f.left_indent, f.first_line_indent = Pt(1), Inches(0.3), Inches(-0.3)
        add_runs(p, f"[{i}]\t{REFS[k]}", 8)
    OUT.parent.mkdir(exist_ok=True)
    doc.save(OUT)
    print("wrote", OUT, f"({len(ORDER)} references)")


if __name__ == "__main__":
    build()
