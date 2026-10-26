# Layer 1: checks that need no AI. Plain Python, free and repeatable.
# Only checks that never depend on context live here: quotes, numbers, banned words, hashtags, placeholders.
# Anything that depends on context (who acted, what was really done, wording of a claim) is left to the judge,
# which sees which field of the record a claim comes from.

import re

from .common import make_row, norm

# Hashtags approved for the series.
REQUIRED_TAGS = ["#AURABuildLog", "#FundraiseInPublic", "#AURAFundraiseLog"]

SEPARATOR = re.compile(r"^-{10,}\s*$", re.M)
PLACEHOLDER = re.compile(r"\[Add:[^\]]*\]")
NUMBER = re.compile(r"\d+(?:[.,]\d+)?\s?%?")
QUOTE = re.compile(r"[“\"]([^”\"]{3,}?)[”\"]")
BANNED = re.compile(r"\b(often|many|always|usually|typically|obviously|shocking|surprising)\b", re.I)


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

    # Numbers: a number in the draft that is not in the record is usually invented, but it can also be
    # derived from the record ("2 of 3"), so it needs a human look instead of an automatic Unsupported.
    record_numbers = {n.replace(" ", "") for n in NUMBER.findall(record_text)}
    for number in dict.fromkeys(x.replace(" ", "") for x in NUMBER.findall(body)):
        if number not in record_numbers:
            rows.append(make_row("number", number, "Needs Human Verification", "not_in_record", "none",
                                 reason="Number does not appear in the record. Check that it is not invented."))

    # Quotes: quoted text must be copied from the record
    record_norm = norm(record_text)
    for quote in QUOTE.findall(body):
        if norm(quote).rstrip("?.!,") not in record_norm:
            rows.append(make_row("quote", quote, "Unsupported", "not_in_record", "none",
                                 reason="Quoted text does not appear in the record."))

    for match in BANNED.finditer(body):
        rows.append(make_row("flag", match.group(0), reason="Banned word in the draft (generalisation or hype)."))

    missing = [tag for tag in REQUIRED_TAGS if tag not in hashtags]
    if missing:
        rows.append(make_row("flag", " ".join(missing), reason="Approved series hashtag missing."))
    for placeholder in placeholders:
        rows.append(make_row("placeholder", placeholder, reason="A person must fill this in before approval."))
    return rows
