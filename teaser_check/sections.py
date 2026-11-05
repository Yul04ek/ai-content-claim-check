# Splitting a teaser into its parts, so that each part can be judged with its own rule.
# The parts follow the headings of the teaser: company snapshot, hypotheses, AURA help, sign-up invitation.
# (Source notes are cut off earlier by split_teaser and are checked by code.)

import re
from pathlib import Path

from .judge import judge_with_llm, load_rubric

SECTION_HEADINGS = {
    "snapshot": r"snapshot|company (overview|profile)",
    "hypotheses": r"hypothes",
    "aura_help": r"aura (help|offers?)|relevant aura|applicable (aura )?offers|what we can offer",
    "signup": r"sign-?\s?up",
}
JUDGED = ("snapshot", "hypotheses", "aura_help")  # the parts the model judges; the sign-up text is template text


def heading_name(line: str) -> str | None:
    """A heading is a short line without a full stop that is not a list item and names one of the parts."""
    text = line.strip()
    if not text or text.endswith((".", "!", "?")) or len(text.split()) > 14 or re.match(r"[-*•]|\d+[.)]", text):
        return None
    return next((name for name, pattern in SECTION_HEADINGS.items() if re.search(pattern, text, re.I)), None)


def split_sections(body: str) -> dict[str, str]:
    """Part name -> text (heading line included). Lines before the first heading are 'start'."""
    parts: dict[str, list[str]] = {}
    current = "start"
    for line in body.splitlines():
        name = heading_name(line)
        if name:
            current = name
        parts.setdefault(current, []).append(line)
    return {name: "\n".join(lines).strip() for name, lines in parts.items()}


def section_of_lines(body: str) -> list[tuple[str, str]]:
    """(line, part name) for every line of the body."""
    out, current = [], "start"
    for line in body.splitlines():
        current = heading_name(line) or current
        out.append((line, current))
    return out


def is_sectioned(rubric_path) -> bool:
    return bool(re.search(r"^## SECTION ", Path(rubric_path).read_text(encoding="utf-8"), re.M))


def parse_sectioned_rubric(rubric_path) -> tuple[str, dict[str, str]]:
    """The rubric file has '## COMMON' and one '## SECTION <name>' block per part."""
    pieces = re.split(r"^## (COMMON|SECTION \w+)\s*$", load_rubric(rubric_path), flags=re.M)
    blocks = {pieces[i]: pieces[i + 1].strip() for i in range(1, len(pieces) - 1, 2)}
    common = blocks.pop("COMMON", "")
    return common, {name.removeprefix("SECTION "): text for name, text in blocks.items()}


def judge_sections(record_text: str, body: str, client=None, model=None, rubric_path=None, call=judge_with_llm):
    """One model call per judged part, each with the common rule plus the rule of that part.
    If the teaser has none of the headings, the whole body is judged once with all rules."""
    common, blocks = parse_sectioned_rubric(rubric_path)
    parts = split_sections(body)
    todo = [(name, parts[name], blocks[name]) for name in JUDGED if parts.get(name) and name in blocks]
    if not todo:
        todo = [("whole teaser", body, "\n\n".join(blocks.values()))]
    judgements, tokens = [], {"input": 0, "output": 0}
    for name, text, block in todo:
        got, used = call(record_text, text, client=client, model=model, system_text=common + "\n\n" + block,
                         label=f"TEASER PART ({name})")
        judgements += got
        tokens["input"] += used["input"]
        tokens["output"] += used["output"]
    return judgements, tokens
