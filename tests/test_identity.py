# Offline tests for identity/match.py (company ID and duplicate detection). Run: python tests/test_identity.py
# All companies here are fictional.
import json
import uuid
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from identity.db_intake import plan_intake
from identity.make_pick import pick_target
from identity.match import (check_input, decide, decide_json, describe_input, host_of, is_platform, jur_key, main_id,
                            name_key, registrable, same_name)

# A small synthetic registry (records as Make would pass them as candidates)
CORVANE = {"group_id": "c-1", "name": "Corvane GmbH", "official_domain": "corvane.de"}
TALLOWICK = {"group_id": "c-2", "name": "Tallowick", "official_domain": ""}
MOVED = {"group_id": "c-3", "name": "Veilpost", "official_domain": "veilpost.io",
         "domain_history": ["veilpost-app.com"]}
UNVERIFIED = {"group_id": "c-4", "name": "Slotwise", "official_domain": "", "candidate_url": "https://www.slotwise.app/"}
REGISTERED = {"group_id": "c-5", "name": "Buildstash Ltd", "official_domain": "buildstash.com",
              "registration_id": "HRB 123456 B"}
CLERA_MUC = {"group_id": "c-6", "name": "Clera", "official_domain": "getclera.com"}
BRAND_A = {"group_id": "c-7", "name": "Northwind Labs", "official_domain": "labs.parentgroup.com"}
REGISTRY = [CORVANE, TALLOWICK, MOVED, UNVERIFIED, REGISTERED, CLERA_MUC, BRAND_A]


def status(new, candidates=REGISTRY):
    return decide(new, candidates)["status"]


# --- helpers ---

def test_host_is_normalised():
    assert host_of("https://www.Corvane.de:443/about?x=1#top") == "corvane.de"
    assert host_of("corvane.de/") == "corvane.de"
    assert host_of("") == "" and host_of(None) == ""


def test_registrable_domain():
    assert registrable("shop.corvane.de") == "corvane.de"
    assert registrable("a.b.co.uk") == "b.co.uk"


def test_platform_pages_and_their_subdomains():
    assert is_platform("claude.ai") and is_platform("jobs.linkedin.com")
    assert not is_platform("corvane.de") and not is_platform("")
    assert is_platform("boardsite-a.example", extra={"boardsite-a.example"})


def test_name_key_removes_legal_forms_accents_and_case():
    assert name_key("Corvane GmbH") == name_key("CORVANE  UG (haftungsbeschränkt)") == "corvane"
    assert name_key("Müller & Söhne GmbH & Co. KG") == "muller sohne"
    assert name_key("GmbH") == "gmbh"  # a name of legal-form words only is kept


def test_a_platform_page_is_never_stored_as_the_company_domain():
    info = describe_input({"name": "Corvane", "website": "https://claude.ai/artifact/abc"})
    assert info["website_is_platform"] and info["domain_candidate"] == ""


# --- input rules ---

def test_no_website_is_allowed_with_another_https_source():
    assert check_input({"name": "Newco", "sources": ["https://startup.jobs/newco-job"]}) == []


def test_entry_without_any_https_source_is_invalid():
    result = decide({"name": "Newco", "website": "http://newco.de"}, REGISTRY)
    assert result["status"] == "INVALID" and "HTTPS source" in result["problems"][0]
    assert decide({"name": "", "sources": ["https://x.de"]}, [])["status"] == "INVALID"


# --- the cases asked for by Tapiwa (16 Nov) ---

def test_same_verified_website_is_a_duplicate():
    result = decide({"name": "Corvane", "website": "https://www.corvane.de/team"}, REGISTRY)
    assert result["status"] == "DUPLICATE" and result["group_id"] == "c-1"
    assert result["matches"][0]["reason"] == "same verified domain"


def test_same_but_unverified_website_goes_to_a_human():
    result = decide({"name": "Slotwise", "website": "https://slotwise.app"}, REGISTRY)
    assert result["status"] == "POSSIBLE_DUPLICATE" and result["matches"][0]["reason"] == "same website, not verified yet"


