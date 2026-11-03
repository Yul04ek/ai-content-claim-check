# Offline tests for teaser_check: no key, no network. The judge is replaced by fakes.
# Run from the repository root:  python tests/test_teaser_check.py
# They prove the code around the judge works. How well the real model judges teasers is measured by the
# suite in cases_teaser/ (python -m teaser_check --suite cases_teaser/cases.json).

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from teaser_check import deterministic as det  # noqa: E402
from teaser_check import judge as jd  # noqa: E402
from teaser_check import pipeline as pl  # noqa: E402
from teaser_check.pack import load_pack, pack_to_text  # noqa: E402

CASES = ROOT / "cases_teaser"
PACK = load_pack(CASES / "pack_Test_001.json")
RECORD = pack_to_text(PACK)


def teaser(name):
    return (CASES / name).read_text(encoding="utf-8")


def rows_for(name):
    text = teaser(name)
    body, _ = det.split_teaser(text)
    return det.deterministic_checks(text, body, PACK, RECORD)


def kinds(rows):
    return [(r["kind"], r["text"]) for r in rows if r["kind"] != "flag"]


def judgement(claim, finding, quote="", ref="none"):
    return jd.ClaimJudgement(claim=claim, finding=finding, source_ref=ref, record_quote=quote, reason="test")


def fake_judge(*items):
    return lambda record_text, body: (list(items), {"input": 0, "output": 0})


def test_pack_text_has_ids_and_hides_nothing():
    assert "FACT F3 [S2]" in RECORD and "SOURCE S1 (https://example.com" in RECORD and "AURA OFFER A1" in RECORD


def test_split_removes_header_and_cuts_sources_and_unknowns():
    body, tail = det.split_teaser(teaser("t1_clean.txt"))
    assert "INTERNAL REVIEW ONLY" not in body and "Sources:" not in body and "Unknown:" not in body
    assert tail.startswith("Sources:") and "revenue" in tail  # the word 'revenue' lives only in the Unknown list


def test_clean_teaser_has_no_deterministic_findings():
    assert rows_for("t1_clean.txt") == []


def test_invented_number_is_found_but_ids_and_hypothesis_numbers_are_not():
    assert ("number", "2") in kinds(rows_for("t2_invented_revenue.txt"))
    assert [t for k, t in kinds(rows_for("t1_clean.txt")) if k == "number"] == []


def test_promise_is_unsupported():
    found = [r for r in rows_for("t4_promise.txt") if r["kind"] == "promise"]
    assert {r["text"].lower() for r in found} == {"guarantee", "fast-tracked"}
    assert all(r["verdict"] == "Unsupported" for r in found)


def test_unlabelled_hypotheses_break_the_rule():
    assert ("rule", "0 labelled hypothesis") in kinds(rows_for("t6_unlabelled.txt"))


def test_unknown_source_id_and_url_are_unsupported():
    k = kinds(rows_for("t8_unknown_source.txt"))
    assert ("ref", "S3") in k and ("url", "https://example.org/news") in k


def test_missing_header_breaks_the_rule():
    assert ("rule", "INTERNAL REVIEW ONLY") in kinds(rows_for("t11_no_header.txt"))


def test_figure_words_are_flags_not_verdicts():
    flags = [r for r in rows_for("t3_growth_claim.txt") if r["kind"] == "flag"]
    assert flags and all(r["verdict"] == "" for r in flags)


def test_supported_with_quote_stays_supported():
    row = jd.apply_rules(judgement("Founded in Germany", "supported", "The company was founded in Germany.", "F2"), RECORD)
    assert row["verdict"] == "Supported"


def test_supported_with_invented_quote_is_downgraded():
    row = jd.apply_rules(judgement("x", "supported", "The company is based in Vienna.", "F2"), RECORD)
    assert row["verdict"] == "Needs Human Verification" and "NOT found" in row["reason"]


def test_supported_without_quote_is_downgraded():
    assert jd.apply_rules(judgement("x", "supported"), RECORD)["verdict"] == "Needs Human Verification"


def test_finding_to_verdict_covers_every_finding():
    from typing import get_args
    assert set(jd.FINDING_TO_VERDICT) == set(get_args(jd.Finding))


def test_parse_tolerates_code_fences():
    reply = '```json\n{"claims": [{"claim": "a", "finding": "supported", "source_ref": "F1", "record_quote": "q", "reason": "r"}]}\n```'
    assert jd.parse_judgements(reply)[0].finding == "supported"


def test_parse_rejects_unknown_finding():
    try:
        jd.parse_judgements('{"claims": [{"claim": "a", "finding": "maybe", "source_ref": "x", "record_quote": "", "reason": "r"}]}')
    except ValueError:
        return
    raise AssertionError("an unknown finding must be rejected")


