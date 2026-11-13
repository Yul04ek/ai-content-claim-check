"""Readable HTML report of one judged teaser: result CSV + teaser text -> one HTML page (no AI, no network)."""
import argparse
import csv
import html
import json
import re
from pathlib import Path

from claim_check.common import norm
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
    "weak_evidence": "Quote chosen poorly",
    "supported": "Judge accepted it",
    "rule_broken": "Rule check (code)",
}
BASIS_TEXT = {"strong": "strong", "partial": "partial", "weak": "weak", "none": "none"}  # words shown for the link to the sources


def _basis_note(r: dict) -> str:
    return f' Link to the sources: <b>{BASIS_TEXT[r["basis"]]}</b>.' if r.get("basis") in BASIS_TEXT else ""


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
    from .sections import heading_name  # here, not at the top: sections imports judge
    bullet = bool(re.match(r"^\s*[-*\u2022]\s*\S", line))  # a bullet is a statement, even a short one ("100% Data Ownership")
    # a short line is a heading, except in the company snapshot, where "Team of 4 people" is a fact
    heading_like = bool(re.match(r"^\W*(source notes?|sources?)\W*$|^\s*#", line, re.I))
    short = len(re.findall(r"\w+", line)) < 5 and not bullet and (part != "snapshot" or heading_like)
    if not line.strip() or short or line.strip().endswith(":") or heading_name(line):
        return "skip"
    if re.match(r"^\s*(?:H\d|\d+[.)])\s*[^.:;]*$", line) and len(line.split()) <= 12:
        return "skip"  # a numbered title such as "1) Privacy-first niche" is a heading
    if re.match(r"^\W*(SOURCE:|Sign up for AURA)", line, re.I):
        return "template"  # source notes and the sign-up sentence are checked by code rules
    if part in ("signup", "start") or re.match(r"^\W*(source notes?|sources?)\b", part or "", re.I):
        return "template"
    return "claim"