def test_different_websites_same_name_goes_to_a_human():
    result = decide({"name": "Corvane", "website": "https://corvane-ai.com"}, REGISTRY)
    assert result["status"] == "POSSIBLE_DUPLICATE"
    assert "different domains" in result["matches"][0]["reason"]


def test_no_website_new_name_is_new():
    assert status({"name": "Quillmoor", "sources": ["https://startup.jobs/quillmoor"]}) == "NEW"


def test_no_website_known_name_goes_to_a_human():
    result = decide({"name": "Tallowick", "sources": ["https://startup.jobs/tallowick"]}, REGISTRY)
    assert result["status"] == "POSSIBLE_DUPLICATE" and result["matches"][0]["group_id"] == "c-2"


def test_changed_domain_is_recognised_from_the_history():
    result = decide({"name": "Veilpost", "website": "https://veilpost-app.com"}, REGISTRY)
    assert result["status"] == "DUPLICATE" and result["group_id"] == "c-3"
    assert result["matches"][0]["reason"] == "earlier domain of this company"


def test_two_companies_on_the_same_platform_are_both_new():
    # Tallowick and Corvane test pages both live on claude.ai: the platform must not join them
    registry = [{"group_id": "t-1", "name": "Tallowick", "official_domain": "", "candidate_url": "https://claude.ai/artifact/S4k"}]
    assert status({"name": "Corvane", "website": "https://claude.ai/artifact/44j2E49j7935imJEMzNxcd"}, registry) == "NEW"


def test_same_platform_and_same_name_goes_to_a_human():
    registry = [{"group_id": "t-1", "name": "Tallowick", "official_domain": "", "candidate_url": "https://claude.ai/artifact/S4k"}]
    assert status({"name": "Tallowick", "website": "https://claude.ai/artifact/other"}, registry) == "POSSIBLE_DUPLICATE"


# --- our own cases ---

def test_same_name_different_companies_are_never_merged():
    # three different companies called Clera (recruiting, procurement, logistics)
    for site in ("https://clera-procurement.de", "https://clera-freight.com"):
        result = decide({"name": "Clera", "website": site}, REGISTRY)
        assert result["status"] == "POSSIBLE_DUPLICATE" and "group_id" not in result


def test_legal_form_variant_with_the_same_verified_domain_is_a_duplicate():
    assert status({"name": "CORVANE UG (haftungsbeschränkt)", "website": "https://corvane.de"}) == "DUPLICATE"


def test_typo_in_the_name_still_matches():
    result = decide({"name": "Bildstash", "website": "https://buildstash.com"}, REGISTRY)
    assert result["status"] == "DUPLICATE" and result["group_id"] == "c-5"


def test_unverified_registration_id_alone_goes_to_a_human():
    result = decide({"name": "Buildstash Software", "registration_id": "hrb123456b", "sources": ["https://x.de"]}, REGISTRY)
    assert result["status"] == "POSSIBLE_DUPLICATE"
    assert result["matches"][0]["reason"] == "same registration ID, not verified for this jurisdiction"


VERIFIED_REG = dict(REGISTERED, registration_verified=True, jurisdiction="Amtsgericht Göttingen")


def test_verified_registration_id_with_the_same_jurisdiction_is_a_duplicate():
    new = {"name": "Buildstash Software", "registration_id": "hrb123456b", "jurisdiction": "amtsgericht gottingen",
           "sources": ["https://x.de"]}
    result = decide(new, [VERIFIED_REG])
    assert result["status"] == "DUPLICATE" and result["group_id"] == "c-5"
    assert result["matches"][0]["reason"].startswith("same verified registration ID")


