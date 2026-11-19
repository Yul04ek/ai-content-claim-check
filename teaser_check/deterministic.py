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
MAX_WORDS = 500  # rough size of "one readable page", all headings and fixed lines included (Yuliia, 9 Nov; was 450); only a flag

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


def loose(text: str) -> str:
    """Letters and digits only, lower case. A quotation is compared with the page text this way, because the snapshot
    often has line breaks and a space before a full stop ("open-source\n. This") that a copied quotation does not have."""
    return re.sub(r"[\W_]+", "", norm(text))


def split_teaser(text: str) -> tuple[str, str]:
    """Return (body for the judge, tail with sources/unknowns). The header line is removed from the body."""
    match = TAIL_HEADING.search(text)
    body, tail = (text[:match.start()], text[match.start():]) if match else (text, "")
    body = "\n".join(line for line in body.splitlines() if not HEADER.search(line))
    return re.sub(r"[ \t]+", " ", body).strip(), tail


WRAPPER = re.compile(r"^Created: \d{4}-\d{2}-\d{2}[ \d:]*$", re.M)  # line added by the Make Google Docs module
COMPANY_LINE = re.compile(r"^Company: (.+)$", re.M)  # header line added by the Make Google Docs module (the input field company_name)


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

    # The company name typed into Make must be the name the sources use: a typo there is repeated all over the teaser.
    company = COMPANY_LINE.search(text)
    if company and loose(company[1]) and loose(company[1]) not in loose(record_text):
        rows.append(make_row("rule", f"company name: {company[1].strip()}", "Needs Human Verification", "rule_broken", "none",
                             reason="The company name in the teaser header does not appear in the pack. Check the spelling typed into Make."))

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

    for quote in QUOTE.findall(body):
        if len(quote.split()) < 4:  # a short term in quotation marks is a label, not a quotation
            continue
        if loose(quote) not in loose(record_text):
            rows.append(make_row("quote", quote, "Unsupported", "not_in_pack", "none",
                                 reason="Quoted text does not appear in the pack."))

    rows += evidence_line_checks(body, pack)
    rows += offer_block_checks(body, pack)

    promise_body = body
    if any(o.get("limits") for o in pack.get("approved_aura_offers", [])):
        # A Limits line is table text ("Does not ... guarantee ..."); a changed one is reported by offer_block_checks.
        promise_body = "\n".join(line for line in body.splitlines() if not re.match(r"^\W*Limits:", line, re.I))
    for match in PROMISE.finditer(promise_body):
        if NEGATION.search(promise_body[max(0, match.start() - 30):match.start()]):  # "terms are not guaranteed" is no promise
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
        if offer.get("human_review") or offer.get("not_customer_ready"):  # "human_review": mention is fine only after a person checks it
            reason = offer.get("human_check_reason",
                               "Not approved as available to customers yet. Mention only after Tapiwa approves the terms.")
            rows.append(make_row("offer", offer["name"], "Needs Human Verification", "rule_broken", offer["id"], reason=reason))
        word = offer.get("must_say")
        if word and not all(re.search(rf"\b(?:{word})\b", b, re.I) for b in blocks):
            said = word.replace("|", "' or '")  # "proposed|in development" -> proposed' or 'in development
            rows.append(make_row("offer", offer["name"], "Needs Human Verification", "rule_broken", offer["id"],
                                 reason=f"{offer['name']} must be described as '{said}' wherever it is mentioned."))
    return rows


EVIDENCE_LINE = re.compile(r"^\W*Evidence:(.*)$", re.I | re.M)
OFFER_LINE = re.compile(r"^\W*Offer:", re.I | re.M)


def evidence_line_checks(body: str, pack: dict) -> list[dict]:
    """Every hypothesis with an 'Offer:' line needs an 'Evidence:' line with a quotation from the COMPANY's sources
    (not from the AURA offer list: the quote must not be the offer talking about itself)."""
    rows: list[dict] = []
    lines = EVIDENCE_LINE.findall(body)
    offers = len(OFFER_LINE.findall(body))
    if offers > len(lines):
        rows.append(make_row("rule", f"{offers} offers, {len(lines)} evidence lines", "Needs Human Verification", "rule_broken", "none",
                             reason="Every hypothesis needs an Evidence line with a quotation from the company's sources."))
    source_norm = loose(" ".join(src.get("excerpt", "") for src in pack.get("sources", [])))
    for line in lines:
        quotes = [q for q in QUOTE.findall(line) if len(q.split()) >= 3]
        if not quotes:
            rows.append(make_row("rule", line.strip()[:100], "Needs Human Verification", "rule_broken", "none",
                                 reason="The Evidence line has no quotation (at least 3 words) from the company's sources."))
        for quote in quotes:
            # "a ... b": each part must stand in the sources on its own (the quote may skip words)
            parts = [p for p in re.split(r"\.{3}|…", quote) if norm(p)]
            if any(loose(p) not in source_norm for p in parts):
                rows.append(make_row("quote", quote, "Unsupported", "not_in_pack", "none",
                                     reason="The evidence quotation does not appear in the company's sources."))
    return rows


