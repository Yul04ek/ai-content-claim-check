# Intake straight from the database (Supabase / Postgres), without Make.
#
# Reads the sources that have no company yet (group_id empty and note empty), groups them by company label,
# runs the same duplicate check as the Make scenario (identity.match.decide) and writes the result back:
#   NEW / POSSIBLE_DUPLICATE -> a new row in companies, its ID written into group_id of the sources
#   DUPLICATE                -> group_id of the sources set to the existing company (no new company row)
#   INVALID                  -> group_id stays empty, "INVALID: <reason>" written into note
# Nothing is deleted and no existing company row is changed. All writes happen in one transaction.
#
# Run:  python -m identity.db_intake            (dry run: prints the plan, writes nothing)
#       python -m identity.db_intake --apply    (writes)
# The connection string comes from the environment variable SUPABASE_DB_URL (never stored in the code).

import argparse
import json
import os
import sys
import uuid

from identity.match import decide
from identity.make_group import clean, website_candidate

REVIEW_STATE = {"NEW": "SOURCE_CANDIDATE_UNVERIFIED", "POSSIBLE_DUPLICATE": "POSSIBLE_DUPLICATE_HELD"}


def as_list(value):
    """Postgres arrays arrive as lists; tolerate None and '; '-separated text as well."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [v for v in value if v]
    return [v.strip() for v in str(value).split(";") if v.strip()]


def to_candidate(company):
    """A companies row in the shape identity.match.decide expects."""
    return {"group_id": company["id"], "name": company.get("label") or "",
            "candidate_url": company.get("candidate_url") or "",
            "official_domain": company.get("official_domain") or "",
            "domain_history": as_list(company.get("domain_history")),
            "registration_id": company.get("registration_id") or "",
            "registration_verified": bool(company.get("registration_verified")),
            "jurisdiction": company.get("jurisdiction") or "",
            "duplicate_of": company.get("duplicate_of") or "",
            "different_from": as_list(company.get("different_from"))}


def group_sources(rows):
    """Unassigned source rows -> one entry per company label (case and extra spaces ignored), order kept."""
    groups, order = {}, []
    for row in rows:
        key = clean(row.get("company_label")).lower()
        if key not in groups:
            groups[key] = {"label": clean(row.get("company_label")), "items": [], "evidence_ids": []}
            order.append(key)
        g = groups[key]
        g["evidence_ids"].append(row["evidence_id"])
        url = clean(row.get("source_url"))
        if url and url not in [u for u, _ in g["items"]]:
            g["items"].append((url, row.get("source_type")))
    return [groups[k] for k in order]


def plan_intake(unassigned, companies, new_id=None):
    """Decide what to write. Pure function: no database, easy to test.

    unassigned: [{"evidence_id", "company_label", "source_url", "source_type"}]
    companies:  rows of the companies table
    Returns {"companies": [new company rows], "assign": [(evidence_id, group_id)],
             "invalid": [(evidence_id, note)], "log": [readable lines]}
    """
    new_id = new_id or (lambda: "G-" + str(uuid.uuid4()))
    candidates = [to_candidate(c) for c in companies]
    plan = {"companies": [], "assign": [], "invalid": [], "log": []}
    for g in group_sources(unassigned):
        website = website_candidate(g["items"])
        new = {"name": g["label"], "website": website, "sources": [u for u, _ in g["items"]]}
        result = decide(new, candidates)
        status, ids = result["status"], ", ".join(g["evidence_ids"])
        if status == "INVALID":
            note = "INVALID: " + "; ".join(result["problems"])
            plan["invalid"] += [(e, note) for e in g["evidence_ids"]]
            plan["log"].append(f"{ids} {g['label']!r}: {note}")
            continue
        if status == "DUPLICATE":
            target = result["group_id"]
            plan["assign"] += [(e, target) for e in g["evidence_ids"]]
            plan["log"].append(f"{ids} {g['label']!r}: DUPLICATE of {target} ({result['matches'][0]['reason']})")
            continue
        company = {"id": new_id(), "label": g["label"], "candidate_url": website or None,
                   "review_state": REVIEW_STATE[status], "match_status": status,
                   "duplicate_candidates": result["matches"]}
        plan["companies"].append(company)
        plan["assign"] += [(e, company["id"]) for e in g["evidence_ids"]]
        candidates.append(to_candidate(company))  # later groups in the same run are compared with it too
        reasons = "; ".join(m["group_id"] + " - " + m["reason"] for m in result["matches"])
        plan["log"].append(f"{ids} {g['label']!r}: {status} -> new company {company['id']}"
                           + (f" (candidates: {reasons})" if reasons else ""))
    return plan


# ---------- database part (needs psycopg, installed in the GitHub workflow) ----------

SELECT_UNASSIGNED = """
select evidence_id, company_label, source_url, source_type
from sources
where group_id is null and (note is null or note = '')
order by evidence_id
for update"""

SELECT_COMPANIES = """
select id, label, candidate_url, official_domain, domain_history, registration_id,
       registration_verified, jurisdiction, duplicate_of, different_from
from companies"""


def run(apply):
    import psycopg  # imported here so the pure part above works without it
    from psycopg.rows import dict_row

    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        sys.exit("SUPABASE_DB_URL is not set")
    with psycopg.connect(url, row_factory=dict_row) as conn:  # one transaction; rolled back on any error
        unassigned = conn.execute(SELECT_UNASSIGNED).fetchall()
        companies = conn.execute(SELECT_COMPANIES).fetchall()
        plan = plan_intake(unassigned, companies)
        print(f"Sources without a company: {len(unassigned)}; companies in the registry: {len(companies)}")
        for line in plan["log"] or ["nothing to do"]:
            print(" ", line)
        if not apply:
            conn.rollback()
            print("Dry run: nothing written. Run with --apply to write.")
            return
        for c in plan["companies"]:
            conn.execute(
                "insert into companies (id, label, candidate_url, review_state, match_status, duplicate_candidates)"
                " values (%s, %s, %s, %s, %s, %s::jsonb)",
                (c["id"], c["label"], c["candidate_url"], c["review_state"], c["match_status"],
                 json.dumps(c["duplicate_candidates"], ensure_ascii=False)))
        for evidence_id, group_id in plan["assign"]:
            conn.execute("update sources set group_id = %s where evidence_id = %s and group_id is null",
                         (group_id, evidence_id))
        for evidence_id, note in plan["invalid"]:
            conn.execute("update sources set note = %s where evidence_id = %s and group_id is null",
                         (note, evidence_id))
        conn.commit()
        print(f"Written: {len(plan['companies'])} new companies, {len(plan['assign'])} sources linked, "
              f"{len(plan['invalid'])} marked INVALID.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Intake of new sources straight from the database.")
    parser.add_argument("--apply", action="store_true", help="write the result (default: dry run)")
    run(parser.parse_args().apply)
