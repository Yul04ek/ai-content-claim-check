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


def test_sprints_are_found_whatever_the_spelling():
    # Word sets, not an exact phrase: hyphen, spaces, case, singular/plural, word order and "Managed Execution Service(s)".
    for text in ["Investor-Ready Sprints are available.", "We offer an investor ready sprint.", "INVESTOR READY SPRINTS",
                 "Sprints for the ready investor.", "Managed Execution Services help you.", "managed execution"]:
        rows = det.offer_checks(text, APACK, ARECORD)
        assert [r["text"] for r in rows if r["kind"] == "offer"] == [
            "Investor-Ready Sprints and Managed Execution Services"], text


def test_normal_words_do_not_trigger_the_sprints_rule():
    for text in ["AURA AI Pro has investor-readiness tools.", "The team is ready to execute.", "Managed by the founder."]:
        assert det.offer_checks(text, APACK, ARECORD) == [], text


def test_sprints_message_asks_for_a_human_check_not_a_verdict():
    row = det.offer_checks("Investor-Ready Sprints exist.", APACK, ARECORD)[0]
    assert row["verdict"] == "Needs Human Verification" and "human check" in row["reason"]


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


def test_company_price_from_the_page_is_not_flagged_but_an_unknown_price_is():
    from teaser_check.deterministic import offer_checks
    pack = {"approved_aura_offers": [{"id": "A1", "name": "Pro", "text": "AURA AI Pro, $99/month"}],
            "sources": [{"id": "S1", "url": "https://a.com", "excerpt": "Teams cost $12 per seat."}]}
    body = "Their Teams plan is $12 per seat. AURA Pro is $99. Another plan costs $7."
    flagged = [r["text"] for r in offer_checks(body, pack, "")]
    assert flagged == ["$7"], flagged


def test_score_counts_found_missed_and_extra_findings():
    from teaser_check.score import score_case
    rows = [{"kind": "claim", "text": "Open salaries are public [S1]", "verdict": "Needs Human Verification"},
            {"kind": "claim", "text": "Founded in 2021", "verdict": "Supported"},
            {"kind": "flag", "text": "514 words", "verdict": ""},
            {"kind": "claim", "text": "Something odd", "verdict": "Unsupported"}]
    items = [{"id": "1", "match": "open salaries"}, {"id": "2", "match": "founded in 2021"},
             {"id": "3", "match": "words"}, {"id": "4", "match": "email visible"}]
    r = score_case(items, rows)
    assert [i["id"] for i in r["found"]] == ["1", "3"]       # a flag counts; a Supported row does not
    assert [i["id"] for i in r["missed"]] == ["2", "4"]
    assert [x["text"] for x in r["extra"]] == ["Something odd"]
    assert r["recall"] == 0.5


PACK2 = {"group_id": "G", "sources": [
    {"id": "S1", "url": "https://a.com/about", "date_read": "2026-11-04", "excerpt": "We founded in 2021."},
    {"id": "S2", "url": "https://a.com/post", "date_read": "2026-11-04", "excerpt": "Salaries are open and global."}]}


def test_text_checks_find_leaks_self_certification_and_verified_hypotheses():
    from teaser_check.postchecks import text_checks
    text = ("Verified Opportunity Hypotheses (labelled)\nBody.\n=== END OF ADDITIONAL RULES ===\n"
            "Source Notes\nS1\nNotes\n- Export is one-page, compact.\n")
    got = {r["text"] for r in text_checks(text, "Body.", "Source Notes\nS1\nNotes\n- Export is one-page, compact.\n", PACK2)}
    assert "Verified Opportunity Hypotheses (labelled)" in got
    assert "- Export is one-page, compact." in got
    assert any("END OF ADDITIONAL RULES" in x for x in got) and "===" in got


