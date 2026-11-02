# Teaser check (task YL-004B)

Independent claim check for AURA opportunity teasers. It is a separate package next to `claim_check/`
(the judge for story drafts), so the calibrated draft judge is not touched. Shared parts (key, retries, CSV columns)
are imported from `claim_check`.

- Input: an evidence pack (`packs/pack_Test_001.json`, the structured version of the PDF) and the teaser text.
- Layer 1 (`teaser_check/deterministic.py`, no AI): internal-review label, 2-3 labelled hypotheses, source/fact IDs and URLs
  that are not in the pack, numbers not in the pack, promises (guarantee, fast-track, Studio acceptance), business-figure words (flags).
- Layer 2 (`teaser_check/judge.py` + `skills/teaser-judge.md`): the model splits the teaser into claims, gives each a finding and an exact
  quote from the pack. Code verifies the quote and maps findings to Supported / Unsupported / Needs Human Verification.
- Result: READY FOR REVIEW / REVIEW / NOT READY (worst verdict decides; a human still approves).

## Run

    python tests/test_teaser_check.py                                   # offline, no key
    python -m teaser_check --suite cases_teaser/cases.json --dry-run    # layer 1 only (NOT a verdict)
    python -m teaser_check --suite cases_teaser/cases.json              # needs BASE_URL, API_KEY, MODEL_NAME (as in Colab)
    python -m teaser_check packs/pack_Test_001.json my_teaser.txt       # one real teaser

## Status

- Rubric version t1 is NOT calibrated. The calibration of the draft judge (6/0/1/35) does not carry over.
- `cases_teaser/` holds 11 synthetic teasers with planted errors (known by construction, no hand labelling): T1 is the clean control.
  Calibrate the same way as before: freeze a baseline, change one rule at a time, 3 runs, compare the level and the findings.
- The offer list in the pack is a TEST list. Replace it with the list approved by Tapiwa. Without a list every statement about AURA
  becomes Needs Human Verification (`aura_offer_unverified`).
- The teaser must list sources and unknowns under a heading that starts with "Sources" or "Unknown"; the text from the first such heading is not judged.
