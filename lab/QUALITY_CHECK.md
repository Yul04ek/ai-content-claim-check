# YL-004 quality check: results of 30 Oct 2026 and recommendations

All data are fictional test records. Make stayed Inactive; every run was a manual Run once.
Raw evidence: `lab/runs/`, `lab/report_2026-10-30.txt`, `lab/VERSIONS.md`, `lab/drafts/`, `lab/make_run_2026-10-30/`.
Frozen starting point: branch `baseline-v1`. Make backup before the sync: `lab/make_backup/`.

## 1. What was tested

| Part | Test | Result |
|---|---|---|
| Judge prompt + code | 5 frozen drafts (F-003..F-007), 42 sentences labelled by hand (labels v1.1), 3 runs per model | Make baseline 29 Oct: TP 4 / FP 2 / FN 3 / TN 33. Accepted v2f + code v2b: gemini-3.5-flash-lite 6/0/1/35 in all 3 runs; gemini-3.1-flash-lite 7/2/0/33, 6/0/1/35, 6/0/1/35 |
| Drafting prompt v2 | 5 records x 3 runs, Gemini 3.1 | "suggest"/"we" 0 of 15; weaker verbs 0 of 15; neutral lead-in in 14 of 15; 7 of 15 slightly over 130 words |
| Everything in Make (30 Oct, 15:12) | judge v2f + code v2b + draft prompt v2, gpt-5-nano drafts, Gemini 3.5 judge | Only F-007 got a correct result. F-004 and F-006: false alarms. F-005: judge answer unreadable. F-003: possible miss (synthesis) |

Rules that gave an effect (one change at a time): questions are not claims; a weaker or different main verb of a proposed action is meaning_shifted; an inference the record does not state is meaning_shifted; a sentence with "because/so" is one claim. Rejected: a broader inference rule (false alarm), a half-quote rule (contradicted the one-claim rule).

## 2. Findings from the Make run of 30 Oct

- Judge failure modes seen in Make but not in the lab: a stray `_comment: ...` line without quotes in the JSON (F-005, check fails), a question listed as a claim (F-004), a required lead-in "One option is to" judged as a weaker verb (F-006). The last one is a conflict between the two prompts.
- Code layer worked: numbers, quotes, hashtags, placeholders correct; the banned word "always" in F-007 was caught independently of the judge. It does not check a maximum length (F-006: 176 words, limit 130) and it does not retry a failed judge call.
- Drafter (gpt-5-nano) invented a recommendation for F-005 although the record says no change is needed.

## 3. How different are drafts (`python lab/compare_drafts.py`)

| Comparison | Different words | Sentences without a close match |
|---|---|---|
| Make 29 Oct vs Make 30 Oct (same record, other prompt) | 37-53% | 40-80% |
| 3 lab runs, same prompt and record (pure variation) | 41-58% (mean 52%) | 53-78% (mean 69%) |

The same prompt gives about as much variation as a new prompt: facts stay (503, 29 documents, 40%), wording changes every time. Therefore one run is never evidence; compare ranges.
Number of claims per draft found by the judge: v1 (29 Oct) 6/7/9/8/7; v2f in Make 3/4/4/6/5; lab 3.1 3-6. About 40% fewer than v1 (one-claim rule, questions skipped, shorter drafts).

## 4. Recommendations for a quality check

1. **Freeze a baseline first.** Drafts, records, human labels and the current prompts go into one frozen branch. Change labels only by the owner of the labels.
2. **Label at sentence level** (claim / question / placeholder; expected verdict: Supported, Unsupported, Needs Human Verification). Write the labelling rules down (for example: a synthesis of several fields = Needs Human Verification) and apply them to every sentence.
3. **Score with TP / FP / FN / TN** against the labels. Matching a judge claim to a labelled sentence needs the merged-claim rule (`lab/score_golden.py`).
4. **One change at a time**, rerun, compare to the previous version. Do not change the judge and the drafter in the same step.
5. **Repeat.** At least 3 runs on at least 2 model versions; report the range, not one number. One sentence is about 2% of 42, so a difference of 1 is noise.
6. **Test the judge on frozen drafts** (so the drafter cannot move the result) and the drafter by counting rule violations (banned words, length, weaker verbs, invented advice) on at least 3 drafts per record.
7. **Prompts must not be tuned to one model.** If a rule only works on one model, simplify the rule.
8. **Keep the code layer as a safety net** (numbers, quotes, banned words, hashtags, placeholders, minimum and maximum length) and make a failed judge visible (CHECK FAILED), never "no issues".
9. **Track failure rate of the judge answer** (unreadable JSON, questions in the list) over all runs; add a retry before accepting a failure.
10. **Acceptance rule used here:** no false alarm and at most one miss on the labelled set in 3 of 3 runs on two models, no unreadable answers in the 15 runs, then one Make run on 5 records compared with the labels.
11. **Different model family for the checker** than for the drafter.
12. **A human always reviews.** The check finds wrong statements, not missing ones (a dropped recommendation or a lost caveat), and misses some synthesis.

## 5. Open items (not done)

- Judge prompt: "only claim objects, no comments"; "a neutral lead-in is not a weaker verb"; retry of the judge on CHECK FAILED (step 7).
- Draft prompt v3: "no issue observed" must not become "works"; if no change is needed, say only that; hard maximum of 130 words; code flag for too long drafts.
- Run today's five Make drafts through the judge on both Gemini models (3 runs each) to see whether the three failures are model-specific.
- Label the 25 new sentences (`lab/labels/new_drafts_v2_to_label.csv`).
- Not synced: `skills/claim-judge.md` still has the old wording; tag `v1-baseline` is local only.

## 6. For the next task (advertising campaign for AURA)

Reuse the method and scripts in `lab/` (runner, scorer, report, compare_drafts). New records, new labels and new rules are needed: claims about benefits, numbers, comparisons, superlatives and guarantees. Freeze a new baseline before any prompt change.
