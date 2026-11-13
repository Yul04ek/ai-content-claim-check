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


def test_placeholder_line_is_reported_for_a_person_and_hidden_from_the_judge():
    seen = {}

    def judge(record_text, body):
        seen["body"] = body
        return [], {"input": 0, "output": 0}

    text = teaser("t9_overgeneralised.txt").replace(
        "\n\n", "\n\nLimits: [Add: more information needed - AURA AI Free, limits]\n\n", 1)
    rows, _ = pl.check_teaser(PACK, text, judge)
    assert [r["text"] for r in rows if r["kind"] == "placeholder"] == ["[Add: more information needed - AURA AI Free, limits]"]
    assert "Add:" not in seen["body"] and "Limits:" not in seen["body"]


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


def test_distribution_restriction_is_not_self_certification_but_accuracy_claims_are():
    from teaser_check.postchecks import text_checks
    keep = ["This teaser is for internal AURA review only and not for publication or external distribution.",
            "Internal-use only: This teaser is for review purposes and should not be published or shared externally."]
    flag = ["This teaser uses only the supplied evidence and approved AURA offers.",
            "No invented revenue, funding or traction.",
            "Export is one-page, compact, and suitable for internal AURA review."]
    got = {r["text"] for r in text_checks("\n".join(keep + flag), "", "", PACK2) if r["finding"] == "rule_broken"}
    for line in keep:
        assert line not in got
    for line in flag:
        assert line in got


def test_verified_snapshot_heading_is_not_a_wrong_label_and_part_headings_are_not_statements():
    from teaser_check.judge import ClaimJudgement
    from teaser_check.postchecks import coverage_checks, text_checks
    from teaser_check.report import _line_kind
    text = "Verified Company Snapshot\n- Founded in 2021.\nOpportunity Hypotheses\nVerified outcome of the test\n"
    got = {r["text"] for r in text_checks(text, "", "", PACK2) if r["finding"] == "rule_broken"}
    assert "Verified Company Snapshot" not in got
    assert "Verified outcome of the test" in got  # a short "Verified ..." line inside the hypotheses part is still wrong
    heads = ["AURA Help \u2014 What we can offer (approved AURA offers)", "Opportunity Hypotheses (2\u20133 clearly labelled)"]
    j = [ClaimJudgement(claim="Founded in 2021", finding="supported", source_ref="S1", record_quote="x", reason="r")]
    assert coverage_checks("\n".join(heads + ["- Founded in 2021."]), j) == []
    assert [_line_kind(h, "hypotheses") for h in heads] == ["skip", "skip"]


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


def _lab_dir(with_gold=True):
    """A tiny lab set (one teaser, one pack, optional gold v2) in a temporary folder."""
    import json, tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    (d / "p.json").write_text(json.dumps({"group_id": "G", "facts": [], "unknowns": [],
        "sources": [{"id": "S1", "url": "https://a.com/x", "date_read": "2026-11-05", "excerpt": "We started in 2011."}]}))
    (d / "t.txt").write_text("INTERNAL REVIEW ONLY\nWe started in 2011 in Berlin.\nSign up to review.\n")
    (d / "rubric.md").write_text("rubric")
    (d / "lab_set.json").write_text(json.dumps({"name": "lab", "cases": [{"case": "X", "pack": "p.json", "teaser": "t.txt"}]}))
    if with_gold:
        (d / "gold_v2.json").write_text(json.dumps({"X": _gold_case()}))
    return d


def test_experiment_runs_every_repeat_and_logs_v2_table_and_mlflow():
    import csv
    from teaser_check.experiment import load_lab_set, run_experiment
    from teaser_check.judge import no_judge
    d = _lab_dir()
    fake = FakeMlflow()
    out = run_experiment(load_lab_set(d / "lab_set.json"), [str(d / "rubric.md")], "m", 2, lambda r: no_judge,
                         store=str(d / "ml"), out_dir=d / "res", mlflow=fake)
    rows = list(csv.DictReader(open(d / "res" / "experiments_v2.csv", encoding="utf-8-sig")))
    assert len(rows) == 2 and rows[0]["case"] == "X" and rows[0]["model"] == "m" and rows[0]["code_n"] == "2"
    assert not (d / "res" / "experiments.csv").exists()  # the old count (list v1) is gone
    assert [r.split(" ", 1)[-1] for r in fake.runs] == ["rubric@m", "rubric@m r1", "rubric@m r2"]  # names start with the date and time
    assert fake.runs[0][:2] == "20"
    metrics = {k.split(" ", 1)[-1]: v for k, v in fake.metrics.items()}  # without the date and time in front
    assert metrics["rubric@m r1"]["v2_X_code_n"] == 2 and metrics["rubric@m r1"]["v2_X_meant"] == 4
    assert metrics["rubric@m"]["v2_X_code_found_mean"] == 0 and metrics["rubric@m"]["repeats"] == 2
    assert "recall_mean" not in metrics["rubric@m"]
    assert len(out[0]["summaries"]) == 2
    assert (d / "res" / "experiment_runs").is_dir()
    assert fake.uri.startswith("sqlite:///") and fake.uri.endswith("mlflow.db") and fake.artifacts.startswith("file:///")


def test_dry_run_writes_nothing_and_a_missing_gold_v2_stops_the_run():
    from teaser_check.experiment import load_lab_set, run_experiment
    from teaser_check.judge import no_judge
    d = _lab_dir()
    fake = FakeMlflow()
    run_experiment(load_lab_set(d / "lab_set.json"), [str(d / "rubric.md")], "dry-run", 1, lambda r: no_judge,
                   store=str(d / "ml"), out_dir=d / "res", mlflow=fake, dry_run=True)
    assert not (d / "res").exists() and fake.runs == []  # no table, no run folders, no MLflow
    d2 = _lab_dir(with_gold=False)
    try:
        run_experiment(load_lab_set(d2 / "lab_set.json"), [str(d2 / "rubric.md")], "m", 1, lambda r: no_judge, out_dir=d2 / "res")
        raise AssertionError("expected SystemExit")
    except SystemExit as stop:
        assert "gold_v2.json" in str(stop)


def test_experiment_writes_a_readable_report_per_teaser_when_a_judge_ran():
    import json, tempfile
    from pathlib import Path
    from teaser_check.experiment import load_lab_set, run_once
    d = Path(tempfile.mkdtemp())
    (d / "p.json").write_text(json.dumps({"group_id": "G", "facts": [], "unknowns": [],
        "sources": [{"id": "S1", "url": "https://a.com/x", "date_read": "2026-11-05", "excerpt": "We started in 2011."}]}))
    (d / "t.txt").write_text("INTERNAL REVIEW ONLY\nWe started in 2011 in Berlin.\nSign up to review.\n")
    (d / "lab.json").write_text(json.dumps({"name": "lab", "cases": [{"case": "X", "pack": "p.json", "teaser": "t.txt", "items": []}]}))
    judge = lambda rec, body: ([], {"input": 1, "output": 1})
    run_once(load_lab_set(d / "lab.json"), judge, d / "out")
    assert (d / "out" / "report_X.html").exists()


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


