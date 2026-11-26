# Judge for the teasers recorded in the database (task YL-004B).
#
# Reads the queue (view teaser_check_queue) together with the text copy of every teaser (table teaser_inputs),
# runs the same checks as the lab (code first, then the judge), builds the PDF report, uploads it to Storage
# (bucket teaser-reports) and writes ONE row to teaser_checks (status DONE with the raw result, or FAILED with the reason).
# A trigger in the database then updates teasers.judge_result. Nothing is published or sent.
#
# Run:  python -m teaser_check.db_judge --dry-run      (reads the queue, code checks only, writes nothing)
#       python -m teaser_check.db_judge                (the judge for the whole queue)
#       python -m teaser_check.db_judge --teaser 4     (one teaser)
# Environment: SUPABASE_DB_URL, API_KEY, BASE_URL, MODEL_NAME (the judge model); for the PDF in Storage also
# SUPABASE_URL and SUPABASE_SERVICE_KEY. Never print or commit them.

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from claim_check.common import ROOT
from claim_check.config import DailyQuotaExhausted, get_client, get_env
from evidence_fetch.build_pack import build_pack, parse_make_evidence

from .experiment import patient
from .judge import judge_with_llm, judged_lines, load_rubric, no_judge
from .pipeline import check_teaser, overall
from .report import build_report

DEFAULT_RUBRIC = "skills/experiments/n3.md"
BUCKET = "teaser-reports"

QUEUE_SQL = """
select q.teaser_id, q.company_id, q.label, q.version, i.teaser_text, i.evidence_text
from public.teaser_check_queue q
left join public.teaser_inputs i on i.teaser_id = q.teaser_id
{where}
order by q.teaser_id
{limit}
"""

# Same columns, but for one teaser that already has a check (a second look with another rubric).
AGAIN_SQL = """
select t.id as teaser_id, t.company_id, c.label, t.version, i.teaser_text, i.evidence_text
from public.teasers t
join public.companies c on c.id = t.company_id
left join public.teaser_inputs i on i.teaser_id = t.id
where t.id = %s
"""

