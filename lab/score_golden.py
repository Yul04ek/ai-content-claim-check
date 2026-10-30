# Score judge results against Yuliia's sentence-level labels (baseline-v1/golden/test_labels_v1.csv).
# Outcome rules (same as the "outcome" column of the Test_Labels sheet):
#   gold "not a claim" or "Supported": judged Supported / not listed -> TN, otherwise FP
#   any other gold verdict:            judged Supported / not listed -> FN, otherwise TP
import csv
import difflib
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "baseline-v1"
LABELS = BASE / "golden" / "test_labels_v1.csv"
MATCH_MIN = 0.75  # minimum text similarity to treat a judge claim as "this sentence"
SEVERITY = {"Supported": 0, "Needs Human Verification": 1, "Unsupported": 2}


def norm(text):
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[\s\W]+", " ", text).strip().lower()


def tokens(text):
    return norm(text).split()


def coverage(claim, sentence):
    """Share of the claim's words that appear in the sentence (the judge often shortens or splits sentences)."""
    c, s = tokens(claim), set(tokens(sentence))
    return sum(w in s for w in c) / len(c) if c else 0.0


def load_labels():
    with open(LABELS, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def judged_verdict(index, sentences, rows):
    """Worst verdict of the judge claims assigned to sentence `index`.

    Each judge claim is assigned to the sentence it covers best (at least MATCH_MIN of its words).
    Code findings (quoted text, numbers) go to the sentence that contains them.
    """
    verdict = None

    def add(v):
        nonlocal verdict
        if verdict is None or SEVERITY[v] > SEVERITY[verdict]:
            verdict = v

    for r in rows:
        if r["kind"] == "claim":
            scores = [coverage(r["text"], s) for s in sentences]
            best = max(scores)
            if best >= MATCH_MIN and scores.index(best) == index:
                add(r["verdict"])
        elif r["kind"] in ("quote", "number") and r["verdict"] and norm(r["text"]) in norm(sentences[index]):
            add(r["verdict"])
    return verdict or "Supported"  # not listed = passed


def score(results_by_case):
    """results_by_case: {"F-003": [row, ...]}, row = {"kind", "text", "verdict"}. Returns (counts, details)."""
    counts, details = Counter(), []
    labels = load_labels()
    for i, lab in enumerate(labels):
        same = [(j, x) for j, x in enumerate(labels) if x["case"] == lab["case"]]
        sentences = [x["draft sentence / claim"] for _, x in same]
        gold = lab["gold verdict (proposed)"]
        got = judged_verdict(sentences.index(lab["draft sentence / claim"]), sentences,
                             results_by_case.get(lab["case"], []))
        flagged = got != "Supported"
        if gold in ("not a claim", "Supported"):
            outcome = "FP" if flagged else "TN"
        else:
            outcome = "TP" if flagged else "FN"
        counts[outcome] += 1
        details.append({"case": lab["case"], "no": lab["no"], "outcome": outcome, "gold": gold, "judged": got,
                        "expected_outcome": lab["outcome"]})
    return counts, details


def rows_from_check_file(path):
    """Read a saved Make check file (offline test of this scorer)."""
    rows, section = [], None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("Problems"):
            section = "problems"
        elif line.startswith("Supported ("):
            section = "supported"
        elif line.startswith("-----") and section == "supported":
            section = None
        elif line.startswith("- ") and section == "problems":
            head, _, _ = line[2:].partition(" -- ")
            label, _, text = head.partition(": ")
            verdict = {"Unsupported": "Unsupported", "Verify": "Needs Human Verification"}.get(label)
            if verdict is None:
                continue
            kind = "claim"
            m = re.match(r'quoted text "(.*)"$', text)
            if m:
                kind, text = "quote", m.group(1)
            elif text.startswith("number "):
                kind, text = "number", text[7:]
            rows.append({"kind": kind, "text": text, "verdict": verdict})
        elif line.startswith("- ") and section == "supported":
            rows.append({"kind": "claim", "text": line[2:].partition(" -- Record:")[0], "verdict": "Supported"})
    return rows


if __name__ == "__main__":
    # Offline self-test: the saved Make results of 29 Oct must give TP 3 / FP 3 / FN 3 / TN 33.
    res = {}
    for p in sorted((BASE / "golden" / "judge_output_v1").glob("F-*_claim_check_v1.txt")):
        res[p.name[:5]] = rows_from_check_file(p)
    counts, details = score(res)
    print({k: counts[k] for k in ("TP", "FP", "FN", "TN")})
    for d in details:
        if d["outcome"] != d["expected_outcome"]:
            print("DIFFERENT FROM SHEET:", d)
