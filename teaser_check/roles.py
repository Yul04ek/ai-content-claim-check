"""Role tags for the lines of the hypotheses part, so the judge knows which hypothesis and which kind of line it is reading.
Pure code, no model. A line under the hypotheses heading gets a prefix like [H2 | rationale]. Other lines are left as they are."""
import re


HEAD = re.compile(r"^\s*(?:[-*•]\s*)?(?:H(\d)\b|(\d+)[.)]\s)", re.I)
LABELS = [
    ("aura side", re.compile(r"^\s*[-*•]?\s*(?:what it maps to|expected fit|maps to|aura fit)\s*:", re.I)),
    ("rationale", re.compile(r"^\s*[-*•]?\s*(?:rationale|why)\s*:", re.I)),
    ("test or note", re.compile(r"^\s*[-*•]?\s*(?:outcome(?: we.d test)?|preconditions?(?:/notes)?|notes?)\s*:", re.I)),
    ("statement", re.compile(r"^\s*[-*•]?\s*hypothesis(?: \d+)?\s*(?:\([^)]*\))?\s*:", re.I)),
]
TAG = re.compile(r"\[H\d+ \| [^\]]*\]\s*")


def tag_hypotheses(body: str) -> str:
    from .sections import section_of_lines  # here, not at the top: sections imports judge, judge imports roles
    out, index = [], 0
    for line, part in section_of_lines(body):
        if part != "hypotheses" or not line.strip():
            out.append(line)
            continue
        head = HEAD.match(line)
        label = next((name for name, rx in LABELS if rx.match(line)), None)
        if head and not label:
            index = int(head.group(1) or head.group(2))
            # "H1: <proposal>" or "1) Title" is the title; "1) Hypothesis 1 (...): text" is a statement
            role = "statement" if re.search(r"hypothesis\s*\d*\s*(\([^)]*\))?\s*:", line, re.I) else "title"
        elif label:
            role = label
        elif index:
            role = "text"
        else:
            out.append(line)  # the part's own heading or an intro line before the first hypothesis
            continue
        out.append(f"[H{index} | {role}] {line.strip()}")
    return "\n".join(out)


def strip_tags(text: str) -> str:
    return TAG.sub("", text or "")