INSERT_SQL = """
insert into public.teaser_checks
  (teaser_id, company_id, status, model, rubric, statements, judge_verified, judge_flagged, code_errors, review_rows,
   report_path, run_ref, error, result)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def load_offers() -> tuple[str, list]:
    """The approved offer table (built from Tapiwa's sheet by offers_build). One place, shared with the lab."""
    data = json.loads((ROOT / "packs" / "aura_offers_v2.json").read_text(encoding="utf-8"))
    return data["status"], data["offers"]


def pack_from_evidence(company_id: str, label: str, teaser_id: int, evidence_text: str) -> dict:
    """The evidence pack of a teaser: the evidence text the generator saw, as sources S1, S2 ..., plus the offer table."""
    sources = parse_make_evidence(evidence_text)
    status, offers = load_offers()
    pack = build_pack(sources, company_id, f"TEASER-{teaser_id}", label, sources[0]["url"],
                      {"approved_aura_offers_status": status, "approved_aura_offers": offers})
    if os.getenv("OFFERS_TABLE_URL"):  # shown in the report as the link of the offer table
        pack["offers_table_url"] = os.environ["OFFERS_TABLE_URL"]
    if os.getenv("OFFERS_TABLE_DATE"):
        pack["offers_table_date"] = os.environ["OFFERS_TABLE_DATE"]
    return pack


def report_numbers(report_html: str) -> dict:
    """The counts of the report header (the report is the one place that counts statements)."""
    def find(pattern):
        m = re.search(pattern, report_html)
        return [int(x) for x in m.groups()] if m else None

    total = find(r"The teaser has (\d+) statements")
    judge = find(r"of (\d+) statements <b>(\d+) verified \(\d+%\)</b>, (\d+) flagged")
    code = find(r"Errors found there: (\d+)\. Review required by the offer table \(not errors\): (\d+)")
    return {"statements": total[0] if total else None,
            "judge_verified": judge[1] if judge else None, "judge_flagged": judge[2] if judge else None,
            "code_errors": code[0] if code else None, "review_rows": code[1] if code else None}


def make_pdf(report_html: str, pdf_path: Path) -> str | None:
    """HTML -> PDF with headless Chrome. Returns None when it worked, else the reason."""
    chrome = next((c for c in (os.getenv("CHROME_BIN"), "google-chrome", "chromium", "chromium-browser") if c and shutil.which(c)), None)
    if not chrome:
        return "no Chrome found on this machine"
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "report.html"
        page.write_text(report_html, encoding="utf-8")
        cmd = [chrome, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
               f"--print-to-pdf={pdf_path}", page.as_uri()]
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return "Chrome timed out"
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        return f"Chrome made no PDF: {done.stderr.strip()[-200:]}"
    return None


def upload_pdf(object_path: str, pdf_path: Path) -> str | None:
    """Upload to the private bucket with the service key. Returns None when it worked, else the reason."""
    base, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
    if not base or not key:
        return "SUPABASE_URL or SUPABASE_SERVICE_KEY is not set"
    request = urllib.request.Request(
        f"{base.rstrip('/')}/storage/v1/object/{BUCKET}/{object_path}", data=pdf_path.read_bytes(), method="POST",
        headers={"Authorization": f"Bearer {key}", "apikey": key, "Content-Type": "application/pdf", "x-upsert": "false"})
    try:
        urllib.request.urlopen(request, timeout=60).close()
    except urllib.error.HTTPError as error:
        return f"Storage answered {error.code}"
    except urllib.error.URLError as error:
        return f"Storage not reachable: {error.reason}"
    return None


def run_ref() -> str | None:
    """Link to this GitHub Actions run, when it runs there."""
    if os.getenv("GITHUB_RUN_ID") and os.getenv("GITHUB_REPOSITORY"):
        return f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    return None


def check_one(row: dict, judge, model: str, rubric: str, pdf: bool) -> dict:
    """Everything for one teaser. Returns the values of one teaser_checks row (DONE or FAILED)."""
    base = {"teaser_id": row["teaser_id"], "company_id": row["company_id"], "model": model, "rubric": rubric, "run_ref": run_ref()}
    try:
        if not row.get("teaser_text") or not row.get("evidence_text"):
            raise ValueError("no text copy in teaser_inputs for this teaser")
        pack = pack_from_evidence(row["company_id"], row["label"], row["teaser_id"], row["evidence_text"])
        rows, tokens = check_teaser(pack, row["teaser_text"], judge)
    except DailyQuotaExhausted:
        raise
    except Exception as error:  # any failure becomes a FAILED row: the teaser stays in the queue and is tried again
        return {**base, "status": "FAILED", "error": f"{type(error).__name__}: {error}"[:500]}
    title = f"{row['label']} | teaser {row['teaser_id']} (version {row['version']})"
    meta = f"rubric {Path(rubric).stem} | model {model}"
    report_html = build_report([dict(r) for r in rows], row["teaser_text"], title, pack, meta)
    pdf_note, report_path = None, None
    if pdf:
        object_path = f"{row['company_id']}/teaser-{row['teaser_id']}_{Path(rubric).stem}_{model}.pdf"
        with tempfile.TemporaryDirectory() as tmp:
            pdf_file = Path(tmp) / "report.pdf"
            pdf_note = make_pdf(report_html, pdf_file) or upload_pdf(object_path, pdf_file)
        report_path = None if pdf_note else object_path
    result = {"overall": overall(rows, dry_run=judge is no_judge), "tokens": tokens, "pdf_problem": pdf_note,
              "pack_sources": [{"id": s["id"], "url": s["url"], "date_read": s["date_read"]} for s in pack["sources"]],
              "rows": json.loads(json.dumps(rows, default=str))}
    return {**base, "status": "DONE", "report_path": report_path, "result": result, **report_numbers(report_html)}


def save(conn, values: dict) -> None:
    from psycopg.types.json import Jsonb  # imported here: the offline tests run without the package
    result = values.get("result")
    conn.execute(INSERT_SQL, (
        values["teaser_id"], values["company_id"], values["status"], values.get("model"), values.get("rubric"),
        values.get("statements"), values.get("judge_verified"), values.get("judge_flagged"), values.get("code_errors"),
        values.get("review_rows"), values.get("report_path"), values.get("run_ref"), values.get("error"),
        Jsonb(result) if result is not None else None))
    conn.commit()


def read_queue(conn, teaser_id: int | None, limit: int | None, again: bool = False) -> list[dict]:
    if again:  # one named teaser, even if it already has a check: a new row is added, the old one stays
        cur = conn.execute(AGAIN_SQL, [teaser_id])
        names = [d.name for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]
    where, params = ("where q.teaser_id = %s", [teaser_id]) if teaser_id else ("", [])
    sql = QUEUE_SQL.format(where=where, limit="limit %s" if limit else "")
    cur = conn.execute(sql, params + ([limit] if limit else []))
    names = [d.name for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Judge for the teasers in the database (queue: view teaser_check_queue).")
    p.add_argument("--teaser", type=int, help="check only this teaser id")
    p.add_argument("--limit", type=int, help="at most this many teasers (the free Gemini tier has a daily quota)")
    p.add_argument("--dry-run", action="store_true", help="code checks only, no model, nothing is written")
    p.add_argument("--no-pdf", action="store_true", help="do not make or upload the PDF")
    p.add_argument("--rubric", default=os.getenv("JUDGE_RUBRIC", DEFAULT_RUBRIC))
    p.add_argument("--again", action="store_true", help="check the given --teaser once more, even if it already has a check")
    args = p.parse_args(argv)
    if args.again and not args.teaser:
        p.error("--again needs --teaser")

    import psycopg
    conn = psycopg.connect(get_env("SUPABASE_DB_URL"))
    queue = read_queue(conn, args.teaser, args.limit, args.again)
    print(f"Queue: {len(queue)} teaser(s)")
    if args.dry_run:
        judge, model = no_judge, "none (dry run)"
    else:
        model = get_env("MODEL_NAME")
        client = get_client()
        judge = patient(lambda record_text, body: judge_with_llm(record_text, body, client=client, model=model, rubric_path=args.rubric))
        judge.judged_lines = judged_lines(load_rubric(args.rubric))
        print(f"Model: {model}, rubric: {args.rubric}")

    failed = 0
    for row in queue:
        print(f"\n== teaser {row['teaser_id']}: {row['label']} (version {row['version']})")
        try:
            values = check_one(row, judge, model, args.rubric, pdf=not args.no_pdf and not args.dry_run)
        except DailyQuotaExhausted:
            print("Daily quota of the model is used up: stopping. The rest stays in the queue.")
            break
        if values["status"] == "FAILED":
            failed += 1
            print("FAILED:", values["error"])
        else:
            print("Result:", values["result"]["overall"])
            print({k: values.get(k) for k in ("statements", "judge_verified", "judge_flagged", "code_errors", "review_rows")})
            if values["result"]["pdf_problem"]:
                print("PDF problem:", values["result"]["pdf_problem"])
        if not args.dry_run:
            save(conn, values)
            print("Saved to teaser_checks.")
    conn.close()
    return 1 if failed and len(queue) == failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
