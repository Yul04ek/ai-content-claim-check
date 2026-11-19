# Score judge results against Yuliia's sentence-level labels (lab/labels/test_labels_v1_1.csv; see lab/labels/CHANGES.md).
# Outcome rules (same as the "outcome" column of the Test_Labels sheet):
#   gold "not a claim" or "Supported": judged Supported / not listed -> TN, otherwise FP
#   any other gold verdict:            judged Supported / not listed -> FN, otherwise TP
import csv
import difflib
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "baseline-v1"
LABELS = Path(__file__).resolve().parent / "labels" / "test_labels_v1_1.csv"  # v1.1; the frozen v1 file is in baseline-v1/golden/
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


def judged_verdicts(sentences, golds, rows):
    """Verdict of the judge for every label sentence of one draft (None = not listed = passed).

    A judge claim is matched to a label sentence in two ways: most words of the claim are in the sentence
    (the judge shortened the sentence), or most words of the sentence are in the claim (the judge joined
    several label sentences into one claim, for example because of "so" or "but").
    A flagged claim that covers several label sentences is a hit for the sentences whose gold verdict is not
    Supported; it is a false alarm only when all the sentences it covers are Supported.
    Code findings (quoted text, numbers) go to the sentence that contains them.
    """
    n = len(sentences)
    verdicts = [None] * n

    def add(i, v):
        if verdicts[i] is None or SEVERITY[v] > SEVERITY[verdicts[i]]:
            verdicts[i] = v

    for r in rows:
        if r["kind"] == "claim":
            in_sentence = [coverage(r["text"], s) for s in sentences]
            covered = {j for j in range(n) if coverage(sentences[j], r["text"]) >= MATCH_MIN}
            best = max(in_sentence)
            if best >= MATCH_MIN:
                covered.add(in_sentence.index(best))
            if not covered or r["verdict"] == "Supported":
                continue
            bad = [j for j in covered if golds[j] not in ("Supported", "not a claim")]
            for j in (bad if len(covered) > 1 and bad else covered):
                add(j, r["verdict"])
        elif r["kind"] in ("quote", "number") and r["verdict"]:
            for j in range(n):
                if norm(r["text"]) in norm(sentences[j]):
                    add(j, r["verdict"])
    return verdicts


def score(results_by_case):
    """results_by_case: {"F-003": [row, ...]}, row = {"kind", "text", "verdict"}. Returns (counts, details)."""
    counts, details = Counter(), []
    labels = load_labels()
    for case in dict.fromkeys(l["case"] for l in labels):
        items = [l for l in labels if l["case"] == case]
        sentences = [l["draft sentence / claim"] for l in items]
        golds = [l["gold verdict (proposed)"] for l in items]
        verdicts = judged_verdicts(sentences, golds, results_by_case.get(case, []))
        for lab, gold, v in zip(items, golds, verdicts):
            got = v or "Supported"
            flagged = got != "Supported"
            if gold in ("not a claim", "Supported"):
                outcome = "FP" if flagged else "TN"
            else:
                outcome = "TP" if flagged else "FN"
            counts[outcome] += 1
            details.append({"case": case, "no": lab["no"], "outcome": outcome, "gold": gold, "judged": got,
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
    # Offline self-test: the saved Make results of 29 Oct must give the baseline of the label file (v1.1: TP 4 / FP 2 / FN 3 / TN 33).
    res = {}
    for p in sorted((BASE / "golden" / "judge_output_v1").glob("F-*_claim_check_v1.txt")):
        res[p.name[:5]] = rows_from_check_file(p)
    counts, details = score(res)
    print({k: counts[k] for k in ("TP", "FP", "FN", "TN")})
    for d in details:
        if d["outcome"] != d["expected_outcome"]:
            print("DIFFERENT FROM SHEET:", d)