def _sentences(line: str) -> list[str]:
    """A line cut into sentences; fragments of fewer than 3 words stay with the sentence before."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"\u201c(\[])", re.sub(r"^\W*(?:[-*\u2022]|\d+[.)])\s*", "", line.strip()))
    out: list[str] = []
    for part in parts:
        if out and len(re.findall(r"\w+", part)) < 3:
            out[-1] += " " + part
        elif part.strip():
            out.append(part.strip())
    return out or [line.strip()]


def _source_html(ref: str, pack: dict | None) -> str:
    """'S1, <address as link>, read <date>' for a company source; 'O1, table (link), read <date>' for a row of the AURA offer table."""
    e = html.escape
    for src in (pack or {}).get("sources", []):
        if src.get("id") == ref:
            url = src.get("url", "")
            link = f'<a href="{e(url)}">{e(url)}</a>' if url.startswith("https://") else e(url)
            return f'{e(ref)}, {link}, read {e(src.get("date_read", ""))}'.rstrip(", ")
    for offer in (pack or {}).get("approved_aura_offers", []):
        if offer.get("id") == ref:
            url, date = (pack or {}).get("offers_table_url", ""), (pack or {}).get("offers_table_date", "")
            where = f'<a href="{e(url)}">table</a>' if url.startswith("https://") else f'offer table: {e(offer.get("name", ""))}'
            return f'{e(ref)}, {where}' + (f", read {e(date)}" if date else "")
    return e(ref) if ref and ref != "none" else "no source named"


WHOLE_TEASER = re.compile(r"^(first offer$|\d+ (labelled )?hypothes|\d+ offers,|\d+ words|source notes|.*: Limits line missing)", re.I)


def _attach_code(code_rows: list[dict], lines: list, kinds: list, sentences: list, sources_end=None):
    """Puts every code finding under the line (or the sentence) it is about. Returns (line index -> rows,
    sentence index -> rows, rows about the whole teaser). A row that matches no line goes to the whole teaser."""
    from .deterministic import loose
    by_line: dict[int, list[dict]] = {}
    by_sentence: dict[int, list[dict]] = {}
    whole: list[dict] = []
    for r in code_rows:
        text = (r.get("text") or "").strip()
        key = loose(text)
        place = None
        if sources_end is not None and re.match(r"source notes:", text, re.I):
            by_line.setdefault(sources_end, []).append(r)  # under the list of sources
            continue
        if key and not WHOLE_TEASER.match(text):
            candidates = [i for i, (line, _) in enumerate(lines) if kinds[i] != "skip" and key in loose(line)]
            if r.get("kind") == "offer":  # an offer row belongs to its "Offer:" line
                candidates = [i for i in candidates if re.match(r"^\W*Offer:", lines[i][0], re.I)] or candidates
            if candidates:
                place = candidates[0]
            else:
                cw = _words(text)
                best, score = None, 0.0
                for i, (line, _) in enumerate(lines):
                    if kinds[i] != "skip" and cw:
                        ov = len(cw & _words(line)) / len(cw)
                        if ov > score:
                            best, score = i, ov
                if best is not None and score >= 0.6:
                    place = best
        if place is None:
            whole.append(r)
            continue
        hit = [k for k, (i, sent) in enumerate(sentences) if i == place and key in loose(sent)]
        if hit:
            by_sentence.setdefault(hit[0], []).append(r)
        else:
            by_line.setdefault(place, []).append(r)
    return by_line, by_sentence, whole


PASSED = '<div class="tag code ok"><b>Code:</b> checked.</div>'


def _ok_code(text: str) -> str:
    return f'<div class="tag code ok"><b>Code:</b> {text}</div>'


def _quote_sources(line: str, pack: dict | None) -> list[str]:
    """Ids of the company sources that hold each quotation of an Evidence line word for word."""
    from .deterministic import QUOTE, loose
    found = []
    for quote in (q for q in QUOTE.findall(line) if len(q.split()) >= 3):
        parts = [loose(p) for p in re.split(r"\.{3}|…", quote) if loose(p)]
        for src in (pack or {}).get("sources", []):
            if parts and all(p in loose(src.get("excerpt", "")) for p in parts):
                found.append(src["id"])
                break
    return list(dict.fromkeys(found))


def _code_pass(line: str, pack: dict | None, offer: dict | None) -> str:
    """What the code compared a line with, when it found no error there; the plain note when it compared with nothing named.
    The note names the part that was checked (offer, limits, evidence, source notes)."""
    from .postchecks import address_of
    if re.match(r"^\W*Evidence:", line, re.I):
        ids = _quote_sources(line, pack)
        if ids:
            return _ok_code("evidence checked. Evidence: " + "; ".join(_source_html(i, pack) for i in ids) + ".")
    m = re.match(r"^\W*(Offer|Limits):", line, re.I)
    if offer and m:
        return _ok_code(f"{m[1].lower()} checked. Evidence: {_source_html(offer['id'], pack)}.")
    for src in (pack or {}).get("sources", []):
        if src.get("url", "").startswith("http") and address_of(src["url"]) in line.lower():
            return _ok_code(f"source notes checked. Evidence: {_source_html(src['id'], pack)}.")
    return PASSED


def _judge_tags(entries: list[dict], pack: dict | None, quote_line: bool = True) -> tuple[list[str], bool]:
    """The judge's verdicts on one statement. A verified one names its source; the code line under it says that the
    judge's quote was found word for word in that source (a verified row whose quote is not found is downgraded)."""
    tags, flagged = [], False
    for r in entries:
        if r.get("finding") == "supported":
            where = _source_html(r.get("source_field", ""), pack)
            tags.append(f'<div class="tag ok"><b>Judge:</b> verified. Evidence: {where}.{_basis_note(r)}</div>')
            if quote_line:  # not on Evidence lines: there the code line of the rule already says where the quote is
                tags.append(_ok_code(f"quote checked. Evidence: {where}."))
        else:
            flagged = True
            what = FINDING_TEXT.get(r["finding"], r["finding"])
            tags.append(f'<div class="tag warn"><b>Judge: {html.escape(what)}.</b> {html.escape(_clean_reason(r.get("reason")))}{_basis_note(r)}</div>')
    return tags, flagged


