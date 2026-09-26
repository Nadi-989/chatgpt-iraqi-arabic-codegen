"""Shared helpers for the ChatGPT / Iraqi-dialect code-generation study."""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)

PROBLEMS_CSV = DATA / "problems.csv"            # the file the researchers edit
GENERATIONS = RESULTS / "generations.jsonl"     # raw ChatGPT replies
EVALUATION = RESULTS / "evaluation.csv"         # one row per generated sample

# The four experimental conditions (RQ1-RQ4 in the paper).
CONDITIONS = ["english", "msa", "iraqi", "iraqi_translated"]
CONDITION_LABELS = {
    "english": "English",
    "msa": "Modern Standard Arabic",
    "iraqi": "Iraqi Arabic",
    "iraqi_translated": "Iraqi -> English (RQ4)",
}

# Identical for every condition, so the only thing that changes is the task text.
SYSTEM_PROMPT = (
    "You are a Python programmer. Complete the function below. "
    "Reply with one Python code block containing the complete function "
    "(signature and body), plus any imports it needs. Do not add tests or explanations."
)

TRANSLATE_PROMPT = (
    "Translate the following programming task description from Iraqi Arabic into "
    "clear English. Keep code, names, numbers and examples unchanged. "
    "Reply with the translation only.\n\n{text}"
)

# Imports HumanEval solutions commonly rely on; prepended when running tests.
IMPORT_HEADER = (
    "import math\nimport re\nimport string\nimport itertools\nimport collections\n"
    "import heapq\nimport functools\nfrom typing import *\n"
)


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_jsonl(path, row):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_problems():
    """Rows of data/problems.csv, joined with the original HumanEval-XL records."""
    en = {r["task_id"]: r for r in read_jsonl(DATA / "English.jsonl")}
    ar = {r["task_id"]: r for r in read_jsonl(DATA / "Arabic.jsonl")}
    with open(PROBLEMS_CSV, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["_en"] = en[row["task_id"]]
        row["_ar"] = ar[row["task_id"]]
    return rows


def build_prompt(problem, condition, translated_text=None):
    """The function stub + docstring shown to ChatGPT for one condition."""
    en, ar = problem["_en"], problem["_ar"]
    if condition == "english":
        return en["prompt"]
    if condition == "msa":
        return ar["prompt"].replace(ar["description"], problem["msa_description"].strip(), 1)
    if condition == "iraqi":
        return ar["prompt"].replace(ar["description"], problem["iraqi_description"].strip(), 1)
    if condition == "iraqi_translated":
        if translated_text is None:
            raise ValueError("iraqi_translated needs the translated description")
        return ar["prompt"].replace(ar["description"], translated_text.strip(), 1)
    raise ValueError(condition)


CODE_BLOCK = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_code(reply, entry_point):
    """Pull the function out of a ChatGPT reply. Returns '' when there is no code."""
    if not reply:
        return ""
    blocks = CODE_BLOCK.findall(reply)
    if blocks:
        # Prefer the block that defines the requested function.
        for block in blocks:
            if re.search(rf"def\s+{re.escape(entry_point)}\s*\(", block):
                return block.strip()
        return blocks[0].strip()
    if re.search(rf"def\s+{re.escape(entry_point)}\s*\(", reply):
        return trim_to_code(reply)  # plain code without fences
    return ""


def trim_to_code(text, max_trim=15):
    """Plain (unfenced) code copied from a chat often carries a line of prose before or after
    it (e.g. a website banner). Drop leading lines before the first import/def and, if the
    code still does not parse, drop trailing lines one by one."""
    import ast
    lines = text.strip().splitlines()
    start = next((i for i, l in enumerate(lines)
                  if re.match(r"\s*(def |import |from |class |@)", l)), 0)
    lines = lines[start:]
    for cut in range(0, min(max_trim, len(lines) - 1) + 1):
        candidate = "\n".join(lines[:len(lines) - cut]).strip()
        try:
            ast.parse(candidate)
            return candidate
        except SyntaxError:
            continue
    return "\n".join(lines).strip()
