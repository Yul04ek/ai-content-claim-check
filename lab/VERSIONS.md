# Judge versions tested on 30 Oct 2026 (golden set of five drafts, labels v1.1, 3 runs per model)

Baseline Make (29 Oct, gemini 3.1): TP 4 / FP 2 / FN 3 / TN 33.
Code module v2a/v2b: quotes inside questions are skipped; v2b also tolerates a broken \u escape in the judge JSON.
Scorer: since the v2f runs a judge claim that joins several label sentences is matched to all of them (a flagged claim is a hit when one of them is not Supported). All numbers below use this scorer (TP/FP/FN/TN per run).

| Version | Change (one per step) | gemini-3.1-flash-lite | gemini-3.5-flash-lite | Decision |
|---|---|---|---|---|
| v1 | Make prompt as it was | 3/3/4/32, 4/1/3/34, 4/2/3/33 | 4/1/3/34, 4/2/3/33, 4/1/3/34 | baseline |
| v2a | questions are not claims (opening statements still count) | 4/1/3/34, 4/3/3/32, 4/4/3/31 | 4/1/3/34 x3 | kept |
| v2b | weaker/different main verb of a proposed action = meaning_shifted | 6/0/1/35, 5/0/2/35, 5/0/2/35 | 4/0/3/35, 5/0/2/35, 5/0/2/35 (run 1: one broken JSON answer) | kept |
| v2c | a new conclusion not stated in the record = meaning_shifted | 6/1/1/34, 6/3/1/32, 6/0/1/35 | 6/1/1/34 x3 | too broad |
| v2d | v2c limited to inference sentences ("this suggests") | 6/3/1/32, 6/1/1/34, 6/1/1/34 | 6/0/1/35 x3 | kept |
| v2e | a quote must cover the whole claim (half-quote) | 6/5/1/30, 6/5/1/30, 6/1/1/34 | 6/1/1/34, 6/0/1/35, 6/1/1/34 | rejected: pushes the judge to split sentences (against labelling rule 2b) |
| v2f | labelling rule 2b: a sentence that depends on "because" / "so" is one claim (v2d + this) | 7/2/0/33, 6/0/1/35, 6/0/1/35 | 6/0/1/35 x3 | **accepted** |

Known limit after v2f: F-007 s7 (synthesis OBSERVATION + USER IMPACT) is found in 1 of 6 runs; the judge usually passes it as Supported with a quote from USER IMPACT only.
Known side effect: when the judge joins two sentences into one claim with a two-part quote, the code cannot find the quote in the record and downgrades Supported to Needs Human Verification (3.1, run 1, F-005 s2+s3). Fix idea: check a quote of several passages part by part.
Verified: the numbers come from the saved runs in lab/runs (raw judge JSON + check texts), scored by lab/score_golden.py; full per-sentence report in lab/report_2026-10-30.txt.
