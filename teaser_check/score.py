# Score the judge against a hand-made list of known errors ("golden" file). No model call here.
# Usage: python -m teaser_check.score golden.json [--json summary.json]
#
# golden.json: {"name": "...", "cases": [{"case": "B", "results": "path/to/results.csv",
#                "items": [{"id": "B1", "match": "open salaries", "why": "..."}]}]}
# An item counts as FOUND when a result row that is not 'Supported' contains the match text
# (flags such as the length flag count too). 'results' paths are relative to the golden file.

import argparse
import csv
import json
from pathlib import Path

from claim_check.common import norm


def load_rows(path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def is_finding(row: dict) -> bool:
    return row["verdict"] in ("Needs Human Verification", "Unsupported") or row["kind"] == "flag"


def row_source(row: dict) -> str:
    """Which layer made a row: the judge's own verdict on a claim, the 'not judged' check, or the code rules."""
    if row.get("kind") == "claim":
        return "judge"
    if row.get("reason", "").startswith("The judge returned no verdict"):
        return "coverage"
    return "code"


def score_case(items: list[dict], rows: list[dict]) -> dict:
    findings = [r for r in rows if is_finding(r)]
    found, missed, used = [], [], set()
    sources = {"code": 0, "judge": 0, "coverage": 0}  # an item counts once: code first, then judge, then 'not judged'
    for item in items:
        needle = norm(item["match"])
        hits = [i for i, r in enumerate(findings) if needle in norm(r["text"])]
        if not hits:
            missed.append(item)
        else:
            found.append(item)
            used.add(hits[0])
            kinds = {row_source(findings[i]) for i in hits}
            sources[next(k for k in ("code", "judge", "coverage") if k in kinds)] += 1
    extra = [r for i, r in enumerate(findings) if i not in used]  # findings nobody listed: a human decides if they are noise
    return {"found": found, "missed": missed, "extra": extra, "sources": sources,
            "recall": len(found) / len(items) if items else 1.0}


def score_file(golden_path) -> dict:
    golden_path = Path(golden_path)
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    cases = {}
    for case in golden["cases"]:
        rows = load_rows(golden_path.parent / case["results"])
        cases[case["case"]] = score_case(case["items"], rows)
    total = sum(len(c["found"]) + len(c["missed"]) for c in cases.values())
    found = sum(len(c["found"]) for c in cases.values())
    return {"name": golden.get("name", golden_path.stem), "cases": cases,
            "found": found, "total": total, "recall": found / total if total else 1.0,
            "extra": sum(len(c["extra"]) for c in cases.values())}


def main() -> None:
    p = argparse.ArgumentParser(description="Score the teaser judge against a list of known errors.")
    p.add_argument("golden")
    p.add_argument("--json", help="write a short summary (for the experiment log)")
    args = p.parse_args()
    result = score_file(args.golden)
    for name, c in result["cases"].items():
        print(f"\n=== {name}: found {len(c['found'])} of {len(c['found']) + len(c['missed'])} (recall {c['recall']:.0%}), "
              f"{len(c['extra'])} other finding(s) to look at")
        for item in c["missed"]:
            print(f"  MISSED {item['id']}: {item['match']}  -- {item.get('why', '')}")
        for r in c["extra"]:
            print(f"  EXTRA  [{r['verdict'] or r['kind']}] {r['text'][:90]}")
    print(f"\nTotal: found {result['found']} of {result['total']} (recall {result['recall']:.0%}), {result['extra']} other finding(s)")
    if args.json:
        summary = {"name": result["name"], "found": result["found"], "total": result["total"],
                   "recall": round(result["recall"], 3), "extra": result["extra"],
                   "missed": [i["id"] for c in result["cases"].values() for i in c["missed"]]}
        Path(args.json).write_text(json.dumps(summary, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
