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
- Two layers. Numbers and quoted text are checked in code because that is exact and free. The model does the rest.
- The judge returns a *finding* (`not_in_record`, `assumption_as_fact`, `qualifier_dropped`, ...), and code maps it to one of the three
  required verdicts (`FINDING_TO_VERDICT` in `judge.py`). The mapping is the one place to change when the reviewer disagrees.
- The judge must quote the record. If the quote is not in the record, or missing, `Supported` becomes `Needs Human Verification`.
- Questions, `[Add: ...]` placeholders, hashtags and the "Suggested topic tags" line are not claims; they are removed before the judge sees the text.
- Dry run (`--dry-run`) never prints "No problems found": without the model a clean result means nothing.
- The checker should be a different model family from the drafter (Make uses an OpenAI model) so the model does not grade its own text.

## Status (state at last update)

- Offline: 20 tests pass; dry run works on all nine cases (the number "30%" and the finished-work words are found).
- **Not yet run against the real model.** The structured JSON answer from Gemini, the model name and the free-tier limits are untested. First step: `--only "T6 "` in Colab.
- Credits of the Make runs are not recorded yet (check Make History: module 3 and module 4 separately).

## Known limitations / TODO

- The check finds wrong statements, not missing ones: a dropped recommendation or a lost caveat (for example the severity limit "the status is displayed") is not detected.
- The same input can give slightly different verdicts between runs. Keep the saved `results/` file of the run that goes into the report.
- Duplicate IDs in the test sheet (F-001, F-002 appear twice, TEST ONLY rows): the first row is used, with a warning.
- Reading drafts directly from Google Docs and writing results to a "Claims" tab are not built; today drafts are text files and results are a CSV.
- Idea: add real approved (draft, source) pairs as style examples for the Make prompt after the supervisor's review.

## Conventions

- Comments are short, plain English. Keep the code simple and readable.
- Run the offline tests of any change before pushing; real model behaviour can only be checked in Colab.
- Do not commit real company data. The data here is a fictional test copy.