OFFER_START = re.compile(r"^\W*Offer:\s*(.*)$", re.I)
BLOCK_LINE = re.compile(r"^\W*(Evidence|Company need|How AURA helps|Limits|Hypothesis):\s*(.*)$", re.I)
ODD_PLACEHOLDER = re.compile(r"\[(?!Add:)[^\]\n]{12,}\]")  # a made-up placeholder: only '[Add: ...]' is the agreed form
STOP = {"a", "an", "the", "and", "to", "for", "of", "in", "with", "on", "or", "is", "as", "by", "its", "their"}


def offer_blocks(body: str) -> list[dict]:
    """Split the hypotheses part into one block per 'Offer:' line; each block holds its lines by name (lower case)."""
    blocks: list[dict] = []
    for line in body.splitlines():
        start = OFFER_START.match(line)
        if start:
            blocks.append({"offer": start.group(1).strip()})
            continue
        field = BLOCK_LINE.match(line)
        if field and blocks:
            blocks[-1][field.group(1).lower()] = field.group(2).strip()
    return blocks


def shared_run(text: str, source: str, size: int = 3) -> str:
    """The first run of at least `size` words (not only filler words) that the text takes over from the source."""
    words = re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)*", norm(text))
    src = " ".join(re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)*", norm(source)))
    for i in range(len(words) - size + 1):
        run = words[i:i + size]
        if not set(run) <= STOP and " ".join(run) in src:
            return " ".join(run)
    return ""


def offer_block_checks(body: str, pack: dict) -> list[dict]:
    """The lines of every offer block are checked against the offer table (Tapiwa's), where code can do it exactly:
    the Offer line and the Limits word for word, the entry offer first, the need not copied from the offer, no made-up placeholder.
    A mismatch row carries the table's own text as the quote. Offers without table fields (old packs) are skipped."""
    rows: list[dict] = []
    offers = [o for o in pack.get("approved_aura_offers", []) if o.get("offer_line")]
    blocks = offer_blocks(body)
    if not offers or not blocks:
        return rows
    flagged_lines: set[str] = set()
    matched = []
    for block in blocks:
        line = block["offer"]
        offer = next((o for o in offers if norm(o["offer_line"]) == norm(line)), None)
        if offer is None:  # not word for word: find the offer by its name
            offer = next((o for o in offers if norm(o["name"]) in norm(line)), None)
            if offer is not None:
                rows.append(make_row("rule", f"Offer: {line}", "Needs Human Verification", "rule_broken", "none", offer["offer_line"],
                                     "The Offer line is not word for word the Offer line of the table."))
        matched.append(offer)
        if offer is None:
            continue
        limits = block.get("limits", "").strip().strip('"“”').strip()
        if not limits or limits.startswith("[Add:"):
            rows.append(make_row("rule", f"{offer['name']}: Limits line missing", "Needs Human Verification", "rule_broken", "none", offer["limits"],
                                 "The table has limits for this offer; the teaser must give them word for word."))
        elif norm(limits) != norm(offer["limits"]):
            flagged_lines.add(block.get("limits", ""))
            rows.append(make_row("rule", f"Limits: {limits[:140]}", "Unsupported", "not_in_pack", "none", offer["limits"],
                                 "The Limits line is not word for word the Limits of the table. A changed limit can turn into a benefit."))
        run = shared_run(block.get("company need", ""), f"{offer['purpose']} {offer['features']}")
        if run:
            rows.append(make_row("rule", f"Company need: {block['company need'][:160]}", "Needs Human Verification", "rule_broken", "none", "",
                                 f"The Company need repeats the wording of the offer ('{run}'). A need must come from the company's evidence."))
    defaults = [o for o in offers if o.get("default")]
    if defaults and (not matched or matched[0] is None or not matched[0].get("default")):
        rows.append(make_row("rule", "first offer", "Needs Human Verification", "rule_broken", "none", defaults[0]["offer_line"],
                             f"{defaults[0]['name']} is the entry offer and must be the first offer of the teaser."))
    for m in ODD_PLACEHOLDER.finditer(body):
        if any(m.group(0) in line for line in flagged_lines):
            continue  # already reported as a changed Limits line
        rows.append(make_row("placeholder", m.group(0), "Needs Human Verification", "rule_broken", "none", "",
                             "Text in square brackets that is not '[Add: ...]'. Missing information is marked only in that form."))
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
    # The teaser does not need source IDs (Yuliia, 9 Nov: AURA makes its own snapshot from a link, its IDs are unknown).
    # The source notes must name at least one source: an address or an ID. Address and date per source: source_note_checks.
    if not re.search(r"https?://|\b[a-z0-9-]+\.[a-z]{2,}\b|\bS\d+\b", tail, re.I):
        rows.append(make_row("rule", "source notes", "Needs Human Verification", "rule_broken", "none",
                             reason="The source notes section names no source (no address and no source ID)."))
    words = len(text.split())
    if words > MAX_WORDS:
        rows.append(make_row("flag", f"{words} words", reason=f"Longer than about one page ({MAX_WORDS} words)."))
    return rows
