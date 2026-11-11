"""A third, independent signal: how strongly the saved sources ENTAIL each statement the judge looked at.

A small NLI model (premise + statement -> entailment / neutral / contradiction) runs locally on your Colab:
no data leaves, and it is not an LLM, so it is not the family of the judge. The number is an extra column;
it changes no verdict. Not tested with a real model here (no network in the sandbox): the logic is tested with a fake.

  python -m teaser_check.nli_score gold_v3.json results/experiment_runs --lab lab_set.json --rubric n2 --out nli.csv
Speed: a statement is compared only with the 8 pieces that share most words with it (--top-k 0 = all pieces), and the same
statement in several repeats is scored once. On a CPU this takes a few minutes; with a GPU runtime (Runtime > Change runtime type) seconds.

Second mode, --pairs: no judge runs needed. For every offer block of the teaser the premise is the teaser's own Evidence quote plus
the Purpose and Features of the offer named in the block; the statements are the Company need and the Hypothesis of that block.
Three numbers per statement (11 Nov): vs the Evidence alone (nli_evidence), vs the offer alone (nli_offer), vs both together
(nli_entailment). Only the entailment number is used; contradiction is noise on texts that are close in topic but unrelated.
  python -m teaser_check.nli_score gold_v3.json --lab lab_set.json --pairs --out nli_pairs.csv

Needs: pip install transformers torch   (Colab has torch). Default model: cross-encoder/nli-deberta-v3-base.
Statements are compared with chunks of the sources (S1..) and the approved offers (O1..); the best chunk counts.
"""
import argparse
import csv
import json
import re
from pathlib import Path

from .deterministic import offer_blocks, split_teaser
from .pack import load_pack
from .score_v2 import toks, touches

DEFAULT_MODEL = "cross-encoder/nli-deberta-v3-base"


def chunks(pack: dict, size: int = 110, step: int = 70) -> list[tuple[str, str]]:
    """(id, text) pieces of about `size` words with overlap: the NLI model reads a short premise only."""
    out = []
    for s in pack.get("sources", []):
        words = (s.get("excerpt") or "").split()
        for i in range(0, max(1, len(words)), step):
            piece = " ".join(words[i:i + size])
            if piece:
                out.append((s["id"], piece))
            if i + size >= len(words):
                break
    for o in pack.get("approved_aura_offers", []):
        out.append((o["id"], f'{o["name"]}. {o.get("purpose", "")} Features: {o.get("features", "")}'.strip()))
    return out


def top_pieces(statement: str, pieces: list[tuple[str, str]], k: int | None) -> list[tuple[str, str]]:
    """The k pieces that share most words with the statement (a rough pre-selection: the NLI model is slow on a CPU).
    The model then picks the best of these. k=None keeps all pieces."""
    if not k or len(pieces) <= k:
        return pieces
    words = toks(statement)
    return sorted(pieces, key=lambda p: -len(words & toks(p[1])))[:k]


def best_entailment(statement: str, pieces: list[tuple[str, str]], scorer, top_k: int | None = None) -> dict:
    """The piece that entails the statement most. scorer(premise, statement) -> {'entailment': p, 'contradiction': p, ...}."""
    best = {"entailment": 0.0, "contradiction": 0.0, "source": ""}
    for source_id, text in top_pieces(statement, pieces, top_k):
        got = scorer(text, statement)
        if got["entailment"] >= best["entailment"]:
            best = {"entailment": got["entailment"], "contradiction": got.get("contradiction", 0.0), "source": source_id}
    return best


