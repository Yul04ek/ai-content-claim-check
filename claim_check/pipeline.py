# Putting the layers together: read the record, clean the draft, run both layers, report.

import csv
import json
from pathlib import Path

from .common import COLUMNS
from .deterministic import clean_draft, deterministic_checks
from .judge import apply_rules

# Fields the drafting prompt sees: label used in the prompt -> column header in the sheet.
RECORD_FIELDS = {
    "SCENARIO": "scenario",
    "OBSERVATION": "observation",
    "SEVERITY": "severity",
    "USER IMPACT": "user impact",
    "RECOMMENDATION": "recommendation",
}


def load_record(csv_path, finding_id: str) -> dict[str, str]:
    """Return the fields of one finding, using the same labels as the drafting prompt."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("ID") or "").strip() == finding_id]
    if not rows:
        raise SystemExit(f"ID {finding_id} not found in {csv_path}")
    if len(rows) > 1:
        # The test sheet contains TEST ONLY rows that reuse F-001 / F-002.
        print(f"  warning: {finding_id} appears {len(rows)} times, using the first row")
    row = rows[0]
    return {label: (row.get(col) or "").strip() for label, col in RECORD_FIELDS.items()}


def record_to_text(record: dict[str, str]) -> str:
    """Empty fields are skipped, as in the drafting prompt."""
    return "\n".join(f"{label}: {value}" for label, value in record.items() if value)


def check_draft(record: dict[str, str], draft_text: str, judge) -> tuple[list[dict], dict]:
    """Run both layers on one draft. judge(record_text, body) -> (judgements, tokens)."""
    record_text = record_to_text(record)
    body, placeholders, hashtags = clean_draft(draft_text)
    rows = deterministic_checks(body, hashtags, placeholders, record_text)
    judgements, tokens = judge(record_text, body)
    return [apply_rules(j, record_text) for j in judgements] + rows, tokens


def overall(rows: list[dict], dry_run: bool) -> str:
    verdicts = {r["verdict"] for r in rows}
    flags = sum(1 for r in rows if r["kind"] == "flag")
    flag_text = f"; {flags} style flag(s)" if flags else ""
    if dry_run:
        # Without the AI layer a clean result means nothing, so never print "No problems found".
        found = ("deterministic findings to review"
                 if verdicts & {"Unsupported", "Needs Human Verification"} else "no deterministic findings")
        return f"DRY RUN (AI layer skipped, NOT a verdict): {found}{flag_text}"
    if "Unsupported" in verdicts:
        text = "NOT READY: unsupported claims found"
    elif "Needs Human Verification" in verdicts:
        text = "REVIEW: some claims need human verification"
    else:
        text = "No problems found by the checker (human review is still required)"
    return text + flag_text


def run_cases(sheet, cases_file, judge, dry_run: bool, only: str | None = None) -> tuple[list[dict], dict]:
    cases = json.loads(Path(cases_file).read_text(encoding="utf-8"))
    base = Path(cases_file).parent  # draft_file is relative to cases.json
    if only:  # for example --only "T6 " runs just the case whose name starts with that text
        cases = [c for c in cases if c["case"].startswith(only)]
        if not cases:
            raise SystemExit(f"No case name starts with {only!r}")

    all_rows: list[dict] = []
    total = {"input": 0, "output": 0}
    for case in cases:
        record = load_record(sheet, case["id"])
        draft = (base / case["draft_file"]).read_text(encoding="utf-8")
        rows, tokens = check_draft(record, draft, judge)
        total["input"] += tokens["input"]
        total["output"] += tokens["output"]

        print(f"\n=== {case['case']} ({case['id']}) ===")
        print("Result  :", overall(rows, dry_run))
        for r in rows:
            if r["verdict"] != "Supported":
                tag = r["verdict"] or r["kind"].upper()
                print(f"  [{tag}] {r['text']}  -- {r['reason']}")
        if case.get("expect"):
            print("Expected:", case["expect"])
        all_rows += [{"case": case["case"], "id": case["id"], **r} for r in rows]
    return all_rows, total


def write_csv(rows: list[dict], path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig opens cleanly in Sheets/Excel
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
