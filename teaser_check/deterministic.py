# Layer 1 for teasers: exact checks, no AI, free and repeatable.
# Only rules that never depend on context live here. Meaning is left to the judge.

import re

from claim_check.common import make_row, norm

from .pack import known_ids, known_urls

HEADER = re.compile(r"INTERNAL REVIEW ONLY", re.I)
# Everything from the first of these headings on (sources, unknowns) is a list, not a claim for the judge.
TAIL_HEADING = re.compile(r"^\W*(source notes?|sources?|unknowns?)\b", re.I | re.M)
ID_REF = re.compile(r"\b([SF]\d+)\b")
PACK_ID = re.compile(r"\b[SFA]\d+\b|_\d+")  # S1, F2, A3 and group IDs such as Test_001 are labels, not figures
URL = re.compile(r"https?://[^\s)\]>,;]+")
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.M)
NUMBER = re.compile(r"\d+(?:[.,]\d+)?\s?%?")
QUOTE = re.compile(r"[“\"]([^”\"]{3,}?)[”\"]")
MONEY = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")
HYPOTHESIS_TAG = re.compile(r"\bH\d\b")  # "H1", "H2": labels of hypotheses, not figures
NEGATION = re.compile(r"\b(not|no|unknown|without|unclear)\b", re.I)
MAX_WORDS = 450  # rough size of "one readable page"; only a flag

# Parts the handover PDF asks for (page 3). Each is a simple word test; whether the content is right is the judge's job.
REQUIRED_PARTS = {
    "company snapshot": re.compile(r"snapshot|who you are|company description|verified description", re.I),
    "AURA help": re.compile(r"\bAURA\b.*\b(help|pathway|offer|support)", re.I | re.S),
    "sign-up invitation": re.compile(r"sign[- ]?up", re.I),
}

# Promises the teaser must never make: Unsupported on sight.
PROMISE = re.compile(
    r"\b(guarantee[sd]?|fast[- ]track\w*|(will|can) (invest|fund|introduce you|connect you)"
    r"|(accepted|acceptance|admission) (in|into|to) (the )?studio|secure (an )?investment"
    r"|will be accepted|automatic(ally)? accept\w*|pre-?approved|you (qualify|are eligible))\b", re.I)
# Words that usually mean an invented business figure: a flag for a human look, not a verdict.
FIGURE_WORDS = re.compile(
    r"\b(revenue|turnover|valuation|ARR|MRR|traction|fast[- ]growing|rapid growth|raised|funded|profitable)\b", re.I)


def split_teaser(text: str) -> tuple[str, str]:
    """Return (body for the judge, tail with sources/unknowns). The header line is removed from the body."""
    match = TAIL_HEADING.search(text)
    body, tail = (text[:match.start()], text[match.start():]) if match else (text, "")
    body = "\n".join(line for line in body.splitlines() if not HEADER.search(line))
    return re.sub(r"[ \t]+", " ", body).strip(), tail


WRAPPER = re.compile(r"^Created: \d{4}-\d{2}-\d{2}[ \d:]*$", re.M)  # line added by the Make Google Docs module


def numbered_items_under_hypotheses(body: str) -> int:
    """Count '1)' / '2.' items after a heading that contains 'hypothes', until the next unindented non-list line."""
    count, inside = 0, False
    for line in body.splitlines():
        if not inside:
            inside = bool(re.search(r"hypothes", line, re.I)) and not line.lstrip().startswith("-")
            continue
        if re.match(r"\s*\d+[.)]\s", line):
            count += 1
        elif line.strip() and not re.match(r"\s*[-•]", line) and count:
            break
    return count