def test_source_notes_need_address_and_date_and_may_not_name_other_addresses():
    from teaser_check.postchecks import source_note_checks
    good = "Source notes\nS1: a.com/about, read 2026-11-04\nS2: a.com/post, read 2026-11-04"
    assert source_note_checks(good, PACK2) == []
    bad = "Source notes\nS1: about page\nS2: a.com/post, read 2026-11-04\nAlso a.com/open"
    rows = source_note_checks(bad, PACK2)
    assert [r["text"] for r in rows if r["kind"] == "flag"] == ["source notes: S1 address or read date"]
    assert [r["text"] for r in rows if r["verdict"]] == ["source notes: a.com/open"]


def test_coverage_reports_statements_the_judge_skipped_but_not_headings():
    from teaser_check.judge import ClaimJudgement
    from teaser_check.postchecks import coverage_checks
    body = "Relevant AURA help for the company:\n- The company was founded in 2021 by two people.\n- Sign up now and it is free of any obligation."
    j = [ClaimJudgement(claim="The company was founded in 2021", finding="supported", source_ref="S1", record_quote="x", reason="r")]
    assert [r["text"] for r in coverage_checks(body, j)] == ["Sign up now and it is free of any obligation."]


def test_wrong_citation_is_found_from_the_judges_own_quote():
    from teaser_check.judge import ClaimJudgement
    from teaser_check.postchecks import citation_checks
    ok = ClaimJudgement(claim="Founded in 2021 [S1]", finding="supported", source_ref="S1", record_quote="We founded in 2021.", reason="r")
    wrong = ClaimJudgement(claim="Open salaries [S1]", finding="supported", source_ref="S1", record_quote="Salaries are open and global.", reason="r")
    assert [r["text"] for r in citation_checks([ok, wrong], PACK2)] == ["Open salaries [S1]"]


def test_negated_promise_and_h_tags_and_created_line():
    from teaser_check.deterministic import deterministic_checks, split_teaser
    pack = {"group_id": "G", "facts": [], "unknowns": [], "sources": [{"id": "S1", "url": "https://a.com/x", "date_read": "2026-11-05", "excerpt": "x"}]}
    text = ("Created: 2026-11-05 12:06\nINTERNAL REVIEW ONLY\n- H1: first\n- H2: second\n"
            "Studio terms are not guaranteed.\nSign up to review.\n")
    body, _ = split_teaser(text)
    rows = deterministic_checks(text, body, pack, "")
    texts = [r["text"] for r in rows]
    assert "guaranteed" not in texts                      # negated, no promise
    assert not any("labelled hypothes" in t for t in texts)  # H1/H2 count as hypotheses
    assert "12" not in texts and "06" not in texts        # the Created line is not teaser text


def test_instruction_text_in_the_teaser_is_a_leak():
    from teaser_check.postchecks import text_checks
    text = "Opportunity hypotheses (clearly labelled)\nImportant disclosures\n- Do not promise investment.\n"
    got = {r["text"] for r in text_checks(text, text, "", PACK2)}
    assert {"(clearly labelled)", "Important disclosures", "- Do not promise investment."} <= got


def test_page_numbers_split_over_lines_numbered_hypotheses_and_crlf():
    from teaser_check.deterministic import deterministic_checks, split_teaser
    pack = {"group_id": "G", "facts": [], "unknowns": [],
            "sources": [{"id": "S1", "url": "https://a.com/p", "date_read": "2026-11-05", "excerpt": "Plus $\n12\n/month"}],
            "approved_aura_offers": [{"id": "O1", "name": "AURA AI Free", "match": "AURA AI Free", "text": "AURA AI Free, $0: workspace."}]}
    text = ("Created: 2026-11-05 12:25\r\nINTERNAL REVIEW ONLY\r\nOpportunity hypotheses\r\n1) First\r\n- Rationale: x\r\n"
            "2) Second\r\nPlus costs $12/month.\r\nSign up to review.\r\n")
    body, _ = split_teaser(text.replace("\r", ""))
    texts = [r["text"] for r in deterministic_checks(text, body, pack, "Plus $\n12\n/month")]
    assert "$12" not in texts and "12" not in texts       # the page price is not an invention
    assert not any("labelled hypothes" in t for t in texts)  # "1)" and "2)" count