def test_verified_registration_id_without_or_with_another_jurisdiction_goes_to_a_human():
    new = {"name": "Buildstash Software", "registration_id": "HRB 123456 B", "sources": ["https://x.de"]}
    assert decide(new, [VERIFIED_REG])["status"] == "POSSIBLE_DUPLICATE"  # the new entry names no jurisdiction
    other = dict(new, jurisdiction="Amtsgericht München")
    assert decide(other, [VERIFIED_REG])["status"] == "POSSIBLE_DUPLICATE"
    unverified = dict(VERIFIED_REG, registration_verified=False)  # the number was typed, never checked
    assert decide(dict(new, jurisdiction="Amtsgericht Göttingen"), [unverified])["status"] == "POSSIBLE_DUPLICATE"


def test_jurisdiction_key_ignores_case_and_accents():
    assert jur_key("Amtsgericht Göttingen") == jur_key("AMTSGERICHT  gottingen") == "amtsgericht gottingen"


def test_same_name_different_registration_ids_goes_to_a_human():
    result = decide({"name": "Buildstash", "registration_id": "HRB 999", "sources": ["https://x.de"]}, REGISTRY)
    assert result["status"] == "POSSIBLE_DUPLICATE"
    assert result["matches"][0]["reason"] == "same name, different registration IDs"


def test_shared_parent_domain_goes_to_a_human():
    result = decide({"name": "Southwind Studio", "website": "https://studio.parentgroup.com"}, REGISTRY)
    assert result["status"] == "POSSIBLE_DUPLICATE"
    assert result["matches"][0]["reason"] == "same parent domain, different subdomains"


def test_same_verified_domain_but_different_name_goes_to_a_human():
    result = decide({"name": "Totally Other GmbH", "website": "https://corvane.de"}, REGISTRY)
    assert result["status"] == "POSSIBLE_DUPLICATE" and "different names" in result["matches"][0]["reason"]


def test_two_sure_matches_go_to_a_human():
    copy = dict(CORVANE, group_id="c-1b")  # the registry already holds Corvane twice
    assert status({"name": "Corvane", "website": "https://corvane.de"}, [CORVANE, copy]) == "POSSIBLE_DUPLICATE"


def test_json_entry_point_for_make():
    out = json.loads(decide_json(json.dumps({"new": {"name": "Corvane", "website": "https://corvane.de"},
                                             "candidates": [CORVANE]})))
    assert out["status"] == "DUPLICATE" and out["group_id"] == "c-1"


# --- Make adapter and the generated Code blocks ---

from identity.make_adapter import NONE, candidate_from_make, make_decide, make_keys
from identity.make_code import build


def run_block(code, inp):
    """Run a generated block the way Make's Code module does: inside a function, with `input` given."""
    scope = {}
    exec("def _make(input):\n" + "\n".join("    " + line for line in code.splitlines()), scope)
    return scope["_make"](inp)


def test_keys_use_a_placeholder_for_empty_values():
    keys = make_keys({"company_label": "Corvane GmbH", "candidate_url": "", "source_urls": "https://a.example/job"})
    assert keys["name_key"] == "corvane" and keys["domain_candidate"] == NONE and keys["registration_key"] == NONE
    assert keys["problems"] == ""


def test_keys_report_a_missing_https_source():
    assert "HTTPS source" in make_keys({"company_label": "Newco", "source_urls": "http://x.de"})["problems"]


def test_decide_reads_aggregated_records_and_skips_the_empty_bundle():
    candidates = [{"group_id": "c-1", "company_label": "Corvane GmbH", "official_domain": "corvane.de"},
                  {}, {"group_id": "c-1", "company_label": "Corvane GmbH", "official_domain": "corvane.de"}]
    out = make_decide({"company_label": "Corvane", "candidate_url": "https://corvane.de",
                       "source_urls": "https://corvane.de; https://a.example/job", "candidates": candidates})
    assert out["status"] == "DUPLICATE" and out["group_id"] == "c-1" and out["candidates_seen"] == 1
    assert out["source_provenance"] == "https://corvane.de; https://a.example/job"