def deterministic_checks(text: str, body: str, pack: dict, record_text: str) -> list[dict]:
    text, body = WRAPPER.sub("", text.replace("\r", "")), WRAPPER.sub("", body.replace("\r", ""))  # Windows line ends too
    rows: list[dict] = []

    if not HEADER.search(text):
        rows.append(make_row("rule", "INTERNAL REVIEW ONLY", "Needs Human Verification", "rule_broken", "none",
                             reason="The internal-review label is missing."))

    # Source and fact IDs must exist in the pack.
    ids = known_ids(pack)
    for ref in dict.fromkeys(ID_REF.findall(text)):
        if ref not in ids:
            rows.append(make_row("ref", ref, "Unsupported", "not_in_pack", "none",
                                 reason="This source or fact ID is not in the evidence pack."))

    # URLs must be sources of the pack.
    urls = known_urls(pack)
    for url in dict.fromkeys(URL.findall(text)):
        if url.rstrip("/.").lower() not in urls:
            rows.append(make_row("url", url, "Unsupported", "not_in_pack", "none",
                                 reason="This URL is not a source in the evidence pack."))

    # Numbers: a figure that is not in the pack may be invented. IDs and list markers are not figures.
    cleaned = re.sub(r"\bhypothesis\s*\d+", "hypothesis", LIST_MARKER.sub("", ID_REF.sub("", body)), flags=re.I)
    cleaned = HYPOTHESIS_TAG.sub("hypothesis", cleaned)
    pack_numbers = {re.sub(r"\s", "", n) for n in NUMBER.findall(PACK_ID.sub("", record_text))}  # "12\n/month" is 12
    for number in dict.fromkeys(re.sub(r"\s", "", x) for x in NUMBER.findall(cleaned)):
        if number not in pack_numbers:
            rows.append(make_row("number", number, "Needs Human Verification", "not_in_pack", "none",
                                 reason="Number does not appear in the pack. Check that it is not invented."))

    record_norm = norm(record_text)
    for quote in QUOTE.findall(body):
        if len(quote.split()) < 4:  # a short term in quotation marks is a label, not a quotation
            continue
        if norm(quote).rstrip("?.!,") not in record_norm:
            rows.append(make_row("quote", quote, "Unsupported", "not_in_pack", "none",
                                 reason="Quoted text does not appear in the pack."))

    for match in PROMISE.finditer(body):
        if NEGATION.search(body[max(0, match.start() - 30):match.start()]):  # "terms are not guaranteed" is no promise
            continue
        rows.append(make_row("promise", match.group(0), "Unsupported", "promise", "none",
                             reason="Promise of investment, introductions or Studio acceptance."))
    for match in FIGURE_WORDS.finditer(body):
        start = max(body.rfind(".", 0, match.start()), body.rfind("\n", 0, match.start())) + 1
        end = [i for i in (body.find(".", match.end()), body.find("\n", match.end())) if i != -1]
        sentence = body[start:min(end) if end else len(body)]
        if NEGATION.search(sentence):  # "revenue ... have not been established" states an unknown, it is not a figure
            continue
        rows.append(make_row("flag", match.group(0), reason="Business-figure word. The pack contains no such figure."))

    rows += offer_checks(body, pack, record_text)
    rows += scope_checks(text, body, tail_text_of(text), pack)

    tags = set(re.findall(r"^\W*(H\d)\b", body, re.M))  # "H1: ..." counts as a labelled hypothesis
    hypotheses = max(len(re.findall(r"\bhypothesis\b", body, re.I)), len(tags), numbered_items_under_hypotheses(body))
    if hypotheses < 2:
        rows.append(make_row("rule", f"{hypotheses} labelled hypothesis", "Needs Human Verification", "rule_broken",
                             "none", reason="The teaser needs 2-3 clearly labelled hypotheses."))
    elif hypotheses > 3:
        rows.append(make_row("flag", f"{hypotheses} labelled hypotheses", reason="More than 3 hypotheses."))
    return rows


def tail_text_of(text: str) -> str:
    return split_teaser(text)[1]