def test_level_is_worst_verdict():
    ok = {"verdict": "Supported", "kind": "claim"}
    nhv = {"verdict": "Needs Human Verification", "kind": "claim"}
    bad = {"verdict": "Unsupported", "kind": "claim"}
    assert pl.level([ok]) == "READY FOR REVIEW" and pl.level([ok, nhv]) == "REVIEW" and pl.level([ok, nhv, bad]) == "NOT READY"


def test_dry_run_never_says_ready():
    assert "NOT a verdict" in pl.overall([], dry_run=True)


def test_full_flow_with_fake_judge_planted_findings():
    # T9: the judge reports 'overgeneralised' -> REVIEW. T10: 'not_in_pack' -> NOT READY.
    rows, _ = pl.check_teaser(PACK, teaser("t9_overgeneralised.txt"),
                              fake_judge(judgement("customers across the globe", "overgeneralised",
                                                   "The company says it supports customers in three countries.", "F4")))
    assert pl.level(rows) == "REVIEW"
    rows, _ = pl.check_teaser(PACK, teaser("t10_other_company.txt"),
                              fake_judge(judgement("runs a cafe like Morgenrot Kaffee", "not_in_pack")))
    assert pl.level(rows) == "NOT READY"


def test_suite_file_points_to_existing_files_and_levels():
    cases = json.loads((CASES / "cases.json").read_text(encoding="utf-8"))
    assert len(cases) == 11
    for c in cases:
        assert (CASES / c["teaser_file"]).exists() and (CASES / c["pack"]).exists()
        assert c["expect_level"] in pl.LEVELS

# --- Approved offer list and Tapiwa's rules (3 Nov): pack_Test_001_approved.json, cases_teaser_approved/ ---
APPROVED = ROOT / "cases_teaser_approved"
APACK = load_pack(ROOT / "packs" / "pack_Test_001_approved.json")
ARECORD = pack_to_text(APACK)


def approved_rows(name):
    text = (APPROVED / name).read_text(encoding="utf-8")
    body, _ = det.split_teaser(text)
    return det.deterministic_checks(text, body, APACK, ARECORD)


def approved_findings(name):
    return {(r["kind"], r["text"]) for r in approved_rows(name) if r["kind"] != "flag"}


def test_real_aura_teaser_has_no_false_alarms_with_approved_list():
    # Prices, "H1".."H3" and the negated words "revenue"/"traction" in an unknowns sentence are not findings.
    assert approved_rows("a0_aura_real.txt") == []


def test_launchpad_must_be_called_proposed():
    assert ("offer", "AURA Startup Launchpad") in approved_findings("a1_launchpad_final.txt")


def test_sprints_and_managed_execution_are_not_available_yet():
    assert ("offer", "Investor-Ready Sprints and Managed Execution Services") in approved_findings("a2_sprints_available.txt")


def test_text_from_idealapp_dna_is_unsupported():
    rows = approved_rows("a3_idealapp_dna_leak.txt")
    assert any(r["kind"] == "scope" and r["verdict"] == "Unsupported" for r in rows)


def test_price_outside_the_offer_list_is_unsupported():
    prices = {r["text"] for r in approved_rows("a4_wrong_price.txt") if r["kind"] == "price"}
    assert prices == {"$49", "$528"}


def test_studio_acceptance_is_a_promise():
    assert ("promise", "will be accepted") in approved_findings("a5_studio_promise.txt")


def test_price_on_the_wrong_offer_and_need_as_fact_are_left_to_the_judge():
    # Code cannot see these: $99 is a real price, "clearly wants AI support" has no marker word. The judge must catch them.
    assert approved_rows("a6_price_on_wrong_offer.txt") == []
    assert approved_rows("a8_need_as_fact.txt") == []


def test_missing_invitation_is_found():
    assert ("rule", "sign-up invitation") in approved_findings("a7_no_invitation.txt")


def test_offer_rules_do_nothing_when_the_pack_has_no_rules():
    # The first suite (test offer list without rules) must behave exactly as before.
    assert rows_for("t1_clean.txt") == []
    assert not any(r["kind"] in ("offer", "price", "scope") for r in rows_for("t4_promise.txt"))


def test_approved_suite_file_points_to_existing_files():
    cases = json.loads((APPROVED / "cases.json").read_text(encoding="utf-8"))
    assert len(cases) == 9
    for c in cases:
        assert (APPROVED / c["teaser_file"]).exists() and (APPROVED / c["pack"]).exists()
        assert c["expect_level"] in pl.LEVELS


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("ok  ", name)
    print(f"\n{len(tests)} tests passed")