def test_patient_judge_stops_at_once_when_the_daily_quota_is_used_up():
    from claim_check.config import DailyQuotaExhausted
    from teaser_check.experiment import patient
    calls = []
    def out_of_quota(rec, body):
        calls.append(1)
        raise DailyQuotaExhausted("429 PerDay")
    waits = []
    try:
        patient(out_of_quota, tries=5, wait=120, sleep=waits.append)("r", "b")
        assert False
    except DailyQuotaExhausted:
        pass
    assert len(calls) == 1 and waits == []


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


def test_experiment_writes_a_readable_report_per_teaser_when_a_judge_ran():
    import json, tempfile
    from pathlib import Path
    from teaser_check.experiment import load_lab_set, run_once
    d = Path(tempfile.mkdtemp())
    (d / "p.json").write_text(json.dumps({"group_id": "G", "facts": [], "unknowns": [],
        "sources": [{"id": "S1", "url": "https://a.com/x", "date_read": "2026-11-05", "excerpt": "We started in 2011."}]}))
    (d / "t.txt").write_text("INTERNAL REVIEW ONLY\nWe started in 2011 in Berlin.\nSign up to review.\n")
    (d / "lab.json").write_text(json.dumps({"name": "lab", "cases": [{"case": "X", "pack": "p.json", "teaser": "t.txt", "items": []}]}))
    judge = lambda rec, body: ([], {"input": 1, "output": 1})
    run_once(load_lab_set(d / "lab.json"), judge, d / "out")
    assert (d / "out" / "report_X.html").exists()


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
    teaser = "Verified snapshot\nTuta has 3 million users worldwide today.\nTuta runs on renewable energy since the start.\nThis line was never looked at by the judge at all."
    rows = [
        {"kind": "claim", "text": "Tuta has 3 million users worldwide today.", "verdict": "Unsupported", "finding": "not_in_pack", "source_field": "none", "record_quote": "", "reason": "Not stated."},
        {"kind": "claim", "text": "Tuta runs on renewable energy since the start.", "verdict": "Supported", "finding": "supported", "source_field": "S1", "record_quote": "renewable energy", "reason": "ok"},
    ]
    pack = {"sources": [{"id": "S1", "url": "https://tuta.com/team", "date_read": "2026-11-05"}]}
    page = build_report(rows, teaser, "Teaser X", pack)
    assert "1 verified (50%)" in page and "1 flagged" in page and "<b>1</b> not checked by anyone" in page
    assert "The teaser has 3 statements" in page and "<b>2</b> read by the judge" in page
    assert "Evidence: S1, https://tuta.com/team, read 2026-11-05" in page and "Nothing in the evidence says this" in page
    assert "renewable energy\u201d" not in page and "<script" not in page  # no duplicated quote, no script


def test_report_counts_code_checked_lines_apart_from_forgotten_lines():
    from teaser_check.report import build_report
    teaser = ("## Company snapshot\nTuta runs on renewable energy since the start.\n## Opportunity hypotheses\n"
              "Offer: AURA AI Free ($0)\nLimits: Monthly AI usage limits apply to every Free account.")
    pack = {"sources": [], "approved_aura_offers": [{"id": "O1", "name": "AURA AI Free", "offer_line": "AURA AI Free ($0)", "text": "AURA AI Free ($0)"}]}
    rows = [{"kind": "claim", "text": "Tuta runs on renewable energy since the start.", "verdict": "Supported", "finding": "supported", "source_field": "S1", "record_quote": "x", "reason": "ok"}]
    page = build_report(rows, teaser, "T", pack)
    assert "The teaser has 3 statements" in page and "<b>2</b> checked by code rules only" in page and "<b>0</b> not checked by anyone" in page
    old_pack = {"sources": []}   # an old pack without table fields: the code does not check these lines
    assert "<b>2</b> not checked by anyone" in build_report(rows, teaser, "T", old_pack)


def test_report_counts_statements_not_lines():
    from teaser_check.report import build_report
    teaser = ("## Company snapshot\nTuta runs on renewable energy since the start. Tuta has offices in Hanover and Berlin today.")
    rows = [{"kind": "claim", "text": "Tuta runs on renewable energy since the start.", "verdict": "Supported", "finding": "supported", "source_field": "S1", "record_quote": "x", "reason": "ok"}]
    page = build_report(rows, teaser, "T", {"sources": []})
    # one line, two statements: one read by the judge, one not checked by anyone
    assert "The teaser has 2 statements" in page and "<b>1</b> read by the judge" in page and "<b>1</b> not checked by anyone" in page
    assert "Nobody checked this statement" in page and "offices in Hanover" in page


def test_report_treats_source_notes_and_sign_up_as_code_checked():
    from teaser_check.report import build_report
    teaser = ("## Company snapshot\nTuta runs on renewable energy since the start.\n\nSource notes\n"
              "https://tuta.com/about, read on 2026-11-04\n\nSign up for AURA AI Free ($0) to review the preliminary Company DNA built from public research about Tuta.")
    rows = [{"kind": "claim", "text": "Tuta runs on renewable energy since the start.", "verdict": "Supported", "finding": "supported", "source_field": "S1", "record_quote": "x", "reason": "ok"}]
    page = build_report(rows, teaser, "T", {"sources": []})
    assert "The teaser has 3 statements" in page and "<b>2</b> checked by code rules only" in page and "<b>0</b> not checked by anyone" in page


def test_code_findings_are_shown_under_their_statement_and_whole_teaser_ones_on_top():
    from teaser_check.report import build_report
    teaser = ("## Company snapshot\nTuta has 3 million users worldwide today.\nTuta runs on renewable energy since the start.\n\nSource notes\n"
              "https://tuta.com/about, read on 2026-11-04")
    rows = [{"kind": "number", "text": "3 million", "verdict": "Needs Human Verification", "finding": "not_in_pack", "reason": "Number not in the pack.", "record_quote": ""},
            {"kind": "rule", "text": "first offer", "verdict": "Needs Human Verification", "finding": "rule_broken", "reason": "Free must come first.", "record_quote": "AURA AI Free ($0)"},
            {"kind": "claim", "text": "Tuta runs on renewable energy since the start.", "verdict": "Supported", "finding": "supported", "source_field": "S1", "record_quote": "x", "reason": "ok"}]
    page = build_report(rows, teaser, "T", {"sources": []})
    assert "About the whole teaser" in page and "Free must come first." in page and "The table says: \u201cAURA AI Free ($0)\u201d" in page
    body = page.split("code checks</h2>")[1]
    first, second = body.index("Tuta has 3 million users"), body.index("Number not in the pack.")
    assert first < second < body.index("Tuta runs on renewable energy")  # the note sits under its own statement
    assert "Automatic checks (code rules, no AI)" not in page  # no separate block at the bottom


