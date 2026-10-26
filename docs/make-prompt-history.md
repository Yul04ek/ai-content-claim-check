# Make drafting prompt: STYLE block and its history

The drafts are written inside Make (AI Toolkit, module "AI draft"). This file records the STYLE part of that prompt,
so the work can be handed over. The RULES part (use only the RECORD, facts vs assumptions vs proposals) did not change.

## Current STYLE block (v4)

```
STYLE
- Audience: anyone who is starting or running a business, or who wants to organise their business documents. Do not assume technical knowledge. Use plain words. If you use a product term (for example Company DNA), explain it in a few simple words or avoid it.
- The first sentence is an opening for a reader who does not know the product. Write it as a plain question or a short everyday scenario about what a person is trying to do, based on the situation in SCENARIO. Use everyday words, no product terms.
- The opening is a question or a scenario, not a statement of fact about people. Do not say what founders, users or people "often", "usually" or "always" do, feel or worry about. Do not use "many", "surprising" or "shocking".
- The opening must not present an assumption (such as USER IMPACT) as if it had been observed.
- Describe the finding itself as one test ("in this test", "during testing"), not as something that always happens.
- Do not connect two screens, items or events into one picture unless OBSERVATION connects them.
- Write one or two flowing paragraphs in this order: opening, what happened, why it may matter, what we suggest next. Do not use labels such as "Situation:" or "What happened:".
- Choose the 2 or 3 most important facts. Do not list every detail from the record.
- Present recommendations as suggestions ("we suggest", "one option is"), never as commitments ("we will", "we aim to").
- Keep the honest limits from the record, including limiting words such as "initially" or "the status is displayed", and statements that the cause cannot be confirmed.
- Add 1 or 2 placeholders where a person should add their own voice, for example [Add: what surprised you?] or [Add: what this taught us about building AURA].
- Do not add plans, decisions or timelines that are not in RECOMMENDATION.
- Length: 80 to 130 words. If the record is short, write a shorter draft. Never pad it with invented details.
- No emojis, no headings, no bullet points.
- End with the line: #AURABuildLog #FundraiseInPublic #AURAFundraiseLog
- Then add one more line: "Suggested topic tags:" followed by 1 or 2 common, widely used hashtags that fit this finding (for example #usabilitytesting). Do not invent new tags. No brand, product or company names.
- Return only the draft text, nothing else.
```

## What each version changed

Each version was tried on one or two findings only, so this is a record of what was seen, not a measurement.

| Version | Change | What the drafts showed afterwards |
|---|---|---|
| v1 | First blueprint: "a short story: what we tested, what we noticed, why it may matter, what we plan to do next" | Invented plan sentence, "We tested" opening, section labels in the text |
| v2 | Audience founders, no "We tested", 1-2 placeholders, hashtags and suggested tags, 80-130 words | Actor mixed up (F-001), caveat lost (F-002), "often" and "leaking" added (F-006), source phrases copied (F-007) |
| v3 | Flowing paragraphs, 2-3 facts, suggestions not commitments, limits kept, rule against "founders often" | "Founders often ..." stayed in F-007 and F-008. Cause: the same prompt asked for a question "a founder would recognise" |
| v4 | Opening is a question or scenario, no claims about people, one-test wording, do not join two screens | F-008: no errors found by manual review (case T9) |

Known gap in all versions: the severity limit "the status is displayed" is often dropped (F-002, F-008).

## What the claim check found (26 Oct 2026)

Checker: gemini-3.1-flash-lite, free tier. One draft per version, so this is a record of what was seen, not a measurement.
The same input can give different verdicts between runs. Saved run: `results/results_all9_gemini-3.1-flash-lite_2026-10-26.csv`.

| Version | Case | What the checker reported |
|---|---|---|
| v1 | T1 (F-007), T3 (F-008) | T1: "Founders often worry ..." Unsupported. T3: "which could mislead decisions" Needs Human Verification |
| v2 | T2 (F-007), T4 (F-008) | T4: "Founders often ask ..." Unsupported. T2: two Needs Human Verification (one looks like a false alarm: the draft sentence was already hedged); "Founders often juggle ..." was missed |
| v3 | T5 (F-008) | "paired with a Company DNA label" Needs Human Verification; "This happens after ..." was missed |
| v4 | T9 (F-008) | nothing reported, same as the manual review |

Error types seen in v1-v3, as ideas for prompt rules. NOT applied yet, and to be tested on other findings than F-007 and F-008:
- A USER IMPACT assumption written as a fact: keep "may", "could", "might".
- A consequence or cause added that the record does not state.
- A limiting word lost ("initially", "the status is displayed").
- Two items joined into one picture ("paired with", "alongside"); v4 already has a rule for this.

The checker finds wrong statements, not missing ones, so a lost recommendation or caveat still needs a human.
