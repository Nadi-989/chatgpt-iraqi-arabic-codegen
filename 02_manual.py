"""Manual mode - run the experiment through the free ChatGPT website instead of an API.

BATCH DESIGN (one chat per language - used in the paper):
    python 02_manual.py batch-export
  -> results/batch_questions_english.txt, _msa.txt, _iraqi.txt
     Same 80 questions, same order, same instructions; only the task descriptions differ.
     For each language: open a NEW ChatGPT chat, attach the file, send exactly BATCH_MESSAGE
     (printed by the command). If ChatGPT stops before question 80, send exactly "continue".
     Copy ChatGPT's whole answer(s) into one text file, e.g. reply_english.txt.
    python 02_manual.py batch-import reply_english.txt --condition english
  -> adds the 80 answers to results/generations.jsonl; then run 03_evaluate.py / 04_analyze.py.

ONE-CHAT-PER-QUESTION DESIGN (alternative):
Step A - make the page of prompts (in Colab or on your computer):
    python 02_manual.py export                          # English + MSA + Iraqi
    python 02_manual.py export --conditions english msa # e.g. before the Iraqi text is ready
  -> results/manual_prompts.html
     Download it and open it in Chrome on your computer. For every prompt:
     copy it, paste it into a NEW ChatGPT chat, copy ChatGPT's whole answer back into the box.
     The page saves your work in the browser; press "Download replies" at the end of each day.

Step B - bring the answers back:
    python 02_manual.py import replies.json
  -> adds them to results/generations.jsonl, then run 03_evaluate.py and 04_analyze.py as usual.

Notes for the paper: the website does not let you set the temperature or a system prompt,
so every prompt starts with the same fixed instruction, each prompt goes into a fresh chat,
and ChatGPT's memory should be switched off. Record the model name the website shows.
"""
import argparse
import datetime as dt
import html
import json
import random
import re
import sys
from pathlib import Path

from common import (CONDITION_LABELS, GENERATIONS, RESULTS, SYSTEM_PROMPT, append_jsonl,
                    build_prompt, load_problems, read_jsonl)

PAGE = RESULTS / "manual_prompts.html"
MANUAL_CONDITIONS = ["english", "msa", "iraqi"]  # RQ4 needs an extra translation step; skipped here
LABELS_AR = {"english": "إنجليزي", "msa": "فصحى", "iraqi": "عراقي"}


def web_prompt(problem, condition):
    """What gets pasted into ChatGPT: the fixed instruction, then the function stub."""
    return f"{SYSTEM_PROMPT}\n\n```python\n{build_prompt(problem, condition).rstrip()}\n```"


def export(conditions, seed):
    problems = load_problems()
    items = []
    for p in problems:
        for c in conditions:
            if c == "iraqi" and not p["iraqi_description"].strip():
                continue
            items.append({"id": f"{p['task_id']}|{c}", "task_id": p["task_id"], "condition": c,
                          "prompt": web_prompt(p, c)})
    missing_iraqi = sum(1 for p in problems if not p["iraqi_description"].strip())
    # Interleave conditions in a fixed random order so no language is always asked first.
    random.Random(seed).shuffle(items)
    page_id = f"iraqi-study-{seed}-{len(items)}"
    PAGE.write_text(TEMPLATE.replace("__DATA__", json.dumps(items, ensure_ascii=False))
                    .replace("__PAGE_ID__", page_id), encoding="utf-8")
    print(f"Saved {PAGE} with {len(items)} prompts.")
    if "iraqi" in conditions and missing_iraqi:
        print(f"Note: {missing_iraqi} problems have no Iraqi text yet, so their Iraqi prompt is not included.")