def test_short_bullets_are_statements_and_chips_tell_who_checked():
    from teaser_check.report import build_report
    teaser = "## Company snapshot\n- Privacy-friendly by design.\n- 100% Data Ownership\n- Tuta has offices in Hanover and Berlin today."
    rows = [{"kind": "claim", "text": "Privacy-friendly by design.", "verdict": "Supported", "finding": "supported", "source_field": "S1", "record_quote": "x", "reason": "ok"},
            {"kind": "claim", "text": "100% Data Ownership", "verdict": "Supported", "finding": "supported", "source_field": "S1", "record_quote": "x", "reason": "ok"},
            {"kind": "claim", "text": "Tuta has offices in Hanover and Berlin today.", "verdict": "Supported", "finding": "supported", "source_field": "S1", "record_quote": "x", "reason": "ok"},
            {"kind": "number", "text": "100%", "verdict": "Needs Human Verification", "finding": "not_in_pack", "reason": "Number not in the pack.", "record_quote": ""}]
    page = build_report(rows, teaser, "T", {"sources": []})
    assert "The teaser has 3 statements" in page and "<b>3</b> read by the judge" in page
    assert "chip" not in page.split("<body>")[1] and page.count("<b>Judge:</b> verified") == 3  # the teaser text carries no marks
    assert "<b>Code needs" not in page and "Number not in the pack." in page


def test_report_names_what_judge_and_code_compared_with():
    from teaser_check.report import build_report
    teaser = ("## Company snapshot\nTeam of 4 people\n## Opportunity hypotheses\nOffer: AURA AI Free ($0)\n"
              "Evidence: \u201cWe have not written a pitch deck yet.\u201d\nLimits: Monthly AI usage limits.\n\nSource notes\n"
              "https://tallowick.test/about, read on 2026-11-13")
    pack = {"sources": [{"id": "S1", "url": "https://tallowick.test/about", "date_read": "2026-11-13", "page_date": "2026-10-20",
                         "excerpt": "We are four people. We have not written a pitch deck yet."}],
            "approved_aura_offers": [{"id": "O1", "name": "AURA AI Free", "offer_line": "AURA AI Free ($0)", "limits": "Monthly AI usage limits."}],
            "offers_table_url": "https://docs.example/table"}
    rows = [{"kind": "claim", "text": "Team of 4 people", "verdict": "Supported", "finding": "supported", "source_field": "S1", "record_quote": "We are four people.", "reason": "ok"},
            {"kind": "claim", "text": "Evidence: \u201cWe have not written a pitch deck yet.\u201d", "verdict": "Supported", "finding": "supported", "source_field": "S1", "record_quote": "We have not written a pitch deck yet.", "reason": "ok"}]
    page = build_report(rows, teaser, "T", pack)
    # the short snapshot line is a statement; the Evidence line is read by the judge and checked by code
    assert "<b>1</b> read by the judge" in page and "<b>1</b> checked by code rules and read by the judge" in page
    assert "<b>3</b> checked by code rules only" in page and "<b>0</b> not checked by anyone" in page
    assert page.count("<b>Judge:</b> verified. Evidence: S1, https://tallowick.test/about, read 2026-11-13") == 2
    assert "quote found word for word. Evidence: S1, https://tallowick.test/about, read 2026-11-13" in page
    assert page.count("against the offer table. Evidence: O1, offer table: AURA AI Free") == 2   # Offer and Limits lines
    assert "address and read date match the saved source. Evidence: S1" in page
    assert '<a href="https://docs.example/table">the table</a>' in page and "page date 2026-10-20" in page


def test_code_only_lines_say_that_the_check_passed():
    from teaser_check.report import build_report
    teaser = "## Company snapshot\nTuta runs on renewable energy since the start.\n\nSource notes\nhttps://tuta.com/about, read on 2026-11-04"
    rows = [{"kind": "claim", "text": "Tuta runs on renewable energy since the start.", "verdict": "Supported", "finding": "supported", "source_field": "S1", "record_quote": "x", "reason": "ok"}]
    page = build_report(rows, teaser, "T", {"sources": []})
    assert "<b>Code:</b> checked, no errors found." in page and "<b>Judge:</b> verified" in page


def test_missing_source_is_named_under_the_source_list():
    from teaser_check.postchecks import source_note_checks
    from teaser_check.report import build_report
    pack = {"sources": [{"id": "S1", "url": "https://a.com/x", "date_read": "2026-11-05"},
                        {"id": "S2", "url": "https://b.com/y", "date_read": "2026-11-05"}]}
    tail = "https://a.com/x, read on 2026-11-05"
    rows = source_note_checks(tail, pack)
    assert "list only 1 of 2 sources: S2 (https://b.com/y) is missing" in rows[0]["reason"]
    teaser = "## Company snapshot\nA runs on renewable energy since the start.\n\nSource notes\n" + tail + "\n\nSign up for AURA AI Free ($0) to review the preliminary Company DNA built from public research about A."
    page = build_report(rows, teaser, "T", pack)
    assert "About the whole teaser" not in page
    body = page.split("code checks</h2>")[1]
    assert body.index("https://a.com/x, read on") < body.index("S2 (https://b.com/y) is missing") < body.index("Sign up for AURA")


def test_basis_is_asked_only_by_a_rubric_with_a_basis_line_and_unknown_words_count_as_empty():
    from teaser_check.judge import output_format, parse_judgements
    root = jd.SKILL_FILE.parent
    assert '"basis"' not in output_format(jd.load_rubric(root / "experiments" / "n1.md"))
    assert '"basis"' in output_format(jd.load_rubric(root / "experiments" / "n2.md"))
    answer = ('{"claims": [{"claim": "a", "finding": "supported", "source_ref": "S1", "record_quote": "q", "reason": "r", "basis": "Strong"},'
              '{"claim": "b", "finding": "not_in_pack", "source_ref": "none", "record_quote": "", "reason": "r", "basis": "maybe"},'
              '{"claim": "c", "finding": "supported", "source_ref": "S1", "record_quote": "q", "reason": "r"}]}')
    assert [j.basis for j in parse_judgements(answer)] == ["strong", "", ""]


def test_basis_goes_to_the_row_the_csv_and_the_report():
    import csv
    import tempfile
    from teaser_check.pipeline import write_csv
    from teaser_check.report import build_report
    j = jd.ClaimJudgement(claim="Tuta may need a shared workspace for its team.", finding="assumption_as_fact", source_ref="none",
                          record_quote="", reason="Loose.", basis="weak")
    row = jd.apply_rules(j, "SOURCE S1 Tuta makes mail.")
    assert row["basis"] == "weak" and "basis" not in jd.apply_rules(jd.ClaimJudgement(claim="x", finding="not_in_pack", source_ref="none", record_quote="", reason="r"), "t")
    with tempfile.TemporaryDirectory() as tmp:
        write_csv([row], Path(tmp) / "x.csv")
        assert list(csv.DictReader(open(Path(tmp) / "x.csv", encoding="utf-8-sig")))[0]["basis"] == "weak"
    page = build_report([row], "## Opportunity hypotheses\nCompany need: Tuta may need a shared workspace for its team.", "T", {"sources": []})
    assert "Link to the sources: <b>weak</b>" in page


