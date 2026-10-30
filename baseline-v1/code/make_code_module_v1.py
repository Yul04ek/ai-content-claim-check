import json
import re

# Inputs (Make Code "Input" variables). judge_answer is optional.
record = input.get('record') or ''
draft = input.get('draft') or ''
judge_answer = input.get('judge_answer') or ''

# ---- Settings (same values as in the claim_check repository) ----
REQUIRED_TAGS = ["#AURABuildLog", "#FundraiseInPublic", "#AURAFundraiseLog"]
SEPARATOR = re.compile(r"^-{10,}\s*$", re.M)
PLACEHOLDER = re.compile(r"\[Add:[^\]]*\]")
NUMBER = re.compile(r"\d+(?:[.,]\d+)?\s?%?")
QUOTE = re.compile(r"[“\"]([^”\"]{3,}?)[”\"]")
BANNED = re.compile(r"\b(often|many|always|usually|typically|obviously|shocking|surprising)\b", re.I)

# How the judge's finding maps to one of the three verdicts
FINDING_TO_VERDICT = {
    "supported": "Supported",
    "not_in_record": "Unsupported",
    "contradicted": "Unsupported",
    "done_not_proposed": "Unsupported",
    "assumption_as_fact": "Needs Human Verification",
    "overgeneralised": "Needs Human Verification",
    "qualifier_dropped": "Needs Human Verification",
    "meaning_shifted": "Needs Human Verification",
}


def norm(text):
    """Normalise quotes and spaces so copy-paste differences do not matter."""
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def make_row(kind, text, verdict="", finding="", source_field="", quote="", reason=""):
    return {"kind": kind, "text": text, "verdict": verdict, "finding": finding,
            "source_field": source_field, "record_quote": quote, "reason": reason}


def clean_draft(text):
    """Remove the document header, hashtags and placeholders. Returns (body, placeholders, hashtags)."""
    parts = SEPARATOR.split(text)
    body = parts[-1] if len(parts) > 1 else text
    body = re.sub(r"\s+", " ", body).strip()
    hashtags = re.findall(r"#\w+", body)
    body = re.sub(r"Suggested topic tags:.*", "", body, flags=re.I)
    body = re.sub(r"#\w+", "", body)
    placeholders = PLACEHOLDER.findall(body)
    body = PLACEHOLDER.sub("", body)
    return re.sub(r"\s+", " ", body).strip(), placeholders, hashtags


def code_checks(body, hashtags, placeholders, record_text):
    """Checks that need no AI: numbers, quotes, banned words, hashtags, placeholders."""
    rows = []
    # A number that is not in the record needs a human look (it may be derived, e.g. "2 of 3")
    record_numbers = {n.replace(" ", "") for n in NUMBER.findall(record_text)}
    for number in dict.fromkeys(x.replace(" ", "") for x in NUMBER.findall(body)):
        if number not in record_numbers:
            rows.append(make_row("number", number, "Needs Human Verification", "not_in_record", "none",
                                 reason="Number does not appear in the record. Check that it is not invented."))
    # Quoted text must be copied from the record
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


def judge_rows(answer, record_text):
    """Turn the judge's JSON answer into rows and verify each quote against the record."""
    start, end = answer.find("{"), answer.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in the judge answer")
    data = json.loads(answer[start:end + 1])
    claims = data.get("claims")
    note = str(data.get("summary") or "").strip()[:600]
    if not isinstance(claims, list):
        raise ValueError("the JSON has no 'claims' list")
    record_norm = norm(record_text)
    rows = []
    for item in claims:
        finding = str(item.get("finding", ""))
        verdict = FINDING_TO_VERDICT.get(finding, "Needs Human Verification")
        reason = str(item.get("reason", ""))
        quote = str(item.get("record_quote", ""))
        if finding not in FINDING_TO_VERDICT:
            reason += " [unknown finding]"
        if quote and norm(quote) not in record_norm:
            reason += " [quote NOT found in record]"
            if verdict == "Supported":
                verdict = "Needs Human Verification"
        elif verdict == "Supported" and not quote:
            verdict = "Needs Human Verification"
            reason += " [no supporting quote given]"
        rows.append(make_row("claim", str(item.get("claim", "")), verdict, finding,
                             str(item.get("source_field", "")), quote, reason))
    return rows, note


# ---- Run the checks ----
MIN_WORDS = 20  # a shorter draft is treated as empty or broken

body, placeholders, hashtags = clean_draft(draft)
rows = code_checks(body, hashtags, placeholders, record)
too_short = len(body.split()) < MIN_WORDS

judge_status = "not provided"
ai_note = ""
if judge_answer.strip():
    try:
        judge_part, ai_note = judge_rows(judge_answer, record)
        rows = judge_part + rows
        judge_status = "ok"
    except (ValueError, AttributeError) as error:
        judge_status = "invalid: " + str(error)[:200]

