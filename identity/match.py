# Company identity and duplicate detection for the founder source registry (task YL-004B).
#
# Pure Python, standard library only, no type hints (runs on older Python too), so the same file can run inside
# Make's Code module.
# Make finds a few candidate records in the registry (by domain, registration ID, name key) and passes them here;
# this code decides. It never merges: an uncertain match goes to a human.
#
# Decisions:
#   DUPLICATE           same VERIFIED registration ID (checked by a human for this jurisdiction), or the same VERIFIED
#                       official domain (or one of its earlier domains) with a matching name, or the same website as an
#                       entry a human already reviewed (linked to the company or marked as a different company) -> use the existing group_id, add the new source to it
#                       (official_domain is filled only by a human after checking the site: filled = verified)
#   POSSIBLE_DUPLICATE  something matches but identity is not proven (same name, unverified or shared domain)
#                       -> new record, held for human review, candidates listed
#   NEW                 nothing matches -> new record with a new group_id (Make generates it with uuid)
#
# Human decisions are remembered in the registry and read here:
#   duplicate_of     a row a human linked to a main company counts as that company (chains are followed, cycles stop)
#   different_from   group_ids a human said are NOT the same company: the weaker of two such matches is dropped
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


def host_of(url):
    """'https://www.Corvane.de:443/about?x=1' -> 'corvane.de'. Empty input gives ''."""
    url = (url or "").strip().lower()
    if not url:
        return ""
    host = url.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    host = host.rsplit("@", 1)[-1].split(":", 1)[0].rstrip(".")
    return host[4:] if host.startswith("www.") else host


def registrable(host):
    """The part a company registers: 'shop.corvane.de' -> 'corvane.de', 'a.b.co.uk' -> 'b.co.uk'."""
    parts = host.split(".")
    keep = 3 if ".".join(parts[-2:]) in TWO_PART_SUFFIXES else 2
    return ".".join(parts[-keep:])


def is_platform(host, extra=None):
    """True for a page on a third-party platform (also its subdomains, e.g. jobs.linkedin.com)."""
    platforms = PLATFORM_DOMAINS | (extra or set())
    return bool(host) and any(host == p or host.endswith("." + p) for p in platforms)


def name_key(name):
    """'Corvane GmbH' and 'CORVANE  UG (haftungsbeschränkt)' -> 'corvane'. Accents, punctuation and legal forms removed."""
    text = (name or "").lower().replace("ß", "ss").replace("&", " ")
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    words = "".join(c if c.isalnum() else " " for c in text).split()
    kept = [w for w in words if w not in LEGAL_FORMS]
    return " ".join(kept or words)  # a name made only of legal-form words keeps them


def same_name(a, b):
    ka, kb = name_key(a), name_key(b)
    return bool(ka and kb) and (ka == kb or difflib.SequenceMatcher(None, ka, kb).ratio() >= NAME_SIMILARITY)


def reg_key(value):
    """'HRB 123 456 B' -> 'HRB123456B'."""
    return "".join(c for c in (value or "").upper() if c.isalnum())


