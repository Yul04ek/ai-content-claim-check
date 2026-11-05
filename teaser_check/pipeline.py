# Putting the layers together for teasers: pack + teaser text -> rows and one overall result.

import csv
import json
from pathlib import Path

from claim_check.common import COLUMNS

from .deterministic import deterministic_checks, split_teaser
from .judge import apply_rules
from .postchecks import citation_checks, coverage_checks, text_checks
from .pack import load_pack, pack_to_text

LEVELS = ["READY FOR REVIEW", "REVIEW", "NOT READY"]  # worst last


def level(rows: list[dict]) -> str:
    verdicts = {r["verdict"] for r in rows}
    if "Unsupported" in verdicts:
        return "NOT READY"
    if "Needs Human Verification" in verdicts:
        return "REVIEW"
    return "READY FOR REVIEW"


def overall(rows: list[dict], dry_run: bool) -> str:
    flags = sum(1 for r in rows if r["kind"] == "flag")
    flag_text = f"; {flags} flag(s)" if flags else ""
    if dry_run:  # without the judge a clean result means nothing
        found = "findings to review" if level(rows) != "READY FOR REVIEW" else "no deterministic findings"
        return f"DRY RUN (judge skipped, NOT a verdict): {found}{flag_text}"
    return level(rows) + " (a human still approves)" + flag_text


def check_teaser(pack: dict, teaser_text: str, judge) -> tuple[list[dict], dict]:
    record_text = pack_to_text(pack)
    body, tail = split_teaser(teaser_text)
    rows = deterministic_checks(teaser_text, body, pack, record_text) + text_checks(teaser_text, body, tail, pack)
    judgements, tokens = judge(record_text, body)
    if judgements:  # with no judge (dry run) every line would be 'not judged'
        rows += coverage_checks(body, judgements) + citation_checks(judgements, pack)
    return [apply_rules(j, record_text) for j in judgements] + rows, tokens


def run_suite(cases_file, judge, dry_run: bool, only: str | None = None):
    """Run every synthetic teaser of a suite. Each case names a pack, a teaser file and the expected level."""
    cases = json.loads(Path(cases_file).read_text(encoding="utf-8"))
    base = Path(cases_file).parent
    if only:
        cases = [c for c in cases if c["case"].startswith(only)]
        if not cases:
            raise SystemExit(f"No case name starts with {only!r}")
    all_rows, total, hits = [], {"input": 0, "output": 0}, 0
    for case in cases:
        pack = load_pack(base / case["pack"])
        rows, tokens = check_teaser(pack, (base / case["teaser_file"]).read_text(encoding="utf-8"), judge)
        total["input"] += tokens["input"]
        total["output"] += tokens["output"]
        got = level(rows)
        match = "" if dry_run else ("  OK" if got == case["expect_level"] else "  MISMATCH")
        hits += got == case["expect_level"]
        print(f"\n=== {case['case']} ({pack['group_id']}) ===")
        print("Result  :", overall(rows, dry_run))
        for r in rows:
            if r["verdict"] != "Supported":
                print(f"  [{r['verdict'] or r['kind'].upper()}] {r['text']}  -- {r['reason']}")
        print(f"Expected: {case['expect_level']} ({case['why']}){match}")
        all_rows += [{"case": case["case"], "id": pack["group_id"], **r} for r in rows]
    if not dry_run:
        print(f"\nLevel matches expectation: {hits} of {len(cases)}")
    return all_rows, total


def write_csv(rows: list[dict], path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
