# AI Content Claim Check

An independent check for AI-written story drafts. It compares a draft with the source finding it was written from,
splits the draft into claims, and gives each claim a verdict:

* **Supported**: the record says it.
* **Unsupported**: the record does not say it, or says something different.
* **Needs Human Verification**: close to the record, but stronger, weaker or less careful (an assumption stated as a fact,
  a dropped limit such as "initially", a general statement from one test).

It runs outside Make, publishes nothing, and writes a CSV for the reviewer. A human still approves every draft.

## Quick start (Google Colab, free)

You need a free Gemini API key: https://aistudio.google.com/apikey (no payment details).

1. Open the notebook in Colab:
   [Open in Colab](https://colab.research.google.com/github/Yul04ek/ai-content-claim-check/blob/main/archive/claim_check_colab.ipynb)
2. In Colab, open the key icon (Secrets) in the left sidebar. Add a secret `GEMINI_API_KEY` with your key and switch on
   "Notebook access". If this repository is private, add a second secret `GITHUB_TOKEN` (a fine-grained token with read access to this repository only).
3. Run the cells from top to bottom. The notebook installs the packages, checks the model with one short message,
   runs the free offline checks, then runs **one** case with the model, and only then all nine.
4. The results are in `results/results.csv`. The last cell downloads them.

The free Gemini tier has per-minute and daily limits. If you see a 429 or 503 error, the script waits and retries by itself.

## Run locally (terminal)

    pip install -r requirements.txt
    python tests/test_claim_check.py               # offline tests, no key
    python -m claim_check --dry-run                # no model, only the checks done in plain Python
    export BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
    export API_KEY=<your Gemini key>
    export MODEL_NAME=<a Gemini model name>
    python -m claim_check --only "T6 "             # one case with the model
    python -m claim_check                          # all cases

## How it works

1. The draft is cleaned: the document header, hashtags, "Suggested topic tags" and `[Add: ...]` placeholders are removed.
2. **Plain Python checks** (no model): quoted text that is not in the record is Unsupported; a number that is not in the record
   needs a human look (Needs Human Verification); banned words and missing series hashtags are flagged.
   Anything that depends on context (who acted, what was really done) is left to the model.
3. **The model** lists the claims and compares each with the record. It must copy a quote from the record for its verdict;
   the code checks that the quote really is there. A "Supported" claim without a real quote becomes "Needs Human Verification".
4. The result is one CSV row per claim, check or flag. Questions and placeholders are not treated as claims.

The rubric the model follows is in `skills/claim-judge.md`. The cases are in `cases/cases.json`: five real drafts, two drafts with deliberate
false claims (an invented number and a fix described as finished; a dropped limit), a clean control, and one draft written with the latest prompt.

## Limits

* It checks what the draft says, not what is missing from it.
* The same input can give slightly different verdicts between runs.
* The data is a fictional test copy. Do not put real investor or company data into an external model.

The Make drafting prompt and its history are in `docs/make-prompt-history.md`.

## Colab notebooks (which one for what)

| Notebook | Task | Use it to | Needs |
|---|---|---|---|
| `evidence_to_drive_colab.ipynb` | YL-004B, no AI | for every company marked `READY_FOR_TEASER` (the whole queue, nothing to type): read its sources (whole group, identical addresses once) from the database, make dated text snapshots, save one file `<company_id>.md` per company in the Drive folder `YL004B evidence` (read by the Make Teaser Generator) | Colab Secret `SUPABASE_DB_URL`; a Google account that can edit the folder |
| `teaser_lab_colab.ipynb` | YL-004B judge | run the judge once on your own pack + teaser files, free checks first | `GEMINI_API_KEY` |

Older notebooks are in `archive/` (they still work, they clone the repository themselves): `claim_check_colab.ipynb` (YL-004 story drafts), `teaser_check_colab.ipynb`, `evidence_fetch_colab.ipynb` (snapshot as text to copy by hand, replaced by `evidence_to_drive_colab.ipynb`), `teaser_experiment_colab.ipynb`, `teaser_experiment_v3_colab.ipynb`, `teaser_experiment_v4_colab.ipynb` (judge experiments).

Order of the teaser work: `evidence_to_drive` (snapshot file on Drive) -> Make generator (teaser) -> `teaser_lab` (judge).