def _code_tag(r: dict, pack: dict | None = None) -> str:
    """One inline note for a code finding: grey, with the table text when the code compared with the table."""
    cls = {"Unsupported": "bad", "Needs Human Verification": "warn"}.get(r.get("verdict", ""), "note")
    what = LABEL.get(r.get("verdict", ""), "Note")  # the reason below says what exactly is wrong
    reason = html.escape(_clean_reason(r.get("reason")))
    if r.get("kind") == "offer":  # a separate rule: every offer except Free carries a review requirement in the table
        ref = r.get("source_field") if r.get("source_field") not in (None, "", "none") else ""
        return f'<div class="tag code {cls}"><b>Code: offer review, {html.escape(what[:1].lower() + what[1:])}.</b> Evidence: {_source_html(ref, pack)}, review requirements.</div>'
    quote = f'<br><span class="q">The table says: \u201c{html.escape(r["record_quote"])}\u201d</span>' if r.get("record_quote") else ""
    who = "Coverage check" if row_source(r) == "coverage" else "Code"
    return f'<div class="tag code {cls}"><b>{who}: {html.escape(what)}.</b> {reason}{quote}</div>'


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


def run_meta(folder) -> str:
    """'2026-11-10 10:46:33 | rubric n2 | model gemini-3.5-flash-lite | repeat 1' from the name of a run folder
    (<date>_<time>_<rubric>_<model>_r<repeat>); '' for any other folder name."""
    m = re.match(r"^(\d{4}-\d\d-\d\d)_(\d\d)-(\d\d)-(\d\d)_([^_]+)_([^_]+)_r(\d+)$", Path(folder).name)
    return f"{m[1]} {m[2]}:{m[3]}:{m[4]} | rubric {m[5]} | model {m[6]} | repeat {m[7]}" if m else ""