def test_new_group_id_only_for_records_that_will_be_written():
    new = make_decide({"company_label": "Quillmoor", "source_urls": "https://a.example/job"})
    assert new["status"] == "NEW" and new["review_state"] == "SOURCE_CANDIDATE_UNVERIFIED"
    assert new["new_group_id"].startswith("G-") and len(new["new_group_id"]) == 38
    assert str(uuid.UUID(new["new_group_id"][2:], version=4)) == new["new_group_id"][2:]
    assert make_decide({"company_label": "Quillmoor", "source_urls": "https://a.example/job"})["new_group_id"] != new["new_group_id"]
    held = make_decide({"company_label": "Tallowick", "source_urls": "https://a.example/j",
                        "candidates": [{"group_id": "t-1", "company_label": "Tallowick"}]})
    assert held["status"] == "POSSIBLE_DUPLICATE" and held["review_state"] == "POSSIBLE_DUPLICATE_HELD" and held["new_group_id"]
    dup = make_decide({"company_label": "Corvane", "candidate_url": "https://corvane.de",
                       "candidates": [{"group_id": "c-1", "company_label": "Corvane", "official_domain": "corvane.de"}]})
    assert dup["status"] == "DUPLICATE" and dup["new_group_id"] == "" and dup["review_state"] == ""
    bad = make_decide({"company_label": "Newco", "source_urls": "http://x.de"})
    assert bad["status"] == "INVALID" and bad["new_group_id"] == ""


def test_decide_accepts_candidates_as_json_text():
    text = json.dumps([{"group_id": "t-1", "company_label": "Tallowick", "candidate_url": "https://claude.ai/artifact/S4k"}])
    out = make_decide({"company_label": "Corvane", "source_urls": "https://claude.ai/artifact/44j", "candidates": text})
    assert out["status"] == "NEW" and out["duplicate_candidates"] == ""


def test_generated_blocks_run_like_in_make():
    blocks = build()
    keys = run_block(blocks["make_keys.py.txt"], {"company_label": "Corvane", "source_urls": "https://a.example/job"})
    assert keys["name_key"] == "corvane"
    out = run_block(blocks["make_decide.py.txt"], {"company_label": "Tallowick", "source_urls": "https://a.example/j",
                                                   "candidates": [{"group_id": "t-1", "company_label": "Tallowick"}]})
    assert out["status"] == "POSSIBLE_DUPLICATE" and "t-1" in out["duplicate_candidates"]


def test_generated_blocks_are_up_to_date():
    here = Path(__file__).resolve().parent.parent / "identity"
    for name, text in build().items():
        assert (here / name).read_text(encoding="utf-8") == text, f"{name} is stale: run python -m identity.make_code"


# --- decisions of a human: duplicate_of and different_from ---

NORDVALE = {"group_id": "n-1", "name": "Nordvale GmbH", "official_domain": "", "candidate_url": "https://nordvale.example/"}


def test_main_company_follows_the_chain_and_stops_at_a_cycle():
    by_id = {"a": {"duplicate_of": "b"}, "b": {"duplicate_of": "c"}, "c": {}}
    assert main_id("a", by_id) == main_id("b", by_id) == main_id("c", by_id) == "c"
    assert main_id("x", by_id) == "x"  # unknown row: itself
    assert main_id("a", {"a": {"duplicate_of": "b"}}) == "b"  # the main row was not returned by the search: its id still counts
    loop = {"a": {"duplicate_of": "b"}, "b": {"duplicate_of": "a"}}
    assert main_id("a", loop) == main_id("b", loop) == "a"  # a cycle ends at the smallest id, whatever the start
    assert main_id("a", {"a": {"duplicate_of": "a"}}) == "a"


def test_a_row_linked_by_a_human_counts_as_its_main_company():
    linked = {"group_id": "n-2", "name": "Nordval", "candidate_url": "https://nordvale.example/", "duplicate_of": "n-1"}
    new = {"name": "Nordvale", "website": "https://nordvale.example"}
    for registry in ([NORDVALE, linked], [linked]):  # the main row may be missing from the search result
        result = decide(new, registry)
        assert result["status"] == "DUPLICATE" and result["group_id"] == "n-1", registry
        assert "linked" in result["matches"][0]["reason"] or len(registry) == 2