unsupported = sum(1 for r in rows if r["verdict"] == "Unsupported")
to_verify = sum(1 for r in rows if r["verdict"] == "Needs Human Verification")
flags = sum(1 for r in rows if r["kind"] == "flag")
n_placeholders = sum(1 for r in rows if r["kind"] == "placeholder")


def plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


# Counts in plain words (placeholders are expected in every draft, so they are not "problems")
parts = []
if unsupported:
    parts.append("%d unsupported" % unsupported)
if to_verify:
    parts.append("%d to verify" % to_verify)
if flags:
    parts.append(plural(flags, "style flag"))
if n_placeholders:
    parts.append(plural(n_placeholders, "placeholder") + " to fill")
counts = ", ".join(parts)

if too_short:
    overall = "REVIEW: draft is too short (%d words)" % len(body.split())
elif judge_status == "not provided":
    # Without the AI layer a clean result means nothing, so never say "no issues found"
    overall = "CHECK FAILED: no judge answer"
elif judge_status != "ok":
    overall = "CHECK FAILED: judge answer unreadable"
elif unsupported:
    overall = "NOT READY: " + counts
elif to_verify or flags:
    # A style flag (banned word, missing hashtag) is a reason to look, even if the judge found nothing
    overall = "REVIEW: " + counts
else:
    overall = "NO ISSUES FOUND (human review still required)"
    if counts:
        overall += ": " + counts

problems = unsupported + to_verify + flags

# ---- Report for the check file (plain text) ----
LABEL = {"claim": "", "number": "number ", "quote": "quoted text ", "flag": ""}


def problem_line(r):
    if r["kind"] == "flag":
        label = "Style"
    elif r["verdict"] == "Unsupported":
        label = "Unsupported"
    else:
        label = "Verify"
    text = r["text"]
    if r["kind"] == "quote":
        text = '"%s"' % text
    return "- %s: %s%s -- %s" % (label, LABEL[r["kind"]], text, r["reason"])


# Order: unsupported first, then verify, then style flags
problem_rows = [r for r in rows if r["verdict"] == "Unsupported"] \
    + [r for r in rows if r["verdict"] == "Needs Human Verification"] \
    + [r for r in rows if r["kind"] == "flag"]
good = [r for r in rows if r["kind"] == "claim" and r["verdict"] == "Supported"]

judge_ok = judge_status == "ok"
report = ["Result: " + overall, "", "-----", "AI-generated:"]
if judge_ok:
    report.append("Judge summary: " + (ai_note or "none"))
    report += ["", "Problems (%d)" % len(problem_rows)]
    for r in problem_rows:
        report.append(problem_line(r))
        if r["kind"] == "claim" and r["record_quote"]:
            report.append('  Record: "%s"' % r["record_quote"])
    report += ["", "Supported (%d)" % len(good)]
    for r in good:
        report.append('- %s -- Record: "%s"' % (r["text"], r["record_quote"]))
else:
    # No judge answer: no claim lists at all (code findings are in the code checks below)
    reason_text = "judge gave no answer" if judge_status == "not provided" else "judge answer unreadable"
    report.append("Judge summary: not available (%s)" % reason_text)

# Fixed list: every code check is always shown, so a missing line can never mean "not run"
numbers = [r for r in rows if r["kind"] == "number"]
quotes = [r for r in rows if r["kind"] == "quote"]
banned = [r for r in rows if r["kind"] == "flag" and r["reason"].startswith("Banned")]
tags = [r for r in rows if r["kind"] == "flag" and r["reason"].startswith("Approved")]
holders = [r for r in rows if r["kind"] == "placeholder"]
words = len(body.split())


def line(name, found, details=""):
    """0 = nothing found. Details only when something was found."""
    return "%s: %d%s" % (name, len(found), " (%s)" % details if found else "")


report += ["", "-----", "Code checks (Python, rule-based)",
           line("Numbers not in the record", numbers, ", ".join(r["text"] for r in numbers)),
           line("Quoted text not in the record", quotes, "; ".join('"%s"' % r["text"] for r in quotes)),
           line("Banned words", banned, ", ".join(r["text"] for r in banned)),
           "Missing series hashtags: %d%s" % (len([t for t in REQUIRED_TAGS if t not in hashtags]),
                                              " (%s)" % " ".join(t for t in REQUIRED_TAGS if t not in hashtags)
                                              if tags else ""),
           "Draft length: %d words%s" % (words, " (too short, minimum %d)" % MIN_WORDS if too_short else ""),
           line("Placeholders to fill", holders, " ".join(r["text"] for r in holders))]

return {
    "overall": overall,
    "judge_status": judge_status,
    "problems": problems,
    "ai_note": ai_note,
    "report_text": "\n".join(report),
    "rows": rows,
}