def build_report(rows: list[dict], teaser: str, title: str = "Teaser check", pack: dict | None = None, meta: str = "") -> str:
    """The teaser line by line with what the judge said about it, plus the code checks. The judge is taken as right."""
    from .sections import section_of_lines  # here, not at the top: sections imports judge

    rows = [r for r in rows if r.get("text")]
    for r in rows:
        r.setdefault("verdict", "")
    judged = [r for r in rows if row_source(r) == "judge"]
    code_rows = [r for r in rows if row_source(r) != "judge"]
    labels = ("Evidence",) + (("Offer", "Limits") if any(o.get("offer_line") for o in (pack or {}).get("approved_aura_offers", [])) else ())
    lines = section_of_lines(teaser)
    kinds = []
    in_sources = False  # lines after a "Source notes" heading belong to the source notes
    for line, part in lines:
        if re.match(r"^\W*(source notes?|sources?)\W*$", line, re.I):
            in_sources = True
        elif re.match(r"^\W*(Sign up for AURA|#)", line, re.I):
            in_sources = False
        kind = _line_kind(line, part)
        if in_sources and kind == "claim":
            kind = "template"
        if kind == "claim" and re.match(r"^\W*(%s):" % "|".join(labels), line, re.I):
            kind = "template"  # Offer, Evidence and Limits lines are compared with the table and the sources by code
        kinds.append(kind)
    sources_end = None  # the last line of the source notes: the note about a missing source sits under it
    in_sources = False
    for i, (line, _) in enumerate(lines):
        if re.match(r"^\W*(source notes?|sources?)\W*$", line, re.I):
            in_sources = True
        elif re.match(r"^\W*(Sign up for AURA|#)", line, re.I):
            in_sources = False
        if (in_sources or re.match(r"^\W*SOURCE:", line, re.I)) and kinds[i] == "template":
            sources_end = i
    # the unit is the statement: a sentence of a line for the judge; a whole line the code checks counts as one statement
    sentences = [(i, sent) for i, (line, _) in enumerate(lines) if kinds[i] == "claim" for sent in _sentences(line)]
    by_sentence: dict[int, list[dict]] = {}
    by_template: dict[int, list[dict]] = {}   # judge verdicts on lines the code checks too (Evidence lines): checked by both
    def best_template(cw):
        best, score = None, 0.0
        for i, (line, _) in enumerate(lines):
            if kinds[i] == "template":
                lw = _words(line)
                ov = len(cw & lw) / max(1, min(len(cw), len(lw)))
                if ov > score:
                    best, score = i, ov
        return best if score >= 0.6 else None

    for r in judged:
        cw = _words(r["text"])
        # an "Evidence: ..." verdict belongs to the Evidence line, not to a hypothesis that repeats the same quote
        if re.match(r"^\W*(%s):" % "|".join(labels), r["text"], re.I) and best_template(cw) is not None:
            by_template.setdefault(best_template(cw), []).append(r)
            continue
        best, score = None, 0.0
        for k, (_, sent) in enumerate(sentences):
            sw = _words(sent)
            ov = len(cw & sw) / max(1, min(len(cw), len(sw)))
            if ov > score:
                best, score = k, ov
        if best is not None and score >= 0.6:
            by_sentence.setdefault(best, []).append(r)
        elif best_template(cw) is not None:
            by_template.setdefault(best_template(cw), []).append(r)
    sent_ids: dict[int, list[int]] = {}
    for k, (i, _) in enumerate(sentences):
        sent_ids.setdefault(i, []).append(k)
    code_by_line, code_by_sentence, code_whole = _attach_code(code_rows, lines, kinds, sentences, sources_end)
    judged_units = list(by_sentence.values()) + list(by_template.values())
    n_ok = sum(1 for e in judged_units if all(r.get("finding") == "supported" for r in e))
    n_flag = len(judged_units) - n_ok
    n_code = sum(1 for kind in kinds if kind == "template")
    n_both = len(by_template)
    n_none = len(sentences) - len(by_sentence)
    offers = [o for o in (pack or {}).get("approved_aura_offers", []) if o.get("offer_line")]
    html_lines = []
    n_code_found = 0   # code findings on the lines that only the code checks
    n_review = 0       # rows that only repeat the review requirement of the offer table: not errors
    offer = None       # the offer of the block the line belongs to (for the Offer and Limits lines)
    for i, (line, part) in enumerate(lines):
        text = html.escape(line)
        m = re.match(r"^\W*Offer:\s*(.*)$", line, re.I)
        if m:
            offer = next((o for o in offers if norm(o["offer_line"]) == norm(m[1])), None) or \
                next((o for o in offers if norm(o["name"]) in norm(m[1])), None)
        if kinds[i] == "skip":
            html_lines.append(f'<div class="ln head">{text or "&nbsp;"}</div>')
            continue
        if kinds[i] == "template":
            found = code_by_line.get(i, [])
            jtags, jflag = _judge_tags(by_template.get(i, []), pack, quote_line=False)
            extra = "".join(_code_tag(r, pack) for r in found)
            bad = jflag or any(r.get("verdict") for r in found if r.get("kind") != "offer")
            n_review += sum(1 for r in found if r.get("kind") == "offer")
            n_code_found += sum(1 for r in found if r.get("kind") != "offer")
            code_part = extra if found else _code_pass(line, pack, offer)
            if found and all(r.get("kind") == "offer" for r in found):
                code_part = _code_pass(line, pack, offer) + extra  # the table check passed; the review requirement stays
            cls = "flag" if bad else ("good" if jtags else "")
            html_lines.append(f'<div class="ln {cls}"><div class="t">{text}</div>{"".join(jtags)}{code_part}</div>')
            continue
        tags, flagged = [], False
        for r in code_by_line.get(i, []):
            tags.append(_code_tag(r, pack))
            flagged = flagged or bool(r.get("verdict"))
        for k in sent_ids.get(i, []):
            entries = by_sentence.get(k, [])
            if not entries:
                what = "" if len(sent_ids[i]) == 1 else f": \u201c{html.escape(sentences[k][1][:90])}\u201d"
                tags.append(f'<div class="tag grey">Nobody checked this statement{what}. The judge did not read it and no code rule covers it</div>')
            for r in code_by_sentence.get(k, []):
                tags.append(_code_tag(r, pack))
                flagged = flagged or bool(r.get("verdict"))
            jtags, jflag = _judge_tags(entries, pack)
            tags += jtags
            flagged = flagged or jflag
        read = [k for k in sent_ids.get(i, []) if by_sentence.get(k)]
        cls = "flag" if flagged else ("good" if read else "")
        html_lines.append(f'<div class="ln {cls}"><div class="t">{text}</div>{"".join(tags)}</div>')
    n_read = n_ok + n_flag
    total = len(sentences) + n_code  # all statements, headings not counted
    pct = round(100 * n_ok / n_read) if n_read else 0
    whole_block = ("<h2>About the whole teaser</h2>" + "".join(f'<div class="ln flag">{_code_tag(r, pack)}</div>' for r in code_whole)) if code_whole else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}{html.escape(' | ' + meta if meta else '')}</title><style>
