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


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("ok  ", name)
    print(f"\n{len(tests)} tests passed")
