# URL -> snapshot of the page text. No AI here: the text is copied as it is, with date and hash.
# The judge and the teaser generator must both use this same snapshot.

import hashlib
import json
import re
from datetime import datetime, timezone
from urllib import robotparser
from urllib.parse import urlparse

from bs4 import BeautifulSoup

USER_AGENT = "yl004b-evidence-test/0.1 (internal research test, no outreach)"
TIMEOUT = 20
DROP_TAGS = ["script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form", "iframe"]
DATE_META = ["article:published_time", "og:article:published_time", "datePublished", "date", "DC.date.issued"]
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def robots_allowed(url: str, get) -> bool:
    """False only if robots.txt clearly disallows. A missing robots.txt means allowed."""
    p = urlparse(url)
    try:
        r = get(f"{p.scheme}://{p.netloc}/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        if r.status_code != 200:
            return True
        rp = robotparser.RobotFileParser()
        rp.parse(r.text.splitlines())
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def find_page_date(soup: BeautifulSoup) -> str:
    """Date shown by the page itself (meta tags, JSON-LD, <time>). Empty string if none."""
    for name in DATE_META:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except ValueError:
            continue
        for item in (data if isinstance(data, list) else [data]):
            if isinstance(item, dict) and item.get("datePublished"):
                return str(item["datePublished"])
    t = soup.find("time")
    if t:
        return (t.get("datetime") or t.get_text()).strip()
    return ""


def find_jsonld_org(soup: BeautifulSoup) -> dict:
    """Name, founders, founding date, address from schema.org Organization markup, if the page has it."""
    out = {}
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except ValueError:
            continue
        for item in (data if isinstance(data, list) else [data]):
            if isinstance(item, dict) and item.get("@type") in ("Organization", "Corporation", "LocalBusiness"):
                for k in ("name", "legalName", "foundingDate", "founder", "address"):
                    if item.get(k):
                        out[k] = item[k]
    return out


def clean_text(soup: BeautifulSoup) -> str:
    for t in soup(DROP_TAGS):
        t.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    lines, last = [], None
    for raw in root.get_text("\n").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line and line != last:  # drop empty lines and repeats of the previous line
            lines.append(line)
            last = line
    return "\n".join(lines)


def snapshot_from_html(html: str, url: str, fetched_at: str = "", headers: dict | None = None, status: int = 200) -> dict:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    page_date = find_page_date(soup)
    org = find_jsonld_org(soup)
    text = clean_text(soup)
    headers = headers or {}
    return {
        "url": url,
        "fetched_at": fetched_at or now_utc(),
        "http_status": status,
        "title": title,
        "page_date": page_date,  # '' means the page shows no date: label it undated
        "last_modified_header": headers.get("Last-Modified", ""),
        "structured_org": org,
        "emails_found": sorted(set(EMAIL_RE.findall(text))),
        "text": text,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def fetch_snapshot(url: str, get=None) -> dict:
    """Download one page and return its snapshot. Raises ValueError for non-HTTPS or blocked pages."""
    if not url.startswith("https://"):
        raise ValueError(f"Only https:// addresses are allowed: {url}")
    if get is None:
        import requests
        get = requests.get
    if not robots_allowed(url, get):
        raise ValueError(f"robots.txt disallows this page: {url}")
    r = get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    if r.status_code != 200:
        raise ValueError(f"HTTP {r.status_code} for {url}")
    ctype = r.headers.get("Content-Type", "")
    if "html" not in ctype and "text" not in ctype:
        raise ValueError(f"Not a text page ({ctype}): {url}")
    return snapshot_from_html(r.text, r.url if hasattr(r, "url") else url, headers=dict(r.headers), status=r.status_code)


def to_source_block(snap: dict) -> str:
    """The text block to paste into the 'evidence' field of the Make teaser generator."""
    date = snap["fetched_at"][:10]
    head = f"SOURCE: {snap['url']}, read on {date}"
    note = f"PAGE DATE: {snap['page_date']}" if snap["page_date"] else "PAGE DATE: none shown (undated page)"
    return f"{head}\n{note}\n{snap['text']}\n"


def to_pack_source(snap: dict, source_id: str) -> dict:
    """The same snapshot as a source entry of the JSON evidence pack."""
    return {"id": source_id, "url": snap["url"], "date_read": snap["fetched_at"][:10],
            "page_date": snap["page_date"] or "none shown", "sha256": snap["sha256"], "excerpt": snap["text"]}
