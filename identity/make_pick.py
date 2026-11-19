# Which company does a human decision on a Companies row refer to?
# Used by the review-decision scenario (Make Code module, one per decision type: same / different company).
#
# Input:  {"typed": "<group ID typed by a human in the sheet, may be empty>",
#          "candidates": "<JSON text of duplicate_candidates from the registry: [{"group_id": ..., "reason": ...}]>"}
# Output: {"target": "<group ID>", "count": <number of different candidates>}
#
# A typed ID always wins. Without it, a single candidate is used. Several candidates, or none, give an empty
# target: the scenario then refuses to guess and a human types the ID.
# Code module in Make: this file followed by a last line "return pick_target(input)".
import json


def pick_target(inp):
    typed = str(inp.get("typed") or "").strip()
    raw = inp.get("candidates") or ""
    if isinstance(raw, str):  # Make passes the stored text
        try:
            raw = json.loads(raw) if raw.strip() else []
        except ValueError:
            raw = []
    ids = []
    for item in raw if isinstance(raw, list) else []:
        group_id = str((item or {}).get("group_id") or "").strip()
        if group_id and group_id not in ids:
            ids.append(group_id)
    target = typed or (ids[0] if len(ids) == 1 else "")
    return {"target": target, "count": len(ids)}
