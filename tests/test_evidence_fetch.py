# Offline tests for evidence_fetch (no network). Run: python tests/test_evidence_fetch.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evidence_fetch.fetch import (fetch_snapshot, robots_allowed, snapshot_from_html, to_pack_source, to_source_block)

HTML = """<html><head><title>About Demo</title>
<meta property="article:published_time" content="2021-09-09T10:00:00Z">
<script type="application/ld+json">{"@type":"Organization","name":"Demo Inc.","foundingDate":"2021"}</script>
<script>var secret = 'drop me';</script></head>
<body><nav>Menu Home</nav><main><h1>About us</h1><p>We build   scheduling tools.</p>
<p>We build   scheduling tools.</p><p>Write to help@demo.com</p></main><footer>Footer links</footer></body></html>"""


class Resp:
    def __init__(self, text="", status=200, ctype="text/html", url="https://demo.com/about"):
        self.text, self.status_code, self.headers, self.url = text, status, {"Content-Type": ctype}, url


def fake_get(routes):
    def get(url, **kw):
        return routes.get(url, Resp(status=404))
    return get


def test_text_is_clean():
    s = snapshot_from_html(HTML, "https://demo.com/about", fetched_at="2026-11-04T10:00:00Z")
    assert "scheduling tools" in s["text"] and "drop me" not in s["text"]
    assert "Menu" not in s["text"] and "Footer" not in s["text"]
    assert s["text"].count("We build scheduling tools.") == 1  # whitespace and repeat removed


def test_dates_and_markup():
    s = snapshot_from_html(HTML, "https://demo.com/about")
    assert s["page_date"].startswith("2021-09-09")
    assert s["structured_org"]["name"] == "Demo Inc."
    assert s["emails_found"] == ["help@demo.com"]


def test_undated_page():
    s = snapshot_from_html("<html><body><main>Hello</main></body></html>", "https://x.com", fetched_at="2026-11-04T10:00:00Z")
    assert s["page_date"] == ""
    assert "undated" in to_source_block(s)


def test_hash_is_stable():
    a = snapshot_from_html(HTML, "https://demo.com/about")
    b = snapshot_from_html(HTML, "https://demo.com/about")
    assert a["sha256"] == b["sha256"]


def test_make_block_and_pack_source():
    s = snapshot_from_html(HTML, "https://demo.com/about", fetched_at="2026-11-04T10:00:00Z")
    block = to_source_block(s)
    assert block.startswith("SOURCE: https://demo.com/about, read on 2026-11-04\nPAGE DATE: 2021-09-09")
    p = to_pack_source(s, "S1")
    assert p["id"] == "S1" and p["date_read"] == "2026-11-04" and p["excerpt"] == s["text"]


def test_fetch_ok():
    get = fake_get({"https://demo.com/robots.txt": Resp("User-agent: *\nAllow: /"), "https://demo.com/about": Resp(HTML)})
    assert "scheduling tools" in fetch_snapshot("https://demo.com/about", get=get)["text"]


def test_robots_disallow_blocks():
    get = fake_get({"https://demo.com/robots.txt": Resp("User-agent: *\nDisallow: /about"), "https://demo.com/about": Resp(HTML)})
    assert not robots_allowed("https://demo.com/about", get)
    try:
        fetch_snapshot("https://demo.com/about", get=get)
        assert False, "should be blocked"
    except ValueError as e:
        assert "robots" in str(e)


def test_rejects_http_404_and_pdf():
    for url, routes in [("http://demo.com/a", {}),
                        ("https://demo.com/about", {}),
                        ("https://demo.com/about", {"https://demo.com/about": Resp("x", ctype="application/pdf")})]:
        try:
            fetch_snapshot(url, get=fake_get(routes))
            assert False, f"should fail: {url}"
        except ValueError:
            pass


def test_parse_and_build_pack():
    from evidence_fetch.build_pack import build_pack, parse_make_evidence
    text = ("SOURCE: https://a.com/about, read on 2026-11-04\nPAGE DATE: none shown (undated page)\nLine one\nLine two\n\n"
            "SOURCE: https://a.com/post, read on 2026-11-04\nPAGE DATE: 2022-09-09\nPost text\n")
    src = parse_make_evidence(text)
    assert [s["url"] for s in src] == ["https://a.com/about", "https://a.com/post"]
    assert src[0]["page_date"] == "" and src[1]["page_date"] == "2022-09-09"
    assert src[0]["text"] == "Line one\nLine two"
    pack = build_pack(src, "G1", "R1", "A Inc.", "https://a.com", {"approved_aura_offers": [{"id": "A1", "text": "x"}]})
    assert pack["sources"][1]["id"] == "S2" and pack["facts"] == [] and pack["approved_aura_offers"][0]["id"] == "A1"


def test_pack_without_facts_works_in_the_checker():
    import json, tempfile
    from teaser_check.pack import load_pack, pack_to_text
    from teaser_check.pipeline import check_teaser
    from teaser_check.judge import no_judge
    pack = {"group_id": "G1", "sources": [{"id": "S1", "url": "https://a.com", "date_read": "2026-11-04",
                                           "page_date": "2022-09-09", "excerpt": "We raised a seed round."}]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(pack, f)
    loaded = load_pack(f.name)
    assert loaded["facts"] == [] and "page date 2022-09-09" in pack_to_text(loaded)
    rows, _ = check_teaser(loaded, "INTERNAL REVIEW ONLY\nA snapshot [S1]. Hypothesis 1. Hypothesis 2. Sign up for AURA help.\nSource notes\nS1", no_judge)
    assert isinstance(rows, list)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} tests passed")
