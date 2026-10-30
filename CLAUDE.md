# CLAUDE.md

Context for working on this repository. Keep it short and update it when decisions change.

## What this is

An independent **claim check** for AI-written story drafts (task YL-004, "AI Content Engine").
The drafts are written in Make (AI Toolkit) from a product-testing finding and saved as Google Docs.
This repository holds the part that runs **outside Make**: it takes the source finding and the draft, splits the
draft into claims, and gives every claim a verdict: `Supported`, `Unsupported` or `Needs Human Verification`.
Nothing is published or sent anywhere. A human reviews the result and approves or rejects the draft.

Workflow required by the supervisor: Story Candidate -> AI draft (Make) -> claim check (this repo) -> review queue -> human approval.
Constraints: fictional test data only (no real investor or company data goes to an external model), no purchases without
approval (AI budget up to $10), Make scenarios stay Inactive (Run once only), nothing published automatically.

## Layout

- `claim_check/` the code. Run it with `python -m claim_check`.
  - `deterministic.py` layer 1, no AI: cleans the draft, finds numbers and quotes that are not in the record, style flags.
  - `judge.py` layer 2, the model: claims -> findings -> verdicts. Verifies the judge's quotes against the record.
  - `pipeline.py` reads the record (CSV), runs both layers, prints and saves the result.
  - `config.py` environment variables, client, `chat()` with retry on 429/5xx. `cli.py` command line. `common.py` helpers.
- `skills/claim-judge.md` the rubric (system prompt) of the judge. Edit the wording there, not in the code.
- `cases/` nine test cases: `cases.json` (case, finding id, draft file, what we expect) and the draft texts.
- `testdata/BZ021_Test_Copy.csv` CSV export of the fictional test sheet (sheet `BZ021_Test_Copy`). Only the columns the drafting prompt sees are used.
- `tests/test_claim_check.py` offline tests (no key, no network).
- `results/` saved runs (`results.csv` etc.). Keep the files of real runs; they are the test evidence.
- `docs/make-prompt-history.md` the STYLE block of the Make prompt and what each version changed.
- `claim_check_colab.ipynb` the user notebook for Colab.

## Environment

Variables (Colab: the notebook sets them from Secrets): `BASE_URL` (Gemini OpenAI-compatible endpoint),
`API_KEY`, `MODEL_NAME`. Optional: `CLAIM_CHECK_PRICE_IN` and `CLAIM_CHECK_PRICE_OUT` (USD per 1M tokens, for a cost line).
Secrets in Colab: `GEMINI_API_KEY`; `GITHUB_TOKEN` only if the repository is private. Never print or commit keys.

Run: `python tests/test_claim_check.py`, `python -m claim_check --dry-run`, `python -m claim_check --only "T6 "`, `python -m claim_check`.

## Design decisions (and why)

- Plain `openai` client with the Gemini endpoint (as in the research agent), not Pydantic AI: fewer moving parts, the same retry helper,
  and the structured answer is validated with Pydantic models. Pydantic AI can replace `judge_with_llm` later.
- Two layers. Quotes, numbers, banned words, hashtags and placeholders are checked in code because that is exact and free. The model does the rest.
- Checks that depend on context are NOT regexes: who acted ("I"), whether something was really done ("shipped"), section labels. The judge decides them
  because it sees the field a claim comes from (SCENARIO/OBSERVATION may describe done work; RECOMMENDATION and USER IMPACT may not). Removed on 26 Oct after review.
- A number that is not in the record gets Needs Human Verification (it can be derived from the record), not an automatic Unsupported.
- The judge returns a *finding* (`not_in_record`, `assumption_as_fact`, `qualifier_dropped`, ...), and code maps it to one of the three
  required verdicts (`FINDING_TO_VERDICT` in `judge.py`). The mapping is the one place to change when the reviewer disagrees.
- The judge must quote the record. If the quote is not in the record, or missing, `Supported` becomes `Needs Human Verification`.
- Questions, `[Add: ...]` placeholders, hashtags and the "Suggested topic tags" line are not claims; they are removed before the judge sees the text.
- Dry run (`--dry-run`) never prints "No problems found": without the model a clean result means nothing.
- The checker should be a different model family from the drafter (Make uses an OpenAI model) so the model does not grade its own text.

## Status (state at last update)

