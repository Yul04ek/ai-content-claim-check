# Re-run the code layers over a SAVED judge answer: no model call, no tokens.
# Use it to try a new code rule on an old run, and to see what the rule changes.
# Usage: python -m teaser_check.replay pack.json teaser.txt saved_results.csv --out new_results.csv

import argparse
import csv

from claim_check.common import ROOT

from .judge import ClaimJudgement
from .pack import load_pack
from .pipeline import check_teaser, overall, write_csv


def judgements_from_csv(path) -> list[ClaimJudgement]:
    """The judge's claims of an earlier run (rows of kind 'claim'), rebuilt as the judge would return them."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["kind"] == "claim"]
    return [ClaimJudgement(claim=r["text"], finding=r["finding"], source_ref=r["source_field"] or "none",
                           record_quote=r["record_quote"], reason=r["reason"]) for r in rows]


def main() -> None:
    p = argparse.ArgumentParser(description="Replay a saved judge answer through the current code rules.")
    p.add_argument("pack")
    p.add_argument("teaser")
    p.add_argument("saved")
    p.add_argument("--out", default=str(ROOT / "results" / "teaser_replay.csv"))
    a = p.parse_args()
    saved = judgements_from_csv(a.saved)
    rows, _ = check_teaser(load_pack(a.pack), open(a.teaser, encoding="utf-8").read(),
                           lambda record, body: (saved, {"input": 0, "output": 0}))
    rows = [{"case": "replay", "id": "", **r} for r in rows]
    write_csv(rows, a.out)
    print("Result  :", overall(rows, dry_run=False))
    print(f"Saved {len(rows)} rows to {a.out} (no model call)")


if __name__ == "__main__":
    main()