def test_need_and_hypothesis_table_shows_the_answer_of_every_repeat():
    import tempfile
    from teaser_check.basis_report import collect
    gold = {"F": {"rows": [{"part": "Hypotheses/Company need", "type": "statement", "verdict": "Unsupported", "text": "Tuta needs a shared workspace for its large team."},
                           {"part": "Snapshot", "type": "statement", "verdict": "Supported", "text": "Tuta makes mail."}]}}
    with tempfile.TemporaryDirectory() as tmp:
        for n, (finding, basis) in enumerate([("not_in_pack", "none"), ("assumption_as_fact", "weak")], 1):
            d = Path(tmp) / f"2026-11-10_10-00-00_n2_m_r{n}"
            d.mkdir()
            (d / "F.csv").write_text("kind,text,finding,basis\nclaim,Tuta needs a shared workspace for its large team.,%s,%s\n" % (finding, basis), encoding="utf-8-sig")
        rows = collect(gold, tmp, "n2")
    assert len(rows) == 1 and rows[0]["gold"] == "Unsupported" and rows[0]["answers"] == ["no-src/none", "assumed/weak"]


def test_run_info_is_in_the_report_and_in_the_csv():
    import csv
    import tempfile
    from teaser_check.pipeline import write_csv
    from teaser_check.report import build_report, run_meta
    assert run_meta("x/2026-11-10_10-46-33_n2_gemini-3.5-flash-lite_r1") == "2026-11-10 10:46:33 | rubric n2 | model gemini-3.5-flash-lite | repeat 1"
    assert run_meta("x/some_other_folder") == ""
    meta = "2026-11-10 10:46:33 | rubric n2 | model m | repeat 1"
    page = build_report([], "## Company snapshot\nTuta makes mail for companies in Europe.", "Teaser F", {"sources": []}, meta)
    assert f"<title>Teaser F | {meta}</title>" in page and f"Run: {meta}" in page
    with tempfile.TemporaryDirectory() as tmp:
        write_csv([{"case": "F", "id": "x", "run": meta, "kind": "claim", "text": "a", "verdict": "Supported", "finding": "supported"}], Path(tmp) / "x.csv")
        out = list(csv.DictReader(open(Path(tmp) / "x.csv", encoding="utf-8-sig")))
    assert out[0]["run"] == meta and list(out[0])[:3] == ["case", "id", "run"]


def test_nli_signal_takes_the_best_piece_and_averages_per_gold_verdict():
    import tempfile
    from teaser_check.nli_score import best_entailment, chunks, score_run, summary
    pack = {"sources": [{"id": "S1", "url": "u", "date_read": "d", "excerpt": "Tuta makes encrypted mail. " + "filler word " * 100 + "Tuta runs on renewable energy."}],
            "approved_aura_offers": [{"id": "O1", "name": "AURA AI Free", "purpose": "entry", "features": "core workspace"}]}
    pieces = chunks(pack)
    assert len(pieces) >= 3 and pieces[-1][0] == "O1"  # the text is cut into pieces, the offers come last

    def fake(premise, statement):  # a pretend NLI model: entails when the premise holds the key word of the statement
        hit = statement.split()[1] in premise
        return {"entailment": 0.9 if hit else 0.1, "contradiction": 0.0}
    got = best_entailment("Tuta runs on renewable energy since the start.", pieces, fake)
    assert got["entailment"] == 0.9 and got["source"] == "S1"
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "p.json").write_text(json.dumps({**pack, "group_id": "G", "facts": [], "unknowns": []}))
        (d / "lab_set.json").write_text(json.dumps({"cases": [{"case": "F", "pack": "p.json", "teaser": "t.txt"}]}))
        run = d / "runs" / "2026-11-10_10-00-00_n2_m_r1"
        run.mkdir(parents=True)
        (run / "F.csv").write_text("kind,text,finding,basis\nclaim,Tuta runs on renewable energy since the start.,supported,\n"
                                   "claim,Tuta needs a shared workspace for its large team.,not_in_pack,none\n", encoding="utf-8-sig")
        gold = {"F": {"rows": [{"part": "Snapshot", "type": "statement", "verdict": "Supported", "text": "Tuta runs on renewable energy since the start."},
                               {"part": "Hypotheses/Company need", "type": "statement", "verdict": "Unsupported", "text": "Tuta needs a shared workspace for its large team."}]}}
        rows = score_run(gold, d / "runs", d / "lab_set.json", "n2", fake)
    assert [r["gold"] for r in rows] == ["Supported", "Unsupported"] and rows[0]["nli_entailment"] == 0.9 and rows[1]["nli_entailment"] == 0.1
    assert "Snapshot" in summary(rows) and "gold Unsupported" in summary(rows)


def test_nli_pairs_use_the_evidence_line_and_the_offer_of_each_block():
    import tempfile
    from teaser_check.nli_score import score_pairs
    pack = {"group_id": "G", "facts": [], "unknowns": [], "sources": [{"id": "S1", "url": "u", "date_read": "d", "excerpt": "We are raising a seed round."}],
            "approved_aura_offers": [{"id": "O1", "name": "AURA AI Free", "offer_line": "AURA AI Free ($0)", "purpose": "entry", "features": "pitch and document workflows"}]}
    teaser = ("## Opportunity hypotheses\nOffer: AURA AI Free ($0)\nEvidence: \"We are raising a seed round.\"\n"
              "Company need: The company may need pitch material for its seed round.\nHow AURA helps: pitch and document workflows.\n"
              "Limits: x\nHypothesis: The company could prepare its pitch with AURA AI Free.\n")
    seen = []

    def fake(premise, statement):
        seen.append((premise, statement))
        return {"entailment": 0.7, "contradiction": 0.0}
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "p.json").write_text(json.dumps(pack))
        (d / "t.txt").write_text(teaser)
        (d / "lab_set.json").write_text(json.dumps({"cases": [{"case": "F", "pack": "p.json", "teaser": "t.txt"}]}))
        gold = {"F": {"rows": [{"part": "Hypotheses/Company need", "type": "statement", "verdict": "Needs human", "text": "The company may need pitch material for its seed round."}]}}
        rows = score_pairs(gold, d / "lab_set.json", fake)
    assert [r["part"] for r in rows] == ["Company need", "Hypothesis"] and rows[0]["gold"] == "Needs human" and rows[0]["offer"] == "AURA AI Free"
    assert seen[0][0].startswith("We are raising a seed round. AURA offer AURA AI Free:") and "pitch and document workflows" in seen[0][0]
    assert seen[0][1] == "The company may need pitch material for its seed round."
    # the same statement is also scored against the Evidence alone and against the offer alone
    assert seen[1][0] == "We are raising a seed round." and seen[2][0].startswith("AURA offer AURA AI Free:")
    assert seen[1][1] == seen[2][1] == seen[0][1] == seen[3][1] and len(seen) == 8   # both, evidence, offer, best company piece
    assert rows[0]["nli_sources"] == 0.7 and rows[0]["best_source"] == "S1"
    assert rows[0]["nli_evidence"] == 0.7 and rows[0]["nli_offer"] == 0.7 and rows[0]["nli_entailment"] == 0.7


