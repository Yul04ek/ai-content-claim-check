# One compact report over all saved lab runs (lab/runs/*): totals per run and every sentence whose outcome
# differs from the Make baseline of 29 Oct. Prints it and saves it as lab/report.txt (send that file, not screenshots).
import glob
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score_golden import load_labels, rows_from_check_file, score  # noqa: E402

CASES = ["F-003", "F-004", "F-005", "F-006", "F-007"]
ROOT = Path(__file__).resolve().parent.parent


def main():
    labels = load_labels()
    out = ["Baseline (Make, 29 Oct): TP 3 / FP 3 / FN 3 / TN 33", ""]
    for folder in sorted(glob.glob(str(ROOT / "lab" / "runs" / "*"))):
        runs = []
        for k in (1, 2, 3, 4, 5):
            try:
                res = {c: rows_from_check_file(f"{folder}/run{k}_{c}_check.txt") for c in CASES}
            except FileNotFoundError:
                break
            runs.append(score(res)[1])
        if not runs:
            continue
        out.append("== " + os.path.basename(folder))
        for k, run in enumerate(runs, 1):
            n = {x: sum(r["outcome"] == x for r in run) for x in ("TP", "FP", "FN", "TN")}
            out.append(f"  run {k}: TP {n['TP']} / FP {n['FP']} / FN {n['FN']} / TN {n['TN']}")
        out.append("  sentences that differ from the baseline (base | outcome per run):")
        shown = False
        for i, lab in enumerate(labels):
            outs = [r[i]["outcome"] for r in runs]
            if any(o != lab["outcome"] for o in outs):
                shown = True
                out.append(f"    {lab['case']} s{lab['no']:>2} | {lab['outcome']} | {' '.join(outs)}  ({lab['draft sentence / claim'][:50]})")
        if not shown:
            out.append("    none")
        out.append("")
    text = "\n".join(out)
    print(text)
    (ROOT / "lab" / "report.txt").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
