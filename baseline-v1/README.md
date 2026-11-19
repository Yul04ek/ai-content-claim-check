# baseline-v1

Frozen state of the YL-004 pipeline (Make scenario 8184273) after the five-draft test of 29 Oct 2026.
Purpose: every later change to a prompt or to the code is compared with this state, one change at a time.

```
prompts/draft_prompt_v1.txt        drafting prompt (module 3), as in Make
prompts/judge_prompt_v1.txt        judge prompt (module 6), as in Make
code/make_code_module_v1.py        Python of the Code module (module 7); wrap in a function to run locally
golden/drafts/                     the five frozen drafts (F-003 ... F-007)
golden/records_v1.csv              the five source records, full text
golden/judge_output_v1/            Make's claim-check text for each draft (v1 judge + v1 code)
golden/test_summary_v1.csv         per-case TP/FP/FN/TN (Yuliia's labels; reference)
golden/test_labels_proposed_earlier_version.csv   earlier label file (Claude-proposed labels, 43 rows); NOT the reference
golden/test_labels_v1.csv          sentence-level labels, 42 rows (Yuliia's; reference)
baseline_results.md                settings, run cost, results, label counts, what is verified
```

Prompt placeholders such as `{{1.`1`}}` are Make field references (record fields B, C, E, F, G and the draft `3.answer`).

To freeze in git:

```bash
git add baseline-v1 && git commit -m "Freeze YL-004 baseline v1" && git tag v1-baseline
```

Note: the judge outputs in `golden/judge_output_v1/` come from Gemini 3.1 Flash Lite. The blueprint now uses gemini-3.5-flash-lite (changed after the run). See `baseline_results.md`.