def test_the_same_website_is_unverified_before_the_human_links_it_and_remembered_after():
    new = {"name": "Nordvale", "website": "https://nordvale.example"}
    assert decide(new, [NORDVALE])["status"] == "POSSIBLE_DUPLICATE"  # first time: a human must look
    linked = {"group_id": "n-2", "name": "Nordvale", "candidate_url": "https://nordvale.example/", "duplicate_of": "n-1"}
    assert decide(new, [NORDVALE, linked])["status"] == "DUPLICATE"  # the same entry again: no new question


def test_rows_of_one_company_are_one_match_not_two():
    linked = {"group_id": "n-2", "name": "Nordvale", "duplicate_of": "n-1"}
    result = decide({"name": "Nordvale", "sources": ["https://x.example/j"]}, [NORDVALE, linked])  # name only, nothing sure
    assert result["status"] == "POSSIBLE_DUPLICATE" and [m["group_id"] for m in result["matches"]] == ["n-1"]


def test_a_linked_row_with_only_a_name_match_is_still_a_question():
    linked = {"group_id": "n-2", "name": "Nordvale", "duplicate_of": "n-1"}
    result = decide({"name": "Nordvale Ltd", "website": "https://other.example"}, [NORDVALE, linked])
    assert result["status"] == "POSSIBLE_DUPLICATE" and result["matches"][0]["group_id"] == "n-1"


LABS = {"group_id": "n-3", "name": "Nordvale Ltd", "official_domain": "", "candidate_url": "https://nordvale.co.uk/",
        "different_from": ["n-1"]}  # a human said: Nordvale Ltd is not Nordvale GmbH


def test_without_the_human_decision_both_similar_companies_are_listed():
    plain = dict(LABS, different_from=[])
    result = decide({"name": "Nordvale", "website": "https://nordvale.co.uk"}, [NORDVALE, plain])
    assert sorted(m["group_id"] for m in result["matches"]) == ["n-1", "n-3"]


def test_different_company_decision_drops_the_weaker_match():
    result = decide({"name": "Nordvale", "website": "https://nordvale.co.uk"}, [NORDVALE, LABS])
    assert result["status"] == "DUPLICATE" and [m["group_id"] for m in result["matches"]] == ["n-3"]  # n-1 is dropped


def test_different_company_decision_is_read_from_either_side():
    gmbh = dict(NORDVALE, different_from=["n-3"])  # the decision is stored on the other record
    labs = dict(LABS, different_from=[])
    result = decide({"name": "Nordvale", "website": "https://nordvale.co.uk"}, [gmbh, labs])
    assert [m["group_id"] for m in result["matches"]] == ["n-3"]


def test_the_same_entry_again_after_a_different_company_decision_is_not_asked_again():
    labs = dict(LABS, candidate_url="https://nordvale.co.uk/")  # the human looked at this row and said: not n-1
    result = decide({"name": "Nordvale Ltd", "website": "https://nordvale.co.uk"}, [NORDVALE, labs])
    assert result["status"] == "DUPLICATE" and result["group_id"] == "n-3"


def test_two_known_different_companies_with_equal_matches_still_go_to_a_human():
    labs = dict(LABS, candidate_url="")
    gmbh = dict(NORDVALE, candidate_url="")
    result = decide({"name": "Nordvale Ltd", "sources": ["https://x.example/j"]}, [gmbh, labs])  # only the name matches both, equally strongly
    assert sorted(m["group_id"] for m in result["matches"]) == ["n-1", "n-3"]


def test_after_the_domain_is_verified_the_known_different_company_is_a_sure_match():
    verified = dict(LABS, official_domain="nordvale.co.uk")
    result = decide({"name": "Nordvale Ltd", "website": "https://www.nordvale.co.uk"}, [NORDVALE, verified])
    assert result["status"] == "DUPLICATE" and result["group_id"] == "n-3"


