# Offline tests for teaser_check/db_judge.py: no database, no key, no network.
# The database is a fake connection, the judge is replaced by fakes, PDF and Storage are switched off or faked.
# Run from the repository root:  python tests/test_db_judge.py
# NOT tested here: the real database, the real model, Chrome on the GitHub runner, Supabase Storage.

import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from teaser_check import db_judge as dj  # noqa: E402
from teaser_check.judge import no_judge  # noqa: E402

EVIDENCE = ("SOURCE: https://example.com/team, read on 2026-11-20\nPAGE DATE: none shown\n"
            "Tallowick is a small team of four people. We opened sign-up for our first customers in October.\n"
            "SOURCE: https://example.com/news, read on 2026-11-21\nPAGE DATE: 2026-09-15\n"
            "Northpier picked Tallowick for its autumn cohort.\n")
TEASER = """DRAFT, NOT APPROVED. INTERNAL REVIEW ONLY.
Company: Tallowick
Company ID: G-test
Evidence file: G-test.md
Created: 2026-11-24 14:00

AURA Opportunity Teaser: Tallowick

## Company snapshot
Tallowick is a small team of four people.

## Opportunity hypotheses
Offer: AURA AI Free ($0)
Evidence: "opened sign-up for our first customers"
Company need: Keeping plans and documents in order while the team grows.
How AURA helps: AURA chat and guidance; core workspace.
Limits: Monthly AI usage limits. Data Rooms, investor pipeline, analytics, Meeting Copilot and custom agents are Pro-only. No guaranteed funding.
Hypothesis: Tallowick may use the core workspace to keep plans in order after opening sign-up.

## Source notes
SOURCE: https://example.com/team, read on 2026-11-20
SOURCE: https://example.com/news, read on 2026-11-21

Sign up for AURA AI Free ($0) to review the preliminary Company DNA built from public research about Tallowick. Free includes monthly AI usage limits."""
ROW = {"teaser_id": 4, "company_id": "G-test", "label": "Tallowick", "version": 1,
       "teaser_text": TEASER, "evidence_text": EVIDENCE}


def test_pack_from_evidence():
    pack = dj.pack_from_evidence("G-test", "Tallowick", 4, EVIDENCE)
    assert [s["id"] for s in pack["sources"]] == ["S1", "S2"]
    assert pack["sources"][1]["page_date"] == "2026-09-15" and pack["website"] == "https://example.com/team"
    assert pack["group_id"] == "G-test" and len(pack["approved_aura_offers"]) == 7  # the offer table is in the pack


def test_done_row_without_pdf():
    values = dj.check_one(ROW, no_judge, "none", "skills/experiments/n3.md", pdf=False)
    assert values["status"] == "DONE" and values["report_path"] is None
    assert values["result"]["rows"] is not None and values["result"]["overall"].startswith("DRY RUN")
    assert values["statements"] and values["code_errors"] is not None  # numbers read from the report header
    json.dumps(values["result"])  # the raw result can be stored as JSON


def test_missing_text_gives_failed_row():
    values = dj.check_one({**ROW, "teaser_text": None}, no_judge, "m", "r", pdf=False)
    assert values["status"] == "FAILED" and "teaser_inputs" in values["error"]
    values = dj.check_one({**ROW, "evidence_text": "no source line here"}, no_judge, "m", "r", pdf=False)
    assert values["status"] == "FAILED" and values["error"]


def test_report_numbers():
    html = ("<b>The teaser has 28 statements</b> x <b>Judge:</b> of 17 statements <b>15 verified (88%)</b>, 2 flagged. "
            "Errors found there: 3. Review required by the offer table (not errors): 2.<br>")
    assert dj.report_numbers(html) == {"statements": 28, "judge_verified": 15, "judge_flagged": 2, "code_errors": 3, "review_rows": 2}
    assert dj.report_numbers("nothing")["statements"] is None