body{{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:16px;line-height:1.5;color:#1d2330;background:#fff}}
h1{{font-size:1.4rem}} .meta{{color:#6b7280;font-size:.85rem;margin-top:-8px}} h2{{font-size:1.1rem;margin-top:28px}}
.sum{{padding:12px 16px;border-radius:8px;border-left:6px solid #5b6b86;background:#eef1f6}}
.ln{{padding:6px 10px;margin:2px 0;border-left:4px solid transparent}} .ln.head{{font-weight:600;margin-top:10px;border:0}}
.ln.good{{border-left-color:#2e8b57}} .ln.flag{{border-left-color:#d68910;background:#fff8ea}}
.t{{white-space:pre-wrap}} .tag{{font-size:.82rem;margin-top:2px}} .tag.ok{{color:#2e7d4f}} .tag.warn{{color:#a86400}} .tag.grey{{color:#6b7280}} .chip{{font-size:.7rem;color:#6b7280;border:1px solid #c9ced8;border-radius:8px;padding:0 6px;margin-right:6px;white-space:nowrap}} .tag.code{{color:#5f6673;background:#f1f2f5;border-left:3px solid #9aa3b2;padding:3px 8px;margin-top:4px;border-radius:3px}} .tag.code.ok{{border-left-color:#2e8b57}} .tag.code.bad{{border-left-color:#c0392b}} .tag.code.warn{{border-left-color:#d68910}} .tag .q{{font-size:.8rem;color:#6b7280}}
.card{{border:1px solid #d8dce3;border-left:5px solid;border-radius:6px;padding:10px 14px;margin:10px 0}} .card.bad{{border-left-color:#c0392b}} .card.warn{{border-left-color:#d68910}} .card.note{{border-left-color:#7f8c8d}}
.badge{{font-size:.75rem;padding:2px 8px;border-radius:10px;color:#fff}} .badge.bad{{background:#c0392b}} .badge.warn{{background:#d68910}} .badge.note{{background:#7f8c8d}}
.what{{font-weight:600}} .stmt{{margin:6px 0;font-style:italic}} .q,.by{{font-size:.85rem;color:#4a5568;margin-top:4px}}
@media (prefers-color-scheme:dark){{body{{background:#14171c;color:#e6e9ef}} .sum{{background:#222833}} .ln.flag{{background:#2d2616}} .card{{border-color:#333a45}} .q,.by{{color:#aab3c2}} .tag.ok{{color:#6fcf97}} .tag.warn{{color:#f2b04d}} .tag.grey{{color:#9aa3b2}} .tag.code{{color:#b8c0cc;background:#222833}}}}
</style></head><body>
<h1>{html.escape(title)}</h1>
{f'<p class="meta">Run: {html.escape(meta)} (the time is the clock of the machine that ran it)</p>' if meta else ''}
<div class="sum"><small><b>How to read this report.</b> <b>Judge</b> = a model read the statement and compared it with the sources. <b>Code</b> = a word-for-word check: the program looks for the quote in the saved source text, and checks the offer and limits lines against the approved table. Under each statement the source is given with its link and the date it was read.<br><b>S</b> = pages about the company. <b>O</b> = rows of the approved AURA offer table. All links are listed at the end.</small></div>
<div class="sum"><b>The teaser has {total} statements</b> (headings not counted):
<b>{len(by_sentence)}</b> read only by the judge, <b>{n_code - n_both}</b> checked only by code, <b>{n_both}</b> checked by both, <b>{n_none}</b> not checked by anyone.<br>
<b>Judge:</b> of {n_read} statements <b>{n_ok} verified ({pct}%)</b>, {n_flag} flagged. <small>This is the share of statements labelled verified, not an accuracy score of the teaser or of the checker.</small><br>
<b>Automatic checks (code):</b> {len(code_rows)} findings, each shown in grey under the statement it belongs to ({len(code_whole)} about the whole teaser, listed first).<br>
Checked by code: the offer, evidence and limits lines, source notes and the sign-up sentence. Errors found there: {n_code_found}. Review required by the offer table (not errors): {n_review}.<br>
<small>Review only: nothing is published or sent. Green = verified against the source, amber = the judge has a remark, grey = checked by code only, or not checked.</small></div>
{whole_block}
<h2>The teaser, statement by statement: judge's verdict and code checks</h2>
{"".join(html_lines)}
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
        meta = run_meta(a.run_dir) if a.run_dir else (rows[0].get("run", "") if rows else "")
        out.write_text(build_report(rows, teaser_path.read_text(encoding="utf-8"), title, pack, meta), encoding="utf-8")
        print("Report:", out)


if __name__ == "__main__":
    main()
