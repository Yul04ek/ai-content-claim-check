# Layer 2: the AI claim judge.
# It splits the draft into claims and compares each one with the record.
# The rubric lives in skills/claim-judge.md, so it can be edited without touching the code.
# The judge's quotes are verified in code: it cannot "support" a claim with words that are not in the record.

from typing import Literal, get_args

from pydantic import BaseModel, Field

from .common import ROOT, make_row, norm
from .config import chat, get_client, get_env

SKILL_FILE = ROOT / "skills" / "claim-judge.md"

Finding = Literal[
    "supported", "not_in_record", "contradicted", "done_not_proposed",
    "assumption_as_fact", "overgeneralised", "qualifier_dropped", "meaning_shifted",
]
SourceField = Literal["SCENARIO", "OBSERVATION", "SEVERITY", "USER IMPACT", "RECOMMENDATION", "none"]

# One place to change how the judge's findings map to the three required verdicts.
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


class ClaimJudgement(BaseModel):
    claim: str = Field(description="One factual statement from the draft, copied or lightly shortened.")
    finding: Finding
    source_field: SourceField
    record_quote: str = Field(description="Words copied exactly from the record; empty if none.")
    reason: str = Field(description="One short sentence.")


class JudgementList(BaseModel):
    claims: list[ClaimJudgement]


def load_rubric() -> str:
    """Read the rubric from the skill file (the text after the front matter)."""
    text = SKILL_FILE.read_text(encoding="utf-8")
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return text.strip()


def output_format() -> str:
    """Tell the model the exact JSON shape. Built from the models above, so they cannot drift apart."""
    findings = ", ".join(get_args(Finding))
    fields = ", ".join(get_args(SourceField))
    return (
        "Return ONLY one JSON object, with no other text and no code fences, in exactly this shape:\n"
        '{"claims": [{"claim": "...", "finding": "<one of: ' + findings + '>", '
        '"source_field": "<one of: ' + fields + '>", "record_quote": "...", "reason": "..."}]}'
    )


def parse_judgements(text: str) -> list[ClaimJudgement]:
    """Parse the model's answer. Tolerates code fences and a few words around the JSON."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in the answer")
    return JudgementList.model_validate_json(text[start:end + 1]).claims


def judge_with_llm(record_text: str, body: str, client=None, model: str | None = None, bad_json_retries: int = 1):
    """Ask the model to judge the claims of one draft. Returns (judgements, tokens)."""
    client = client or get_client()
    model = model or get_env("MODEL_NAME")
    messages = [
        {"role": "system", "content": load_rubric() + "\n\n" + output_format()},
        {"role": "user", "content": f"SOURCE RECORD\n{record_text}\n\nDRAFT\n{body}"},
    ]
    tokens = {"input": 0, "output": 0}
    for attempt in range(bad_json_retries + 1):
        reply = chat(client, model=model, messages=messages)
        usage = getattr(reply, "usage", None)
        tokens["input"] += getattr(usage, "prompt_tokens", 0) or 0
        tokens["output"] += getattr(usage, "completion_tokens", 0) or 0
        content = reply.choices[0].message.content or ""
        try:
            return parse_judgements(content), tokens
        except ValueError as error:  # includes pydantic's ValidationError
            if attempt >= bad_json_retries:
                raise ValueError(f"The judge did not return valid JSON: {str(error)[:300]}") from error
            messages += [
                {"role": "assistant", "content": content},
                {"role": "user", "content": f"That answer was not valid ({str(error)[:300]}). "
                                             "Return only the JSON object in the required shape."},
            ]


def no_judge(record_text: str, body: str):
    """Dry-run judge: skips the AI layer."""
    return [], {"input": 0, "output": 0}


def apply_rules(judgement: ClaimJudgement, record_text: str) -> dict:
    """Turn the judge's finding into a verdict and verify its quote against the record."""
    verdict = FINDING_TO_VERDICT[judgement.finding]
    reason = judgement.reason
    if judgement.record_quote and norm(judgement.record_quote) not in norm(record_text):
        reason += " [quote NOT found in record]"
        if verdict == "Supported":
            verdict = "Needs Human Verification"
    elif verdict == "Supported" and not judgement.record_quote:
        verdict = "Needs Human Verification"
        reason += " [no supporting quote given]"
    return make_row("claim", judgement.claim, verdict, judgement.finding, judgement.source_field,
                    judgement.record_quote, reason)