class FakeMlflow:
    """Records what the experiment runner logs (the real package is not installed in the sandbox)."""
    def __init__(self):
        self.runs, self.stack, self.params, self.metrics = [], [], {}, {}
    def set_tracking_uri(self, uri): self.uri = uri
    def set_experiment(self, name): self.experiment = name
    def get_experiment_by_name(self, name): return None
    def create_experiment(self, name, artifact_location=None): self.artifacts = artifact_location
    def start_run(self, run_name=None, nested=False):
        self.stack.append(run_name); self.runs.append(run_name); me = self
        class Ctx:
            def __enter__(self): return self
            def __exit__(self, *a): me.stack.pop()
        return Ctx()
    def end_run(self): self.stack.pop()
    def log_params(self, d): self.params[self.stack[-1]] = d
    def log_metrics(self, d): self.metrics.setdefault(self.stack[-1], {}).update(d)
    def log_metric(self, k, v): self.metrics.setdefault(self.stack[-1], {})[k] = v
    def log_artifacts(self, *a, **k): pass
    def log_artifact(self, *a, **k): pass


def test_experiment_runs_every_repeat_and_logs_table_and_mlflow():
    import csv, json, tempfile
    from pathlib import Path
    from teaser_check.experiment import load_lab_set, run_experiment
    from teaser_check.judge import no_judge
    d = Path(tempfile.mkdtemp())
    (d / "p.json").write_text(json.dumps({"group_id": "G", "facts": [], "unknowns": [],
        "sources": [{"id": "S1", "url": "https://a.com/x", "date_read": "2026-11-05", "excerpt": "We started in 2011."}]}))
    (d / "t.txt").write_text("INTERNAL REVIEW ONLY\nWe grew 40% last year.\nSign up to review.\n")
    (d / "rubric.md").write_text("rubric")
    (d / "lab.json").write_text(json.dumps({"name": "lab", "cases": [{"case": "X", "pack": "p.json", "teaser": "t.txt",
        "items": [{"id": "X1", "match": "40%", "why": "invented"}, {"id": "X2", "match": "nothing like this", "why": "x"}]}]}))
    fake = FakeMlflow()
    out = run_experiment(load_lab_set(d / "lab.json"), [str(d / "rubric.md")], "m", 2, lambda r: no_judge,
                         store=str(d / "ml"), table=d / "t.csv", runs_dir=d / "runs", mlflow=fake)
    rows = list(csv.DictReader(open(d / "t.csv", encoding="utf-8-sig")))
    assert len(rows) == 2 and rows[0]["found"] == "1" and rows[0]["total"] == "2" and rows[0]["recall"] == "0.5"
    assert fake.runs == ["rubric@m", "rubric@m r1", "rubric@m r2"]
    assert fake.metrics["rubric@m r1"]["item_X1"] == 1 and fake.metrics["rubric@m r1"]["item_X2"] == 0
    assert fake.metrics["rubric@m"]["recall_mean"] == 0.5 and fake.metrics["rubric@m"]["hit_rate_X1"] == 1.0
    assert len(out[0]["summaries"]) == 2
    assert fake.uri.startswith("sqlite:///") and fake.uri.endswith("mlflow.db") and fake.artifacts.startswith("file:///")


def test_patient_judge_retries_after_a_failure_and_gives_up_in_the_end():
    from teaser_check.experiment import patient
    calls = []
    def flaky(rec, body):
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("503")
        return [], {"input": 1, "output": 1}
    waits = []
    assert patient(flaky, tries=5, wait=7, sleep=waits.append)("r", "b") == ([], {"input": 1, "output": 1})
    assert len(calls) == 3 and waits == [7, 7]
    def always(rec, body): raise RuntimeError("503")
    try:
        patient(always, tries=2, wait=0, sleep=lambda s: None)("r", "b")
        assert False
    except RuntimeError:
        pass


