# Snapshot blocks (make_evidence.txt) -> evidence pack JSON for the teaser judge.
# The pack holds the page text as sources, with no hand-written facts, so the judge checks against the page itself.
# Usage: python -m evidence_fetch.build_pack make_evidence.txt --group SIM-G-0002 --record SIM-REC-0002 \
#            --label "Cal.com, Inc." --website https://cal.com --offers packs/pack_Test_001_approved.json --out pack.json

import argparse
import json
import re
from pathlib import Path

HEADER = re.compile(r"^SOURCE: (?P<url>\S+?), read on (?P<date>\d{4}-\d{2}-\d{2})\s*$")
UNKNOWNS = [
    "Current funding status and any later rounds", "Current team size", "Revenue, customer numbers and traction",
    "How the company manages its planning and business documents", "Which tools it uses",
    "Whether it plans to raise money", "Whether the founders want AI support", "The right contact person",
]


def parse_make_evidence(text: str) -> list[dict]:
    """Split the pasted evidence into sources. Each block: SOURCE line, PAGE DATE line, then the page text."""
    sources, current = [], None
    for line in text.splitlines():
        m = HEADER.match(line)
        if m:
            current = {"url": m["url"], "date_read": m["date"], "page_date": "", "lines": []}
            sources.append(current)
        elif current is not None:
            if line.startswith("PAGE DATE:") and not current["lines"] and not current["page_date"]:
                value = line.split(":", 1)[1].strip()
                current["page_date"] = "" if value.lower().startswith("none") else value
            else:
                current["lines"].append(line)
    if not sources:
        raise ValueError("No 'SOURCE: <address>, read on <date>' line found")
    for s in sources:
        s["text"] = "\n".join(s.pop("lines")).strip()
    return sources


def build_pack(sources: list[dict], group_id: str, record_id: str, label: str, website: str, offers_pack: dict) -> dict:
    pack = {
        "group_id": group_id, "record_id": record_id, "company_label": label, "website": website,
        "practice_run": True, "ids_note": "SIMULATED IDs. Real IDs come from the Make source queue.",
        "sources": [{"id": f"S{i}", "url": s["url"], "date_read": s["date_read"],
                     "page_date": s["page_date"] or "none shown", "excerpt": s["text"]} for i, s in enumerate(sources, 1)],
        "facts": [], "unknowns": UNKNOWNS,
    }
    for key in ("approved_aura_offers_status", "approved_aura_offers", "forbidden_terms", "offers_table_url", "offers_table_date"):
        if key in offers_pack:
            pack[key] = offers_pack[key]
    return pack


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m evidence_fetch.build_pack")
    ap.add_argument("evidence", help="make_evidence.txt (SOURCE blocks)")
    ap.add_argument("--group", required=True)
    ap.add_argument("--record", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--website", default="")
    ap.add_argument("--offers", required=True, help="a pack JSON with approved_aura_offers to copy")
    ap.add_argument("--offers-table-url", default="", help="link to the offer table, shown in the report (kept in the pack, not in the code)")
    ap.add_argument("--offers-table-date", default="", help="date the offer table was read (copied), shown in the report")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    sources = parse_make_evidence(Path(a.evidence).read_text(encoding="utf-8"))
    offers = json.loads(Path(a.offers).read_text(encoding="utf-8"))
    pack = build_pack(sources, a.group, a.record, a.label, a.website, offers)
    if a.offers_table_url:
        pack["offers_table_url"] = a.offers_table_url
    if a.offers_table_date:
        pack["offers_table_date"] = a.offers_table_date
    Path(a.out).write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Pack {a.group}: {len(sources)} sources, {sum(len(s['text'].split()) for s in sources)} words -> {a.out}")


if __name__ == "__main__":
    main()