def test_nli_preselects_pieces_and_scores_a_repeated_statement_once():
    import tempfile
    from teaser_check.nli_score import score_run, top_pieces
    pieces = [("S1", "alpha beta gamma delta"), ("S2", "completely unrelated words here"), ("S3", "gamma delta epsilon zeta"), ("O1", "more filler text")]
    assert [p[0] for p in top_pieces("gamma delta epsilon", pieces, 2)] == ["S3", "S1"] and top_pieces("x", pieces, None) == pieces
    calls = []

    def fake(premise, statement):
        calls.append(premise)
        return {"entailment": 0.5, "contradiction": 0.0}
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "p.json").write_text(json.dumps({"group_id": "G", "facts": [], "unknowns": [], "sources": [{"id": "S1", "url": "u", "date_read": "d", "excerpt": "alpha beta gamma"}]}))
        (d / "lab_set.json").write_text(json.dumps({"cases": [{"case": "F", "pack": "p.json", "teaser": "t.txt"}]}))
        for n in (1, 2, 3):  # three repeats of the same judged statement
            run = d / "runs" / f"2026-11-10_10-00-0{n}_n2_m_r{n}"
            run.mkdir(parents=True)
            (run / "F.csv").write_text("kind,text,finding,basis\nclaim,Tuta runs on alpha beta energy.,supported,\n", encoding="utf-8-sig")
        rows = score_run({"F": {"rows": []}}, d / "runs", d / "lab_set.json", "n2", fake)
    assert len(rows) == 3 and len(calls) == 1  # three rows, one model call (one piece, scored once)


def test_quote_joined_with_ellipsis_is_checked_piece_by_piece():
    record = "The team is based in Vienna and has ten people. Elsewhere: it serves customers in three countries."
    assert jd.quote_in_pack("based in Vienna and has ten people... serves customers in three countries", record)
    assert not jd.quote_in_pack("based in Vienna... has a hundred people", record)


def test_role_tags_mark_hypothesis_lines_and_are_stripped_from_claims():
    from teaser_check.roles import tag_hypotheses, strip_tags
    body = ("AURA Opportunity Teaser - X\nVerified company snapshot\n- X makes mail.\n"
            "Opportunity hypotheses (clearly labelled)\n- H1: X could use AURA AI Pro\nWhat it maps to: Company DNA.\n"
            "Rationale: X is based in Germany and serves founders.\nPreconditions/notes: No revenue claims.\n"
            "AURA help and applicable offers\n- AURA AI Free, $0.\n")
    tagged = tag_hypotheses(body).splitlines()
    assert tagged[2] == "- X makes mail."  # outside the hypotheses: unchanged
    assert tagged[4].startswith("[H1 | title]") and tagged[5].startswith("[H1 | aura side]")
    assert tagged[6].startswith("[H1 | rationale]") and tagged[7].startswith("[H1 | test or note]")
    assert tagged[9] == "- AURA AI Free, $0."
    assert strip_tags("[H1 | rationale] X is based in Germany.") == "X is based in Germany."


def test_rubric_can_take_a_finding_out_of_the_list_the_judge_may_choose_from():
    assert "hypothesis_unlabelled" in jd.output_format("plain rubric")
    out = jd.output_format("text\nNO FINDINGS: hypothesis_unlabelled, promise\n")
    assert "hypothesis_unlabelled" not in out and "promise" not in out and "not_in_pack" in out


def _gold_case():
    row = lambda text, typ, verdict, by, prob="", part="Snapshot": {"part": part, "text": text, "type": typ, "verdict": verdict,
                                                                   "by": by, "err": "", "prob": prob, "note": ""}
    return {"title": "X", "whole": [["X9", "700 words", "code"]], "rows": [
        row("We started in 2011 in Berlin", "statement", "Supported", "judge"),
        row("We have 500 customers worldwide", "statement", "Unsupported", "judge", "error"),
        row("Founders always need investors", "statement", "Unsupported", "judge", "error"),
        row("Each founder may like it", "statement", "Needs human", "judge"),
        row("Preconditions: do not promise results", "instruction", "not a claim", "code", "error", "Hypotheses"),
    ]}


def test_v2_scores_what_the_judge_read_found_and_flagged_wrongly():
    from teaser_check.score_v2 import score_case_v2
    rows = [
        {"kind": "claim", "text": "We started in 2011 in Berlin", "finding": "not_in_pack"},      # fine line, flagged: false flag
        {"kind": "claim", "text": "We have 500 customers worldwide", "finding": "not_in_pack"},   # error found
        {"kind": "claim", "text": "Founders always need investors", "finding": "supported"},      # error missed
        {"kind": "rule", "text": "Preconditions: do not promise results", "finding": "rule_broken"},
        {"kind": "flag", "text": "700 words", "finding": ""},
        {"kind": "coverage", "text": "Each founder may like it", "finding": "rule_broken"},        # code row, not a judge answer
    ]
    s = score_case_v2(_gold_case(), rows)
    assert (s["meant"], s["read"], s["errors"], s["found"], s["false_flags"]) == (4, 3, 2, 1, 1)
    assert s["decided"] == 3 and s["right"] == 1  # the Needs-human line was not read, the other two: 1 right of 3
    assert s["code_n"] == 2 and s["code_found"] == 2 and s["missed"] == ["Founders always need investors"]


