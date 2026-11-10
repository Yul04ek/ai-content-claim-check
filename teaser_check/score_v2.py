# Scoring against the gold standard v2 (sentence by sentence, marked by hand). No model call.
#
# gold_v2.json (next to lab_set.json, OUTSIDE the repository, it holds real company text):
#   {"B": {"title": "...", "whole": [["B7", "514 words, limit 450", "code"]],
#          "rows": [{"part", "text", "type", "verdict", "by", "err", "prob", "note"}, ...]}, ...}
# type: statement / heading / template / instruction / self-certification / source note / header
# verdict (statements only): Supported / Unsupported / Needs human; everything else is "not a claim"
# by: judge / code / both (who should find it); prob: "error", "disputed" or ""
#
# The statistics are given per teaser. Only the judge's own answer counts (finding != "supported" is a flag);
# what our code changes afterwards (quote check, coverage rows) is not counted for the judge.

import json
import re
from pathlib import Path
from statistics import mean

STOP = set("a an the of to and or in on for with by is are as at be it its that this from into than".split())


def load_gold(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def toks(text: str) -> set[str]:
    """The words of a text without the words in square brackets (citation tags, placeholders). A text that is
    nothing but a bracket (the model's own made-up placeholder) keeps its words, or it could never be matched."""
    text = (text or "").lower()
    found = {w for w in re.findall(r"[a-z0-9$%+]+", re.sub(r"\[[^\]]*\]", " ", text)) if w not in STOP}
    return found or {w for w in re.findall(r"[a-z0-9$%+]+", text) if w not in STOP}


def touches(judge: set, gold: set) -> bool:
    """A judge row covers a gold sentence: it holds most of its words, or it lies almost completely inside it."""
    if not judge or not gold:
        return False
    inter = len(judge & gold)
    return inter / len(gold) >= 0.7 or inter / len(judge) >= 0.8


def score_judge(gold_case: dict, rows: list[dict]) -> dict:
    gold = gold_case["rows"]
    gold_toks = [toks(g["text"]) for g in gold]
    seen, flagged = set(), set()
    false_flags = nonclaim_flags = unmatched = hyp_unlabelled = 0
    for r in rows:
        if r.get("kind") != "claim":
            continue
        words = toks(r.get("text", ""))
        hit = [i for i, g in enumerate(gold_toks) if touches(words, g)]
        is_flag = r.get("finding") != "supported"
        hyp_unlabelled += r.get("finding") == "hypothesis_unlabelled"
        seen.update(hit)
        if not is_flag:
            continue
        flagged.update(hit)
        if not hit:
            unmatched += 1
        elif all(gold[i]["type"] != "statement" for i in hit):
            nonclaim_flags += 1
        elif all(gold[i]["verdict"] == "Supported" for i in hit if gold[i]["type"] == "statement"):
            false_flags += 1
    meant = [i for i, g in enumerate(gold) if g["type"] == "statement" and g["by"] in ("judge", "both")]
    errors = [i for i in meant if gold[i]["verdict"] == "Unsupported"]
    read = [i for i in meant if i in seen]
    decided = [i for i in read if gold[i]["verdict"] != "Needs human"]
    right = [i for i in decided if (gold[i]["verdict"] == "Unsupported") == (i in flagged)]
    found = [i for i in errors if i in flagged]
    return {"meant": len(meant), "read": len(read), "errors": len(errors), "found": len(found),
            "decided": len(decided), "right": len(right), "false_flags": false_flags,
            "nonclaim_flags": nonclaim_flags, "unmatched": unmatched, "hyp_unlabelled": hyp_unlabelled,
            "found_idx": found, "error_idx": errors, "missed": [gold[i]["text"][:80] for i in errors if i not in flagged]}


def whole_found(item: str, code_texts: list[str]) -> int:
    """Did a code row report this whole-teaser item? Matched by the kind of rule: length ("514 words"), source notes
    that miss a source ("source notes: S3 ..."), the entry offer not first ("first offer")."""
    item = item.lower()
    if "words" in item:
        return int(any(re.search(r"\d+ words", t) for t in code_texts))
    if "source notes" in item:
        return int(any(t.startswith("source notes") for t in code_texts))
    if "first offer" in item:
        return int("first offer" in code_texts)
    return 0


def score_code(gold_case: dict, rows: list[dict]) -> dict:
    """Which gold problems for the code (by code or both, not statements for the judge) did the code rules find."""
    gold = gold_case["rows"]
    gold_toks = [toks(g["text"]) for g in gold]
    hit, code_texts = set(), []
    for r in rows:
        if r.get("kind") not in ("rule", "offer", "flag"):
            continue
        text = str(r.get("text", ""))
        code_texts.append(text.lower())
        if re.search(r"\d+ words", text):
            continue
        elif text.lower().startswith("source notes"):
            hit.update(i for i, g in enumerate(gold) if g["part"] == "Source notes" and g["type"] == "heading")
        elif r.get("kind") == "offer":
            hit.update(i for i, g in enumerate(gold) if text.lower() in g["text"].lower() and g["prob"] == "error")
        else:
            words = toks(text)
            hit.update(i for i, g in enumerate(gold_toks) if touches(words, g))
    own = [i for i, g in enumerate(gold) if g["prob"] == "error" and g["by"] in ("code", "both")
           and (g["type"] != "statement" or g["by"] == "code")]
    whole = gold_case.get("whole", [])
    return {"code_n": len(own) + len(whole), "code_found": len([i for i in own if i in hit]) + sum(whole_found(w[1], code_texts) for w in whole),
            "code_missed": [gold[i]["text"][:70] for i in own if i not in hit]}


def score_case_v2(gold_case: dict, rows: list[dict]) -> dict:
    return {**score_judge(gold_case, rows), **score_code(gold_case, rows)}


def _rng(values: list) -> str:
    return f"{mean(values):.1f}" + (f" ({min(values)}-{max(values)})" if min(values) != max(values) else "")


def format_table(case: str, title: str, by_rubric: dict[str, list[dict]]) -> str:
    """One teaser, one line per rubric: averages over the repeats, in brackets the smallest and largest value."""
    first = next(iter(by_rubric.values()))[0]
    lines = [f"Teaser {title}: the judge is given {first['meant']} statements, {first['errors']} of them are errors; "
             f"the code should find {first['code_n']} problems"]
    head = f"  {'rubric':<10} {'runs':>4}  {'read':>11}  {'errors found':>13}  {'false flags':>11}  {'right verdicts':>16}  {'code found':>10}"
    lines.append(head)
    for rubric, runs in by_rubric.items():
        lines.append(f"  {rubric:<10} {len(runs):>4}  {_rng([r['read'] for r in runs]):>11}  {_rng([r['found'] for r in runs]):>13}  "
                     f"{_rng([r['false_flags'] for r in runs]):>11}  "
                     f"{_rng([r['right'] for r in runs]):>8} of {mean(r['decided'] for r in runs):>4.1f}  "
                     f"{_rng([r['code_found'] for r in runs]):>10}")
    return "\n".join(lines)


def score_run_dir(gold: dict, run_dir) -> dict:
    """Re-score a saved run folder (one CSV per case). Used for old runs: python -m teaser_check.score_v2 gold_v2.json <runs>"""
    import csv
    out = {}
    for case, gold_case in gold.items():
        path = Path(run_dir) / f"{case}.csv"
        if path.exists():
            with open(path, encoding="utf-8-sig", newline="") as f:
                out[case] = score_case_v2(gold_case, list(csv.DictReader(f)))
    return out


def main() -> None:
    import argparse
    from collections import defaultdict
    p = argparse.ArgumentParser(description="Score saved experiment runs against gold standard v2 (no model call).")
    p.add_argument("gold")
    p.add_argument("runs", help="the folder 'experiment_runs' with one folder per run")
    p.add_argument("--after", default="00-00-00", help="skip run folders stamped earlier than HH-MM-SS")
    args = p.parse_args()
    gold = load_gold(args.gold)
    table = defaultdict(lambda: defaultdict(list))  # case -> rubric -> [scores]
    for folder in sorted(Path(args.runs).iterdir()):
        m = re.match(r"\d{4}-\d\d-\d\d_(\d\d-\d\d-\d\d)_(.+)_(gemini-[\w.\-]+)_r\d+$", folder.name)
        if not m or m.group(1) < args.after:
            continue
        label = "t1" if m.group(2) == "teaser-judge" else m.group(2)
        if m.group(3) != "gemini-3.1-flash-lite":  # the same rubric on another model is a different line of the table
            label += "@" + m.group(3).removeprefix("gemini-")
        for case, s in score_run_dir(gold, folder).items():
            table[case][label].append(s)
    for case in gold:
        if table[case]:
            print(format_table(case, gold[case].get("title", case), table[case]), "\n")


if __name__ == "__main__":
    main()