- Offline: 20 tests pass; dry run works on all nine cases (in T6 the invented number "30%" is found and marked Needs Human Verification).
- First Colab test (26 Oct): the key and endpoint work; the model answered 503 "high demand" for both gemini-3.1-flash-lite and gemini-3.5-flash-lite (overload, not a wrong name). The notebook test cell now retries.
- Real runs, case T6 (26 Oct, gemini-3.1-flash-lite): the JSON answer from Gemini is valid. Run 1: 2 claims Unsupported, 794 in / 410 out tokens.
  After removing the context-dependent regexes: 3 claims Unsupported (relabelled items, "dropped by 30% in a follow-up test", "already shipped the fix"), 849 in / 448 out.
  The number "30%" is also listed by code as Needs Human Verification. Two rows for one invention is by design: the claim (model) and the bare number (code, safety net). The strictest verdict decides the result.
- Full run, all nine cases (26 Oct, gemini-3.1-flash-lite, free tier): finished, 74 rows, 8025 in / 4994 out tokens (about 1 cent at paid prices). The retry helper handled two 503 answers and one timeout (20 s waits).
  Caught: invented or finished claims (T1, T4 "Founders often ask", T6, T8), assumption stated as fact (T2, T3, T8). Clean controls T7 and T9 gave no false alarms.
  Missed: T2 "Founders often juggle..." (same kind as T1/T4, so run-to-run variation), T3 dropped "initially", T4 "looked like they were updated" and "alongside the Company DNA screen", T5 "This happens after...".
  Noise: T2 "users may need to restate" flagged although the draft is hedged; T8 first claim is supported but the judge's quote was not found, so it was downgraded.
  Saved in `results/`: `results_all9_gemini-3.1-flash-lite_2026-10-26.csv` (this run, goes into the report) and the first T6 run. Name every saved run with the model and the date.
- Next (waiting for Tapiwa's approval, because it is a purchase): prepaid OpenRouter credit of $5-10 (OpenAI-compatible, base URL `https://openrouter.ai/api/v1`, not yet tested).
  Prices seen on 26 Oct from third-party pages, to be checked: GPT-5 Mini $0.25/$2.00, Claude Sonnet 5.5 $2/$10, per 1M tokens. A full nine-case run is about 1-6 cents.
  Plan: run the same nine cases with a stronger model of another family than the Make drafter (not GPT) and compare with the Gemini run. GPT-5 Mini only for quick debugging.
  The free Gemini tier is fine for fictional data only: free-tier prompts may be used by Google, so never use it for real data.
- Update 27 Oct: the user prefers to stay with Gemini as the checker (Make drafts with GPT and she codes with Claude, so the checker must be independent of both); OpenRouter is optional.
  Tapiwa (26 Oct, 17:07): "Let me see if I can extend the paid Gemini to you. I believe I have a teams one. Will check tomorrow". Not verified: whether that plan gives a Gemini API key, which the script needs. Nothing is bought.
- Credits of the Make runs are not recorded yet (check Make History: module 3 and module 4 separately).

- Update 30 Oct: judge prompt v2f + code v2b accepted on the golden set (gemini-3.5-flash-lite 6/0/1/35 in 3 runs); drafting prompt v2 tested; all three pasted into the Make scenario (Inactive), first Run once at 15:12 is evaluated in `lab/QUALITY_CHECK.md`. Open: three judge failure modes seen in Make, draft prompt v3. The new task from Monday 2 Nov (advertising campaign for AURA) needs new records, labels and rules. Frozen starting point: branch `baseline-v1`; lab work: branch `lab-step3`.

## Known limitations / TODO

- The check finds wrong statements, not missing ones: a dropped recommendation or a lost caveat (for example the severity limit "the status is displayed") is not detected.
- The same input can give slightly different verdicts between runs. Keep the saved `results/` file of the run that goes into the report.
- Duplicate IDs in the test sheet (F-001, F-002 appear twice, TEST ONLY rows): the first row is used, with a warning.
- Decision: drafts are read as text files and results are saved as files (a CSV per run, named with the model and the date). Nothing is written back into the Google Sheet.
  Reading drafts directly from Google Docs is only an idea, not decided and not built.
- Idea: add real approved (draft, source) pairs as style examples for the Make prompt after the supervisor's review.

## Conventions

- Comments are short, plain English. Keep the code simple and readable.
- Run the offline tests of any change before pushing; real model behaviour can only be checked in Colab.
- Do not commit real company data. The data here is a fictional test copy.
