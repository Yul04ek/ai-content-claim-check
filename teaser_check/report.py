"""Readable HTML report of one judged teaser: result CSV + teaser text -> one HTML page (no AI, no network)."""
import argparse
import csv
import html
import json
import re
from pathlib import Path

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


def _highlight(teaser: str, rows: list[dict]) -> str:
    spans = []
    for r in rows:
        if r["verdict"] in ("", "Supported"):
            continue
        sp = _find_span(teaser, r["text"])
        if sp:
            spans.append((sp[0], sp[1], r["verdict"]))
    spans.sort()
    out, pos, last_end = [], 0, 0
    for start, end, verdict in spans:
        if start < last_end:  # overlap: keep the first span
            continue
        out.append(html.escape(teaser[pos:start]))
        out.append(f'<mark class="{CSS_CLASS[verdict]}">{html.escape(teaser[start:end])}</mark>')
        pos = last_end = end
    out.append(html.escape(teaser[pos:]))
    return "".join(out)


def _card(r: dict) -> str:
    verdict = r["verdict"]
    finding = FINDING_TEXT.get(r.get("finding", ""), r.get("finding", ""))
    quote = (r.get("record_quote") or "").strip()
    reason = html.escape((r.get("reason") or "").strip())
    quote_html = f'<div class="q"><b>Judge quoted from the evidence:</b> “{html.escape(quote)}”</div>' if quote else ""
    return (
        f'<div class="card {CSS_CLASS[verdict]}"><div class="head"><span class="badge {CSS_CLASS[verdict]}">{LABEL[verdict]}</span> '
        f'<span class="what">{html.escape(finding)}</span></div>'
        f'<div class="stmt"><span class="lbl">Teaser:</span> {html.escape(r["text"])}</div>'
        f'<div class="why"><b>Why:</b> {reason}</div>{quote_html}'
        f'<div class="by">Found by: {SOURCE_TEXT[row_source(r)]}</div></div>'
    )


def _judge_raw_ok(r: dict) -> bool:
    """The judge itself said 'supported' (code may have downgraded it because the quote was missing)."""
    return row_source(r) == "judge" and r.get("finding") == "supported"


def _clean_reason(text: str) -> str:
    """Judge's own reason, without the notes our code appended."""
    return (text or "").replace(" [quote NOT found in pack]", "").replace(" [no supporting quote given]", "").strip()


def build_report(rows: list[dict], teaser: str, title: str = "Teaser check") -> str:
    """Two blocks as the reviewer gets them: code checks and the judge's verdict, exactly as the judge gave it."""
    rows = [r for r in rows if r.get("text")]
    for r in rows:
        r.setdefault("verdict", "")
    pos = lambda r: (_find_span(teaser, r["text"]) or (10**9, 0))[0]
    code_rows = sorted((r for r in rows if row_source(r) != "judge"), key=pos)
    judged = [r for r in rows if row_source(r) == "judge"]
    flagged = sorted((r for r in judged if r.get("finding") != "supported"), key=pos)
    accepted = [r for r in judged if r.get("finding") == "supported"]
    pct = round(100 * len(accepted) / len(judged)) if judged else 0
    kinds = {}
    for r in flagged:
        kinds[r["finding"]] = kinds.get(r["finding"], 0) + 1
    kinds_txt = " · ".join(f"{FINDING_TEXT.get(k, k)}: {n}" for k, n in sorted(kinds.items(), key=lambda x: -x[1])) or "none"

    def judge_card(r):
        quote = (r.get("record_quote") or "").strip()
        q = f'<div class="q"><b>Evidence from the source (judge’s quote):</b> “{html.escape(quote)}”</div>' if quote else '<div class="q">The judge named no evidence from the source.</div>'
        return (f'<div class="card warn"><div class="head"><span class="badge warn">Needs attention</span> '
                f'<span class="what">{html.escape(FINDING_TEXT.get(r["finding"], r["finding"]))}</span></div>'
                f'<div class="stmt"><span class="lbl">Teaser:</span> {html.escape(r["text"])}</div>'
                f'<div class="why"><b>Why:</b> {html.escape(_clean_reason(r.get("reason")))}</div>{q}</div>')

    judge_cards = "".join(judge_card(r) for r in flagged) or "<p>The judge flagged nothing.</p>"
    code_cards = "".join(_card(r) for r in code_rows) or "<p>No findings.</p>"
    ok_list = "".join(
        f'<li>{html.escape(r["text"])}<div class="q">Evidence from the source: “{html.escape((r.get("record_quote") or "")[:300])}”</div></li>' for r in accepted
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
body{{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:16px;line-height:1.5;color:#1d2330;background:#fff}}
h1{{font-size:1.4rem}} h2{{font-size:1.1rem;margin-top:28px}}
.sum{{padding:12px 16px;border-radius:8px;border-left:6px solid #5b6b86;background:#eef1f6}}
.card{{border:1px solid #d8dce3;border-left:5px solid;border-radius:6px;padding:10px 14px;margin:10px 0}} .card.bad{{border-left-color:#c0392b}} .card.warn{{border-left-color:#d68910}} .card.note{{border-left-color:#7f8c8d}}
.badge{{font-size:.75rem;padding:2px 8px;border-radius:10px;color:#fff}} .badge.bad{{background:#c0392b}} .badge.warn{{background:#d68910}} .badge.note{{background:#7f8c8d}}
.lbl{{font-style:normal;font-size:.75rem;color:#4a5568;text-transform:uppercase}} .what{{font-weight:600}} .stmt{{margin:6px 0;font-style:italic}} .q,.by{{font-size:.85rem;color:#4a5568;margin-top:4px}}
pre{{white-space:pre-wrap;background:#f6f7f9;padding:12px;border-radius:6px;font-family:inherit}} mark.bad{{background:#f8c9c4}} mark.warn{{background:#fde3a7}}
@media (prefers-color-scheme:dark){{body{{background:#14171c;color:#e6e9ef}} pre{{background:#1d2128}} .card{{border-color:#333a45}} .q,.by{{color:#aab3c2}} .sum{{background:#222833}} mark{{color:#111}}}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<div class="sum"><b>Judge:</b> {len(judged)} statements checked, <b>{len(accepted)} supported ({pct}%)</b>, {len(flagged)} need attention.<br>
<small>Needs attention by type: {html.escape(kinds_txt)}</small><br>
<b>Automatic checks (code):</b> {len(code_rows)} findings.<br>
<small>Review only: nothing is published or sent. The judge's verdict is shown as the judge gave it.</small></div>
<h2>The teaser (flagged places highlighted)</h2><pre>{_highlight(teaser, code_rows + flagged)}</pre>
<h2>1. Judge: statements that need attention ({len(flagged)})</h2>{judge_cards}
<h2>2. Automatic checks (code rules, no AI) ({len(code_rows)})</h2>{code_cards}
<h2>Judge: supported statements ({len(accepted)})</h2><details><summary>Show them with the judge's quote</summary><ul>{ok_list}</ul></details>
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
                jobs.append((csv_path, Path(a.lab).parent / c["teaser"], Path(a.run_dir) / f"report_{c['case']}.html", f"Teaser {c['case']}"))
    else:
        jobs.append((Path(a.csv), Path(a.teaser), Path(a.out or "report.html"), Path(a.teaser).stem))
    for csv_path, teaser_path, out, title in jobs:
        rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
        out.write_text(build_report(rows, teaser_path.read_text(encoding="utf-8"), title), encoding="utf-8")
        print("Report:", out)


if __name__ == "__main__":
    main()
