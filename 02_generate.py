"""Step 2 - send every problem to ChatGPT in each condition and save the raw replies.

Two ways to reach the ChatGPT models:

  A) Free - GitHub Models (needs a GitHub account; limited requests per day)
    export GITHUB_TOKEN=github_pat_...      (a token with the "models: read" permission)
    python 02_generate.py --provider github --model openai/gpt-4o-mini --samples 0 --limit 5
    python 02_generate.py --provider github --model openai/gpt-4o-mini --samples 0
       -> stops by itself when the daily limit is reached; run the same command the next day
          and it continues where it stopped.

  B) Paid - OpenAI API
    export OPENAI_API_KEY=sk-...
    python 02_generate.py --model <model-name> --limit 5    # small pilot first
    python 02_generate.py --model <model-name>              # full run

  No API at all (tests the pipeline):
    python 02_generate.py --mock

For each problem and condition it stores:
    sample 0      -> temperature 0   (main pass@1 result, and the code-quality analysis)
    samples 1..N  -> temperature 0.8 (used for pass@k; use --samples 0 to skip them)

Everything goes to results/generations.jsonl, one JSON object per reply, including the model
name the API reports and a timestamp - record both in the paper.
The script can be stopped and re-run at any time; finished replies are skipped.
"""
import argparse
import datetime as dt
import os
import sys
import time

from common import (CONDITIONS, GENERATIONS, RESULTS, SYSTEM_PROMPT, TRANSLATE_PROMPT,
                    append_jsonl, build_prompt, load_problems, read_jsonl)

TRANSLATIONS = RESULTS / "translations.jsonl"
PROVIDERS = {
    # name: (chat-completions URL, environment variable holding the key)
    "openai": ("https://api.openai.com/v1/chat/completions", "OPENAI_API_KEY"),
    "github": ("https://models.github.ai/inference/chat/completions", "GITHUB_TOKEN"),
}


class LimitReached(Exception):
    """The provider's daily quota is used up; stop cleanly and resume later."""


class ChatGPT:
    """Talks to an OpenAI-compatible chat-completions endpoint with plain HTTP requests."""

    def __init__(self, model, seed, provider="openai", delay=0.0):
        import requests  # imported here so --mock works without it
        self.requests = requests
        self.url, key_var = PROVIDERS[provider]
        key = (os.environ.get(key_var) or "").strip()  # pasted keys often carry a trailing newline
        if not key:
            sys.exit(f"Set the {key_var} environment variable first.")
        self.headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        self.model, self.seed, self.delay = model, seed, delay
        self.unsupported = set()  # parameters the model rejected (temperature / seed)

    def ask(self, messages, temperature):
        """Returns (reply_text, reported_model, finish_reason, temperature_used)."""
        for attempt in range(6):
            body = {"model": self.model, "messages": messages}
            if "seed" not in self.unsupported:
                body["seed"] = self.seed
            if "temperature" not in self.unsupported:
                body["temperature"] = temperature
            if self.delay:
                time.sleep(self.delay)
            try:
                r = self.requests.post(self.url, headers=self.headers, json=body, timeout=120)
            except self.requests.RequestException as e:
                wait = 2 ** attempt * 5
                print(f"  ! connection problem ({type(e).__name__}); retrying in {wait}s")
                time.sleep(wait)
                continue
            text = r.text
            if r.status_code == 200:
                try:
                    data = r.json()
                    choice = data["choices"][0]
                except (ValueError, KeyError, IndexError):
                    raise RuntimeError(f"unexpected reply from the server: {text[:300]}")
                used = None if "temperature" in self.unsupported else temperature
                return ((choice.get("message") or {}).get("content") or "",
                        data.get("model", ""), choice.get("finish_reason", ""), used)
            if r.status_code in (401, 403):
                sys.exit(f"The server refused the key ({r.status_code}): {text[:300]}\n"
                         "Check that the key is complete and has the 'Models: read' permission.")
            if r.status_code == 400:
                bad = next((p for p in ("temperature", "seed")
                            if p in text.lower() and p not in self.unsupported), None)
                if bad:
                    print(f"  ! this model does not accept '{bad}' - continuing without it; "
                          "note this in the paper")
                    self.unsupported.add(bad)
                    continue
                raise RuntimeError(f"request rejected (400): {text[:300]}")
            if r.status_code == 429:
                try:
                    retry_after = int(float(r.headers.get("retry-after", 0)))
                except ValueError:
                    retry_after = 0
                low = text.lower()
                if retry_after > 300 or "per day" in low or "daily" in low or "86400" in low:
                    raise LimitReached(text[:200])
                wait = max(retry_after, 2 ** attempt * 5)
                print(f"  ! rate limit; waiting {wait}s")
                time.sleep(wait)
                continue
            wait = 2 ** attempt * 5  # 5xx and anything else: try again
            print(f"  ! server error {r.status_code}; retrying in {wait}s")
            time.sleep(wait)
        raise RuntimeError("API kept failing after 6 attempts")


class Mock:
    """Answers with the reference solution, so the evaluation steps can be tested for free."""
    model = "mock-canonical-solution"

    def __init__(self, problems):
        self.current = None  # set by the main loop to the problem being asked

    def ask(self, messages, temperature):
        text = messages[-1]["content"]
        if text.startswith("Translate the following"):
            return "(mock translation) " + text.split("\n\n", 1)[1][:200], self.model, "stop", temperature
        code = text + self.current["_en"]["canonical_solution"]
        return f"```python\n{code}\n```", self.model, "stop", temperature


