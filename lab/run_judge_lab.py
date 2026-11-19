# Lab run of the Make judge (baseline v1) on the five golden drafts, N times, scored against the labels.
# Uses the EXACT Make judge prompt and the EXACT Make Code module from baseline-v1/, so a result that differs
# from 3/3/3/33 comes from the model (or its randomness), not from a changed prompt.
#
# Usage (env: BASE_URL, API_KEY, MODEL_NAME as in claim_check/config.py):
#   python lab/run_judge_lab.py --runs 3
#   python lab/run_judge_lab.py --runs 3 --model gemini-3.5-flash-lite   # another model, saved in its own folder
#   python lab/run_judge_lab.py --runs 3 --prompt lab/prompts/judge_prompt_v2a.txt   # a changed prompt
#   python lab/run_judge_lab.py --runs 1 --dry     # no model call: prints the prompt of the first case
import argparse
import csv
import datetime
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from score_golden import BASE, score  # noqa: E402

DEFAULT_PROMPT = BASE / "prompts" / "judge_prompt_v1.txt"  # the Make prompt of baseline v1
DEFAULT_CODE = BASE / "code" / "make_code_module_v1.py"  # the Make Code module of baseline v1
CODE = DEFAULT_CODE.read_text(encoding="utf-8")
FIELDS = {"1": "scenario", "2": "observation", "4": "severity", "5": "user impact", "6": "recommendation"}


def load_records():
    with open(BASE / "golden" / "records_v1.csv", encoding="utf-8") as f:
        return {r["ID"]: r for r in csv.DictReader(f)}


def record_text(rec):
    """The same five-line block that Make builds for the Code module (input 'record')."""
    return "\n".join(f"{name.upper()}: {rec[col]}" for name, col in (
        ("scenario", "scenario"), ("observation", "observation"), ("severity", "severity"),
        ("user impact", "user impact"), ("recommendation", "recommendation")))


def draft_body(case):
    """The draft without the document header (Make passes only the model answer, {{3.answer}})."""
    text = (BASE / "golden" / "drafts" / f"{case}_draft_v1.txt").read_text(encoding="utf-8")
    parts = re.split(r"^-{10,}\s*$", text, flags=re.M)
    return parts[-1].strip() if len(parts) > 1 else text.strip()


def build_prompt(rec, draft, prompt):
    text = prompt
    for key, col in FIELDS.items():
        text = text.replace("{{1.`%s`}}" % key, rec[col])
    return text.replace("{{3.answer}}", draft)


def run_code_module(record, draft, judge_answer):
    """Run the Make Python module. Make runs it as a function body, so wrap it the same way."""
    src = "def _run(input):\n" + "\n".join("    " + line for line in CODE.splitlines())
    scope = {}
    exec(compile(src, "make_code_module_v1.py", "exec"), scope)
    return scope["_run"]({"record": record, "draft": draft, "judge_answer": judge_answer})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--prompt", default=str(DEFAULT_PROMPT), help="judge prompt file (default: baseline v1)")
    ap.add_argument("--code", default=str(DEFAULT_CODE), help="Code module file (default: baseline v1)")
    ap.add_argument("--model", default=None, help="model name; default: MODEL_NAME from the environment")
    args = ap.parse_args()
    global CODE
    CODE = Path(args.code).read_text(encoding="utf-8")

    prompt_path = Path(args.prompt)
    prompt = prompt_path.read_text(encoding="utf-8")
    records = load_records()
    cases = sorted(records)
    if args.dry:
        print(build_prompt(records[cases[0]], draft_body(cases[0]), prompt))
        return

    from claim_check.config import chat, get_client, get_env
    client, model = get_client(), args.model or get_env("MODEL_NAME")
    tag = "" if prompt_path.resolve() == DEFAULT_PROMPT.resolve() else prompt_path.stem + "_"  # keep v1 folder names unchanged
    if Path(args.code).resolve() != DEFAULT_CODE.resolve():
        tag += Path(args.code).stem + "_"  # a changed Code module gets its own folder too
    stamp = f"{model}_{tag}{datetime.date.today().isoformat()}"
    out_dir = ROOT / "lab" / "runs" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    per_run, flips = [], {}
    for k in range(1, args.runs + 1):
        results = {}
        for case in cases:
            rec, draft = records[case], draft_body(case)
            print(f"run {k} {case}: asking {model} ...", flush=True)  # progress line before the (slow) model call
            reply = chat(client, model=model, messages=[{"role": "user", "content": build_prompt(rec, draft, prompt)}])
            answer = reply.choices[0].message.content or ""
            (out_dir / f"run{k}_{case}_judge_raw.txt").write_text(answer, encoding="utf-8")  # raw JSON, kept as evidence
            out = run_code_module(record_text(rec), draft, answer)
            (out_dir / f"run{k}_{case}_check.txt").write_text(out["report_text"], encoding="utf-8")
            results[case] = out["rows"]
            print(f"run {k} {case}: {out['overall']}", flush=True)
        counts, details = score(results)
        per_run.append(counts)
        for d in details:
            flips.setdefault((d["case"], d["no"]), []).append(d["outcome"])
        print(f"run {k}: TP {counts['TP']} / FP {counts['FP']} / FN {counts['FN']} / TN {counts['TN']}")

    print("\nSentences whose outcome changed between runs (= judge instability):")
    for (case, no), outs in flips.items():
        if len(set(outs)) > 1:
            print(f"  {case} sentence {no}: {' / '.join(outs)}")
    (out_dir / "summary.json").write_text(json.dumps(
        [{k: c[k] for k in ("TP", "FP", "FN", "TN")} for c in per_run], indent=1), encoding="utf-8")
    print("Saved in", out_dir)
    print("READY: all runs finished.", flush=True)


if __name__ == "__main__":
    main()
