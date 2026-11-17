# Glue between Make (scenario 8310124) and identity/match.py: reads the Make inputs and registry records,
# returns flat fields Make can map. Pure Python, standard library only, no type hints.
#
# Code module 1 (keys):     make_keys(input)    -> search keys for the Data Store search
# Code module 2 (decision): make_decide(input)  -> NEW / DUPLICATE / POSSIBLE_DUPLICATE / INVALID
# Empty keys become NONE: a search for an empty value would match every record whose field is empty.

try:  # in the repository; inside Make these names are defined above (the block holds match.py first)
    from identity.match import check_input, decide, describe_input, host_of, json, truthy
except ImportError:
    pass

import uuid

NONE = "__none__"
REVIEW_STATE = {"NEW": "SOURCE_CANDIDATE_UNVERIFIED", "POSSIBLE_DUPLICATE": "POSSIBLE_DUPLICATE_HELD"}


def split_list(text, sep):
    return [p.strip() for p in (text or "").replace("\n", sep).split(sep) if p.strip()]


def new_from_make(inp):
    """Inputs of the scenario -> the new entry for decide()."""
    return {"name": inp.get("company_label") or "", "website": inp.get("candidate_url") or "",
            "registration_id": inp.get("registration_id") or "",
            "jurisdiction": inp.get("registration_jurisdiction") or "",
            "sources": split_list(inp.get("source_urls"), ";")}


def candidate_from_make(item):
    """One aggregated search result (flat fields named as in the registry) -> a candidate for decide()."""
    return {"group_id": item.get("group_id") or "", "name": item.get("company_label") or "",
            "aliases": split_list(item.get("aliases"), ";"), "official_domain": host_of(item.get("official_domain")),
            "domain_history": [host_of(d) for d in split_list(item.get("domain_history"), ",")],
            "candidate_url": item.get("candidate_url") or "", "registration_id": item.get("registration_id") or "",
            "registration_verified": truthy(item.get("registration_verified")),
            "jurisdiction": item.get("jurisdiction") or "",
            "duplicate_of": item.get("duplicate_of") or "",
            "different_from": split_list(item.get("different_from"), ";")}


def make_keys(inp):
    new = new_from_make(inp)
    info = describe_input(new)
    return {"name_key": info["name_key"] or NONE, "domain_candidate": info["domain_candidate"] or NONE,
            "registration_key": info["registration_key"] or NONE, "company_label": new["name"].strip() or NONE,
            "problems": "; ".join(check_input(new))}


def make_decide(inp):
    raw = inp.get("candidates") or []
    if isinstance(raw, str):  # Make may pass the aggregated array as JSON text
        raw = json.loads(raw) if raw.strip() else []
    seen, candidates = set(), []
    for item in raw:
        c = candidate_from_make(item or {})
        if c["group_id"] and c["group_id"] not in seen:  # an empty search bundle has no group_id
            seen.add(c["group_id"])
            candidates.append(c)
    result = decide(new_from_make(inp), candidates)
    info = result["input"]
    # a new permanent ID (full UUIDv4) only for a record that will be written; a DUPLICATE keeps the existing group_id
    new_id = "G-" + str(uuid.uuid4()) if result["status"] in REVIEW_STATE else ""
    return {"status": result["status"], "group_id": result.get("group_id", ""),
            "new_group_id": new_id, "review_state": REVIEW_STATE.get(result["status"], ""),
            "duplicate_candidates": json.dumps(result["matches"], ensure_ascii=False) if result["matches"] else "",
            "problems": "; ".join(result.get("problems", [])), "candidates_seen": len(candidates),
            "name_key": info["name_key"], "registration_key": info["registration_key"],
            "source_provenance": "; ".join(new_from_make(inp)["sources"])}