def test_v2_table_is_per_teaser_and_experiment_writes_it_when_gold_v2_is_there():
    import csv, json, tempfile
    from pathlib import Path
    from teaser_check.experiment import load_lab_set, run_experiment
    from teaser_check.judge import no_judge
    d = Path(tempfile.mkdtemp())
    (d / "p.json").write_text(json.dumps({"group_id": "G", "facts": [], "unknowns": [],
        "sources": [{"id": "S1", "url": "https://a.com/x", "date_read": "2026-11-05", "excerpt": "We started in 2011."}]}))
    (d / "t.txt").write_text("INTERNAL REVIEW ONLY\nWe started in 2011 in Berlin.\nSign up to review.\n")
    (d / "rubric.md").write_text("rubric")
    (d / "lab_set.json").write_text(json.dumps({"name": "lab", "cases": [{"case": "X", "pack": "p.json", "teaser": "t.txt", "items": []}]}))
    (d / "gold_v2.json").write_text(json.dumps({"X": _gold_case()}))
    lab = load_lab_set(d / "lab_set.json")
    assert lab["gold_v2"] is not None
    run_experiment(lab, [str(d / "rubric.md")], "m", 2, lambda r: no_judge, out_dir=d)
    rows = list(csv.DictReader(open(d / "experiments_v2.csv", encoding="utf-8-sig")))
    assert len(rows) == 2 and rows[0]["case"] == "X" and rows[0]["meant"] == "4" and rows[0]["read"] == "0"
    from teaser_check.score_v2 import format_table
    text = format_table("X", "X", {"r": [{"meant": 4, "errors": 2, "code_n": 2, "read": 3, "found": 1, "false_flags": 0,
                                           "right": 2, "decided": 3, "code_found": 2}]})
    assert "the judge is given 4 statements, 2 of them are errors" in text and text.splitlines()[-1].lstrip().startswith("r ")


def test_rubrics_without_hypothesis_unlabelled_do_not_offer_it_to_the_model():
    import teaser_check.judge as judge_module
    from teaser_check.judge import output_format
    from teaser_check.sections import parse_sectioned_rubric
    root = judge_module.SKILL_FILE.parent / "experiments"
    for name in ("t2n", "t3n", "t4bn"):  # whole-teaser rubrics
        assert "hypothesis_unlabelled" not in output_format((root / f"{name}.md").read_text(encoding="utf-8")), name
        assert "hypothesis_without_fact" in output_format((root / f"{name}.md").read_text(encoding="utf-8")), name
    common, blocks = parse_sectioned_rubric(root / "s1n.md")  # part-by-part rubric: every call gets common + one block
    assert blocks and all("hypothesis_unlabelled" not in output_format(common + "\n\n" + b) for b in blocks.values())
    assert all("hypothesis_unlabelled" not in b for b in blocks.values())  # and the rule text is gone too
    for name in ("t2", "s1"):  # the originals still offer it (control)
        text = (root / f"{name}.md").read_text(encoding="utf-8")
        if name == "s1":
            common, blocks = parse_sectioned_rubric(root / "s1.md")
            text = common + "\n\n" + blocks["hypotheses"]
        assert "hypothesis_unlabelled" in output_format(text), name


# --- Offer list v2 (Tapiwa's table, 9 Nov): packs/aura_offers_v2.json, human review kept even when the facts are right ---
V2PACK = load_pack(ROOT / "packs" / "pack_Test_001_approved_v2.json")
V2RECORD = pack_to_text(V2PACK)


def v2_offer_rows(text):
    return {(r["text"], r["verdict"]) for r in det.offer_checks(text, V2PACK, V2RECORD) if r["kind"] == "offer"}


def test_v2_free_needs_no_human_check_but_pro_does_even_when_right():
    assert v2_offer_rows("AURA AI Free ($0) gives a core workspace.") == set()
    assert ("AURA AI Pro", "Needs Human Verification") in v2_offer_rows("AURA AI Pro ($99 per user/month) adds Data Rooms.")


def test_v2_launchpad_and_equity_studio_must_say_proposed_or_in_development():
    assert ("AURA Startup Launchpad", "Needs Human Verification") in v2_offer_rows("AURA Startup Launchpad costs $5,000.")
    rows = det.offer_checks("AURA Startup Launchpad is proposed at $5,000.", V2PACK, V2RECORD)
    assert [r["reason"] for r in rows if "must be described" in r["reason"]] == []
    rows = det.offer_checks("The Launchpad is in development.", V2PACK, V2RECORD)
    assert [r["reason"] for r in rows if "must be described" in r["reason"]] == []
    rows = det.offer_checks("AURA Equity Studio accepts founders.", V2PACK, V2RECORD)
    assert any("must be described as 'proposed'" in r["reason"] for r in rows)


def test_v2_sprints_managed_execution_and_enterprise_are_separate_offers_with_human_check():
    assert v2_offer_rows("Investor-Ready Sprints help you.") == {("Investor-Ready Sprints", "Needs Human Verification")}
    assert v2_offer_rows("Managed Execution Services help you.") == {("Managed Execution Services", "Needs Human Verification")}
    assert v2_offer_rows("AURA AI Enterprise is contact-led.") == {("AURA AI Enterprise", "Needs Human Verification")}


def test_v2_prices_from_the_table_are_known_and_others_are_not():
    body = "AURA AI Pro costs $99 per user/month or $828 per user/year. The Launchpad (proposed) is $5,000."
    assert [r["text"] for r in det.offer_checks(body, V2PACK, V2RECORD) if r["kind"] == "price"] == []
    assert [r["text"] for r in det.offer_checks("AURA AI Pro costs $149.", V2PACK, V2RECORD) if r["kind"] == "price"] == ["$149"]


def test_source_notes_need_a_source_but_not_a_source_id():
    tail = "Source notes\nhttps://cal.com/about, read on 2026-11-04"
    assert [r for r in det.scope_checks("x", "x", tail, {}) if r["text"] == "source notes"] == []
    assert [r for r in det.scope_checks("x", "x", "Source notes\nS1, S2", {}) if r["text"] == "source notes"] == []
    rows = [r for r in det.scope_checks("x", "x", "Source notes\nthe company page", {}) if r["text"] == "source notes"]
    assert rows and "no source address" not in rows[0]["reason"] and "names no source" in rows[0]["reason"]


def test_offer_files_are_built_from_the_table_and_up_to_date():
    from teaser_check import offers_build as ob
    for name, text in ob.build().items():
        assert (ROOT / "packs" / name).read_text(encoding="utf-8") == text, name + ": run python -m teaser_check.offers_build"
    offers = json.loads((ROOT / "packs" / "aura_offers_v2.json").read_text(encoding="utf-8"))["offers"]
    assert [o["id"] for o in offers] == ["O1", "O2", "O3", "O4", "O5", "O6", "O7"]
    assert V2PACK["approved_aura_offers"] == offers


def test_evidence_line_needs_a_quote_from_the_company_sources_not_from_the_offer_list():
    pack = {"sources": [{"id": "S1", "url": "https://a.com", "excerpt": "We publish revenue, growth and team metrics for everyone."}],
            "approved_aura_offers": [{"id": "O1", "name": "AURA AI Free", "text": "AURA AI Free: a free entry point for founders to begin planning."}]}
    ok = 'Offer: X\nEvidence: "publish revenue, growth and team metrics"\nCompany need: y'
    assert det.evidence_line_checks(ok, pack) == []
    from_offer = 'Offer: X\nEvidence: "a free entry point for founders to begin planning"\nCompany need: y'
    assert [r["kind"] for r in det.evidence_line_checks(from_offer, pack)] == ["quote"]
    no_quote = "Offer: X\nEvidence: the company is open about its metrics\nCompany need: y"
    assert [r["kind"] for r in det.evidence_line_checks(no_quote, pack)] == ["rule"]
    missing = "Offer: X\nHypothesis: z\nOffer: Y\nEvidence: \"publish revenue, growth and team metrics\""
    assert [r["kind"] for r in det.evidence_line_checks(missing, pack)] == ["rule"]
    assert det.evidence_line_checks("Hypothesis 1: old format, no Offer lines", pack) == []


