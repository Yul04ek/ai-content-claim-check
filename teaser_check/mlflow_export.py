"""Readable view of an MLflow store: one table (CSV and HTML), one row per run.

Reads the SQLite database of MLflow directly, so it needs no mlflow package and no web server.
  python -m teaser_check.mlflow_export /content/mlruns --out results/mlflow_overview
writes results/mlflow_overview.csv and results/mlflow_overview.html.
"""
import argparse
import csv
import datetime
import html
import sqlite3
from pathlib import Path


def db_path(store: str) -> Path:
    """A folder with mlflow.db, a path to mlflow.db, or sqlite:///path."""
    store = store.replace("sqlite:///", "", 1) if store.startswith("sqlite:///") else store
    path = Path(store)
    return path / "mlflow.db" if path.is_dir() else path


def read_runs(store: str) -> list[dict]:
    """One dict per run: time, name, kind (parent/repeat), params and the last value of every metric."""
    con = sqlite3.connect(f"file:{db_path(store)}?mode=ro", uri=True)
    experiments = dict(con.execute("select experiment_id, name from experiments"))
    parents = {u: v for u, k, v in con.execute("select run_uuid, key, value from tags") if k == "mlflow.parentRunId"}
    rows = []
    for uuid, name, start, exp_id, status in con.execute(
            "select run_uuid, name, start_time, experiment_id, status from runs where lifecycle_stage = 'active' order by start_time"):
        row = {"start": datetime.datetime.fromtimestamp(start / 1000).strftime("%Y-%m-%d %H:%M:%S"),
               "experiment": experiments.get(exp_id, ""), "run": name,
               "kind": "repeat" if uuid in parents else "all repeats (mean/min/max)", "status": status}
        row.update({k: v for k, v in con.execute("select key, value from params where run_uuid = ?", (uuid,))})
        # metrics: the newest value of every key
        for key, value in con.execute("select key, value from metrics where run_uuid = ? order by timestamp, step", (uuid,)):
            row[key] = round(value, 3)
        rows.append(row)
    con.close()
    return rows


SHOWN = [("read", "read"), ("found", "errors found"), ("false_flags", "false flags"), ("right", "right verdicts"), ("code_found", "code found")]


def long_rows(rows: list[dict]) -> list[dict]:
    """One row per run and teaser (readable); for the parent run the numbers are means over the repeats."""
    out = []
    for r in rows:
        mean = r["kind"].startswith("all")
        teasers = sorted({k.split("_")[1] for k in r if k.startswith("v2_")})
        for t in teasers:
            row = {"start": r["start"], "run": r["run"], "kind": "mean of repeats" if mean else "repeat " + str(r.get("repeat", "")),
                   "teaser": t, "statements": r.get(f"v2_{t}_meant", ""), "errors in gold": r.get(f"v2_{t}_errors", "")}
            for key, title in SHOWN:
                row[title] = r.get(f"v2_{t}_{key}" + ("_mean" if mean else ""), "")
            out.append(row)
    return out


def write_overview(store: str, out: str) -> list[Path]:
    """Writes <out>.csv (readable, long format) and <out>_all_columns.csv and <out>.html; returns the paths."""
    rows = read_runs(store)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    first = ["start", "experiment", "run", "kind", "status", "rubric", "model", "repeat"]
    wide = first + sorted({k for r in rows for k in r} - set(first))
    wide_path = out.with_name(out.name + "_all_columns.csv")
    with open(wide_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=wide)
        writer.writeheader()
        writer.writerows(rows)
    table = long_rows(rows)
    columns = list(table[0]) if table else ["start", "run"]
    csv_path, html_path = out.with_suffix(".csv"), out.with_suffix(".html")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(table)
    head = "".join(f"<th>{html.escape(c)}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(r.get(c, '')))}</td>" for c in columns) + "</tr>" for r in table)
    html_path.write_text(
        "<!doctype html><meta charset='utf-8'><title>MLflow overview</title>"
        "<style>body{font:13px sans-serif;margin:16px}table{border-collapse:collapse}"
        "td,th{border:1px solid #ccc;padding:3px 6px;text-align:left;white-space:nowrap}th{background:#eee}</style>"
        "<h2>MLflow runs, read from the database (one row per run and teaser)</h2>"
        "<p>'mean of repeats' rows belong to the parent run of one rubric; 'repeat N' rows to one repeat. "
        "Run names start with the date and time of the experiment.</p>"
        f"<table><tr>{head}</tr>{body}</table>", encoding="utf-8")
    return [csv_path, html_path, wide_path]


def main() -> None:
    p = argparse.ArgumentParser(description="Readable table of an MLflow store.")
    p.add_argument("store", help="MLflow folder (with mlflow.db), the database file or sqlite:///...")
    p.add_argument("--out", default="mlflow_overview", help="file name without extension")
    args = p.parse_args()
    for path in write_overview(args.store, args.out):
        print("written:", path)


if __name__ == "__main__":
    main()
