# Offline tests for identity/match.py (company ID and duplicate detection). Run: python tests/test_identity.py
# All companies here are fictional.
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from identity.match import check_input, decide, decide_json, describe_input, host_of, is_platform, name_key, registrable

# A small synthetic registry (records as Make would pass them as candidates)
CORVANE = {"company_id": "c-1", "name": "Corvane GmbH", "official_domain": "corvane.de", "domain_verified": True}
TALLOWICK = {"company_id": "c-2", "name": "Tallowick", "official_domain": "", "domain_verified": False}
MOVED = {"company_id": "c-3", "name": "Veilpost", "official_domain": "veilpost.io", "domain_verified": True,
         "domain_history": ["veilpost-app.com"]}
UNVERIFIED = {"company_id": "c-4", "name": "Slotwise", "official_domain": "slotwise.app", "domain_verified": False}
REGISTERED = {"company_id": "c-5", "name": "Buildstash Ltd", "official_domain": "buildstash.com", "domain_verified": True,
              "registration_id": "HRB 123456 B"}
CLERA_MUC = {"company_id": "c-6", "name": "Clera", "official_domain": "getclera.com", "domain_verified": True}
BRAND_A = {"company_id": "c-7", "name": "Northwind Labs", "official_domain": "labs.parentgroup.com", "domain_verified": True}
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
    assert result["status"] == "DUPLICATE" and result["company_id"] == "c-1"
    assert result["matches"][0]["reason"] == "same verified domain"


def test_same_but_unverified_website_goes_to_a_human():
    result = decide({"name": "Slotwise", "website": "https://slotwise.app"}, REGISTRY)
    assert result["status"] == "POSSIBLE_DUPLICATE" and result["matches"][0]["reason"] == "same domain, not verified yet"


def test_different_websites_same_name_goes_to_a_human():
    result = decide({"name": "Corvane", "website": "https://corvane-ai.com"}, REGISTRY)
    assert result["status"] == "POSSIBLE_DUPLICATE"
    assert "different domains" in result["matches"][0]["reason"]


def test_no_website_new_name_is_new():
    assert status({"name": "Quillmoor", "sources": ["https://startup.jobs/quillmoor"]}) == "NEW"


def test_no_website_known_name_goes_to_a_human():
    result = decide({"name": "Tallowick", "sources": ["https://startup.jobs/tallowick"]}, REGISTRY)
    assert result["status"] == "POSSIBLE_DUPLICATE" and result["matches"][0]["company_id"] == "c-2"


def test_changed_domain_is_recognised_from_the_history():
    result = decide({"name": "Veilpost", "website": "https://veilpost-app.com"}, REGISTRY)
    assert result["status"] == "DUPLICATE" and result["company_id"] == "c-3"
    assert result["matches"][0]["reason"] == "earlier domain of this company"


def test_two_companies_on_the_same_platform_are_both_new():
    # Tallowick and Corvane test pages both live on claude.ai: the platform must not join them
    registry = [{"company_id": "t-1", "name": "Tallowick", "official_domain": "", "domain_verified": False}]
    assert status({"name": "Corvane", "website": "https://claude.ai/artifact/44j2E49j7935imJEMzNxcd"}, registry) == "NEW"


def test_same_platform_and_same_name_goes_to_a_human():
    registry = [{"company_id": "t-1", "name": "Tallowick", "official_domain": "", "domain_verified": False}]
    assert status({"name": "Tallowick", "website": "https://claude.ai/artifact/other"}, registry) == "POSSIBLE_DUPLICATE"


# --- our own cases ---

def test_same_name_different_companies_are_never_merged():
    # three different companies called Clera (recruiting, procurement, logistics)
    for site in ("https://clera-procurement.de", "https://clera-freight.com"):
        result = decide({"name": "Clera", "website": site}, REGISTRY)
        assert result["status"] == "POSSIBLE_DUPLICATE" and "company_id" not in result


def test_legal_form_variant_with_the_same_verified_domain_is_a_duplicate():
    assert status({"name": "CORVANE UG (haftungsbeschränkt)", "website": "https://corvane.de"}) == "DUPLICATE"


def test_typo_in_the_name_still_matches():
    result = decide({"name": "Bildstash", "website": "https://buildstash.com"}, REGISTRY)
    assert result["status"] == "DUPLICATE" and result["company_id"] == "c-5"


def test_same_registration_id_is_a_duplicate_even_with_another_name():
    result = decide({"name": "Buildstash Software", "registration_id": "hrb123456b", "sources": ["https://x.de"]}, REGISTRY)
    assert result["status"] == "DUPLICATE" and result["matches"][0]["reason"] == "same registration ID"


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
    copy = dict(CORVANE, company_id="c-1b")  # the registry already holds Corvane twice
    assert status({"name": "Corvane", "website": "https://corvane.de"}, [CORVANE, copy]) == "POSSIBLE_DUPLICATE"


def test_json_entry_point_for_make():
    out = json.loads(decide_json(json.dumps({"new": {"name": "Corvane", "website": "https://corvane.de"},
                                             "candidates": [CORVANE]})))
    assert out["status"] == "DUPLICATE" and out["company_id"] == "c-1"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} tests passed")
