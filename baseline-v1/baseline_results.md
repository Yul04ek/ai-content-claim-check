# YL-004 baseline v1: frozen results (29 Oct 2026)

All data are fictional test records. The scenario stays Inactive. Nothing was run or changed in Make to build this folder (read-only access).

## Scenario settings (read from Make on 30 Oct 2026)

| Item | Value |
|---|---|
| Scenario | "YL004 AI story draft", ID 8184273, team 3099897, Inactive |
| Last edit in Make | 2026-10-29T12:05:21Z (the test runs were at about 09:44-09:46Z; see "Not verified" below) |
| Module 1 | Google Sheets, Search Rows, sheet BZ021_Test_Copy, filter `M = Yes AND K = Open`, limit 100 (current value; Yuliia changed it to 100 after the run of 29 Oct; it does not affect five candidates), sort ascending, FORMATTED_VALUE |
| Module 2 | Google Sheets, Search Rows, sheet Story queue, filter `A = {{1.0}}` (ID) |
| Module 3 | AI Toolkit "Ask", filter "No draft yet" (`2.A != 1.ID`), model: gpt-5-nano, reasoning minimal (Make's AI Provider, default connection) |
| Module 4 | Google Docs, create draft document, folder "Story draft" |
| Module 6 | AI Toolkit "Ask" (judge), model at the run of 29 Oct: Gemini 3.1 Flash Lite (Yuliia's recollection; the exact Make model ID was not checked). Model in the current blueprint: gemini-3.5-flash-lite (changed after the run). Error handler = Resume with empty answer |
| Module 7 | Code (Python), "Code check (numbers, quotes, flags)", `code/make_code_module_v1.py` |
| Module 8 | Google Docs, create check document, error handler = Resume with empty link |
| Module 5 | Google Sheets, Add Row (OVERWRITE) in Story queue |
| Temperature / other model parameters | not shown in the blueprint; not checked |

## Run of 29 Oct (five new drafts, one run)

Checked on 30 Oct against Make's execution list for scenario 8184273 (read-only):

- Execution da548a8313e54905aecffe4ab742c582, manual, started 2026-10-29 09:44:47Z, SUCCESS: 112.3 s, 42.72 credits (4272 centicredits), 37 operations. Five drafts: about 22 s and 7.1 credits per draft.
- Empty run before it (e40e996443024a14819ae078c6bdf8e7, 09:40:07Z, no candidates): 0.85 s, 2 credits, 2 operations.

## Make result per draft (Story queue, column D)

| ID | Result |
|---|---|
| F-003 | NOT READY: 1 unsupported, 2 placeholders to fill |
| F-004 | NOT READY: 1 unsupported, 2 placeholders to fill |
| F-005 | NOT READY: 2 unsupported, 1 to verify, 1 placeholder to fill |
| F-006 | NO ISSUES FOUND (human review still required): 2 placeholders to fill |
| F-007 | NOT READY: 1 unsupported, 2 placeholders to fill (the "unsupported" is only the code check on the quoted word "remembers") |

The full text of each check is in `golden/judge_output_v1/`.

## Reference labels (Yuliia, 42 sentences: 37 claims + 5 questions)

| | count |
|---|---|
| TP (found) | 3 |
| FN (missed) | 3 |
| FP (false alarm) | 3 |
| TN (correctly passed) | 33 |

Source: the Test_Labels tab (`golden/test_labels_v1.csv`, 42 sentence-level rows, all "sure? = yes") and the Test_Summary tab of the Google Sheet (`golden/test_summary_v1.csv`, exported 30 Oct), which matches the day log of 29 Oct. Per case (TP / FP / FN / TN): F-003 0/1/1/4, F-004 1/0/0/7, F-005 2/1/0/6, F-006 0/0/1/10, F-007 0/1/1/6. The tab has no uncounted rows. These are Yuliia's own corrected labels and are the reference for all later comparisons. Note: the "HOW TO READ" text in that tab still says the gold labels were proposed by Claude; that sentence is left over from the earlier version.

Misses (FN): F-003 sentence 6, F-006 sentence 11 (verb weakened, judge passed it), F-007 sentence 7 (synthesis from several fields).
False alarms (FP): F-003 sentence 4, F-005 sentence 1 (opening question flagged by the judge), F-007 sentence 1 (code flagged a quoted word in a question).
Found (TP): F-004 sentence 7, F-005 sentences 7 and 9.

## Earlier label file (not the reference)

`golden/test_labels_proposed_earlier_version.csv` is the xlsx attached on 30 Oct (file created 2026-10-29 12:19Z). Its gold labels were proposed by Claude from the record fields, and 6 rows are marked "sure? = ?" (not counted). It has 43 rows (38 claims + 5 questions); F-003 is split into 7 rows there. Outcomes by the sheet's own formula (the xlsx has no stored results, so they were computed): TP 3, FP 2, FN 0, TN 32, not counted 6.

The Google Sheet tab was changed later (2026-10-29 14:48Z) and holds Yuliia's own labels: 42 sentences, all sure, TP 3 / FN 3 / FP 3 / TN 33. That version is the reference above. The two versions differ in sentence splitting and in several gold verdicts, so their counts must not be mixed. The `outcome (computed)` column in the CSV applies the same formula as the sheet.

## What was checked today

- The five draft texts and five check texts in `golden/` were copied from the Google Docs on Drive.
- `golden/records_v1.csv` is the full text of the five records, decoded from a CSV export of sheet BZ021_Test_Copy.
- Prompts and code vs. the blueprint file attached on 30 Oct (`YL004_AI_story_draft.blueprint.json`): `draft_prompt_v1.txt`, `judge_prompt_v1.txt` and `make_code_module_v1.py` are byte-identical to the blueprint text (CRLF in the STYLE block included). Model settings in that blueprint: drafting = "small" (gpt-5-nano, reasoning minimal, connection 11707707), judge = gemini-3.5-flash-lite (connection 12448331; this is the current setting, the run of 29 Oct used 3.1). The blueprint also has the same module flow and filters as in the table above.
- The code module was run locally on the five drafts and records (without a judge answer). Its "Code checks" lines (numbers, quoted text, banned words, hashtags, word counts, placeholders) match the saved results of 29 Oct for all five drafts. This confirms that the code module copy and the draft copies are consistent with what ran. It does not test the judge part of the code.

## Not verified

- Edits after the run: Make lists two edits at 11:23Z and 12:05Z on 29 Oct (after the run at 09:44Z). Yuliia recalls that she changed only the Search Rows limit (to 100) and the judge model (from Gemini 3.1 to 3.5). So the attached blueprint differs from the state at the run in these two settings. Prompts and code are said to be unchanged; that rests on her recollection, and the file `YL004_make_prompt_history.md` supports it for the STYLE block only. The exact model ID used for 3.1 was not checked.
- Consequence for comparisons: `golden/judge_output_v1/` was produced with Gemini 3.1. Running the same prompt on Gemini 3.5 is a change of the judge model, so it counts as one change of its own and is compared against these results, not mixed with prompt changes. The drafting model (gpt-5-nano) is not reported as changed.
- Line endings: the live drafting prompt has Windows line breaks (CRLF) inside the STYLE block; `draft_prompt_v1.txt` keeps them. The judge prompt has plain line breaks.
- The code module was copied from the blueprint text, not compared byte by byte with a second export.
- The judge's answers are not deterministic. The same input can give a different verdict on another run (day log, open question 8).

## Still missing for a complete golden set

- The raw JSON the judge returned per draft. Make's execution detail for the run of 29 Oct returned only the status "SUCCESS", with no module inputs or outputs, so the raw answers are not available from the API. The check files contain the processed report with each claim, verdict and record quote, which is the main content. To get raw answers a new run would be needed (only with Yuliia's permission).