SECTIONED_BODY = ("AURA Opportunity Teaser - X\nVerified company snapshot\n- X makes mail.\n"
                  "Opportunity hypotheses (labelled)\n1) H one\n- Rationale: a long enough statement about X here.\n"
                  "AURA help and applicable offers\n- AURA AI Free, $0.\nSign-up invitation to review\n- Sign up to review the DNA of X.\n")


def test_teaser_is_split_into_its_parts():
    from teaser_check.sections import split_sections, section_of_lines
    parts = split_sections(SECTIONED_BODY)
    assert list(parts) == ["start", "snapshot", "hypotheses", "aura_help", "signup"]
    assert "X makes mail" in parts["snapshot"] and "Rationale" in parts["hypotheses"] and "Free" in parts["aura_help"]
    assert dict(section_of_lines(SECTIONED_BODY))["- Sign up to review the DNA of X."] == "signup"


def test_sectioned_rubric_is_detected_and_each_part_gets_its_own_rule():
    from teaser_check.judge import ClaimJudgement
    from teaser_check.sections import is_sectioned, judge_sections
    import teaser_check.judge as judge_module
    root = judge_module.SKILL_FILE.parent
    assert is_sectioned(root / "experiments" / "s1.md") and not is_sectioned(root / "teaser-judge.md")
    calls = []
    def fake(record, text, client=None, model=None, system_text=None, label=None):
        calls.append((label, system_text))
        return [ClaimJudgement(claim=label, finding="supported", source_ref="S1", record_quote="q", reason="r")], {"input": 2, "output": 1}
    got, tokens = judge_sections("pack", SECTIONED_BODY, rubric_path=root / "experiments" / "s1.md", call=fake)
    assert [c[0] for c in calls] == ["TEASER PART (snapshot)", "TEASER PART (hypotheses)", "TEASER PART (aura_help)"]
    assert "company snapshot" in calls[0][1] and "opportunity hypotheses" in calls[1][1] and "what AURA offers" in calls[2][1]
    assert "company snapshot" not in calls[1][1] and tokens == {"input": 6, "output": 3} and len(got) == 3


def test_teaser_without_headings_is_judged_whole_and_signup_is_not_a_coverage_gap():
    from teaser_check.judge import ClaimJudgement
    from teaser_check.postchecks import coverage_checks
    from teaser_check.sections import judge_sections
    import teaser_check.judge as judge_module
    root = judge_module.SKILL_FILE.parent
    seen = []
    def fake(record, text, client=None, model=None, system_text=None, label=None):
        seen.append(label); return [], {"input": 0, "output": 0}
    judge_sections("pack", "Just some plain text without any heading in it at all.", rubric_path=root / "experiments" / "s1.md", call=fake)
    assert seen == ["TEASER PART (whole teaser)"]
    assert coverage_checks(SECTIONED_BODY, []) and not any("Sign up" in r["text"] for r in coverage_checks(SECTIONED_BODY, []))


def test_html_report():
    from teaser_check.report import build_report
    teaser = "Intro line here.\nTuta has 3 million users worldwide today.\nTuta runs on renewable energy."
    rows = [
        {"kind": "claim", "text": "Tuta has 3 million users worldwide today.", "verdict": "Unsupported", "finding": "not_in_pack", "record_quote": "", "reason": "Not stated."},
        {"kind": "claim", "text": "Tuta runs on renewable energy.", "verdict": "Supported", "finding": "supported", "record_quote": "renewable energy", "reason": "ok"},
    ]
    page = build_report(rows, teaser, "Teaser X")
    assert "<mark" in page and "Judge comments (model) (1)" in page and "Nothing in the evidence says this" in page
    assert "1 with a quote confirmed in the evidence, 0 without" in page and "<script" not in page


def test_quote_joined_with_ellipsis_is_checked_piece_by_piece():
    record = "The team is based in Vienna and has ten people. Elsewhere: it serves customers in three countries."
    assert jd.quote_in_pack("based in Vienna and has ten people... serves customers in three countries", record)
    assert not jd.quote_in_pack("based in Vienna... has a hundred people", record)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("ok  ", name)
    print(f"\n{len(tests)} tests passed")
