"""Company need and Hypothesis sentences: what the judge said in every repeat (finding / link to the sources).

Shows at a glance whether the verdict flips between repeats and whether the link rating (field basis)
separates the sentences the gold marks as errors from the hedged ones.
  python -m teaser_check.basis_report gold_v3.json results/experiment_runs --rubric n2 [--out table.csv]
"""
import argparse
import csv
import json
from pathlib import Path

from .score_v2 import toks, touches

SHORT = {"supported": "ok", "not_in_pack": "no-src", "assumption_as_fact": "assumed", "aura_offer_unverified": "offer?",
         "promise": "promise", "contradicted": "contra", "overgeneralised": "stretch", "meaning_shifted": "shifted",
         "hypothesis_without_fact": "no-fact"}


def collect(gold: dict, run_dir, rubric: str) -> list[dict]:
    """One dict per gold sentence of a need/hypothesis line: gold verdict and the answer of every repeat."""
    runs = sorted(Path(run_dir).glob(f"*_{rubric}_*_r*"))
    out = []
    for case, g in gold.items():
        rows = g["rows"]
        for i, r in enumerate(rows):
            part = r.get("part", "")
            if r.get("type") != "statement" or not ("Company need" in part or "Hypothesis" in part):
                continue
            gt = toks(r["text"])
            answers = []
            for run in runs:
                file = run / f"{case}.csv"
                if not file.exists():
                    continue
                hits = [x for x in csv.DictReader(open(file, encoding="utf-8-sig"))
                        if x.get("kind") == "claim" and touches(toks(x["text"]), gt)]
                if not hits:
                    answers.append("not read")
                    continue
                worst = max(hits, key=lambda x: x.get("finding") != "supported")
                answers.append(f'{SHORT.get(worst["finding"], worst["finding"])}/{worst.get("basis") or "-"}')
            out.append({"case": case, "part": part.split("/")[-1], "gold": r.get("verdict", ""), "text": r["text"][:70],
                        "answers": answers})
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Need and hypothesis sentences across repeats.")
    p.add_argument("gold")
    p.add_argument("run_dir")
    p.add_argument("--rubric", default="n2", help="rubric name in the run folder names (default n2)")
    p.add_argument("--out", help="also write a CSV")
    a = p.parse_args()
    rows = collect(json.loads(Path(a.gold).read_text(encoding="utf-8")), a.run_dir, a.rubric)
    print(f"{'teaser':6} {'gold':12} {'part':13} {'sentence':70}  finding/link in every repeat")
    for r in rows:
        print(f"{r['case']:6} {r['gold'][:12]:12} {r['part'][:13]:13} {r['text']:70}  " + "  ".join(r["answers"]))
    if a.out:
        with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["teaser", "gold", "part", "sentence", "answers per repeat"])
            for r in rows:
                w.writerow([r["case"], r["gold"], r["part"], r["text"], " | ".join(r["answers"])])


if __name__ == "__main__":
    main()
