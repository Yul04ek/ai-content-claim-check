# The evidence pack: the structured (JSON) version of the PDF a human reads.
# The judge compares a teaser only with this text, so nothing else can count as evidence.

import json
from pathlib import Path


def load_pack(path) -> dict:
    pack = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("group_id", "sources", "facts"):
        if not pack.get(key):
            raise SystemExit(f"Pack {path}: field '{key}' is missing or empty")
    return pack


def pack_to_text(pack: dict) -> str:
    """Labelled plain text of the pack. This is the 'record' the judge sees and quotes from."""
    lines = [f"COMPANY: {pack.get('company_label', '')} (group {pack['group_id']})",
             f"WEBSITE: {pack.get('website', '')}"]
    for s in pack["sources"]:
        lines.append(f"SOURCE {s['id']} ({s['url']}, read {s.get('date_read', '?')}): \"{s['excerpt']}\"")
    for f in pack["facts"]:
        lines.append(f"FACT {f['id']} [{f['source']}]: {f['text']}")
    for u in pack.get("unknowns", []):
        lines.append(f"UNKNOWN: {u}")
    offers = pack.get("approved_aura_offers") or []
    if offers:
        lines.append(f"AURA OFFER LIST STATUS: {pack.get('approved_aura_offers_status', 'unknown')}")
        lines += [f"AURA OFFER {o['id']}: {o['text']}" for o in offers]
    else:
        lines.append("AURA OFFER LIST: not provided")
    return "\n".join(lines)


def known_ids(pack: dict) -> set[str]:
    return {s["id"] for s in pack["sources"]} | {f["id"] for f in pack["facts"]}


def known_urls(pack: dict) -> set[str]:
    urls = {s["url"] for s in pack["sources"]}
    if pack.get("website"):
        urls.add(pack["website"])
    return {u.rstrip("/").lower() for u in urls}