def test_pdf_problem_is_recorded_not_fatal():
    saved = (dj.make_pdf, dj.upload_pdf)
    try:
        dj.make_pdf = lambda html, path: "no Chrome found on this machine"
        values = dj.check_one(ROW, no_judge, "m", "r.md", pdf=True)
        assert values["status"] == "DONE" and values["report_path"] is None
        assert values["result"]["pdf_problem"] == "no Chrome found on this machine"
        dj.make_pdf = lambda html, path: (path.write_bytes(b"%PDF-1.4 test") and None)
        dj.upload_pdf = lambda object_path, path: None
        values = dj.check_one(ROW, no_judge, "m", "r.md", pdf=True)
        assert values["report_path"] == "G-test/teaser-4_r_m.pdf" and values["result"]["pdf_problem"] is None
        dj.upload_pdf = lambda object_path, path: "Storage answered 403"
        values = dj.check_one(ROW, no_judge, "m", "r.md", pdf=True)
        assert values["report_path"] is None and values["result"]["pdf_problem"] == "Storage answered 403"
    finally:
        dj.make_pdf, dj.upload_pdf = saved


def test_upload_needs_keys():
    import os
    old = {k: os.environ.pop(k, None) for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY")}
    try:
        assert "not set" in dj.upload_pdf("x/y.pdf", ROOT / "README.md")
    finally:
        os.environ.update({k: v for k, v in old.items() if v})


class FakeConn:
    def __init__(self):
        self.calls, self.committed = [], 0

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self

    def commit(self):
        self.committed += 1


def test_save_writes_one_row_with_matching_columns():
    fake = types.ModuleType("psycopg.types.json")
    fake.Jsonb = lambda v: ("JSONB", v)
    saved = {k: sys.modules.get(k) for k in ("psycopg", "psycopg.types", "psycopg.types.json")}
    sys.modules.update({"psycopg": types.ModuleType("psycopg"), "psycopg.types": types.ModuleType("psycopg.types"), "psycopg.types.json": fake})
    try:
        conn = FakeConn()
        values = dj.check_one(ROW, no_judge, "m", "r.md", pdf=False)
        dj.save(conn, values)
        sql, params = conn.calls[0]
        assert "insert into public.teaser_checks" in sql and conn.committed == 1
        assert len(params) == sql.count("%s") == 14 and params[0] == 4 and params[2] == "DONE" and params[-1][0] == "JSONB"
        dj.save(conn, {"teaser_id": 4, "company_id": "G-test", "status": "FAILED", "error": "boom"})
        assert conn.calls[1][1][2] == "FAILED" and conn.calls[1][1][-1] is None  # no result for a failed run
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def test_read_queue_builds_the_query():
    class Cur:
        description = [types.SimpleNamespace(name=n) for n in ("teaser_id", "label")]

        def fetchall(self):
            return [(4, "Tallowick")]

    class Conn:
        def execute(self, sql, params):
            self.sql, self.params = sql, params
            return Cur()

    conn = Conn()
    assert dj.read_queue(conn, 4, 2) == [{"teaser_id": 4, "label": "Tallowick"}]
    assert "where q.teaser_id = %s" in conn.sql and "limit %s" in conn.sql and conn.params == [4, 2]
    dj.read_queue(conn, None, None)
    assert "where" not in conn.sql and conn.params == []


def test_run_ref_only_on_github():
    import os
    old = {k: os.environ.pop(k, None) for k in ("GITHUB_RUN_ID", "GITHUB_REPOSITORY")}
    try:
        assert dj.run_ref() is None
        os.environ.update({"GITHUB_RUN_ID": "77", "GITHUB_REPOSITORY": "a/b"})
        assert dj.run_ref() == "https://github.com/a/b/actions/runs/77"
    finally:
        for k in ("GITHUB_RUN_ID", "GITHUB_REPOSITORY"):
            os.environ.pop(k, None)
        os.environ.update({k: v for k, v in old.items() if v})


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("ok  ", name)
    print(f"\n{len(tests)} tests passed")
