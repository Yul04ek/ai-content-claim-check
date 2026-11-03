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

## Update 3 Nov: approved offer list and Tapiwa's rules

- `packs/pack_Test_001_approved.json`: the same evidence plus the five approved AURA offers (O1-O5, wording as relayed by Tapiwa) and `forbidden_terms`
  (IdealApp's own Company DNA, other test companies). The first suite still uses the old pack with the TEST list, so its baseline stays comparable.
- Offer fields in the pack: `match` (regex for the offer name) or `match_words` (word sets: the offer is named if the text contains all words of one set, whatever the hyphen, case, plural or order),
  `must_say` (Launchpad: "proposed"), `not_customer_ready` with `human_check_reason` (Sprints / Managed Execution: any mention = Needs Human Verification, a person decides).
- New code rules (layer 1): price not in the offer list = Unsupported; Launchpad without "proposed" = Needs Human Verification; Sprints/Managed Execution
  mentioned = Needs Human Verification; forbidden term = Unsupported; missing company snapshot, AURA help, sign-up invitation or source notes;
  Studio acceptance phrases; teaser longer than 450 words = flag. "H1".."H3" are no longer counted as numbers; a figure word in a sentence with
  "not/no/unknown" is no longer flagged.
- `cases_teaser_approved/`: 9 cases made from the real AURA teaser of 3 Nov with one planted error each (A0 is the control).
  A6 (price on the wrong offer) and A8 (need stated as fact) are JUDGE ONLY: code cannot see them.
- Not done: rubric t1 is unchanged (not calibrated). Proposed rubric additions are listed in the hand-over message and need 3 runs each.
