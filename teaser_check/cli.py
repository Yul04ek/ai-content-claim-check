# Command line.
#   One teaser:  python -m teaser_check packs/pack_Test_001.json my_teaser.txt [--dry-run] [--model M]
#   Test suite:  python -m teaser_check --suite cases_teaser/cases.json [--dry-run] [--only "T2 "]

import argparse
import os
from pathlib import Path

from claim_check.common import ROOT
from claim_check.config import get_client, get_env

from .judge import judge_with_llm, no_judge
from .pack import load_pack
from .report import build_report
from .pipeline import check_teaser, overall, run_suite, write_csv


def main() -> None:
    p = argparse.ArgumentParser(description="Independent claim check for AURA opportunity teasers.")
    p.add_argument("pack", nargs="?", help="evidence pack JSON")
    p.add_argument("teaser", nargs="?", help="teaser text file")
    p.add_argument("--suite", help="cases.json of the synthetic test suite")
    p.add_argument("--out", default=str(ROOT / "results" / "teaser_results.csv"))
    p.add_argument("--model", help="overrides MODEL_NAME")
    p.add_argument("--dry-run", action="store_true", help="deterministic checks only, no model call")
    p.add_argument("--only", help='suite only: run the case whose name starts with this text')
    args = p.parse_args()
    if not args.suite and not (args.pack and args.teaser):
        p.error("give a pack and a teaser file, or --suite")

    if args.dry_run:
        judge = no_judge
    else:
        client = get_client()
        model = args.model or get_env("MODEL_NAME")
        print(f"Model: {model}")
        judge = lambda record_text, body: judge_with_llm(record_text, body, client=client, model=model)

    if args.suite:
        rows, tokens = run_suite(args.suite, judge, args.dry_run, args.only)
    else:
        pack = load_pack(args.pack)
        text = open(args.teaser, encoding="utf-8").read()
        rows, tokens = check_teaser(pack, text, judge)
        rows = [{"case": "single", "id": pack["group_id"], **r} for r in rows]
        print("Result  :", overall(rows, args.dry_run))
        for r in rows:
            if r["verdict"] != "Supported":
                print(f"  [{r['verdict'] or r['kind'].upper()}] {r['text']}  -- {r['reason']}")
    write_csv(rows, args.out)
    if not args.suite and not args.dry_run:  # readable page next to the CSV
        page = Path(args.out).with_suffix(".html")
        page.write_text(build_report([dict(r) for r in rows], text, Path(args.teaser).stem, pack), encoding="utf-8")
        print(f"Report  : {page}")
    print(f"\nSaved {len(rows)} rows to {args.out}")
    print(f"Tokens used: input {tokens['input']}, output {tokens['output']}")
    pin, pout = os.getenv("CLAIM_CHECK_PRICE_IN"), os.getenv("CLAIM_CHECK_PRICE_OUT")
    if pin and pout and not args.dry_run:
        print(f"Estimated cost: ${tokens['input'] / 1e6 * float(pin) + tokens['output'] / 1e6 * float(pout):.4f}")


if __name__ == "__main__":
    main()
