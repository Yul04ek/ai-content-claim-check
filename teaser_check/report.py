"""Readable HTML report of one judged teaser: result CSV + teaser text -> one HTML page (no AI, no network)."""
import argparse
import csv
import html
import json
import re
from pathlib import Path

from teaser_check.pack import load_pack
from teaser_check.score import row_source

RANK = {"Unsupported": 3, "Needs Human Verification": 2, "Supported": 0, "": 1}
LABEL = {
    "Unsupported": "Not supported",
    "Needs Human Verification": "Check by a human",
    "Supported": "Supported",
    "": "Note",
}
CSS_CLASS = {"Unsupported": "bad", "Needs Human Verification": "warn", "Supported": "ok", "": "note"}
FINDING_TEXT = {
    "not_in_pack": "Nothing in the evidence says this",
    "contradicted": "The evidence says something different",
    "promise": "Promises or implies investment or acceptance",
    "assumption_as_fact": "Assumption stated as a fact",
    "overgeneralised": "Fact stretched too far",
    "meaning_shifted": "Meaning is stronger or different",
    "hypothesis_unlabelled": "Possibility written as an established fact",
    "hypothesis_without_fact": "Hypothesis without a fact behind it",
    "aura_offer_unverified": "AURA offer not on the approved list",
    "supported": "Judge accepted it",
    "rule_broken": "Rule check (code)",
}
SOURCE_TEXT = {"judge": "the judge (model)", "code": "a code rule", "coverage": "coverage check: the judge gave no verdict for this line"}


def _find_span(teaser: str, text: str):
    words = re.findall(r"\S+", text or "")
    if len(words) < 3:
        return None
    for n in (len(words), min(len(words), 8)):
        m = re.search(r"\s+".join(re.escape(w) for w in words[:n]), teaser, re.I)
        if m:
            return m.span()
    return None


def _clean_reason(text: str) -> str:
    return (text or "").replace(" [quote NOT found in pack]", "").replace(" [no supporting quote given]", "").strip()


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", (text or "").lower()))


def _line_kind(line: str, part: str) -> str:
    """'skip' for headings and empty lines, 'template' for parts the judge does not read, else 'claim'."""
    if len(re.findall(r"\w+", line)) < 5 or line.strip().endswith(":"):
        return "skip"
    if re.match(r"^\s*(?:H\d|\d+[.)])\s*[^.:;]*$", line) and len(line.split()) <= 12:
        return "skip"  # a numbered title such as "1) Privacy-first niche" is a heading
    if part in ("signup", "start") or re.match(r"^\W*(source notes?|sources?)\b", part or "", re.I):
        return "template"
    return "claim"


def _source_name(ref: str, pack: dict | None) -> str:
    for src in (pack or {}).get("sources", []):
        if src.get("id") == ref:
            return f'{ref}, {src.get("url", "")}, read {src.get("date_read", "")}'.rstrip(", ")
    return ref if ref and ref != "none" else "no source named"


def _card(r: dict) -> str:
    """One card for a finding of the code rules."""
    verdict = r["verdict"]
    finding = FINDING_TEXT.get(r.get("finding", ""), r.get("finding", ""))
    reason = html.escape(_clean_reason(r.get("reason")))
    by = "coverage check: the judge gave no verdict for this line" if row_source(r) == "coverage" else "code rule"
    return (
        f'<div class="card {CSS_CLASS[verdict]}"><div class="head"><span class="badge {CSS_CLASS[verdict]}">{LABEL[verdict]}</span> '
        f'<span class="what">{html.escape(finding)}</span></div>'
        f'<div class="stmt">{html.escape(r["text"])}</div>'
        f'<div class="why"><b>Why:</b> {reason}</div><div class="by">Found by: {by}</div></div>'
    )


def build_report(rows: list[dict], teaser: str, title: str = "Teaser check", pack: dict | None = None) -> str:
    """The teaser line by line with what the judge said about it, plus the code checks. The judge is taken as right."""
    from .sections import section_of_lines  # here, not at the top: sections imports judge

    rows = [r for r in rows if r.get("text")]
    for r in rows:
        r.setdefault("verdict", "")
    judged = [r for r in rows if row_source(r) == "judge"]
    code_rows = [r for r in rows if row_source(r) != "judge"]
    # which teaser line does each judge entry belong to: the line that holds most of its words
    lines = section_of_lines(teaser)
    by_line: dict[int, list[dict]] = {}
    for r in judged:
        cw = _words(r["text"])
        best, score = None, 0.0
        for i, (line, part) in enumerate(lines):
            if _line_kind(line, part) == "skip":
                continue
            lw = _words(line)
            ov = len(cw & lw) / max(1, min(len(cw), len(lw)))
            if ov > score:
                best, score = i, ov
        if best is not None and score >= 0.6:
            by_line.setdefault(best, []).append(r)
    html_lines, n_ok, n_flag, n_none = [], 0, 0, 0
    for i, (line, part) in enumerate(lines):
        kind = _line_kind(line, part)
        text = html.escape(line)
        if kind == "skip":
            html_lines.append(f'<div class="ln head">{text or "&nbsp;"}</div>')
            continue
        if kind == "template":
            html_lines.append(f'<div class="ln"><div class="t">{text}</div><div class="tag grey">Header, sign-up text or source note: checked by code rules, not by the judge</div></div>')
            continue
        entries = by_line.get(i, [])
        if not entries:
            n_none += 1
            html_lines.append(f'<div class="ln"><div class="t">{text}</div><div class="tag grey">The judge did not check this line</div></div>')
            continue
        tags = []
        for r in entries:
            if r.get("finding") == "supported":
                n_ok += 1
                tags.append(f'<div class="tag ok">Verified. Evidence: {html.escape(_source_name(r.get("source_field", ""), pack))}</div>')
            else:
                n_flag += 1
                what = FINDING_TEXT.get(r["finding"], r["finding"])
                tags.append(f'<div class="tag warn"><b>{html.escape(what)}.</b> {html.escape(_clean_reason(r.get("reason")))}</div>')
        cls = "flag" if any(r.get("finding") != "supported" for r in entries) else "good"
        html_lines.append(f'<div class="ln {cls}"><div class="t">{text}</div>{"".join(tags)}</div>')
    checked = n_ok + n_flag
    total = checked + n_none
    pct = round(100 * n_ok / checked) if checked else 0
    code_cards = "".join(_card(r) for r in code_rows) or "<p>No findings.</p>"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
