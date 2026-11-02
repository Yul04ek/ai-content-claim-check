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

# Promises the teaser must never make: Unsupported on sight.
PROMISE = re.compile(
    r"\b(guarantee[sd]?|fast[- ]track\w*|(will|can) (invest|fund|introduce you|connect you)"
    r"|(accepted|acceptance|admission) (in|into|to) (the )?studio|secure (an )?investment)\b", re.I)
# Words that usually mean an invented business figure: a flag for a human look, not a verdict.
FIGURE_WORDS = re.compile(
    r"\b(revenue|turnover|valuation|ARR|MRR|traction|fast[- ]growing|rapid growth|raised|funded|profitable)\b", re.I)


def split_teaser(text: str) -> tuple[str, str]:
    """Return (body for the judge, tail with sources/unknowns). The header line is removed from the body."""
    match = TAIL_HEADING.search(text)
    body, tail = (text[:match.start()], text[match.start():]) if match else (text, "")
    body = "\n".join(line for line in body.splitlines() if not HEADER.search(line))
    return re.sub(r"[ \t]+", " ", body).strip(), tail


def deterministic_checks(text: str, body: str, pack: dict, record_text: str) -> list[dict]:
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
    pack_numbers = {n.replace(" ", "") for n in NUMBER.findall(PACK_ID.sub("", record_text))}
    for number in dict.fromkeys(x.replace(" ", "") for x in NUMBER.findall(cleaned)):
        if number not in pack_numbers:
            rows.append(make_row("number", number, "Needs Human Verification", "not_in_pack", "none",
                                 reason="Number does not appear in the pack. Check that it is not invented."))

    record_norm = norm(record_text)
    for quote in QUOTE.findall(body):
        if norm(quote).rstrip("?.!,") not in record_norm:
            rows.append(make_row("quote", quote, "Unsupported", "not_in_pack", "none",
                                 reason="Quoted text does not appear in the pack."))

    for match in PROMISE.finditer(body):
        rows.append(make_row("promise", match.group(0), "Unsupported", "promise", "none",
                             reason="Promise of investment, introductions or Studio acceptance."))
    for match in FIGURE_WORDS.finditer(body):
        rows.append(make_row("flag", match.group(0), reason="Business-figure word. The pack contains no such figure."))

    hypotheses = len(re.findall(r"\bhypothesis\b", body, re.I))
    if hypotheses < 2:
        rows.append(make_row("rule", f"{hypotheses} labelled hypothesis", "Needs Human Verification", "rule_broken",
                             "none", reason="The teaser needs 2-3 clearly labelled hypotheses."))
    elif hypotheses > 3:
        rows.append(make_row("flag", f"{hypotheses} labelled hypotheses", reason="More than 3 hypotheses."))
    return rows
