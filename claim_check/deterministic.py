# Layer 1: checks that need no AI. Plain Python, free and repeatable.
# Numbers and quotes that are not in the record are Unsupported;
# everything else here is a flag for the reviewer (no verdict).

import re

from .common import make_row, norm

# Hashtags approved for the series.
REQUIRED_TAGS = ["#AURABuildLog", "#FundraiseInPublic", "#AURAFundraiseLog"]

SEPARATOR = re.compile(r"^-{10,}\s*$", re.M)
PLACEHOLDER = re.compile(r"\[Add:[^\]]*\]")
NUMBER = re.compile(r"\d+(?:[.,]\d+)?\s?%?")
QUOTE = re.compile(r"[“\"]([^”\"]{3,}?)[”\"]")
BANNED = re.compile(r"\b(often|many|always|usually|typically|obviously|shocking|surprising)\b", re.I)
FIRST_PERSON = re.compile(r"\b(I|I'm|I've|my|me)\b")
DONE_WORDS = re.compile(r"\b(fixed|shipped|released|rolled out|relabell?ed|resolved)\b", re.I)
LABELS = re.compile(r"\b(Situation|What happened|Why it matters[^:]{0,20}|What we propose next|What we suggest next):")


def clean_draft(text: str) -> tuple[str, list[str], list[str]]:
    """Return (body, placeholders, hashtags).

    Removes the document header (everything above the dashed line), the hashtag line and the
    'Suggested topic tags' line, and takes out [Add: ...] placeholders, so the judge sees only the story.
    """
    parts = SEPARATOR.split(text)
    body = parts[-1] if len(parts) > 1 else text
    body = re.sub(r"\s+", " ", body).strip()
    hashtags = re.findall(r"#\w+", body)
    body = re.sub(r"Suggested topic tags:.*", "", body, flags=re.I)
    body = re.sub(r"#\w+", "", body)
    placeholders = PLACEHOLDER.findall(body)
    body = PLACEHOLDER.sub("", body)
    return re.sub(r"\s+", " ", body).strip(), placeholders, hashtags


def deterministic_checks(body: str, hashtags: list[str], placeholders: list[str], record_text: str) -> list[dict]:
    rows: list[dict] = []

    # Numbers: every number in the draft must appear in the record
    record_numbers = {n.replace(" ", "") for n in NUMBER.findall(record_text)}
    for number in dict.fromkeys(x.replace(" ", "") for x in NUMBER.findall(body)):
        if number not in record_numbers:
            rows.append(make_row("number", number, "Unsupported", "not_in_record", "none",
                                 reason="Number does not appear anywhere in the record."))

    # Quotes: quoted text must be copied from the record
    record_norm = norm(record_text)
    for quote in QUOTE.findall(body):
        if norm(quote).rstrip("?.!,") not in record_norm:
            rows.append(make_row("quote", quote, "Unsupported", "not_in_record", "none",
                                 reason="Quoted text does not appear in the record."))

    # Style flags. Quoted text is verbatim from the product, so "Show me a draft"
    # must not trigger the first-person flag.
    body_no_quotes = QUOTE.sub("", body)
    for regex, text, why in [
        (BANNED, body, "Banned word in the draft (generalisation or hype)."),
        (FIRST_PERSON, body_no_quotes,
         "First-person singular. Check who actually acted (the record is written in the tester's voice)."),
        (DONE_WORDS, body, "Wording that sounds like finished work. A recommendation must stay a proposal."),
        (LABELS, body, "Section label in the text. The draft should be flowing prose."),
    ]:
        for match in regex.finditer(text):
            rows.append(make_row("flag", match.group(0), reason=why))

    missing = [tag for tag in REQUIRED_TAGS if tag not in hashtags]
    if missing:
        rows.append(make_row("flag", " ".join(missing), reason="Approved series hashtag missing."))
    for placeholder in placeholders:
        rows.append(make_row("placeholder", placeholder, reason="A person must fill this in before approval."))
    return rows