body{{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:16px;line-height:1.5;color:#1d2330;background:#fff}}
h1{{font-size:1.4rem}} h2{{font-size:1.1rem;margin-top:28px}}
.sum{{padding:12px 16px;border-radius:8px;border-left:6px solid #5b6b86;background:#eef1f6}}
.ln{{padding:6px 10px;margin:2px 0;border-left:4px solid transparent}} .ln.head{{font-weight:600;margin-top:10px;border:0}}
.ln.good{{border-left-color:#2e8b57}} .ln.flag{{border-left-color:#d68910;background:#fff8ea}}
.t{{white-space:pre-wrap}} .tag{{font-size:.82rem;margin-top:2px}} .tag.ok{{color:#2e7d4f}} .tag.warn{{color:#a86400}} .tag.grey{{color:#6b7280}}
.card{{border:1px solid #d8dce3;border-left:5px solid;border-radius:6px;padding:10px 14px;margin:10px 0}} .card.bad{{border-left-color:#c0392b}} .card.warn{{border-left-color:#d68910}} .card.note{{border-left-color:#7f8c8d}}
.badge{{font-size:.75rem;padding:2px 8px;border-radius:10px;color:#fff}} .badge.bad{{background:#c0392b}} .badge.warn{{background:#d68910}} .badge.note{{background:#7f8c8d}}
.what{{font-weight:600}} .stmt{{margin:6px 0;font-style:italic}} .q,.by{{font-size:.85rem;color:#4a5568;margin-top:4px}}
@media (prefers-color-scheme:dark){{body{{background:#14171c;color:#e6e9ef}} .sum{{background:#222833}} .ln.flag{{background:#2d2616}} .card{{border-color:#333a45}} .q,.by{{color:#aab3c2}} .tag.ok{{color:#6fcf97}} .tag.warn{{color:#f2b04d}} .tag.grey{{color:#9aa3b2}}}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<div class="sum"><b>Judge:</b> {checked} statements checked, <b>{n_ok} verified ({pct}%)</b>, {n_flag} flagged. {n_none} lines were not checked by the judge.<br>
<b>Automatic checks (code):</b> {len(code_rows)} findings (below the teaser).<br>
<small>Review only: nothing is published or sent. Green = verified against the source, amber = the judge has a remark, grey = not checked by the judge.</small></div>
<h2>The teaser with the judge's verdict</h2>
{"".join(html_lines)}
<h2>Automatic checks (code rules, no AI) ({len(code_rows)})</h2>{code_cards}
</body></html>"""


def main():
    ap = argparse.ArgumentParser(description="HTML report from a result CSV and the teaser text.")
    ap.add_argument("csv", nargs="?", help="result CSV of one case")
    ap.add_argument("teaser", nargs="?", help="teaser text file")
    ap.add_argument("--out", help="output HTML file")
    ap.add_argument("--run-dir", help="folder of one experiment run (B.csv, C.csv, ...)")
    ap.add_argument("--lab", help="lab_set.json (with --run-dir)")
    a = ap.parse_args()
    jobs = []
    if a.run_dir:
        lab = json.loads(Path(a.lab).read_text(encoding="utf-8"))
        for c in lab["cases"]:
            csv_path = Path(a.run_dir) / f"{c['case']}.csv"
            if csv_path.exists():
                jobs.append((csv_path, Path(a.lab).parent / c["teaser"], Path(a.run_dir) / f"report_{c['case']}.html", f"Teaser {c['case']}",
                             load_pack(Path(a.lab).parent / c["pack"])))
    else:
        jobs.append((Path(a.csv), Path(a.teaser), Path(a.out or "report.html"), Path(a.teaser).stem, None))
    for csv_path, teaser_path, out, title, pack in jobs:
        rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
        out.write_text(build_report(rows, teaser_path.read_text(encoding="utf-8"), title, pack), encoding="utf-8")
        print("Report:", out)


if __name__ == "__main__":
    main()
