"""Step 4 - statistics and the tables for Section 4 of the paper.

Usage:
    python 04_analyze.py            # tables + statistics -> results/report.md
    python 04_analyze.py --kappa    # after both annotators filled results/error_annotation.csv

Produces:
    results/report.md             all tables of Section 4, ready to paste into the paper
    results/error_annotation.csv  replies that passed in English but failed in Iraqi Arabic,
                                  for manual error classification (RQ3) by two annotators
"""
import argparse
import csv
import itertools
import sys
from math import comb

import pandas as pd
from scipy.stats import wilcoxon
from statsmodels.stats.contingency_tables import mcnemar
from statsmodels.stats.multitest import multipletests

from common import (CONDITION_LABELS, CONDITIONS, EVALUATION, GENERATIONS, RESULTS,
                    extract_code, read_jsonl)

REPORT = RESULTS / "report.md"
ANNOTATION = RESULTS / "error_annotation.csv"
ERROR_CATEGORIES = ["dialect word misunderstood", "partial understanding",
                    "ordinary logic error", "non-code reply", "other"]
PAIRS = [("english", "msa"), ("english", "iraqi"), ("msa", "iraqi"),
         ("iraqi", "iraqi_translated"), ("english", "iraqi_translated")]


def md_table(df):
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def pass_at_k(n, c, k):
    if n - c < k:
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)


def correctness(ev):
    main = ev[ev.sample_id == 0]
    sampled = ev[ev.sample_id > 0]
    rows = []
    for cond in [c for c in CONDITIONS if c in set(ev.condition)]:
        m = main[main.condition == cond]
        s = sampled[sampled.condition == cond].groupby("task_id").passed.agg(["count", "sum"])
        n = int(s["count"].min()) if len(s) else 0
        row = {"Condition": CONDITION_LABELS[cond], "Problems": len(m),
               "pass@1 (%)": f"{100 * m.passed.mean():.1f}"}
        if n:
            row["pass@1, sampled (%)"] = f"{100 * s.apply(lambda r: pass_at_k(r['count'], r['sum'], 1), axis=1).mean():.1f}"
            row[f"pass@{n} (%)"] = f"{100 * s.apply(lambda r: pass_at_k(r['count'], r['sum'], n), axis=1).mean():.1f}"
        if "passed_shared_helpers" in main and (main.passed_shared_helpers != main.passed).any():
            row["pass@1 with shared helpers (%)"] = f"{100 * m.passed_shared_helpers.mean():.1f}"
        row["Syntax errors (%)"] = f"{100 * (1 - m[m.no_code == 0].syntax_ok.mean()):.1f}" \
            if (m.no_code == 0).any() else "-"
        row["No code (%)"] = f"{100 * m.no_code.mean():.1f}"
        rows.append(row)
    return pd.DataFrame(rows)


def mcnemar_tests(ev):
    main = ev[ev.sample_id == 0].pivot_table(index="task_id", columns="condition", values="passed")
    rows = []
    for a, b in PAIRS:
        if a not in main or b not in main:
            continue
        both = main[[a, b]].dropna()
        t = pd.crosstab(both[a], both[b]).reindex(index=[0, 1], columns=[0, 1], fill_value=0)
        discordant = t.loc[1, 0] + t.loc[0, 1]
        res = mcnemar(t.values, exact=discordant < 25)
        rows.append({"Comparison (A vs B)": f"{CONDITION_LABELS[a]} vs {CONDITION_LABELS[b]}",
                     "Problems": len(both), "Only A passes": int(t.loc[1, 0]),
                     "Only B passes": int(t.loc[0, 1]), "p": res.pvalue})
    df = pd.DataFrame(rows)
    if len(df):
        df["p (Bonferroni)"] = multipletests(df.p, method="bonferroni")[1]
        df["Significant (p<0.05)"] = df["p (Bonferroni)"].map(lambda p: "yes" if p < 0.05 else "no")
        df["p"] = df.p.map(lambda p: f"{p:.4f}")
        df["p (Bonferroni)"] = df["p (Bonferroni)"].map(lambda p: f"{p:.4f}")
    return df


def quality(ev):
    main = ev[(ev.sample_id == 0) & (ev.syntax_ok == 1)].copy()
    for c in ["pylint_score", "cyclomatic_max", "sloc"]:
        main[c] = pd.to_numeric(main[c], errors="coerce")
    rows = []
    for cond in [c for c in CONDITIONS if c in set(main.condition)]:
        m = main[main.condition == cond]
        lang = m.text_language.fillna("").value_counts(normalize=True)
        rows.append({"Condition": CONDITION_LABELS[cond], "Replies": len(m),
                     "pylint (/10)": f"{m.pylint_score.mean():.2f}",
                     "Cyclomatic (max)": f"{m.cyclomatic_max.mean():.2f}",
                     "SLOC": f"{m.sloc.mean():.1f}",
                     "Arabic comments (%)": f"{100 * lang.get('arabic', 0):.1f}",
                     "Mixed-language comments (%)": f"{100 * lang.get('mixed', 0):.1f}"})
    tests = []
    for a, b in [("english", "msa"), ("english", "iraqi"), ("msa", "iraqi")]:
        for metric in ["pylint_score", "cyclomatic_max", "sloc"]:
            x = main[main.condition == a].set_index("task_id")[metric]
            y = main[main.condition == b].set_index("task_id")[metric]
            both = pd.concat([x, y], axis=1, keys=[a, b]).dropna()
            if len(both) < 5 or (both[a] - both[b]).abs().sum() == 0:
                p = float("nan")
            else:
                p = wilcoxon(both[a], both[b]).pvalue
            tests.append({"Comparison": f"{CONDITION_LABELS[a]} vs {CONDITION_LABELS[b]}",
                          "Metric": metric, "Pairs": len(both), "p": p})
    tdf = pd.DataFrame(tests)
    if len(tdf):
        ok = tdf.p.notna()
        tdf["p (Bonferroni)"] = float("nan")
        if ok.any():
            tdf.loc[ok, "p (Bonferroni)"] = multipletests(tdf.loc[ok, "p"], method="bonferroni")[1]
        for c in ["p", "p (Bonferroni)"]:
            tdf[c] = tdf[c].map(lambda p: "-" if pd.isna(p) else f"{p:.4f}")
    return pd.DataFrame(rows), tdf


