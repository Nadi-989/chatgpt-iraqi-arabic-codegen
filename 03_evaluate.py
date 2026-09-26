"""Step 3 - run the tests and measure code quality for every saved reply.

Usage:
    python 03_evaluate.py              # all replies
    python 03_evaluate.py --workers 8  # faster on a machine with more cores

WARNING: this runs code written by ChatGPT. Run it inside a virtual machine, a container, or at
least a separate user account, never on a machine with important files.

Output: results/evaluation.csv, one row per reply, with
    passed              1 if all HumanEval tests pass, else 0
    syntax_ok           1 if the code parses
    no_code             1 if the reply contained no function at all (e.g. a question back)
    failure             short reason when the tests fail (assertion, exception type, timeout)
    pylint_score        0-10 (temperature-0 replies only)
    cyclomatic_max      highest cyclomatic complexity of any function (radon)
    sloc                source lines of code (radon)
    text_language       language of the comments/docstrings ChatGPT wrote itself (docstrings
                        copied from the prompt are ignored): none / english / arabic / mixed
"""
import argparse
import ast
import csv
import io
import re
import subprocess
import sys
import tempfile
import tokenize
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from common import EVALUATION, GENERATIONS, IMPORT_HEADER, extract_code, load_problems, read_jsonl

TIMEOUT = 10  # seconds per test run
ARABIC = re.compile(r"[؀-ۿ]")
LATIN = re.compile(r"[A-Za-z]{2,}")
FIELDS = ["task_id", "condition", "sample_id", "temperature", "model_reported", "passed",
          "passed_shared_helpers", "syntax_ok", "no_code", "failure", "pylint_score", "cyclomatic_max", "sloc",
          "text_language", "dialect_level"]


def latest_replies():
    """Last successful reply for each (task, condition, sample)."""
    rows = {}
    for r in read_jsonl(GENERATIONS):
        if not r["error"]:
            rows[(r["task_id"], r["condition"], r["sample_id"])] = r
    return list(rows.values())


def run_tests(code, test, entry_point):
    program = f"{IMPORT_HEADER}\n{code}\n\n{test}\n\ncheck({entry_point})\n"
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "solution.py"
        path.write_text(program, encoding="utf-8")
        try:
            p = subprocess.run([sys.executable, str(path)], cwd=d, capture_output=True,
                               text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            return 0, "timeout"
    if p.returncode == 0:
        return 1, ""
    last = [l for l in p.stderr.strip().splitlines() if l.strip()]
    reason = last[-1] if last else f"exit code {p.returncode}"
    return 0, ("AssertionError" if reason.startswith("AssertionError") else reason)[:120]


def pylint_score(code):
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "solution.py"
        path.write_text(code + "\n", encoding="utf-8")
        p = subprocess.run([sys.executable, "-m", "pylint", str(path), "--score=y",
                            "--disable=missing-module-docstring"],
                           capture_output=True, text=True, timeout=120)
    m = re.search(r"rated at (-?[\d.]+)/10", p.stdout)
    return float(m.group(1)) if m else ""


def complexity(code):
    try:
        from radon.complexity import cc_visit
        from radon.raw import analyze
        blocks = cc_visit(code)
        return (max((b.complexity for b in blocks), default=1), analyze(code).sloc)
    except Exception:
        return "", ""


def text_language(code, prompt):
    """Language of the comments and docstrings ChatGPT wrote itself.

    Docstrings copied back from the prompt are ignored, so the measure reflects new text only.
    """
    pieces = []
    squash = lambda s: re.sub(r"\s+", "", s)
    prompt_flat = squash(prompt)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(code).readline):
            if tok.type == tokenize.COMMENT:
                pieces.append(tok.string)
        for node in ast.walk(ast.parse(code)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                doc = ast.get_docstring(node)
                if doc and squash(doc)[:40] not in prompt_flat:
                    pieces.append(doc)
    except (SyntaxError, tokenize.TokenError, IndentationError):
        return ""
    text = " ".join(pieces)
    has_ar, has_en = bool(ARABIC.search(text)), bool(LATIN.search(re.sub(r">>>.*", "", text)))
    return {(False, False): "none", (False, True): "english",
            (True, False): "arabic", (True, True): "mixed"}[(has_ar, has_en)]


def collect_helpers(replies, problems):
    """Top-level functions ChatGPT defined anywhere in its answers, per condition and sample.

    In the one-chat batch design ChatGPT sometimes calls a helper (e.g. is_prime) that it wrote
    in the answer to another question. The strict score counts that as a failure; the
    'shared helpers' score also runs the code with the missing helper added, so the two
    effects (batch design vs. understanding the task) can be separated."""
    helpers = {}
    for r in replies:
        code = extract_code(r["reply"], r["entry_point"])
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                key = (r["condition"], r["sample_id"], node.name)
                helpers.setdefault(key, ast.get_source_segment(code, node))
    return helpers


def evaluate(reply, problems, helpers=None):
    prob = problems[reply["task_id"]]
    code = extract_code(reply["reply"], reply["entry_point"])
    row = {k: reply.get(k, "") for k in ("task_id", "condition", "sample_id", "temperature",
                                          "model_reported")}
    row["dialect_level"] = prob["dialect_level"]
    if not code:
        return {**row, "passed": 0, "passed_shared_helpers": 0, "syntax_ok": 0, "no_code": 1,
                "failure": "no code in reply"}
    try:
        ast.parse(code)
        syntax_ok = 1
    except SyntaxError:
        syntax_ok = 0
    passed, failure = run_tests(code, prob["_en"]["test"], reply["entry_point"]) if syntax_ok \
        else (0, "SyntaxError")
    shared = passed
    m = re.match(r"NameError: name '(\w+)' is not defined", failure or "")
    if m and helpers:
        helper = helpers.get((reply["condition"], reply["sample_id"], m.group(1)))
        if helper:
            shared, _ = run_tests(helper + "\n\n" + code, prob["_en"]["test"], reply["entry_point"])
    row.update(passed=passed, passed_shared_helpers=shared, syntax_ok=syntax_ok, no_code=0,
               failure=failure)
    if reply["sample_id"] == 0 and syntax_ok:  # quality metrics on the main (temperature-0) reply
        row["pylint_score"] = pylint_score(code)
        row["cyclomatic_max"], row["sloc"] = complexity(code)
        row["text_language"] = text_language(code, reply["prompt"])
    return row


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()
    if not GENERATIONS.exists():
        sys.exit("No results/generations.jsonl yet - run 02_generate.py first.")
    problems = {pr["task_id"]: pr for pr in load_problems()}
    replies = latest_replies()
    print(f"Evaluating {len(replies)} replies with {args.workers} workers...")
    with ThreadPoolExecutor(args.workers) as pool:
        helpers = collect_helpers(replies, problems)
        rows = list(pool.map(lambda r: evaluate(r, problems, helpers), replies))
    rows.sort(key=lambda r: (r["condition"], int(r["task_id"].split("/")[1]), r["sample_id"]))
    with open(EVALUATION, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"Saved {EVALUATION}")


if __name__ == "__main__":
    main()
