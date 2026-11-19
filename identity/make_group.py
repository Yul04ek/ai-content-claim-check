# Rows of the Evidence sheet that have no company ID yet -> one group per company, for the intake scenario.
# Make's "Search Rows" returns one bundle per source URL. This turns them into one entry per company.
# Rows are grouped by the company label as written (case and extra spaces ignored). Different labels stay
# different entries: the duplicate check decides later whether they are the same company.
#
# Code module (grouping): make_group(input) -> {"groups": [{company_label, candidate_url, source_urls, row_numbers}]}
# The Iterator after this module gives each group's fields directly: {{15.company_label}}, not {{15.value.company_label}}.
# Input: {"rows": [{"row": 2, "label": "Corvane", "url": "https://...", "type": "Other"}, ...]}

try:  # in the repository; inside Make these names are defined above (the block holds match.py first)
    from identity.match import host_of, is_platform, json
except ImportError:
    pass

WEBSITE_TYPE = "company website"  # value of the column "Source type" that marks the company's own site


def clean(text):
    return " ".join(str(text or "").split())


def website_candidate(items):
    """The company's site: the URL marked 'Company website', else the first HTTPS URL that is not on a platform."""
    for url, kind in items:
        if clean(kind).lower() == WEBSITE_TYPE:
            return url
    for url, kind in items:
        if url.lower().startswith("https://") and not is_platform(host_of(url)):
            return url
    return ""


def make_group(inp):
    raw = inp.get("rows") or []
    if isinstance(raw, str):  # Make may pass the aggregated array as JSON text
        raw = json.loads(raw) if raw.strip() else []
    groups, order = {}, []
    for item in raw:
        item = item or {}
        label = clean(item.get("label"))
        url = clean(item.get("url"))
        key = label.lower()
        if key not in groups:
            groups[key] = {"company_label": label, "items": [], "row_numbers": []}
            order.append(key)
        group = groups[key]
        group["row_numbers"].append(int(float(item.get("row"))))
        if url and url not in [u for u, _ in group["items"]]:
            group["items"].append((url, item.get("type")))
    out = []
    for key in order:
        g = groups[key]
        out.append({"company_label": g["company_label"], "candidate_url": website_candidate(g["items"]),
                    "source_urls": "; ".join(u for u, _ in g["items"]), "row_numbers": g["row_numbers"]})
    return {"groups": out}
