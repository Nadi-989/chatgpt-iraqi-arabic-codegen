# Results

Model(s) reported by the API: chatgpt.com (web, batch)

## 4.1 Functional correctness (RQ1, RQ4)

| Condition | Problems | pass@1 (%) | Syntax errors (%) | No code (%) |
| --- | --- | --- | --- | --- |
| English | 80 | 91.2 | 0.0 | 0.0 |
| Modern Standard Arabic | 80 | 85.0 | 0.0 | 0.0 |

McNemar tests on the temperature-0 replies (paired by problem):

| Comparison (A vs B) | Problems | Only A passes | Only B passes | p | p (Bonferroni) | Significant (p<0.05) |
| --- | --- | --- | --- | --- | --- | --- |
| English vs Modern Standard Arabic | 80 | 6 | 1 | 0.1250 | 0.1250 | no |

## 4.2 Code quality (RQ2)

| Condition | Replies | pylint (/10) | Cyclomatic (max) | SLOC | Arabic comments (%) | Mixed-language comments (%) |
| --- | --- | --- | --- | --- | --- | --- |
| English | 80 | 6.99 | 3.34 | 6.5 | 0.0 | 0.0 |
| Modern Standard Arabic | 80 | 6.85 | 3.24 | 6.0 | 0.0 | 0.0 |

Wilcoxon signed-rank tests (paired by problem):

| Comparison | Metric | Pairs | p | p (Bonferroni) |
| --- | --- | --- | --- | --- |
| English vs Modern Standard Arabic | pylint_score | 80 | 0.3245 | 0.9734 |
| English vs Modern Standard Arabic | cyclomatic_max | 80 | 0.6201 | 1.0000 |
| English vs Modern Standard Arabic | sloc | 80 | 0.0011 | 0.0032 |
| English vs Iraqi Arabic | pylint_score | 0 | - | - |
| English vs Iraqi Arabic | cyclomatic_max | 0 | - | - |
| English vs Iraqi Arabic | sloc | 0 | - | - |
| Modern Standard Arabic vs Iraqi Arabic | pylint_score | 0 | - | - |
| Modern Standard Arabic vs Iraqi Arabic | cyclomatic_max | 0 | - | - |
| Modern Standard Arabic vs Iraqi Arabic | sloc | 0 | - | - |

## 4.3 Error types (RQ3)

0 problems passed in English but failed in Iraqi Arabic. Label them in `error_annotation.csv` (categories: dialect word misunderstood, partial understanding, ordinary logic error, non-code reply, other), then run `python 04_analyze.py --kappa`.

## 4.4 Effect of dialect level

_no Iraqi results yet_
