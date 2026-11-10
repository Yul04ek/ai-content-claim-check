# Layer 2 for teasers: the AI judge. Same method as claim_check/judge.py (claims -> findings -> verdicts,
# quotes verified in code), but its own findings and its own rubric (skills/teaser-judge.md).
# claim_check/ is not touched: the judge for story drafts stays exactly as calibrated.

import re
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, Field, field_validator

from claim_check.common import ROOT, make_row, norm
from claim_check.config import chat, get_client, get_env
from .roles import strip_tags, tag_hypotheses

SKILL_FILE = ROOT / "skills" / "teaser-judge.md"

Finding = Literal[
    "supported", "not_in_pack", "contradicted", "assumption_as_fact", "overgeneralised",
    "meaning_shifted", "promise", "hypothesis_unlabelled", "hypothesis_without_fact", "aura_offer_unverified",
]

# One place to change how findings map to the three verdicts.
FINDING_TO_VERDICT = {
    "supported": "Supported",
    "not_in_pack": "Unsupported",
    "contradicted": "Unsupported",
    "promise": "Unsupported",
    "assumption_as_fact": "Needs Human Verification",
    "overgeneralised": "Needs Human Verification",
    "meaning_shifted": "Needs Human Verification",
    "hypothesis_unlabelled": "Needs Human Verification",
    "hypothesis_without_fact": "Needs Human Verification",
    "aura_offer_unverified": "Needs Human Verification",
}


# How strongly the sources lead to a company need or a hypothesis (asked only when the rubric has a line "BASIS:").
# It is an extra opinion: the verdict still comes from the finding. The words are chosen here (BASIS_TEXT shows them in the report).
BASIS_LEVELS = ("strong", "partial", "weak", "none")


class ClaimJudgement(BaseModel):
    claim: str = Field(description="One statement from the teaser, copied or lightly shortened.")
    finding: Finding
    source_ref: str = Field(description="ID the quote comes from (S1, F2, A1) or 'none'.")
    record_quote: str = Field(description="Words copied exactly from the pack; empty if none.")
    reason: str = Field(description="One short sentence.")
    basis: str = Field(default="", description="strong, partial, weak or none; only for Company need and Hypothesis lines.")

    @field_validator("basis", mode="before")
    @classmethod
    def _known_basis(cls, value):
        value = str(value or "").strip().lower()
        return value if value in BASIS_LEVELS else ""  # anything else counts as "not given"


class JudgementList(BaseModel):
    claims: list[ClaimJudgement]


def load_rubric(path=None) -> str:
    text = Path(path or SKILL_FILE).read_text(encoding="utf-8")
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return text.strip()


def output_format(rubric_text: str = "") -> str:
    """The JSON shape. A rubric line 'NO FINDINGS: a, b' takes those findings out of the list the model may choose from."""
    skip = re.search(r"^NO FINDINGS:\s*(.+)$", rubric_text, re.M)
    skipped = {x.strip() for x in skip.group(1).split(",")} if skip else set()
    findings = ", ".join(f for f in get_args(Finding) if f not in skipped)
    basis = ', "basis": "<strong, partial, weak or none for Company need and Hypothesis lines, else empty>"' \
        if re.search(r"^BASIS:", rubric_text, re.M) else ""
    return ("Return ONLY one JSON object, with no other text and no code fences, in exactly this shape:\n"
            '{"claims": [{"claim": "...", "finding": "<one of: ' + findings + '>", '
            '"source_ref": "<S1, F2, A1 ... or none>", "record_quote": "...", "reason": "..."' + basis + '}]}')


def parse_judgements(text: str) -> list[ClaimJudgement]:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in the answer")
    return JudgementList.model_validate_json(text[start:end + 1]).claims


def judge_with_llm(record_text: str, body: str, client=None, model: str | None = None, bad_json_retries: int = 1,
                   rubric_path=None, system_text=None, label="TEASER"):
    """Ask the model to judge the claims of one teaser (or of one part of it). Returns (judgements, tokens)."""
    client = client or get_client()
    model = model or get_env("MODEL_NAME")
    rubric_text = system_text or load_rubric(rubric_path)
    tagged = "ROLE TAGS" in rubric_text  # the rubric asks for role tags on the hypothesis lines (see roles.py)
    if tagged:
        body = tag_hypotheses(body)
    messages = [
        {"role": "system", "content": rubric_text + "\n\n" + output_format(rubric_text)},
        {"role": "user", "content": f"EVIDENCE PACK\n{record_text}\n\n{label}\n{body}"},
    ]
    tokens = {"input": 0, "output": 0}
    for attempt in range(bad_json_retries + 1):
        reply = chat(client, model=model, messages=messages)
        usage = getattr(reply, "usage", None)
        tokens["input"] += getattr(usage, "prompt_tokens", 0) or 0
        tokens["output"] += getattr(usage, "completion_tokens", 0) or 0
        content = reply.choices[0].message.content or ""
        try:
            found = parse_judgements(content)
            if tagged:
                for j in found:
                    j.claim = strip_tags(j.claim)
            return found, tokens
        except ValueError as error:
            if attempt >= bad_json_retries:
                raise ValueError(f"The judge did not return valid JSON: {str(error)[:300]}") from error
            messages += [{"role": "assistant", "content": content},
                         {"role": "user", "content": f"That answer was not valid ({str(error)[:300]}). "
                                                      "Return only the JSON object in the required shape."}]


def no_judge(record_text: str, body: str):
    """Dry-run judge: skips the AI layer."""
    return [], {"input": 0, "output": 0}


def quote_in_pack(quote: str, record_text: str) -> bool:
    """True if the quote is in the pack. A quote joined with '...' is checked piece by piece (every piece must be there)."""
    if norm(quote) in norm(record_text):
        return True
    pieces = [norm(p) for p in re.split(r"\.{3}|\u2026", quote) if len(norm(p).split()) >= 2]
    return bool(pieces) and all(p in norm(record_text) for p in pieces)


def apply_rules(j: ClaimJudgement, record_text: str) -> dict:
    """Finding -> verdict, and the judge's quote is verified against the pack."""
    verdict = FINDING_TO_VERDICT[j.finding]
    reason = j.reason
    if j.record_quote and not quote_in_pack(j.record_quote, record_text):
        reason += " [quote NOT found in pack]"
        if verdict == "Supported":
            verdict = "Needs Human Verification"
    elif verdict == "Supported" and not j.record_quote:
        verdict = "Needs Human Verification"
        reason += " [no supporting quote given]"
    row = make_row("claim", j.claim, verdict, j.finding, j.source_ref, j.record_quote, reason)
    if j.basis:
        row["basis"] = j.basis
    return row
