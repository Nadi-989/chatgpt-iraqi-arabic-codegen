# Results

Model(s) reported by the API: GPT-5.6 Luna

## 4.1 Functional correctness (RQ1, RQ4)

| Condition | Problems | pass@1 (%) | pass@1 with shared helpers (%) | Syntax errors (%) | No code (%) |
| --- | --- | --- | --- | --- | --- |
| English | 80 | 91.2 | 91.2 | 0.0 | 0.0 |
| Modern Standard Arabic | 80 | 83.8 | 90.0 | 0.0 | 0.0 |
| Iraqi Arabic | 80 | 93.8 | 93.8 | 0.0 | 0.0 |

McNemar tests on the temperature-0 replies (paired by problem):

| Comparison (A vs B) | Problems | Only A passes | Only B passes | p | p (Bonferroni) | Significant (p<0.05) |
| --- | --- | --- | --- | --- | --- | --- |
| English vs Modern Standard Arabic | 80 | 7 | 1 | 0.0703 | 0.2109 | no |
| English vs Iraqi Arabic | 80 | 2 | 4 | 0.6875 | 1.0000 | no |
| Modern Standard Arabic vs Iraqi Arabic | 80 | 1 | 9 | 0.0215 | 0.0645 | no |

## 4.2 Code quality (RQ2)

| Condition | Replies | pylint (/10) | Cyclomatic (max) | SLOC | Arabic comments (%) | Mixed-language comments (%) |
| --- | --- | --- | --- | --- | --- | --- |
| English | 80 | 6.99 | 3.34 | 6.5 | 0.0 | 0.0 |
| Modern Standard Arabic | 80 | 6.56 | 3.29 | 6.2 | 1.2 | 1.2 |
| Iraqi Arabic | 80 | 7.22 | 3.46 | 7.3 | 0.0 | 0.0 |

Wilcoxon signed-rank tests (paired by problem):

| Comparison | Metric | Pairs | p | p (Bonferroni) |
| --- | --- | --- | --- | --- |
| English vs Modern Standard Arabic | pylint_score | 80 | 0.8302 | 1.0000 |
| English vs Modern Standard Arabic | cyclomatic_max | 80 | 0.9339 | 1.0000 |
| English vs Modern Standard Arabic | sloc | 80 | 0.7079 | 1.0000 |
| English vs Iraqi Arabic | pylint_score | 80 | 0.0025 | 0.0223 |
| English vs Iraqi Arabic | cyclomatic_max | 80 | 0.1808 | 1.0000 |
| English vs Iraqi Arabic | sloc | 80 | 0.0018 | 0.0160 |
| Modern Standard Arabic vs Iraqi Arabic | pylint_score | 80 | 0.0031 | 0.0281 |
| Modern Standard Arabic vs Iraqi Arabic | cyclomatic_max | 80 | 0.2166 | 1.0000 |
| Modern Standard Arabic vs Iraqi Arabic | sloc | 80 | 0.0002 | 0.0016 |

## 4.3 Error types (RQ3)

2 problems passed in English but failed in Iraqi Arabic. Label them in `error_annotation.csv` (categories: dialect word misunderstood, partial understanding, ordinary logic error, non-code reply, other), then run `python 04_analyze.py --kappa`.

## 4.4 Effect of dialect level

| Dialect level | Problems | pass@1 (%) |
| --- | --- | --- |
| light | 22 | 100.0 |
| medium | 38 | 92.1 |
| heavy | 20 | 90.0 |