def done_keys():
    if not GENERATIONS.exists():
        return set()
    # Failed requests are not "done", so re-running the script retries them.
    return {(r["task_id"], r["condition"], r["sample_id"])
            for r in read_jsonl(GENERATIONS) if not r["error"]}


def get_translation(llm, problem, cache):
    tid = problem["task_id"]
    if tid not in cache:
        msg = [{"role": "user", "content": TRANSLATE_PROMPT.format(text=problem["iraqi_description"])}]
        text, reported, _, _ = llm.ask(msg, 0.0)
        cache[tid] = text
        append_jsonl(TRANSLATIONS, {"task_id": tid, "iraqi": problem["iraqi_description"],
                                     "english_translation": text, "model_reported": reported})
    return cache[tid]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", help="model name, e.g. openai/gpt-4o-mini on GitHub Models")
    p.add_argument("--provider", choices=list(PROVIDERS), default="openai",
                   help="openai (paid API) or github (free GitHub Models)")
    p.add_argument("--samples", type=int, default=5, help="extra samples per prompt for pass@k (default 5)")
    p.add_argument("--temperature", type=float, default=0.8, help="temperature of the extra samples")
    p.add_argument("--seed", type=int, default=2026, help="API seed (best effort reproducibility)")
    p.add_argument("--conditions", nargs="+", default=CONDITIONS, choices=CONDITIONS)
    p.add_argument("--limit", type=int, help="only the first N problems (pilot run)")
    p.add_argument("--max-requests", type=int, help="stop after this many requests in this run")
    p.add_argument("--delay", type=float, help="seconds between requests "
                   "(default 4.5 for github to stay under 15 per minute, 0 for openai)")
    p.add_argument("--mock", action="store_true", help="no API calls; use reference solutions")
    args = p.parse_args()
    if not args.mock and not args.model:
        p.error("--model is required (or use --mock to test without the API)")
    delay = args.delay if args.delay is not None else (4.5 if args.provider == "github" else 0.0)

    problems = load_problems()[: args.limit]
    llm = Mock(problems) if args.mock else ChatGPT(args.model, args.seed, args.provider, delay)
    requested_model = llm.model
    done = done_keys()
    cache = {r["task_id"]: r["english_translation"] for r in read_jsonl(TRANSLATIONS)} \
        if TRANSLATIONS.exists() else {}

    jobs = []
    for prob in problems:
        for cond in args.conditions:
            if cond.startswith("iraqi") and not prob["iraqi_description"].strip():
                continue
            for sid in range(args.samples + 1):
                if (prob["task_id"], cond, sid) not in done:
                    jobs.append((prob, cond, sid))
    skipped = sum(1 for pr in problems if not pr["iraqi_description"].strip())
    if skipped and any(c.startswith("iraqi") for c in args.conditions):
        print(f"Note: {skipped} problems have no Iraqi text yet and are skipped for the Iraqi conditions.")
    print(f"{len(jobs)} replies to request ({len(done)} already saved). Model: {requested_model}")

    sent = 0
    for i, (prob, cond, sid) in enumerate(jobs, 1):
        if args.max_requests and sent >= args.max_requests:
            print(f"Reached --max-requests {args.max_requests}. Run again to continue.")
            break
        if args.mock:
            llm.current = prob
        try:
            if cond == "iraqi_translated" and prob["task_id"] not in cache:
                sent += 1
            translated = get_translation(llm, prob, cache) if cond == "iraqi_translated" else None
        except LimitReached as e:
            print(f"\nDaily limit reached ({e}).\nEverything so far is saved. "
                  "Run the same command again tomorrow to continue.")
            break
        prompt = build_prompt(prob, cond, translated)
        temperature = 0.0 if sid == 0 else args.temperature
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}]
        sent += 1
        try:
            reply, reported, finish, used_t = llm.ask(messages, temperature)
            error = ""
        except LimitReached as e:
            print(f"\nDaily limit reached ({e}).\nEverything so far is saved. "
                  "Run the same command again tomorrow to continue.")
            break
        except Exception as e:  # keep going; the failure is recorded and can be retried
            reply, reported, finish, used_t, error = "", "", "", temperature, repr(e)
        append_jsonl(GENERATIONS, {
            "task_id": prob["task_id"], "entry_point": prob["entry_point"], "condition": cond,
            "sample_id": sid, "temperature": used_t, "model_requested": requested_model,
            "model_reported": reported, "finish_reason": finish,
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "prompt": prompt, "reply": reply, "error": error,
        })
        if error:
            print(f"  ! {prob['task_id']} {cond} #{sid}: {error[:120]}")
        if i % 20 == 0 or i == len(jobs):
            print(f"  {i}/{len(jobs)} done")

    missing = {(pr["task_id"], c, s) for pr, c, s in jobs} - done_keys()
    if missing:
        print(f"{len(missing)} replies still missing. Run the same command again to get them.")
    else:
        print("All replies saved. Next: python 03_evaluate.py")


if __name__ == "__main__":
    main()