def paragraphs(body: str) -> list[str]:
    """Blocks separated by blank lines; a single line is used when the text has no blank lines."""
    blocks = [b for b in re.split(r"\n\s*\n", body) if b.strip()]
    return blocks if len(blocks) > 1 else [l for l in body.splitlines() if l.strip()]


def words_of(text: str) -> set[str]:
    """Lower-case words without a final 's', so 'Investor-Ready Sprints' and 'investor ready sprint' look the same."""
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in re.findall(r"[a-z0-9]+", text.lower())}


def mentions(block: str, offer: dict) -> bool:
    """True if the block names the offer: by a regex ('match') or by word sets ('match_words'): any set with all its words."""
    if offer.get("match") and re.search(offer["match"], block, re.I):
        return True
    found = words_of(block)
    return any(all(w in found for w in word_set) for word_set in offer.get("match_words", []))


def offer_checks(body: str, pack: dict, record_text: str) -> list[dict]:
    """Rules about the approved AURA offer list (from the pack): prices, 'proposed', offers not yet available."""
    offers = pack.get("approved_aura_offers") or []
    rows: list[dict] = []
    if not offers:
        return rows
    # A price must exist in the offer list. Whether it belongs to the right offer is left to the judge.
    offer_text = " ".join(o["text"] for o in offers)
    known = {re.sub(r"\s", "", m) for m in MONEY.findall(offer_text)}
    # A price that stands in the page text is the company's own price; whose price it is, is left to the judge.
    source_text = " ".join(s.get("excerpt", "") for s in pack.get("sources", []))
    company_prices = {re.sub(r"\s", "", m) for m in MONEY.findall(source_text)}  # "$\n12" on a page is $12
    for price in dict.fromkeys(re.sub(r"\s", "", m) for m in MONEY.findall(body)):
        if price not in known and price not in company_prices:
            rows.append(make_row("price", price, "Unsupported", "not_in_pack", "none",
                                 reason="This price is not in the approved AURA offer list."))
    for offer in offers:
        if not (offer.get("match") or offer.get("match_words")):
            continue
        blocks = [b for b in paragraphs(body) if mentions(b, offer)]
        if not blocks:
            continue
        if offer.get("not_customer_ready"):
            reason = offer.get("human_check_reason",
                               "Not approved as available to customers yet. Mention only after Tapiwa approves the terms.")
            rows.append(make_row("offer", offer["name"], "Needs Human Verification", "rule_broken", offer["id"], reason=reason))
        word = offer.get("must_say")
        if word and not all(re.search(rf"\b{word}\b", b, re.I) for b in blocks):
            rows.append(make_row("offer", offer["name"], "Needs Human Verification", "rule_broken", offer["id"],
                                 reason=f"{offer['name']} must be described as '{word}' wherever it is mentioned."))
    return rows


def scope_checks(text: str, body: str, tail: str, pack: dict) -> list[dict]:
    """Rules about the shape of the teaser and about text that must not come from other companies."""
    rows: list[dict] = []
    for term in pack.get("forbidden_terms", []):
        if re.search(re.escape(term), text, re.I):
            rows.append(make_row("scope", term, "Unsupported", "not_in_pack", "none",
                                 reason="Term from IdealApp's own Company DNA or another company. Prospect research must stay separate."))
    for part, pattern in REQUIRED_PARTS.items():
        if not pattern.search(text):  # whole text: the fixed sign-up invitation may stand after the source notes
            rows.append(make_row("rule", part, "Needs Human Verification", "rule_broken", "none",
                                 reason=f"Required part is missing: {part}."))
    if not re.search(r"\bS\d+\b", tail):
        rows.append(make_row("rule", "source notes", "Needs Human Verification", "rule_broken", "none",
                             reason="The source notes section has no source IDs (S1, S2, ...)."))
    words = len(text.split())
    if words > MAX_WORDS:
        rows.append(make_row("flag", f"{words} words", reason=f"Longer than about one page ({MAX_WORDS} words)."))
    return rows
