# Company identity and duplicate detection for the founder source registry (task YL-004B).
#
# Pure Python, standard library only, so the same file can run inside Make's Code module.
# Make finds a few candidate records in the registry (by domain, registration ID, name key) and passes them here;
# this code decides. It never merges: an uncertain match goes to a human.
#
# Decisions:
#   DUPLICATE           same registration ID, or the same VERIFIED official domain (or one of its earlier domains)
#                       with a matching name -> use the existing company_id, add the new source to it
#   POSSIBLE_DUPLICATE  something matches but identity is not proven (same name, unverified or shared domain)
#                       -> new record, held for human review, candidates listed
#   NEW                 nothing matches -> new record with a new company_id (Make generates it with uuid)
#
# A third-party page (job board, directory, accelerator, social network, claude.ai) is never a company's own domain.

import difflib
import json
import unicodedata

PLATFORM_DOMAINS = {
    # pages that host many companies: never used as a company's identity domain
    "claude.ai", "linkedin.com", "xing.com", "facebook.com", "instagram.com", "x.com", "twitter.com",
    "youtube.com", "medium.com", "substack.com", "github.com", "notion.site", "google.com", "sites.google.com",
    "startup.jobs", "ziprecruiter.de", "arbeitnow.com", "stepstone.de", "indeed.com", "join.com", "wellfound.com",
    "crunchbase.com", "dealroom.co", "f6s.com", "pitchbook.com", "northdata.com", "startbase.com",
    "ycombinator.com", "techstars.com", "eu-startups.com", "munich-startup.de", "producthunt.com",
    "wixsite.com", "webflow.io", "carrd.co", "framer.website", "vercel.app", "netlify.app",
}
TWO_PART_SUFFIXES = {"co.uk", "org.uk", "ac.uk", "com.au", "co.nz", "co.za", "com.br", "co.jp", "com.tr"}
LEGAL_FORMS = {
    "gmbh", "ug", "haftungsbeschrankt", "ag", "se", "kg", "kgaa", "gbr", "ohg", "ev", "mbh", "co",
    "inc", "ltd", "llc", "plc", "corp", "corporation", "company", "limited", "lp", "llp",
    "sarl", "sas", "sa", "bv", "nv", "oy", "ab", "as", "aps", "spa", "srl", "sp", "zoo",
}
NAME_SIMILARITY = 0.9  # difflib ratio of two name keys counted as "the same name" (catches typos like Bildstash/Buildstash)


def host_of(url: str) -> str:
    """'https://www.Corvane.de:443/about?x=1' -> 'corvane.de'. Empty input gives ''."""
    url = (url or "").strip().lower()
    if not url:
        return ""
    host = url.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    host = host.rsplit("@", 1)[-1].split(":", 1)[0].rstrip(".")
    return host.removeprefix("www.")


def registrable(host: str) -> str:
    """The part a company registers: 'shop.corvane.de' -> 'corvane.de', 'a.b.co.uk' -> 'b.co.uk'."""
    parts = host.split(".")
    keep = 3 if ".".join(parts[-2:]) in TWO_PART_SUFFIXES else 2
    return ".".join(parts[-keep:])


def is_platform(host: str, extra: set | None = None) -> bool:
    """True for a page on a third-party platform (also its subdomains, e.g. jobs.linkedin.com)."""
    platforms = PLATFORM_DOMAINS | (extra or set())
    return bool(host) and any(host == p or host.endswith("." + p) for p in platforms)


def name_key(name: str) -> str:
    """'Corvane GmbH' and 'CORVANE  UG (haftungsbeschränkt)' -> 'corvane'. Accents, punctuation and legal forms removed."""
    text = (name or "").lower().replace("ß", "ss").replace("&", " ")
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    words = "".join(c if c.isalnum() else " " for c in text).split()
    kept = [w for w in words if w not in LEGAL_FORMS]
    return " ".join(kept or words)  # a name made only of legal-form words keeps them


def same_name(a: str, b: str) -> bool:
    ka, kb = name_key(a), name_key(b)
    return bool(ka and kb) and (ka == kb or difflib.SequenceMatcher(None, ka, kb).ratio() >= NAME_SIMILARITY)