def hf_scorer(model_name: str = DEFAULT_MODEL):
    """The real scorer (Hugging Face transformers); imported only here so the tests need no package."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    device = "cuda" if torch.cuda.is_available() else "cpu"  # a GPU runtime in Colab makes this about 20 times faster
    print("NLI model on", device)
    tok = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name).to(device).eval()
    labels = {int(i): name.lower() for i, name in model.config.id2label.items()}

    def score(premise: str, statement: str) -> dict:
        batch = tok(premise, statement, truncation=True, max_length=512, return_tensors="pt").to(device)
        with torch.no_grad():
            probs = torch.softmax(model(**batch).logits[0], dim=-1).tolist()
        return {labels[i]: p for i, p in enumerate(probs)}
    return score


def score_run(gold: dict, run_dir, lab_file, rubric: str, scorer, top_k: int | None = 8) -> list[dict]:
    """One line per judged statement in every run folder of the rubric: gold verdict, judge finding, basis, NLI."""
    lab = json.loads(Path(lab_file).read_text(encoding="utf-8"))
    base = Path(lab_file).parent
    out = []
    for case in lab["cases"]:
        name = case["case"]
        pieces = chunks(load_pack(base / case["pack"]))
        gold_rows = [r for r in gold.get(name, {}).get("rows", []) if r.get("type") == "statement"]
        gt = [toks(r["text"]) for r in gold_rows]
        done: dict[str, dict] = {}  # the same statement in another repeat is scored only once
        for run in sorted(Path(run_dir).glob(f"*_{rubric}_*_r*")):
            file = run / f"{name}.csv"
            if not file.exists():
                continue
            for r in csv.DictReader(open(file, encoding="utf-8-sig")):
                if r.get("kind") != "claim":
                    continue
                hit = [i for i, g in enumerate(gt) if touches(toks(r["text"]), g)]
                if r["text"] not in done:
                    done[r["text"]] = best_entailment(r["text"], pieces, scorer, top_k)
                    print(f"  {name}: {len(done)} statements scored", flush=True)
                got = done[r["text"]]
                out.append({"run": run.name, "case": name, "part": gold_rows[hit[0]]["part"].split("/")[-1] if hit else "",
                            "gold": gold_rows[hit[0]]["verdict"] if hit else "", "judge": r.get("finding", ""),
                            "basis": r.get("basis", ""), "nli_entailment": round(got["entailment"], 3),
                            "nli_contradiction": round(got["contradiction"], 3), "best_source": got["source"],
                            "statement": r["text"][:90]})
    return out


def offer_for_block(block: dict, pack: dict) -> dict | None:
    """The approved offer a block is about, found from its Offer line."""
    line = (block.get("offer") or "").lower()
    for o in pack.get("approved_aura_offers", []):
        if o["name"].lower() in line or (o.get("offer_line") or "").lower() == line:
            return o
    return None


def score_pairs(gold: dict, lab_file, scorer) -> list[dict]:
    """Per offer block: does Evidence + offer entail the Company need? the Hypothesis? (no judge runs needed)"""
    lab = json.loads(Path(lab_file).read_text(encoding="utf-8"))
    base = Path(lab_file).parent
    out = []
    for case in lab["cases"]:
        name = case["case"]
        pack = load_pack(base / case["pack"])
        body, _ = split_teaser((base / case["teaser"]).read_text(encoding="utf-8"))
        gold_rows = [r for r in gold.get(name, {}).get("rows", []) if r.get("type") == "statement"]
        gt = [toks(r["text"]) for r in gold_rows]
        for n, block in enumerate(offer_blocks(body), 1):
            offer = offer_for_block(block, pack)
            evidence = re.sub(r'^["\u201c]|["\u201d]$', "", (block.get("evidence") or "").strip())
            if not offer or not evidence:
                continue  # no pair to test: the code checks a missing Evidence line elsewhere
            offer_text = f'AURA offer {offer["name"]}: {offer.get("purpose", "")} Features: {offer.get("features", "")}'
            both = f"{evidence} {offer_text}"   # the two sources together (the cross signal)
            for part, key in (("Company need", "company need"), ("Hypothesis", "hypothesis")):
                text = block.get(key) or ""
                if not text:
                    continue
                hit = [i for i, g in enumerate(gt) if touches(toks(text), g) and part in gold_rows[i]["part"]]
                statement = re.sub(r"^\w+:\s*", "", text)
                # The same statement against each source alone and against both together:
                #   high only vs the evidence -> rests on the company's own words
                #   high only vs the offer    -> probably re-written from the offer
                #   high only vs both         -> the link needs the two sources
                #   low everywhere            -> not supported by either
                got = scorer(both, statement)
                ent = scorer(evidence, statement)["entailment"]
                off = scorer(offer_text, statement)["entailment"]
                out.append({"case": name, "block": n, "offer": offer["name"], "part": part,
                            "gold": gold_rows[hit[0]]["verdict"] if hit else "",
                            "nli_entailment": round(got["entailment"], 3), "nli_contradiction": round(got.get("contradiction", 0.0), 3),
                            "nli_evidence": round(ent, 3), "nli_offer": round(off, 3),
                            "evidence": evidence[:80], "statement": text[:90]})
    return out


def summary(rows: list[dict]) -> str:
    """Average NLI entailment per gold verdict: do the real errors score lower than the supported statements?"""
    lines = []
    for part in ("Snapshot", "Company need", "How AURA helps", "Hypothesis"):
        for gold in ("Supported", "Needs human", "Unsupported"):
            vals = [r["nli_entailment"] for r in rows if r["part"] == part and r["gold"] == gold]
            if vals:
                lines.append(f"{part:15} gold {gold:12} n={len(vals):3}  mean entailment {sum(vals) / len(vals):.2f}  (min {min(vals):.2f}, max {max(vals):.2f})")
    return "\n".join(lines)


def write_rows(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["case"])
        w.writeheader()
        w.writerows(rows)
    print("written:", path)


def main() -> None:
    p = argparse.ArgumentParser(description="NLI entailment of the judged statements (an extra signal, no verdict).")
    p.add_argument("gold")
    p.add_argument("run_dir", nargs="?", help="folder with the run folders (not needed with --pairs)")
    p.add_argument("--lab", required=True, help="lab_set.json")
    p.add_argument("--pairs", action="store_true", help="test Evidence + offer against the Company need and the Hypothesis of every block")
    p.add_argument("--rubric", default="n2")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--top-k", type=int, default=8, help="compare a statement with the k most similar pieces (0 = all)")
    p.add_argument("--out", default="nli_scores.csv")
    a = p.parse_args()
    gold = json.loads(Path(a.gold).read_text(encoding="utf-8"))
    if a.pairs:
        rows = score_pairs(gold, a.lab, hf_scorer(a.model))
        for r in rows:
            print(f"{r['case']} block {r['block']} {r['part']:13} gold {r['gold'][:11]:11} "
                  f"evidence {r['nli_evidence']:.2f}  offer {r['nli_offer']:.2f}  both {r['nli_entailment']:.2f}  {r['statement'][:50]}")
        write_rows(rows, a.out)
        return
    if not a.run_dir:
        p.error("run_dir is needed without --pairs")
    rows = score_run(gold, a.run_dir, a.lab, a.rubric, hf_scorer(a.model), a.top_k or None)
    write_rows(rows, a.out)
    print(summary(rows))


if __name__ == "__main__":
    main()
