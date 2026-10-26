# Small helpers shared by the other modules.

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Columns of the result CSV (one row per claim, check or flag)
COLUMNS = ["case", "id", "kind", "text", "verdict", "finding", "source_field", "record_quote", "reason"]


def norm(text: str) -> str:
    """Normalise quotes and spaces so that copy-paste differences do not matter."""
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def make_row(kind, text, verdict="", finding="", source_field="", quote="", reason="") -> dict:
    """One result row. kind: claim | number | quote | flag | placeholder."""
    return {"kind": kind, "text": text, "verdict": verdict, "finding": finding,
            "source_field": source_field, "record_quote": quote, "reason": reason}