def by_dialect_level(ev):
    m = ev[(ev.sample_id == 0) & (ev.condition == "iraqi")]
    if m.empty:
        return pd.DataFrame()
    g = m.groupby(m.dialect_level.fillna("unset")).passed.agg(["count", "mean"]).reset_index()
    order = {"light": 0, "medium": 1, "heavy": 2}
    g = g.sort_values("dialect_level", key=lambda s: s.map(lambda v: order.get(v, 9)))
    return pd.DataFrame({"Dialect level": g.dialect_level, "Problems": g["count"],
                         "pass@1 (%)": (100 * g["mean"]).map(lambda v: f"{v:.1f}")})


def write_annotation_sheet(ev):
    """Replies that pass in English but fail in Iraqi (temperature 0), for manual labelling."""
    main = ev[ev.sample_id == 0].pivot_table(index="task_id", columns="condition", values="passed")
    if "english" not in main or "iraqi" not in main:
        return 0
    ids = main[(main.english == 1) & (main.iraqi == 0)].index
    if ANNOTATION.exists():
        old = pd.read_csv(ANNOTATION, encoding="utf-8-sig", dtype=str).fillna("")
        labelled = old[["annotator_1_category", "annotator_2_category", "agreed_category"]]
        if (labelled != "").any().any():
            print(f"{ANNOTATION.name} already has labels - not overwriting it.")
            return len(ids)
    gens = {(r["task_id"], r["condition"]): r for r in read_jsonl(GENERATIONS)
            if r["sample_id"] == 0 and not r["error"]}
    fail = ev[(ev.sample_id == 0) & (ev.condition == "iraqi")].set_index("task_id").failure
    with open(ANNOTATION, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["task_id", "iraqi_prompt", "chatgpt_code", "test_failure",
                    "annotator_1_category", "annotator_2_category", "agreed_category", "example_note"])
        for tid in sorted(ids, key=lambda t: int(t.split("/")[1])):
            g = gens[(tid, "iraqi")]
            w.writerow([tid, g["prompt"], extract_code(g["reply"], g["entry_point"]) or g["reply"],
                        fail.get(tid, ""), "", "", "", ""])
    return len(ids)


def kappa():
    from sklearn.metrics import cohen_kappa_score  # noqa: optional dependency
    df = pd.read_csv(ANNOTATION, encoding="utf-8-sig").fillna("")
    both = df[(df.annotator_1_category != "") & (df.annotator_2_category != "")]
    if both.empty:
        sys.exit("No rows labelled by both annotators yet.")
    k = cohen_kappa_score(both.annotator_1_category, both.annotator_2_category)
    print(f"Cohen's kappa = {k:.3f} on {len(both)} replies")
    agreed = df[df.agreed_category != ""]
    if len(agreed):
        counts = agreed.agreed_category.value_counts()
        out = pd.DataFrame({"Error type": counts.index, "Count": counts.values,
                            "Share (%)": (100 * counts.values / counts.sum()).round(1)})
        print(md_table(out))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--kappa", action="store_true", help="agreement between the two annotators")
    args = p.parse_args()
    if args.kappa:
        return kappa()
    if not EVALUATION.exists():
        sys.exit("No results/evaluation.csv yet - run 03_evaluate.py first.")
    ev = pd.read_csv(EVALUATION, encoding="utf-8-sig")
    models = sorted(set(ev.model_reported.dropna().astype(str)))

    parts = ["# Results", "", f"Model(s) reported by the API: {', '.join(models)}", ""]
    parts += ["## 4.1 Functional correctness (RQ1, RQ4)", "", md_table(correctness(ev)), "",
              "McNemar tests on the temperature-0 replies (paired by problem):", ""]
    mc = mcnemar_tests(ev)
    parts += [md_table(mc) if len(mc) else "_not enough conditions yet_", ""]
    qt, qtests = quality(ev)
    parts += ["## 4.2 Code quality (RQ2)", "", md_table(qt), "",
              "Wilcoxon signed-rank tests (paired by problem):", "",
              md_table(qtests) if len(qtests) else "_not enough data_", ""]
    n_ann = write_annotation_sheet(ev)
    parts += ["## 4.3 Error types (RQ3)", "",
              f"{n_ann} problems passed in English but failed in Iraqi Arabic. "
              f"Label them in `{ANNOTATION.name}` (categories: {', '.join(ERROR_CATEGORIES)}), "
              "then run `python 04_analyze.py --kappa`.", ""]
    dl = by_dialect_level(ev)
    parts += ["## 4.4 Effect of dialect level", "",
              md_table(dl) if len(dl) else "_no Iraqi results yet_", ""]
    REPORT.write_text("\n".join(parts), encoding="utf-8")
    print("\n".join(parts))
    print(f"\nSaved {REPORT}")


if __name__ == "__main__":
    main()