def reg_key(value: str) -> str:
    """'HRB 123 456 B' -> 'HRB123456B'."""
    return "".join(c for c in (value or "").upper() if c.isalnum())


def names_of(record: dict) -> list[str]:
    return [record.get("name", "")] + list(record.get("aliases") or [])


def describe_input(new: dict, extra_platforms: set | None = None) -> dict:
    """The fields Make stores for a new entry: website host, whether it is a third-party platform, name key."""
    host = host_of(new.get("website", ""))
    platform = is_platform(host, extra_platforms)
    return {"name_key": name_key(new.get("name", "")), "website_host": host, "website_is_platform": platform,
            "domain_candidate": "" if platform else host, "registration_key": reg_key(new.get("registration_id", ""))}


def check_input(new: dict) -> list[str]:
    """Problems that stop an entry: no name, or no HTTPS source at all (website or another public source)."""
    problems = []
    if not name_key(new.get("name", "")):
        problems.append("company name is missing")
    urls = [new.get("website", "")] + list(new.get("sources") or [])
    if not any((u or "").strip().lower().startswith("https://") for u in urls):
        problems.append("at least one HTTPS source is needed (official website or another public source)")
    return problems


def decide(new: dict, candidates: list[dict], extra_platforms: set | None = None) -> dict:
    """Compare a new entry with candidate records of the registry.

    new:        {"name", "website" (optional), "registration_id" (optional), "sources" (list of URLs)}
    candidates: registry records {"company_id", "name", "aliases", "official_domain", "domain_verified",
                "domain_history", "registration_id"}
    Returns {"status", "company_id" (only for DUPLICATE), "matches": [{"company_id", "reason"}], "input": {...}}.
    """
    info = describe_input(new, extra_platforms)
    problems = check_input(new)
    if problems:
        return {"status": "INVALID", "matches": [], "problems": problems, "input": info}

    domain, reg = info["domain_candidate"], info["registration_key"]
    sure, unsure = [], []
    for c in candidates:
        cid = c.get("company_id", "")
        name_match = any(same_name(new.get("name", ""), n) for n in names_of(c))
        if reg and reg == reg_key(c.get("registration_id", "")):
            sure.append({"company_id": cid, "reason": "same registration ID"})
            continue
        if reg and reg_key(c.get("registration_id", "")):  # both have registration IDs and they differ
            if name_match:
                unsure.append({"company_id": cid, "reason": "same name, different registration IDs"})
            continue
        known = [d for d in [c.get("official_domain", "")] + list(c.get("domain_history") or []) if d]
        if domain and known:
            if domain in known:
                if c.get("domain_verified") and name_match:
                    reason = "same verified domain" if domain == c.get("official_domain") else "earlier domain of this company"
                    sure.append({"company_id": cid, "reason": reason})
                elif not c.get("domain_verified"):
                    unsure.append({"company_id": cid, "reason": "same domain, not verified yet"})
                else:
                    unsure.append({"company_id": cid, "reason": "same domain, different names (shared or parent domain?)"})
                continue
            if any(registrable(domain) == registrable(d) for d in known):
                unsure.append({"company_id": cid, "reason": "same parent domain, different subdomains"})
                continue
        if name_match:
            if domain and known:
                why = "same name, different domains (changed website or another company?)"
            else:
                why = "same name, no domain to compare"
            unsure.append({"company_id": cid, "reason": why})

    if len(sure) == 1 and not unsure:
        return {"status": "DUPLICATE", "company_id": sure[0]["company_id"], "matches": sure, "input": info}
    if sure or unsure:  # several sure matches also need a human: the registry may already hold a duplicate
        return {"status": "POSSIBLE_DUPLICATE", "matches": sure + unsure, "input": info}
    return {"status": "NEW", "matches": [], "input": info}


def decide_json(payload: str) -> str:
    """Entry point for Make's Code module: JSON in ({"new": {...}, "candidates": [...]}), JSON out."""
    data = json.loads(payload)
    return json.dumps(decide(data["new"], data.get("candidates") or []), ensure_ascii=False)