def test_different_company_pair_follows_the_linked_rows():
    linked = {"group_id": "n-4", "name": "Nordvale", "duplicate_of": "n-1"}  # a row of Nordvale GmbH
    result = decide({"name": "Nordvale", "website": "https://nordvale.co.uk"}, [linked, LABS])
    assert [m["group_id"] for m in result["matches"]] == ["n-3"]  # n-4 is n-1, which is not n-3


def test_make_adapter_reads_the_decision_fields():
    rows = [dict(NORDVALE, group_id="n-1", company_label="Nordvale GmbH", candidate_url="https://nordvale.example/"),
            {"group_id": "n-2", "company_label": "Nordval", "candidate_url": "https://nordvale.example/",
             "duplicate_of": "n-1", "registration_verified": "true", "jurisdiction": "Göttingen", "different_from": "n-9; n-8"}]
    out = make_decide({"company_label": "Nordvale", "candidate_url": "https://nordvale.example", "candidates": rows})
    assert out["status"] == "DUPLICATE" and out["group_id"] == "n-1" and out["new_group_id"] == ""
    c = candidate_from_make(rows[1])
    assert c["duplicate_of"] == "n-1" and c["different_from"] == ["n-9", "n-8"] and c["registration_verified"] is True
    assert candidate_from_make({"group_id": "x"})["registration_verified"] is False


def test_reasons_tell_a_typo_and_different_websites_apart():
    a1 = {"group_id": "o-1", "name": "Orlanne", "candidate_url": "https://orlanne.example"}
    src = ["https://jobs.example/x"]

    def reason(new):
        return decide(new, [a1])["matches"][0]["reason"]

    assert reason({"name": "Orlane", "sources": src}) == "similar name, no website to compare"
    assert reason({"name": "Orlanne", "sources": src}) == "same name, no website to compare"
    assert reason({"name": "Orlanne", "website": "https://other.example", "sources": src}) == "same name, different websites (not verified)"
    assert reason({"name": "Orlane", "website": "https://other.example", "sources": src}) == "similar name, different websites (not verified)"


def test_group_evidence_rows_into_companies():
    from identity.make_group import make_group
    rows = [{"row": 2, "label": "Corvane", "url": "https://a.example/1", "type": "Other"},
            {"row": 3, "label": "corvane ", "url": "https://a.example/2", "type": "Other"},
            {"row": 4, "label": "Tallowick", "url": "https://b.example/x", "type": "Other"},
            {"row": 5, "label": "Tallowick", "url": "https://tallowick.example/", "type": "Company website"}]
    groups = make_group({"rows": rows})["groups"]
    assert [g["company_label"] for g in groups] == ["Corvane", "Tallowick"]
    assert groups[0]["row_numbers"] == [2, 3] and groups[0]["source_urls"] == "https://a.example/1; https://a.example/2"
    assert groups[0]["candidate_url"] == "https://a.example/1"
    assert groups[1]["candidate_url"] == "https://tallowick.example/"
    assert make_group({"rows": json.dumps(rows)}) == make_group({"rows": rows}) and make_group({"rows": []}) == {"groups": []}


def test_pick_target_for_a_human_decision():
    one = json.dumps([{"group_id": "G-1", "reason": "same name"}])
    two = json.dumps([{"group_id": "G-1", "reason": "x"}, {"group_id": "G-2", "reason": "y"}])
    assert pick_target({"typed": "", "candidates": one}) == {"target": "G-1", "count": 1}  # single candidate is used
    assert pick_target({"typed": "G-9", "candidates": two})["target"] == "G-9"  # a typed ID always wins
    assert pick_target({"typed": " ", "candidates": two}) == {"target": "", "count": 2}  # several: a human must choose
    assert pick_target({"typed": "", "candidates": ""}) == {"target": "", "count": 0}  # no candidates
    assert pick_target({"typed": "", "candidates": "not json"})["target"] == ""  # broken text never crashes
    assert pick_target({"typed": "", "candidates": [{"group_id": "G-1"}, {"group_id": "G-1"}]})["target"] == "G-1"