def import_replies(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    replies, model = data.get("replies", {}), data.get("model", "").strip()
    problems = {p["task_id"]: p for p in load_problems()}
    done = set()
    if GENERATIONS.exists():
        done = {(r["task_id"], r["condition"], r["sample_id"]) for r in read_jsonl(GENERATIONS)
                if not r["error"]}
    added = skipped = empty = 0
    for key, entry in replies.items():
        task_id, cond = key.split("|")
        text = (entry.get("reply") or "").strip()
        if not text:
            empty += 1
            continue
        if (task_id, cond, 0) in done:
            skipped += 1
            continue
        p = problems[task_id]
        append_jsonl(GENERATIONS, {
            "task_id": task_id, "entry_point": p["entry_point"], "condition": cond,
            "sample_id": 0, "temperature": None, "model_requested": "chatgpt.com (web)",
            "model_reported": entry.get("model") or model or "chatgpt.com (web)",
            "finish_reason": "", "timestamp": entry.get("time") or
            dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "prompt": web_prompt(p, cond), "reply": text, "error": "",
        })
        added += 1
    print(f"Added {added} replies ({skipped} already imported, {empty} still empty).")
    print("Next: python 03_evaluate.py  then  python 04_analyze.py")


BATCH_HEADER = (
    "Below are 80 Python programming questions. For each question, complete the function.\n"
    "Answer ALL 80 questions, in order. For each one, write its number (for example\n"
    "\"Question 1\") and then one Python code block containing the complete function\n"
    "(signature and body) plus any imports it needs. Do not add tests or explanations."
)
BATCH_MESSAGE = "Answer all 80 questions in the attached file, in order, following its instructions."
BATCH_CONTINUE = "continue"


def batch_order(seed):
    """One fixed question order, shared by every language."""
    problems = load_problems()
    random.Random(seed).shuffle(problems)
    return problems


def batch_export(conditions, seed):
    problems = batch_order(seed)
    for cond in conditions:
        if cond == "iraqi":
            missing = [p["task_id"] for p in problems if not p["iraqi_description"].strip()]
            if missing:
                print(f"Skipping the Iraqi file: {len(missing)} problems have no Iraqi text yet.")
                continue
        parts = [BATCH_HEADER, ""]
        for n, p in enumerate(problems, 1):
            parts += [f"### Question {n}", "```python", build_prompt(p, cond).rstrip(), "```", ""]
        out = RESULTS / f"batch_questions_{cond}.txt"
        out.write_text("\n".join(parts), encoding="utf-8")
        print(f"Saved {out}")
    order = RESULTS / "batch_order.json"
    order.write_text(json.dumps([p["task_id"] for p in problems]), encoding="utf-8")
    print(f"\nFor each language: new chat, attach the file, send exactly:\n  {BATCH_MESSAGE}\n"
          f"If ChatGPT stops early, send exactly: {BATCH_CONTINUE}")


NUMBER_LINE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*(?:question|q|سؤال|السؤال)?\s*#?\s*(\d{1,2})\s*[\.\):\-–]?\s*(?:\*\*)?\s*$",
    re.IGNORECASE)


def split_batch_reply(text):
    """{question number: text of its answer} from ChatGPT's long reply."""
    answers, current, in_code = {}, None, False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        m = None if in_code else NUMBER_LINE.match(line)
        if m and 1 <= int(m.group(1)) <= 80:
            current = int(m.group(1))
            # A number seen again means the answers start after a pasted copy of the
            # questions; keep only the latest (the answer).
            answers[current] = []
            continue
        if current is not None:
            answers[current].append(line)
    return {n: "\n".join(lines).strip() for n, lines in answers.items()}


def batch_import(path, condition, seed, model):
    order_file = RESULTS / "batch_order.json"
    order = json.loads(order_file.read_text(encoding="utf-8")) if order_file.exists() \
        else [p["task_id"] for p in batch_order(seed)]
    problems = {p["task_id"]: p for p in load_problems()}
    answers = split_batch_reply(Path(path).read_text(encoding="utf-8-sig"))
    done = set()
    if GENERATIONS.exists():
        done = {(r["task_id"], r["condition"]) for r in read_jsonl(GENERATIONS)
                if not r["error"] and r["sample_id"] == 0}
    added, problems_found = 0, []
    for n, task_id in enumerate(order, 1):
        p = problems[task_id]
        if (task_id, condition) in done:
            continue
        text = answers.get(n, "")
        if not text:
            problems_found.append(f"Question {n} ({task_id}): no answer found")
            text = ""
        elif not re.search(rf"def\s+{re.escape(p['entry_point'])}\s*\(", text):
            problems_found.append(f"Question {n} ({task_id}): answer does not define {p['entry_point']}()")
        append_jsonl(GENERATIONS, {
            "task_id": task_id, "entry_point": p["entry_point"], "condition": condition,
            "sample_id": 0, "temperature": None, "model_requested": "chatgpt.com (web, batch)",
            "model_reported": model or "chatgpt.com (web, batch)", "finish_reason": "",
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "prompt": f"[batch question {n}]\n{build_prompt(p, condition)}",
            "reply": text, "error": "",
        })
        added += 1
    print(f"Found {len(answers)} numbered answers; added {added} replies for '{condition}'.")
    for line in problems_found:
        print("  ! " + line)
    print("Next: python 03_evaluate.py  then  python 04_analyze.py")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>أسئلة ChatGPT - تجربة اللهجة العراقية</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e2e1dc;--accent:#1f6f5c;--done:#e7f3ee;--warn:#fff4e0}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,"Segoe UI",Tahoma,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line);padding:12px 16px}
