"""Step 1 - build data/problems.csv, the sheet the researchers fill in.

Usage:
    python 01_prepare_data.py            # create problems.csv (never overwrites your edits)
    python 01_prepare_data.py --check    # report what is still missing before running the experiment

problems.csv has one row per HumanEval-XL Python problem (80 in total):
    task_id, entry_point       - identifiers, do not edit
    english_description        - original text, for reference only
    msa_description            - Arabic text from HumanEval-XL; review and correct it
    msa_reviewed               - write "yes" after reviewing the MSA text
    literal_warning            - "check" when quoted words (e.g. 'zero') were translated;
                                 the tests still expect the English words, so fix the MSA text
    iraqi_description          - write the task the way an Iraqi student would type it
    iraqi_writer               - initials of the person who wrote it (writer A / writer B)
    dialect_level              - light / medium / heavy
    meaning_verified           - "yes" after a third speaker confirmed the meaning is unchanged
    notes                      - anything else
"""
import argparse
import csv
import re
import sys

from common import DATA, PROBLEMS_CSV, read_jsonl

FIELDS = [
    "task_id", "entry_point", "english_description", "msa_description", "msa_reviewed",
    "literal_warning", "iraqi_description", "iraqi_writer", "dialect_level",
    "meaning_verified", "notes",
]
QUOTED = re.compile(r"""['"]([A-Za-z][A-Za-z ]{0,20})['"]""")


def literal_warning(en_desc, ar_desc):
    """Flag problems whose quoted English literals are missing from the Arabic text."""
    literals = {m for m in QUOTED.findall(en_desc) if len(m) > 1}
    missing = [lit for lit in literals if lit not in ar_desc]
    return "check: " + ", ".join(sorted(missing)) if missing else ""


def create():
    if PROBLEMS_CSV.exists():
        sys.exit(f"{PROBLEMS_CSV.name} already exists - not overwriting your edits. "
                 "Delete it first if you really want to start over.")
    en = read_jsonl(DATA / "English.jsonl")
    ar = {r["task_id"]: r for r in read_jsonl(DATA / "Arabic.jsonl")}
    with open(PROBLEMS_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for e in en:
            a = ar[e["task_id"]]
            w.writerow({
                "task_id": e["task_id"],
                "entry_point": e["entry_point"],
                "english_description": e["description"].strip(),
                "msa_description": a["description"].strip(),
                "msa_reviewed": "",
                "literal_warning": literal_warning(e["description"], a["description"]),
                "iraqi_description": "", "iraqi_writer": "", "dialect_level": "",
                "meaning_verified": "", "notes": "",
            })
    flagged = sum(1 for e in en if literal_warning(e["description"], ar[e["task_id"]]["description"]))
    print(f"Created {PROBLEMS_CSV} with {len(en)} problems.")
    print(f"{flagged} problems have a literal_warning - review their MSA text first.")
    print("Open it in Excel or LibreOffice (UTF-8) and fill in the Iraqi columns.")


def check():
    with open(PROBLEMS_CSV, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    todo = {
        "iraqi_description empty": [r for r in rows if not r["iraqi_description"].strip()],
        "msa_reviewed not yes": [r for r in rows if r["msa_reviewed"].strip().lower() != "yes"],
        "meaning_verified not yes": [r for r in rows if r["meaning_verified"].strip().lower() != "yes"],
        "dialect_level not light/medium/heavy": [
            r for r in rows if r["dialect_level"].strip().lower() not in {"light", "medium", "heavy"}],
        "literal_warning still set": [r for r in rows if r["literal_warning"].strip()],
    }
    ready = True
    for what, bad in todo.items():
        if bad:
            ready = False
            ids = ", ".join(r["task_id"] for r in bad[:8]) + (" ..." if len(bad) > 8 else "")
            print(f"[{len(bad):>2}] {what}: {ids}")
    if any(not r["iraqi_writer"].strip() for r in rows):
        ready = False
        print("[!!] some rows have no iraqi_writer recorded")
    print("\nREADY - run 02_generate.py" if ready else "\nNot ready yet (see above).")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="report what is still missing")
    args = p.parse_args()
    check() if args.check else create()
