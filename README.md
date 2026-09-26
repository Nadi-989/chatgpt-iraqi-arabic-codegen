# Does ChatGPT Understand Iraqi Arabic?

Data and scripts for the paper *"Does ChatGPT Understand Iraqi Arabic? An Empirical Study of Prompt Dialect and Generated Code Quality."*

We gave ChatGPT (GPT-5.6 Luna, free web version, September 2026) the same 80 Python problems from [HumanEval-XL](https://github.com/floatai/HumanEval-XL) in English, Modern Standard Arabic (MSA), and Iraqi Arabic. Every answer was run against the original unit tests.

## Results

| Prompt | Passed | pass@1 |
|---|---|---|
| English | 73/80 | 91.2% |
| MSA (corrected) | 67/80 | 83.8% (90.0% with shared helpers) |
| Iraqi Arabic | 75/80 | 93.8% |

No difference is statistically significant (McNemar, Bonferroni-corrected).

## Contents

| Path | What it is |
|---|---|
| `data/problems.csv` | The 80 problems: English, corrected MSA, Iraqi Arabic, dialect level, notes on every MSA correction |
| `data/English.jsonl`, `data/Arabic.jsonl` | Original HumanEval-XL files (MIT licence) |
| `results/final/` | ChatGPT's raw answers, evaluation per answer, and the final report |
| `results/run1/` | Pilot run on the uncorrected MSA prompts |
| `01_prepare_data.py` … `04_analyze.py` | Pipeline: prepare → generate → evaluate → analyse |

## Reproduce the evaluation

```bash
pip install -r requirements.txt
python 02_manual.py batch-export                               # question files, one per language
python 02_manual.py batch-import reply_english.txt --condition english
python 03_evaluate.py                                          # runs generated code: use a sandbox
python 04_analyze.py                                           # tables -> results/report.md
```

`02_generate.py` can also query the OpenAI API directly (`--model`), or run without any API (`--mock`) to test the pipeline.

## Notes

- 16 of the 80 HumanEval-XL MSA prompts contained translation errors; corrections are logged in the `notes` column of `problems.csv`.
- Iraqi prompts were drafted with Claude (not ChatGPT) and reviewed by a native Iraqi speaker.

## Licence

Code: MIT. Problems derived from HumanEval-XL (MIT).
