# Offline tests: no API key, no network. The model call is replaced by fakes.
# Run from the repository root:  python tests/test_claim_check.py
#
# They prove that the code around the model works. They say nothing about how well the real model judges
# claims; that is measured by the nine cases in cases/cases.json.

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from claim_check import deterministic as det  # noqa: E402
from claim_check import judge as jd  # noqa: E402
from claim_check import pipeline as pl  # noqa: E402

SHEET = ROOT / "testdata" / "BZ021_Test_Copy.csv"
RECORD_F008 = pl.load_record(SHEET, "F-008")
RECORD_TEXT = pl.record_to_text(RECORD_F008)


def read_case(name: str) -> str:
    return (ROOT / "cases" / name).read_text(encoding="utf-8")


def judgement(claim, finding, quote="", field="none", reason="test"):
    return jd.ClaimJudgement(claim=claim, finding=finding, source_field=field, record_quote=quote, reason=reason)


def fake_reply(content, prompt_tokens=10, completion_tokens=5):
    """Looks like the answer of client.chat.completions.create."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


# --- cleaning and deterministic checks ---------------------------------------

def test_clean_draft_removes_header_tags_and_placeholders():
    body, placeholders, hashtags = det.clean_draft(read_case("t5_F008_v3.txt"))
    assert "DRAFT, NOT APPROVED" not in body and "Source row" not in body
    assert "#" not in body and "Suggested topic tags" not in body
    assert "[Add" not in body and len(placeholders) == 1
    assert "#AURABuildLog" in hashtags


def test_clean_draft_handles_inline_hashtags():
    body, _, hashtags = det.clean_draft(read_case("t1_F007_v1.txt"))  # hashtags on the same line as the text
    assert "#" not in body and "usabilitytesting" not in body
    assert "#usabilitytesting" in hashtags


def test_number_not_in_record_needs_human_look_but_record_numbers_pass():
    rows = det.deterministic_checks("Confusion dropped by 30%. Draft reached 40%.", det.REQUIRED_TAGS, [], RECORD_TEXT)
    numbers = [r for r in rows if r["kind"] == "number"]
    assert [r["text"] for r in numbers] == ["30%"]
    assert numbers[0]["verdict"] == "Needs Human Verification"


def test_invented_quote_is_unsupported_but_real_quote_passes():
    body = "Home listed “What is StudioFlow’s target market?” and “All fixed now”."
    rows = det.deterministic_checks(body, det.REQUIRED_TAGS, [], RECORD_TEXT)
    assert [r["text"] for r in rows if r["kind"] == "quote"] == ["All fixed now"]


def test_flags():
    rows = det.deterministic_checks("Founders often worry about it.", [], [], RECORD_TEXT)
    assert {"often"} == {r["text"] for r in rows if r["kind"] == "flag" and "Banned" in r["reason"]}
    assert any("hashtag missing" in r["reason"] for r in rows)


def test_context_dependent_wording_is_left_to_the_judge():
    # "I", "shipped" and section labels can be right or wrong depending on where the claim comes from,
    # so plain Python must not flag them.
    body = "I generated a plan. What happened: we shipped the report, which was fixed."
    rows = det.deterministic_checks(body, det.REQUIRED_TAGS, [], "x")
    assert not [r for r in rows if r["kind"] == "flag"]


# --- verdict rules ------------------------------------------------------------

def test_finding_mapping_to_three_verdicts():
    verdicts = {jd.apply_rules(judgement("c", f), RECORD_TEXT)["verdict"] for f in jd.FINDING_TO_VERDICT}
    assert verdicts <= {"Supported", "Unsupported", "Needs Human Verification"}
    assert jd.apply_rules(judgement("c", "not_in_record"), RECORD_TEXT)["verdict"] == "Unsupported"
    assert jd.apply_rules(judgement("c", "overgeneralised"), RECORD_TEXT)["verdict"] == "Needs Human Verification"


def test_judge_cannot_support_a_claim_with_a_fake_quote():
    fake = judgement("x", "supported", quote="This sentence is not in the record at all", field="OBSERVATION")
    row = jd.apply_rules(fake, RECORD_TEXT)
    assert row["verdict"] == "Needs Human Verification" and "NOT found" in row["reason"]


def test_supported_without_quote_is_downgraded():
    assert jd.apply_rules(judgement("x", "supported"), RECORD_TEXT)["verdict"] == "Needs Human Verification"


def test_supported_with_real_quote_stays_supported():
    quote = "after approval, final application was still pending"
    assert jd.apply_rules(judgement("x", "supported", quote=quote, field="OBSERVATION"), RECORD_TEXT)["verdict"] == "Supported"


# --- reading the model's answer -----------------------------------------------

GOOD_JSON = ('{"claims": [{"claim": "c", "finding": "not_in_record", "source_field": "none", '
             '"record_quote": "", "reason": "r"}]}')


def test_rubric_loads_from_the_skill_file_without_front_matter():
    rubric = jd.load_rubric()
    assert rubric.startswith("You are an independent fact checker") and "name: claim-judge" not in rubric


def test_output_format_lists_every_allowed_finding():
    fmt = jd.output_format()
    assert all(f in fmt for f in jd.FINDING_TO_VERDICT)


def test_parse_accepts_code_fences_and_surrounding_words():
    assert jd.parse_judgements("```json\n" + GOOD_JSON + "\n```")[0].finding == "not_in_record"
    assert jd.parse_judgements("Here you go: " + GOOD_JSON + " Done.")[0].claim == "c"


def test_parse_rejects_unknown_finding_and_missing_json():
    bad = GOOD_JSON.replace("not_in_record", "made_up_value")
    for text in (bad, "no json here"):
        try:
            jd.parse_judgements(text)
        except ValueError:
            continue
        raise AssertionError("expected ValueError")


def test_judge_retries_once_on_invalid_json_and_sums_tokens():
    replies = [fake_reply("sorry, here is prose"), fake_reply(GOOD_JSON)]
    calls = []
    jd.chat = lambda client, **kwargs: (calls.append(kwargs), replies.pop(0))[1]  # replace the real model call
    judgements, tokens = jd.judge_with_llm("RECORD", "body", client=object(), model="m")
    assert len(calls) == 2 and judgements[0].claim == "c"
    assert tokens == {"input": 20, "output": 10}
    assert calls[1]["messages"][-1]["role"] == "user" and "not valid" in calls[1]["messages"][-1]["content"]


def test_judge_gives_up_after_second_invalid_answer():
    jd.chat = lambda client, **kwargs: fake_reply("still not json")
    try:
        jd.judge_with_llm("RECORD", "body", client=object(), model="m")
    except ValueError as error:
        assert "valid JSON" in str(error)
    else:
        raise AssertionError("expected ValueError")


# --- whole pipeline -----------------------------------------------------------

def test_end_to_end_with_fake_judge():
    def fake_judge(record_text, body):
        assert "[Add" not in body and "#" not in body  # the judge never sees placeholders or hashtags
        return [judgement("Confusion dropped by 30%", "not_in_record"),
                judgement("Company DNA showed 0% accepted", "supported",
                          quote="Company DNA initially showed 0% accepted", field="OBSERVATION")], {"input": 10, "output": 5}

    rows, tokens = pl.check_draft(RECORD_F008, read_case("t6_F008_fake_numbers.txt"), fake_judge)
    assert tokens == {"input": 10, "output": 5}
    assert "NOT READY" in pl.overall(rows, dry_run=False)
    assert any(r["kind"] == "claim" and r["verdict"] == "Supported" for r in rows)


def test_dry_run_never_says_no_problems():
    assert "NOT a verdict" in pl.overall([], dry_run=True)
    assert "No problems" not in pl.overall([], dry_run=True)


def test_control_case_has_no_unsupported_and_no_flags():
    rows, _ = pl.check_draft(pl.load_record(SHEET, "F-006"), read_case("t7_F006_clean_control.txt"), jd.no_judge)
    assert not [r for r in rows if r["verdict"] == "Unsupported" or r["kind"] == "flag"]


def test_every_case_file_exists_and_its_id_is_in_the_sheet():
    import json

    for case in json.loads((ROOT / "cases" / "cases.json").read_text(encoding="utf-8")):
        assert (ROOT / "cases" / case["draft_file"]).exists(), case["draft_file"]
        assert pl.load_record(SHEET, case["id"])["SCENARIO"]


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok  ", name)
    print(f"\n{len(tests)} tests passed")
