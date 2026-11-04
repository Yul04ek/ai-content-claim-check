import argparse
import json
from pathlib import Path

from .fetch import fetch_snapshot, snapshot_from_html, to_pack_source, to_source_block


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m evidence_fetch", description="Page(s) -> dated text snapshot(s). No AI.")
    ap.add_argument("urls", nargs="*", help="https:// addresses to read")
    ap.add_argument("--html-file", help="a saved HTML file instead of downloading (use with exactly one URL)")
    ap.add_argument("--out", default="snapshots", help="output folder (default: snapshots)")
    a = ap.parse_args(argv)
    if not a.urls:
        ap.error("give at least one URL")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    snaps = []
    for url in a.urls:
        if a.html_file:
            snap = snapshot_from_html(Path(a.html_file).read_text(encoding="utf-8"), url)
        else:
            try:
                snap = fetch_snapshot(url)
            except ValueError as e:
                print(f"SKIPPED: {e}")
                continue
        snaps.append(snap)
        print(f"OK {url}: {len(snap['text'].split())} words, page date: {snap['page_date'] or 'none'}, emails: {snap['emails_found']}")
    if not snaps:
        raise SystemExit("No page was read.")
    (out / "snapshots.json").write_text(json.dumps(snaps, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "make_evidence.txt").write_text("\n".join(to_source_block(s) for s in snaps), encoding="utf-8")
    (out / "pack_sources.json").write_text(
        json.dumps([to_pack_source(s, f"S{i}") for i, s in enumerate(snaps, 1)], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Saved in {out}/: snapshots.json, make_evidence.txt (paste into Make), pack_sources.json")