def test_evidence_quote_with_dots_is_checked_part_by_part():
    pack = {"sources": [{"id": "S1", "url": "https://a.com", "excerpt": "We publish revenue and growth. Our team metrics are open for everyone."}]}
    skipped = 'Offer: X\nEvidence: "publish revenue ... team metrics are open"\nCompany need: y'
    assert det.evidence_line_checks(skipped, pack) == []
    wrong = 'Offer: X\nEvidence: "publish revenue ... secret plans are open"\nCompany need: y'
    assert [r["kind"] for r in det.evidence_line_checks(wrong, pack)] == ["quote"]


def _block(offer_name, need="Needs a way to keep its plans in order.", limits=None, line=None):
    o = next(x for x in V2PACK["approved_aura_offers"] if x["name"] == offer_name)
    return (f"Offer: {line or o['offer_line']}\nEvidence: \"we build scheduling software\"\nCompany need: {need}\n"
            f"How AURA helps: x\nLimits: {limits if limits is not None else o['limits']}\nHypothesis: y\n")


def test_offer_block_is_checked_against_the_table_word_for_word():
    ok = _block("AURA AI Free") + "\n" + _block("AURA AI Pro")
    assert det.offer_block_checks(ok, V2PACK) == []
    changed = _block("AURA AI Free", limits="Included monthly AI usage; no guaranteed funding.")
    rows = det.offer_block_checks(changed, V2PACK)
    assert [(r["verdict"], r["record_quote"]) for r in rows] == [("Unsupported", next(o for o in V2PACK["approved_aura_offers"] if o["name"] == "AURA AI Free")["limits"])]
    assert [r["verdict"] for r in det.offer_block_checks(_block("AURA AI Free", limits='"' + next(o for o in V2PACK["approved_aura_offers"] if o["name"] == "AURA AI Free")["limits"] + '"'), V2PACK)] == []
    gone = det.offer_block_checks(_block("AURA AI Free", limits="[Add: more information needed - Free, Limits]"), V2PACK)
    assert [r["verdict"] for r in gone] == ["Needs Human Verification"]
    short = det.offer_block_checks(_block("AURA AI Pro", line="AURA AI Pro ($99)") , V2PACK)
    assert any("not word for word" in r["reason"] for r in short)


def test_entry_offer_must_come_first_and_the_need_must_not_copy_the_offer():
    pro_first = _block("AURA AI Pro") + "\n" + _block("AURA AI Free")
    assert [r["text"] for r in det.offer_block_checks(pro_first, V2PACK)] == ["first offer"]
    assert [r["text"] for r in det.offer_block_checks(_block("AURA AI Pro"), V2PACK)] == ["first offer"]
    copied = _block("AURA AI Enterprise", need="A team with tailored workspace configuration and security needs.")
    rows = det.offer_block_checks(_block("AURA AI Free") + "\n" + copied, V2PACK)
    assert len(rows) == 1 and rows[0]["text"].startswith("Company need: A team with tailored workspace")
    assert "tailored workspace configuration" in rows[0]["reason"]


def test_made_up_placeholder_is_reported_and_old_packs_are_skipped():
    body = _block("AURA AI Free") + "How AURA helps: [No data in the reference for this field]\n"
    assert [r["kind"] for r in det.offer_block_checks(body, V2PACK)] == ["placeholder"]
    assert [r["kind"] for r in det.offer_block_checks("Offer: [Add: more information needed - Free, Offer]", V2PACK)] == ["rule"]  # only "first offer": the agreed form is no placeholder row
    assert det.offer_block_checks(_block("AURA AI Free"), {"approved_aura_offers": [{"id": "O1", "name": "AURA AI Free", "text": "x"}]}) == []


def test_quote_ignores_line_breaks_and_a_space_before_the_full_stop_of_the_page_text():
    pack = {"sources": [{"id": "S1", "url": "https://a.com", "excerpt": "To this day, the core of Pirsch is\nopen-source\n. This means the way we collect data is fully transparent."}], "facts": []}
    body = 'Offer: X\nEvidence: "The core of Pirsch is open-source. This means the way we collect data is fully transparent."\nCompany need: y'
    assert det.evidence_line_checks(body, pack) == []
    record = pack["sources"][0]["excerpt"]
    rows = det.deterministic_checks("x\n" + body, body, pack, record)
    assert [r for r in rows if r["kind"] == "quote"] == []


def test_limits_lines_of_the_table_are_no_promise():
    free = next(o for o in V2PACK["approved_aura_offers"] if o["name"] == "AURA AI Pro")
    body = _block("AURA AI Pro")
    assert "guarantee" in free["limits"]
    rows = det.deterministic_checks("x\n" + body, body, V2PACK, V2RECORD)
    assert [r for r in rows if r["kind"] == "promise"] == []
    promise = body + "\nHypothesis: AURA will guarantee investor introductions."
    assert [r["kind"] for r in det.deterministic_checks("x\n" + promise, promise, V2PACK, V2RECORD) if r["kind"] == "promise"] == ["promise"]


def test_lines_checked_by_code_are_not_reported_as_unjudged():
    from teaser_check.postchecks import coverage_checks
    body = ("Offer: AURA AI Pro ($99 per user/month, or $828 per user/year)\nEvidence: \"we build scheduling software for teams of any size.\"\n"
            "Limits: Monthly AI usage limits. Data Rooms are Pro-only.\nCompany need: The firm may need a place for its plans.")
    assert len(coverage_checks(body, [])) == 4
    left = coverage_checks(body, [], ("Evidence", "Offer", "Limits"))
    assert [r["text"][:12] for r in left] == ["Company need"]


def test_new_rubric_n1_loads_and_keeps_the_findings_list():
    from teaser_check.judge import load_rubric, output_format
    text = load_rubric(ROOT / "skills" / "experiments" / "n1.md")
    assert "Company need" in text and "How AURA helps" in text
    assert "hypothesis_unlabelled" not in output_format(text) and "aura_offer_unverified" in output_format(text)


