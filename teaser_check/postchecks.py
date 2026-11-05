# Exact checks that need no model, added after the first real data (4 Nov, Cal.com): each one catches
# an error the judge missed. Part 1 looks at the text only; part 2 looks at what the judge returned.

import re
from urllib.parse import urlparse

from claim_check.common import make_row, norm

from .deterministic import ID_REF, words_of

LEAK = re.compile(r"={3,}|ADDITIONAL RULES|END OF (THE )?(ADDITIONAL )?RULES|\{\{|\}\}|\(clearly labelled\)"
                  r"|^[^\w\n]*(important )?disclosures?\b.*$|^[^\w\n]*preconditions?\b.*$|^[-\t ]*do not\b.*$", re.I | re.M)
SELF_CERT = re.compile(r"\bthis (teaser|document|export) (uses|contains|follows|is|has)\b|\bexport is\b|\bno invented\b", re.I)
VERIFIED_HYPOTHESES = re.compile(r"^[^\n]*\bverified\b[^\n]*hypothes[^\n]*$", re.I | re.M)
ADDRESS = re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}/[\w./-]*[\w-]", re.I)


def address_of(url: str) -> str:
    """'https://cal.com/about/' -> 'cal.com/about' (lower case, without scheme, www and a final slash)."""
    p = urlparse(url)
    return (p.netloc.removeprefix("www.") + p.path.rstrip("/")).lower()


def line_of(text: str, match) -> str:
    """The whole line a regex match stands in (at most 160 characters)."""
    start = text.rfind("\n", 0, match.start()) + 1
    end = text.find("\n", match.end())
    return text[start:end if end != -1 else len(text)].strip()[:160]


def text_checks(text: str, body: str, tail: str, pack: dict) -> list[dict]:
    rows = []
    for m in dict.fromkeys(x.group(0).strip() for x in LEAK.finditer(text)):
        rows.append(make_row("rule", m, "Needs Human Verification", "rule_broken", "none",
                             reason="Text from the instructions or a template field leaked into the teaser."))
    for m in dict.fromkeys(line_of(text, x) for x in SELF_CERT.finditer(text)):  # the whole text: a 'Notes' block sits in the tail
        rows.append(make_row("rule", m, "Needs Human Verification", "rule_broken", "none",
                             reason="The teaser vouches for itself. Only the check can say whether it is accurate."))
    for m in dict.fromkeys(x.group(0).strip()[:160] for x in VERIFIED_HYPOTHESES.finditer(text)):
        rows.append(make_row("rule", m, "Needs Human Verification", "rule_broken", "none",
                             reason="Hypotheses cannot be called verified."))
    rows += source_note_checks(tail, pack)
    return rows


def source_note_checks(tail: str, pack: dict) -> list[dict]:
    """The source notes must give every source's address and read date, and name no source that is not in the pack."""
    rows, tail_norm = [], tail.lower()
    sources = pack.get("sources", [])
    if not tail.strip():
        return rows  # a missing section is reported by the 'source notes' rule
    known = {address_of(s["url"]) for s in sources if s["url"].startswith("http")}
    for s in sources:
        if s["url"].startswith("http") and (address_of(s["url"]) not in tail_norm or s.get("date_read", "") not in tail):
            rows.append(make_row("flag", f"source notes: {s['id']} address or read date",
                                 reason=f"Source notes miss the address or the read date of {s['id']}."))
    for m in dict.fromkeys(x.group(0).lower().rstrip(".,;)") for x in ADDRESS.finditer(tail)):
        if not any(m == k or m.startswith(k + "/") for k in known):
            rows.append(make_row("rule", f"source notes: {m}", "Needs Human Verification", "not_in_pack", "none",
                                 reason="Source notes name an address that is not a source in the pack."))
    return rows


def coverage_checks(body: str, judgements) -> list[dict]:
    """Every sentence of the teaser must have been judged. A line no judged claim overlaps is reported."""
    claim_sets = [words_of(j.claim) for j in judgements]
    rows = []
    for line in body.splitlines():
        text = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        words = words_of(text)
        if len(text.split()) < 5 or text.endswith(":"):  # headings and labels are not statements
            continue
        if not any(c and len(c & words) / min(len(c), len(words)) >= 0.6 for c in claim_sets):
            rows.append(make_row("coverage", text[:160], "Needs Human Verification", "rule_broken", "none",
                                 reason="The judge returned no verdict for this statement."))
    return rows


def citation_checks(judgements, pack: dict) -> list[dict]:
    """A claim cites [S1] but the judge's own quote stands in another source: the citation is wrong."""
    rows = []
    sources = {s["id"]: norm(s.get("excerpt", "")) for s in pack.get("sources", [])}
    for j in judgements:
        cited = set(re.findall(r"\bS\d+\b", j.claim))
        if not cited or not j.record_quote:
            continue
        where = {sid for sid, t in sources.items() if norm(j.record_quote) in t}
        if where and not (cited & where):
            rows.append(make_row("citation", j.claim[:160], "Needs Human Verification", "meaning_shifted", ",".join(sorted(cited)),
                                 reason=f"Cites {', '.join(sorted(cited))}, but the supporting text is in {', '.join(sorted(where))}."))
    return rows