def test_one_typo_in_a_longer_name_is_similar():
    assert same_name("Corvaen", "Corvane") and same_name("Korvane", "Corvane")  # swapped / changed letter
    assert same_name("Corvanne", "Corvane")  # added letter
    assert not same_name("Corvain", "Corvane")  # two letters differ
    assert not same_name("Nora", "Nova")  # short names: one letter is too much
    assert not same_name("Tallowick lab", "Tallowick")  # an extra word is not a typo


# the prototype database on 2026-11-19 (companies table), all fictional
DB_COMPANIES = [
    {"id": "G-corvane", "label": "Corvane"},
    {"id": "G-corvane-gmbh", "label": "Corvane GmbH", "duplicate_of": "G-corvane"},
    {"id": "G-corvane-2", "label": "Corvane", "different_from": ["G-corvane"]},
    {"id": "G-tallowick", "label": "Tallowick", "candidate_url": "https://claude.ai/artifact/S4kC"},
    {"id": "G-tallowick-lab", "label": "Tallowick lab", "candidate_url": "https://claude.ai/artifact/S4kD"},
]


def test_db_intake_plan():
    ids = iter(["G-new-1", "G-new-2", "G-new-3"])
    rows = [
        {"evidence_id": "EV-013", "company_label": "Corvaen", "source_url": "https://corvaen.example/about", "source_type": "Other"},
        {"evidence_id": "EV-014", "company_label": "Quillmoor", "source_url": "https://quillmoor.example/", "source_type": "Company website"},
        {"evidence_id": "EV-015", "company_label": "quillmoor ", "source_url": "https://quillmoor.example/jobs", "source_type": "Other"},
        {"evidence_id": "EV-016", "company_label": "Nameless", "source_url": None, "source_type": "Other"},
    ]
    plan = plan_intake(rows, DB_COMPANIES, new_id=lambda: next(ids))
    new = {c["label"]: c for c in plan["companies"]}
    # the typo is caught; both Corvane companies stay candidates (a human said they differ, but neither is stronger)
    assert new["Corvaen"]["match_status"] == "POSSIBLE_DUPLICATE"
    assert new["Corvaen"]["review_state"] == "POSSIBLE_DUPLICATE_HELD"
    assert {m["group_id"] for m in new["Corvaen"]["duplicate_candidates"]} == {"G-corvane", "G-corvane-2"}
    # two sources with the same label become one company; its website is the one marked "Company website"
    assert new["Quillmoor"]["match_status"] == "NEW" and new["Quillmoor"]["candidate_url"] == "https://quillmoor.example/"
    assert ("EV-014", new["Quillmoor"]["id"]) in plan["assign"] and ("EV-015", new["Quillmoor"]["id"]) in plan["assign"]
    # no HTTPS source: no company, a reason in the note
    assert [e for e, _ in plan["invalid"]] == ["EV-016"] and plan["invalid"][0][1].startswith("INVALID:")
    assert "Nameless" not in new and len(plan["companies"]) == 2


def test_db_intake_links_to_a_company_created_in_the_same_run():
    rows = [{"evidence_id": "EV-1", "company_label": "Fennick", "source_url": "https://fennick.example/", "source_type": "Company website"},
            {"evidence_id": "EV-2", "company_label": "Fennick GmbH", "source_url": "https://news.example/f", "source_type": "Other"}]
    plan = plan_intake(rows, [], new_id=iter(["G-a", "G-b"]).__next__)
    assert [c["match_status"] for c in plan["companies"]] == ["NEW", "POSSIBLE_DUPLICATE"]
    assert plan["companies"][1]["duplicate_candidates"][0]["group_id"] == "G-a"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} tests passed")