def test_rubric_n3_adds_weak_evidence_and_judges_the_evidence_line():
    from teaser_check.judge import FINDING_TO_VERDICT, ClaimJudgement, judged_lines, load_rubric, output_format
    from teaser_check.postchecks import coverage_checks
    n1, n3 = (load_rubric(ROOT / "skills" / "experiments" / f"{name}.md") for name in ("n1", "n3"))
    assert "weak_evidence" in output_format(n3) and "hypothesis_without_fact" not in output_format(n3)
    assert "weak_evidence" not in output_format(n1) and "weak_evidence" not in output_format("")  # old rubrics are unchanged
    assert FINDING_TO_VERDICT["weak_evidence"] == "Needs Human Verification"
    assert judged_lines(n3) == ("Evidence",) and judged_lines(n1) == ()
    # with n3 an Evidence line the judge skipped is reported; with n1 it is the code's line
    body = "## Opportunity hypotheses\nEvidence: \"We are a team of six people working from two cities.\"\nCompany need: The team may need one shared place for its plans and documents."
    need = [ClaimJudgement(claim="The team may need one shared place for its plans and documents.", finding="supported",
                           source_ref="S1", record_quote="x", reason="r")]
    judge = lambda rec, text: (need, {})
    pack = {"group_id": "X_1", "sources": [{"id": "S1", "url": "https://x-demo.example", "excerpt": "x"}], "facts": [],
            "approved_aura_offers": [{"id": "O1", "name": "AURA AI Free", "offer_line": "AURA AI Free ($0)", "text": "AURA AI Free ($0)"}]}
    assert not coverage_checks(body, need, ("Evidence", "Offer", "Limits"))
    assert len(coverage_checks(body, need, ("Offer", "Limits"))) == 1
    judge.judged_lines = ("Evidence",)
    rows, _ = pl.check_teaser(pack, "DRAFT. INTERNAL REVIEW ONLY.\n" + body, judge)
    assert any(r["kind"] == "coverage" and "team of six" in r["text"] for r in rows)


def test_score_code_finds_whole_teaser_items_by_the_kind_of_rule():
    from teaser_check.score_v2 import score_code
    gold = {"rows": [], "whole": [["F4", "Source notes list 2 of 3 sources", "code"], ["G3", "AURA AI Free is not the first offer", "code"]]}
    rows = [{"kind": "flag", "text": "source notes: S3 address or read date"}, {"kind": "rule", "text": "first offer"}]
    assert score_code(gold, rows)["code_found"] == 2
    assert score_code(gold, rows[:1])["code_found"] == 1 and score_code(gold, [])["code_found"] == 0


def test_company_name_of_the_header_must_appear_in_the_pack():
    from teaser_check.score_v2 import score_code
    pack = {"group_id": "X_1", "sources": [{"id": "S1", "url": "https://acme-demo.example", "excerpt": "Acme Robotics builds arms."}], "facts": []}
    record = "COMPANY: Acme Robotics\nS1: Acme Robotics builds arms."
    def rows_for(name):
        text = f"DRAFT, NOT APPROVED. INTERNAL REVIEW ONLY.\nCompany: {name}\n\n## Company snapshot\nIt builds arms."
        return [r for r in det.deterministic_checks(text, det.split_teaser(text)[0], pack, record) if r["text"].startswith("company name")]
    assert not rows_for("Acme Robotics") and not rows_for("acme robotics")
    typo = rows_for("Acme Robotiks")
    assert len(typo) == 1 and typo[0]["verdict"] == "Needs Human Verification"
    gold = {"rows": [], "whole": [["M0", "Company name misspelled in the input (Acme Robotiks)", "code"]]}
    assert score_code(gold, typo)["code_found"] == 1 and score_code(gold, [])["code_found"] == 0


def test_lab_set_can_name_its_gold_file():
    import tempfile
    from teaser_check.experiment import load_lab_set
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "lab_set.json").write_text(json.dumps({"name": "x", "gold": "gold_v3.json", "cases": []}))
        assert load_lab_set(d / "lab_set.json")["gold_v2"] is None and load_lab_set(d / "lab_set.json")["gold_name"] == "gold_v3.json"
        (d / "gold_v3.json").write_text(json.dumps({"F": _gold_case()}))
        assert list(load_lab_set(d / "lab_set.json")["gold_v2"]) == ["F"]


def test_mlflow_overview_is_read_from_the_database_without_the_mlflow_package():
    import sqlite3
    import tempfile
    from teaser_check.mlflow_export import write_overview
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        con = sqlite3.connect(d / "mlflow.db")
        con.executescript("""
            create table experiments (experiment_id int, name text);
            create table runs (run_uuid text, name text, start_time int, experiment_id int, status text, lifecycle_stage text);
            create table params (key text, value text, run_uuid text);
            create table metrics (key text, value real, timestamp int, run_uuid text, step int);
            create table tags (key text, value text, run_uuid text);
            insert into experiments values (1, 'exp');
            insert into runs values ('p', '2026-11-10 n1@m', 1794303255933, 1, 'FINISHED', 'active');
            insert into runs values ('c', '2026-11-10 n1@m r1', 1794303274125, 1, 'FINISHED', 'active');
            insert into tags values ('mlflow.parentRunId', 'p', 'c');
            insert into params values ('rubric', 'n1', 'c'), ('repeat', '1', 'c');
            insert into metrics values ('v2_F_found', 2, 1, 'c', 0), ('v2_F_meant', 13, 1, 'c', 0), ('v2_F_found_mean', 2.5, 1, 'p', 0);
        """)
        con.commit()
        con.close()
        csv_path, html_path, wide_path = write_overview(str(d), str(d / "out" / "overview"))
        text = csv_path.read_text()
        assert "repeat 1,F,13.0" in text and "mean of repeats,F" in text and "2026-11-10 n1@m r1" in text
        assert "<table>" in html_path.read_text() and "v2_F_found" in wide_path.read_text()


def test_csv_says_who_decided_each_row():
    import csv
    import tempfile
    from teaser_check.pipeline import write_csv
    rows = [{"kind": "claim", "text": "a", "verdict": "Supported", "finding": "supported"},
            {"kind": "claim", "text": "b", "verdict": "Needs Human Verification", "finding": "supported"},  # quote check lowered it
            {"kind": "claim", "text": "c", "verdict": "Unsupported", "finding": "not_in_pack"},
            {"kind": "rule", "text": "first offer", "verdict": "Needs Human Verification", "finding": "rule_broken"},
            {"kind": "coverage", "text": "d", "verdict": "Needs Human Verification", "finding": "rule_broken"},
            {"kind": "citation", "text": "e", "verdict": "Needs Human Verification", "finding": "meaning_shifted"}]
    with tempfile.TemporaryDirectory() as tmp:
        write_csv(rows, Path(tmp) / "x.csv")
        out = list(csv.DictReader(open(Path(tmp) / "x.csv", encoding="utf-8-sig")))
    assert list(out[0]).index("decided_by") == list(out[0]).index("verdict") + 1
    assert [r["decided_by"] for r in out] == ["judge", "judge, lowered by code (quote)", "judge", "code",
                                             "code (the judge did not read it)", "code (checked the judge's source)"]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("ok  ", name)
    print(f"\n{len(tests)} tests passed")
