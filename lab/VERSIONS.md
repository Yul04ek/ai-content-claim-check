# Judge versions tested on 30 Oct 2026 (golden set of five drafts, labels v1.1, 3 runs per model)

Baseline Make (29 Oct, gemini 3.1): TP 4 / FP 2 / FN 3 / TN 33. Code module v2a/v2b: quotes in questions are skipped; v2b also tolerates a broken \u escape in the judge JSON.

| Version | Change (one per step) | gemini-3.1-flash-lite | gemini-3.5-flash-lite | Decision |
|---|---|---|---|---|
| v1 | Make prompt as it was | 3-4 TP, 1-2 FP, 3-4 FN, unstable | 4 TP, 1-2 FP, 3 FN, 1 sentence unstable | baseline |
| v2a | questions are not claims (opening statements still count) | no clear change | stable, FP flicker on questions gone | kept |
| v2b | weaker/different main verb of a proposed action = meaning_shifted | 5-6 TP, 0 FP | 4-5 TP, 0 FP (one broken JSON answer in run 1) | kept |
| v2c | a new conclusion not stated in the record = meaning_shifted | 6 TP, 0-2 FP | 6 TP, 1 FP (F-005 s6) | too broad |
| v2d | v2c limited to inference sentences ("this suggests") | 6 TP, 1 FP (F-005 s6), 1 FN | 6 TP, 0 FP, 1 FN, identical in 3 runs | **accepted** |
| v2e | a quote must cover the whole claim (half-quote) | same as v2d | same as v2d, F-005 s6 flickers | rejected: no gain |

Known limit after v2d: F-007 s7 (synthesis OBSERVATION + USER IMPACT) is still passed as Supported by both models, with a quote from USER IMPACT only.
Verified: all numbers above come from the saved runs in lab/runs (raw judge JSON + check texts) and lab/report_2026-10-30.txt.
