# Step 5 lab: write new drafts for the five golden records with a drafting prompt, N times, then check them with the
# accepted judge (prompt v2f + Code module v2c). Prints a compact report (no labels needed) and saves everything.
# NOTE: the drafter here is the model from MODEL_NAME / --model (Gemini), not Make's gpt-5-nano. It tests the prompt wording;
# the final check with the real drafter is step 6 (one run in Make).
#
# Usage (env: BASE_URL, API_KEY, MODEL_NAME):
#   python lab/run_draft_lab.py --runs 3 --prompt lab/prompts/draft_prompt_v2.txt
#   python lab/run_draft_lab.py --runs 1 --dry        # no model call: prints the filled prompt of the first record
import argparse
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_judge_lab as L  # noqa: E402

DEFAULT_DRAFT_PROMPT = ROOT / "lab" / "prompts" / "draft_prompt_v2.txt"
JUDGE_PROMPT = ROOT / "lab" / "prompts" / "judge_prompt_v2f.txt"
CODE = ROOT / "lab" / "code" / "make_code_module_v2c.py"
FIELDS = {"0": "ID", "1": "scenario", "2": "observation", "4": "severity", "5": "user impact", "6": "recommendation"}


def fill(prompt, rec):
    for key, col in FIELDS.items():
        prompt = prompt.replace("{{1.`%s`}}" % key, rec[col])
    return prompt


IMPERATIVES = {"fix", "make", "clarify", "keep", "provide", "explain", "add", "show", "tell", "prevent", "ensure", "label", "link",
               "allow", "let", "display", "use", "rename", "move", "improve", "remove", "update", "change", "replace", "document"}


def leading_verbs(recommendation):
    """Action verbs of RECOMMENDATION: the first word of each sentence, if it is a common imperative (rough list)."""
    words = [s.strip().split(" ")[0].lower() for s in re.split(r"[.]\s+|[.]$", recommendation) if s.strip()]
    return [w for w in words if w in IMPERATIVES]


def auto_checks(draft, rec):
    """Deterministic checks of the two things the prompt change is about."""
    body = re.split(r"^-{10,}\s*$", draft, flags=re.M)[-1]
    body = re.sub(r"Suggested topic tags:.*", "", body, flags=re.I)  # the required tag line is allowed
    suggest = len(re.findall(r"\bsuggest\w*", body, flags=re.I))
    we = len(re.findall(r"\bwe\b", body, flags=re.I))
    verbs = {v: (v[:max(3, len(v) - 2)] in body.lower()) for v in leading_verbs(rec["recommendation"])}
    return suggest, we, verbs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--prompt", default=str(DEFAULT_DRAFT_PROMPT), help="drafting prompt file")
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    prompt_path = Path(args.prompt)
    draft_prompt = prompt_path.read_text(encoding="utf-8")
    records = L.load_records()
    cases = sorted(records)
    if args.dry:
        print(fill(draft_prompt, records[cases[0]]))
        return

    from claim_check.config import chat, get_client, get_env
    client, model = get_client(), args.model or get_env("MODEL_NAME")
    L.CODE = CODE.read_text(encoding="utf-8")
    judge_prompt = JUDGE_PROMPT.read_text(encoding="utf-8")
    out_dir = ROOT / "lab" / "drafts" / f"{model}_{prompt_path.stem}_{datetime.date.today().isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = [f"Drafter: {model} | drafting prompt: {prompt_path.name} | judge: {JUDGE_PROMPT.name} + {CODE.name}", ""]
    for k in range(1, args.runs + 1):
        for case in cases:
            rec = records[case]
            print(f"run {k} {case}: writing the draft ...", flush=True)
            reply = chat(client, model=model, messages=[{"role": "user", "content": fill(draft_prompt, rec)}])
            draft = (reply.choices[0].message.content or "").strip()
            (out_dir / f"run{k}_{case}_draft.txt").write_text(draft, encoding="utf-8")
            print(f"run {k} {case}: judging ...", flush=True)
            answer = chat(client, model=model, messages=[{"role": "user", "content": L.build_prompt(rec, draft, judge_prompt)}]).choices[0].message.content or ""
            (out_dir / f"run{k}_{case}_judge_raw.txt").write_text(answer, encoding="utf-8")
            out = L.run_code_module(L.record_text(rec), draft, answer)
            (out_dir / f"run{k}_{case}_check.txt").write_text(out["report_text"], encoding="utf-8")
            suggest, we, verbs = auto_checks(draft, rec)
            lines.append(f"run {k} {case}: {len(draft.split())} words | 'suggest' x{suggest} | 'we' x{we} | "
                         f"record verbs kept: {', '.join(v + (' yes' if ok else ' NO') for v, ok in verbs.items()) or '-'}")
            lines.append(f"   judge+code: {out['overall']}")
            for row in out["report_text"].splitlines():
                if row.startswith(("- Unsupported", "- Verify", "- Style")):
                    lines.append("   " + row[:170])
    text = "\n".join(lines)
    print("\n" + text)
    (out_dir / "report.txt").write_text(text, encoding="utf-8")
    print("\nSaved in", out_dir)
    print("READY: all drafts written and checked.", flush=True)


if __name__ == "__main__":
    main()