def jur_key(value):
    """'Amtsgericht Göttingen' and 'amtsgericht gottingen' -> 'amtsgericht gottingen' (jurisdiction of a registration ID)."""
    text = "".join(c for c in unicodedata.normalize("NFKD", (value or "").lower()) if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def truthy(value):
    """A flag from the registry: True, or text 'true' / 'yes' / '1' (Make may pass either)."""
    return value is True or str(value).strip().lower() in ("true", "yes", "1")


def main_id(group_id, by_id):
    """The main company of a row: follow duplicate_of until a row has none. A cycle ends at its smallest id."""
    seen, current = set(), group_id
    while True:
        nxt = (by_id.get(current) or {}).get("duplicate_of") or ""
        if not nxt or nxt == current:
            return current
        seen.add(current)
        if nxt in seen:
            return min(seen | {nxt})
        current = nxt


def names_of(record):
    return [record.get("name", "")] + list(record.get("aliases") or [])


def describe_input(new, extra_platforms=None):
    """The fields Make stores for a new entry: website host, whether it is a third-party platform, name key."""
    host = host_of(new.get("website", ""))
    platform = is_platform(host, extra_platforms)
    return {"name_key": name_key(new.get("name", "")), "website_host": host, "website_is_platform": platform,
            "domain_candidate": "" if platform else host, "registration_key": reg_key(new.get("registration_id", ""))}


def check_input(new):
    """Problems that stop an entry: no name, or no HTTPS source at all (website or another public source)."""
    problems = []
    if not name_key(new.get("name", "")):
        problems.append("company name is missing")
    urls = [new.get("website", "")] + list(new.get("sources") or [])
    if not any((u or "").strip().lower().startswith("https://") for u in urls):
        problems.append("at least one HTTPS source is needed (official website or another public source)")
    return problems


SURE = 5  # rank of a sure match; unsure matches rank lower (used only to apply "different company" decisions)


def compare_one(new, c, info, extra_platforms=None):
    """One registry row against the new entry. Returns None, or (is sure, rank, reason)."""
    domain, reg = info["domain_candidate"], info["registration_key"]
    name_match = any(same_name(new.get("name", ""), n) for n in names_of(c))
    exact = name_key(new.get("name", "")) in [name_key(n) for n in names_of(c)]
    name_rank = 2 if exact else 1
    label = "same name" if exact else "similar name"  # a typo or a close spelling is not "the same name"
    c_reg = reg_key(c.get("registration_id", ""))
    if reg and reg == c_reg:
        # a number alone means nothing: it counts only when a human checked it in the register of the same jurisdiction
        jurisdiction = jur_key(new.get("jurisdiction", ""))
        if truthy(c.get("registration_verified")) and jurisdiction and jurisdiction == jur_key(c.get("jurisdiction", "")):
            return True, SURE, "same verified registration ID (" + jurisdiction + ")"
        return False, 4, "same registration ID, not verified for this jurisdiction"
    if reg and c_reg:  # both have registration IDs and they differ
        return (False, name_rank, label + ", different registration IDs") if name_match else None
    reviewed = c.get("duplicate_of") or c.get("different_from")  # a human already looked at this entry
    confirmed = host_of(c.get("candidate_url", "")) if reviewed else ""
    if domain and confirmed == domain and name_match:
        return True, SURE, "same website as an entry a human already reviewed"
    known = [d for d in [c.get("official_domain", "")] + list(c.get("domain_history") or []) if d]  # verified
    entered = host_of(c.get("candidate_url", ""))
    entered = "" if is_platform(entered, extra_platforms) or entered in known else entered  # not verified
    if domain and known:
        if domain in known:
            if name_match:
                return True, SURE, "same verified domain" if domain == c.get("official_domain") else "earlier domain of this company"
            return False, 2, "same domain, different names (shared or parent domain?)"
        if any(registrable(domain) == registrable(d) for d in known):
            return False, 2, "same parent domain, different subdomains"
    if domain and entered == domain:
        return False, 3, "same website, not verified yet"
    if name_match:
        if domain and known:
            return False, name_rank, label + ", different domains (changed website or another company?)"
        if domain and entered:  # both gave a website, neither is verified, and they differ
            return False, name_rank, label + ", different websites (not verified)"
        return False, name_rank, label + ", no website to compare"
    return None


def decide(new, candidates, extra_platforms=None):
    """Compare a new entry with candidate records of the registry.

    new:        {"name", "website" (optional), "registration_id" (optional), "jurisdiction" (optional), "sources" (list of URLs)}
    candidates: registry records {"group_id", "name", "aliases", "official_domain", "domain_history",
                "candidate_url", "registration_id", "registration_verified", "jurisdiction",
                "duplicate_of", "different_from"}
                official_domain is written only by a human after checking the site: filled = verified.
                candidate_url is the site somebody entered, not verified.
    Returns {"status", "group_id" (only for DUPLICATE), "matches": [{"group_id", "reason"}], "input": {...}}.
    """
    info = describe_input(new, extra_platforms)
    problems = check_input(new)
    if problems:
        return {"status": "INVALID", "matches": [], "problems": problems, "input": info}

    by_id = {c.get("group_id", ""): c for c in candidates}
    best = {}  # main company -> (is sure, rank, reason); a row linked by a human counts as its main company
    for c in candidates:
        found = compare_one(new, c, info, extra_platforms)
        if not found:
            continue
        cid = c.get("group_id", "")
        main = main_id(cid, by_id)
        sure_now, rank, reason = found
        if main != cid:
            reason += " (via an entry linked to this company)"
        if main not in best or (sure_now, rank) > best[main][:2]:
            best[main] = (sure_now, rank, reason)

    pairs = set()  # companies a human said are different
    for c in candidates:
        mine = main_id(c.get("group_id", ""), by_id)
        for other in c.get("different_from") or []:
            pairs.add(frozenset((mine, main_id(other, by_id))))
    dropped = {m for m in best for o in best
               if o != m and frozenset((o, m)) in pairs and best[o][:2] > best[m][:2]}  # the stronger match explains the entry

    sure = [{"group_id": m, "reason": v[2]} for m, v in best.items() if m not in dropped and v[0]]
    unsure = [{"group_id": m, "reason": v[2]} for m, v in best.items() if m not in dropped and not v[0]]
    if len(sure) == 1 and not unsure:
        return {"status": "DUPLICATE", "group_id": sure[0]["group_id"], "matches": sure, "input": info}
    if sure or unsure:  # several sure matches also need a human: the registry may already hold a duplicate
        return {"status": "POSSIBLE_DUPLICATE", "matches": sure + unsure, "input": info}
    return {"status": "NEW", "matches": [], "input": info}


def decide_json(payload):
    """Entry point for Make's Code module: JSON in ({"new": {...}, "candidates": [...]}), JSON out."""
    data = json.loads(payload)
    return json.dumps(decide(data["new"], data.get("candidates") or []), ensure_ascii=False)
