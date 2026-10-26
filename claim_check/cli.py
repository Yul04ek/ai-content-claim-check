# Command line: python -m claim_check [--dry-run] [--only "T6 "] [--out results/results.csv]

import argparse
import os

from .common import ROOT
from .config import get_client, get_env
from .judge import judge_with_llm, no_judge
from .pipeline import run_cases, write_csv


def main() -> None:
    p = argparse.ArgumentParser(description="Independent claim check for AI story drafts.")
    p.add_argument("--sheet", default=str(ROOT / "testdata" / "BZ021_Test_Copy.csv"),
                   help="CSV export of the findings sheet")
    p.add_argument("--cases", default=str(ROOT / "cases" / "cases.json"))
    p.add_argument("--out", default=str(ROOT / "results" / "results.csv"))
    p.add_argument("--model", help="overrides MODEL_NAME")
    p.add_argument("--dry-run", action="store_true", help="deterministic checks only, no model call")
    p.add_argument("--only", help='run only the case whose name starts with this text, e.g. --only "T6 "')
    args = p.parse_args()

    if args.dry_run:
        judge = no_judge
    else:
        client = get_client()  # fails early and clearly when the key or the address is missing
        model = args.model or get_env("MODEL_NAME")
        print(f"Model: {model}")
        judge = lambda record_text, body: judge_with_llm(record_text, body, client=client, model=model)

    rows, tokens = run_cases(args.sheet, args.cases, judge, args.dry_run, args.only)
    write_csv(rows, args.out)

    print(f"\nSaved {len(rows)} rows to {args.out}")
    print(f"Tokens used: input {tokens['input']}, output {tokens['output']}")
    price_in, price_out = os.getenv("CLAIM_CHECK_PRICE_IN"), os.getenv("CLAIM_CHECK_PRICE_OUT")
    if price_in and price_out and not args.dry_run:  # USD per 1M tokens, from the provider's price page
        cost = tokens["input"] / 1e6 * float(price_in) + tokens["output"] / 1e6 * float(price_out)
        print(f"Estimated cost: ${cost:.4f}")


if __name__ == "__main__":
    main()
