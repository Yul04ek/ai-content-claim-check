# Builds everything that uses the AURA offer reference from ONE place:
#   packs/aura_offer_cards.csv     a copy of Tapiwa's sheet "AURA offer cards" (edit it when he changes the sheet)
#   packs/aura_offer_extras.json   our own fields (offer line, status, match rules, wording)
# Output:
#   packs/aura_offers_v2.json      the offer list for the code and the judge (pack field approved_aura_offers)
#   packs/make_offer_reference.txt the reference block to paste into the Make prompt
# Run: python -m teaser_check.offers_build        (check only, no writing: python -m teaser_check.offers_build --check)

import csv
import json
import sys
from pathlib import Path

PACKS = Path(__file__).resolve().parent.parent / "packs"
SOURCE = "Tapiwa's table 'AURA offer cards' (Google Sheet, sheet Offers), as filled in on 9 Nov 2026"


def load():
    with open(PACKS / "aura_offer_cards.csv", encoding="utf-8", newline="") as f:
        cards = list(csv.DictReader(f))
    extras = json.loads((PACKS / "aura_offer_extras.json").read_text(encoding="utf-8"))
    return [(c, extras[c["Offer"]]) for c in cards]


def offer_for_code(card: dict, extra: dict) -> dict:
    name = extra.get("name", card["Offer"])
    text = (f"{name} ({card['Pricing'].rstrip('.')}): {card['Purpose (what it is for)']} Features: {card['Features']} "
            f"Limits: {card['Limitations']} Review requirements: {card['Review requirements']}")
    offer = {"id": extra["id"], "name": name}
    for key in ("match", "match_words", "must_say"):
        if key in extra:
            offer[key] = extra[key]
    if extra.get("human_review"):
        offer["human_review"] = True
        offer["human_check_reason"] = f"Human review required (Tapiwa's table): {card['Review requirements']}"
    offer["text"] = text
    return offer


def make_block(pairs) -> str:
    out = ["AURA OFFER REFERENCE (the only offers you may mention)"]
    for i, (card, extra) in enumerate(pairs, 1):
        out += [f"{i}. Offer line: {extra['offer_line']}",
                f"   Purpose: {card['Purpose (what it is for)']}",
                f"   Features: {card['Features']}",
                f"   Limits: {card['Limitations']}",
                f"   Wording: {extra['wording']}"]
    out.append("Do not mention any other AURA offer or service.")
    return "\n".join(out) + "\n"


def build() -> dict[str, str]:
    pairs = load()
    status = (f"APPROVED reference list: {SOURCE}. Launchpad, Equity Studio, Sprints and Managed Execution are proposed or planned, "
              "never available; no guaranteed funding, introductions or results; no unlimited usage; every offer except Free needs a human check before it is mentioned.")
    offers = json.dumps({"status": status, "offers": [offer_for_code(c, e) for c, e in pairs]}, ensure_ascii=False, indent=1)
    return {"aura_offers_v2.json": offers, "make_offer_reference.txt": make_block(pairs)}


if __name__ == "__main__":
    files = build()
    if "--check" in sys.argv:
        stale = [n for n, t in files.items() if not (PACKS / n).exists() or (PACKS / n).read_text(encoding="utf-8") != t]
        print("up to date" if not stale else "OUT OF DATE: " + ", ".join(stale) + " (run python -m teaser_check.offers_build)")
        sys.exit(1 if stale else 0)
    for name, text in files.items():
        (PACKS / name).write_text(text, encoding="utf-8")
        print("wrote", PACKS / name)