.wrap{max-width:900px;margin:0 auto}h1{font-size:18px;margin:0 0 6px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.progress{height:8px;background:var(--line);border-radius:4px;overflow:hidden;flex:1 1 200px}.progress i{display:block;height:100%;background:var(--accent);width:0}
button,label.btn{font:inherit;font-size:14px;border:1px solid var(--line);background:var(--card);border-radius:8px;padding:6px 12px;cursor:pointer}
button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
input[type=text]{font:inherit;font-size:14px;padding:6px 8px;border:1px solid var(--line);border-radius:8px;min-width:180px}
details.help{background:var(--warn);border-radius:8px;padding:8px 12px;margin:12px 0;font-size:15px}
main{padding:16px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:0 0 14px}
.card.done{background:var(--done)}.meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:14px;color:var(--muted)}
.tag{background:var(--bg);border:1px solid var(--line);border-radius:999px;padding:0 10px;color:var(--ink)}
pre{direction:ltr;text-align:left;white-space:pre-wrap;background:#f1f1ee;border-radius:8px;padding:10px;font-size:13px;max-height:220px;overflow:auto;margin:8px 0}
textarea{direction:ltr;width:100%;min-height:110px;font:13px/1.5 ui-monospace,Consolas,monospace;border:1px solid var(--line);border-radius:8px;padding:8px}
.ok{color:var(--accent);font-weight:600}
</style></head><body>
<header><div class="wrap">
<h1>أسئلة التجربة: انسخي السؤال ← الصقيه بمحادثة ChatGPT جديدة ← الصقي الجواب هنا</h1>
<div class="bar">
<div class="progress"><i id="prog"></i></div><span id="count"></span>
<label>النموذج الظاهر بـ ChatGPT: <input type="text" id="model" placeholder="مثلاً: GPT-5 mini"></label>
<button id="onlyTodo">أظهري الباقي بس</button>
<button class="primary" id="download">نزّلي الأجوبة (replies.json)</button>
<label class="btn">رجّعي ملف أجوبة<input type="file" id="restore" accept=".json" hidden></label>
</div></div></header>
<main class="wrap">
<details class="help" open><summary><b>التعليمات (اقريها مرة وحدة)</b></summary>
<ol>
<li>بـ ChatGPT طفّي الذاكرة: Settings ← Personalization ← Memory (أو استعملي Temporary chat).</li>
<li>لكل سؤال: اضغطي «انسخي السؤال»، افتحي <b>محادثة جديدة</b> بـ ChatGPT، الصقيه وأرسليه.</li>
<li>تحت جواب ChatGPT اضغطي أيقونة النسخ (المربعين)، والصقي الجواب كامل بالمربع هنا. لا تعدّلين شي.</li>
<li>إذا ChatGPT سأل سؤال بدل ما يكتب كود، الصقي سؤاله مثل ما هو. هذا نتيجة مهمة.</li>
<li>الصفحة تحفظ وحدها بهذا المتصفح. بآخر كل يوم اضغطي «نزّلي الأجوبة» واحفظي الملف.</li>
<li>اكتبي اسم النموذج اللي يظهر بـ ChatGPT فوك، وإذا تغيّر بنص الشغل غيّريه.</li>
</ol></details>
<div id="list"></div>
</main>
<script>
const ITEMS = __DATA__;
const KEY = "__PAGE_ID__";
const LABELS = {english:"إنجليزي", msa:"فصحى", iraqi:"عراقي"};
let state = {model:"", replies:{}};
try { const s = localStorage.getItem(KEY); if (s) state = JSON.parse(s); } catch(e) {}
let onlyTodo = false;
const $ = id => document.getElementById(id);
function save(){ try { localStorage.setItem(KEY, JSON.stringify(state)); } catch(e) {} updateCount(); }
function updateCount(){
  const n = ITEMS.filter(it => (state.replies[it.id]||{}).reply?.trim()).length;
  $("count").textContent = n + " / " + ITEMS.length;
  $("prog").style.width = (100*n/ITEMS.length) + "%";
}
function render(){
  const list = $("list"); list.innerHTML = "";
  ITEMS.forEach((it, i) => {
    const r = state.replies[it.id] || {};
    const done = !!(r.reply && r.reply.trim());
    if (onlyTodo && done) return;
    const card = document.createElement("div"); card.className = "card" + (done ? " done" : "");
    card.innerHTML = `<div class="meta"><b>#${i+1}</b><span class="tag">${LABELS[it.condition]}</span>
      <span>${it.task_id}</span><span class="ok">${done ? "✓ تم" : ""}</span></div>
      <pre></pre><button class="copy">انسخي السؤال</button>
      <div style="margin-top:8px">جواب ChatGPT:</div><textarea placeholder="الصقي جواب ChatGPT هنا"></textarea>`;
    card.querySelector("pre").textContent = it.prompt;
    const ta = card.querySelector("textarea"); ta.value = r.reply || "";
    card.querySelector(".copy").onclick = async (e) => {
      try { await navigator.clipboard.writeText(it.prompt); }
      catch(err) { const t=document.createElement("textarea"); t.value=it.prompt; document.body.appendChild(t); t.select(); document.execCommand("copy"); t.remove(); }
      e.target.textContent = "✓ انسخ"; setTimeout(()=>e.target.textContent="انسخي السؤال", 1500);
    };
    ta.oninput = () => {
      state.replies[it.id] = {reply: ta.value, model: state.model, time: new Date().toISOString()};
      const d = !!ta.value.trim(); card.classList.toggle("done", d);
      card.querySelector(".ok").textContent = d ? "✓ تم" : ""; save();
    };
    list.appendChild(card);
  });
  updateCount();
}
$("model").value = state.model || "";
$("model").oninput = e => { state.model = e.target.value; save(); };
$("onlyTodo").onclick = e => { onlyTodo = !onlyTodo; e.target.textContent = onlyTodo ? "أظهري الكل" : "أظهري الباقي بس"; render(); };
$("download").onclick = () => {
  const blob = new Blob([JSON.stringify({page:KEY, model:state.model, replies:state.replies}, null, 1)], {type:"application/json"});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "replies.json"; a.click();
};
$("restore").onchange = async e => {
  const f = e.target.files[0]; if (!f) return;
  try { const d = JSON.parse(await f.text());
    state.replies = Object.assign({}, d.replies || {}, state.replies); if (!state.model) state.model = d.model || "";
    $("model").value = state.model; save(); render(); alert("رجعت الأجوبة ✓");
  } catch(err) { alert("الملف مو صحيح"); }
};
window.addEventListener("beforeunload", save);
render();
</script></body></html>
"""


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="make results/manual_prompts.html")
    e.add_argument("--conditions", nargs="+", default=MANUAL_CONDITIONS, choices=MANUAL_CONDITIONS)
    e.add_argument("--seed", type=int, default=2026, help="order of the prompts (keep it fixed)")
    i = sub.add_parser("import", help="add a downloaded replies.json to the results")
    i.add_argument("file")
    be = sub.add_parser("batch-export", help="one question file per language (batch design)")
    be.add_argument("--conditions", nargs="+", default=MANUAL_CONDITIONS, choices=MANUAL_CONDITIONS)
    be.add_argument("--seed", type=int, default=2026)
    bi = sub.add_parser("batch-import", help="read ChatGPT's long answer for one language")
    bi.add_argument("file")
    bi.add_argument("--condition", required=True, choices=MANUAL_CONDITIONS)
    bi.add_argument("--model", default="", help="model name shown on the ChatGPT website")
    bi.add_argument("--seed", type=int, default=2026)
    args = p.parse_args()
    if args.cmd == "export":
        export(args.conditions, args.seed)
    elif args.cmd == "batch-export":
        batch_export(args.conditions, args.seed)
    elif args.cmd == "batch-import":
        if not Path(args.file).exists():
            sys.exit(f"File not found: {args.file}")
        batch_import(args.file, args.condition, args.seed, args.model)
    else:
        if not Path(args.file).exists():
            sys.exit(f"File not found: {args.file}")
        import_replies(args.file)


if __name__ == "__main__":
    main()
