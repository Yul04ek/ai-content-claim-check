# Controlled experiments for the teaser judge: the same set of teasers with known errors,
# one change at a time (rubric file, model), several repeats, every run logged.
#
# Usage:
#   python -m teaser_check.experiment lab_set.json --rubric skills/teaser-judge.md --repeats 3 [--model M]
#   python -m teaser_check.experiment lab_set.json --rubric a.md b.md --repeats 3 --store /path/to/mlruns
#   python -m teaser_check.experiment lab_set.json --dry-run       (code rules only, no model, tests the setup)
#
# lab_set.json (paths relative to the file; keep it OUTSIDE the repository, it holds real company text):
#   {"name": "lab_set_v1", "cases": [{"case": "B", "pack": "pack.json", "teaser": "teaser.txt",
#                                      "items": [{"id": "B1", "match": "open salaries", "why": "..."}]}]}
#
# Always written: a table row per run (results/experiments.csv) and the result CSV of every case.
# Also logged when the package `mlflow` is installed and --store is given: one parent run per
# (rubric, model) with one child run per repeat. Parent: mean/min/max recall and a hit rate per item.

import argparse
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path

from claim_check.common import ROOT
from claim_check.config import get_client, get_env

from .judge import judge_with_llm, no_judge
from .pack import load_pack
from .pipeline import check_teaser, write_csv
from .score import score_case

TABLE_COLUMNS = ["time", "lab_set", "rubric", "rubric_sha", "model", "repeat", "found", "total", "recall",
                 "other_findings", "tokens_in", "tokens_out", "per_case"]


def load_lab_set(path) -> dict:
    path = Path(path)
    lab = json.loads(path.read_text(encoding="utf-8"))
    lab["base"] = path.parent
    return lab


def sha_of(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:8]


def run_once(lab: dict, judge, out_dir) -> dict:
    """One pass over all teasers of the lab set. Returns the summary; result CSVs go to out_dir."""
    out_dir = Path(out_dir)
    cases, tokens = {}, {"input": 0, "output": 0}
    found = total = extra = 0
    for case in lab["cases"]:
        pack = load_pack(lab["base"] / case["pack"])
        text = (lab["base"] / case["teaser"]).read_text(encoding="utf-8")
        rows, tok = check_teaser(pack, text, judge)
        tokens["input"] += tok["input"]
        tokens["output"] += tok["output"]
        write_csv([{"case": case["case"], "id": pack["group_id"], **r} for r in rows], out_dir / f"{case['case']}.csv")
        scored = score_case(case["items"], [{"case": case["case"], "id": pack["group_id"], **r} for r in rows])
        cases[case["case"]] = {"found": [i["id"] for i in scored["found"]], "missed": [i["id"] for i in scored["missed"]],
                               "extra": len(scored["extra"]), "recall": scored["recall"]}
        found += len(scored["found"])
        total += len(case["items"])
        extra += len(scored["extra"])
    return {"cases": cases, "found": found, "total": total, "recall": found / total if total else 1.0,
            "extra": extra, "tokens": tokens}


def append_table(path, row: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=TABLE_COLUMNS)
        if new:
            writer.writeheader()
        writer.writerow(row)


def log_child(mlflow, summary: dict, params: dict, out_dir: Path, rubric: str) -> None:
    """One MLflow run for one repeat."""
    mlflow.log_params(params)
    mlflow.log_metrics({"found": summary["found"], "total": summary["total"], "recall": summary["recall"],
                        "other_findings": summary["extra"], "tokens_in": summary["tokens"]["input"],
                        "tokens_out": summary["tokens"]["output"]})
    for name, case in summary["cases"].items():
        mlflow.log_metric(f"recall_{name}", case["recall"])
        for item in case["found"]:
            mlflow.log_metric(f"item_{item}", 1)
        for item in case["missed"]:
            mlflow.log_metric(f"item_{item}", 0)
    mlflow.log_artifacts(str(out_dir), artifact_path="results")
    mlflow.log_artifact(rubric, artifact_path="rubric")


def log_parent(mlflow, summaries: list[dict]) -> None:
    """Over all repeats of one configuration: how big and how stable is the result."""
    recalls = [s["recall"] for s in summaries]
    mlflow.log_metrics({"recall_mean": sum(recalls) / len(recalls), "recall_min": min(recalls),
                        "recall_max": max(recalls), "repeats": len(recalls),
                        "other_findings_mean": sum(s["extra"] for s in summaries) / len(summaries)})
    hits = {}
    for s in summaries:
        for case in s["cases"].values():
            for item in case["found"]:
                hits[item] = hits.get(item, 0) + 1
            for item in case["missed"]:
                hits.setdefault(item, 0)
    for item, n in hits.items():
        mlflow.log_metric(f"hit_rate_{item}", n / len(summaries))  # 1.0 = found every time, 0.33 = found once in 3 runs


def run_experiment(lab: dict, rubrics: list[str], model: str, repeats: int, judge_factory, store=None,
                   experiment="teaser-judge", table=None, runs_dir=None, mlflow=None) -> list[dict]:
    """Every rubric x repeats. judge_factory(rubric_path) returns the judge function."""
    runs_dir = Path(runs_dir or ROOT / "results" / "experiment_runs")
    table = table or ROOT / "results" / "experiments.csv"
    if mlflow and store:
        mlflow.set_tracking_uri(store)
        mlflow.set_experiment(experiment)
    stamp = f"{datetime.datetime.now():%Y-%m-%d_%H-%M-%S}"
    all_summaries = []
    for rubric in rubrics:
        rname, sha = Path(rubric).stem, sha_of(rubric)
        judge = judge_factory(rubric)
        parent = mlflow.start_run(run_name=f"{rname}@{model}") if mlflow and store else None
        summaries = []
        for repeat in range(1, repeats + 1):
            out_dir = runs_dir / f"{stamp}_{rname}_{model}_r{repeat}".replace("/", "-")
            summary = run_once(lab, judge, out_dir)
            summaries.append(summary)
            params = {"lab_set": lab.get("name", ""), "rubric": rname, "rubric_sha": sha, "model": model, "repeat": repeat}
            if mlflow and store:
                with mlflow.start_run(run_name=f"{rname}@{model} r{repeat}", nested=True):
                    log_child(mlflow, summary, params, out_dir, rubric)
            append_table(table, {
                "time": datetime.datetime.now().isoformat(timespec="seconds"), "lab_set": params["lab_set"],
                "rubric": rname, "rubric_sha": sha, "model": model, "repeat": repeat, "found": summary["found"],
                "total": summary["total"], "recall": round(summary["recall"], 3), "other_findings": summary["extra"],
                "tokens_in": summary["tokens"]["input"], "tokens_out": summary["tokens"]["output"],
                "per_case": "; ".join(f"{k} {len(v['found'])}/{len(v['found']) + len(v['missed'])}" for k, v in summary["cases"].items())})
            print(f"{rname} r{repeat}: found {summary['found']} of {summary['total']} "
                  f"(recall {summary['recall']:.0%}), other findings {summary['extra']}, "
                  f"tokens {summary['tokens']['input']}/{summary['tokens']['output']}")
        if parent:
            log_parent(mlflow, summaries)
            mlflow.end_run()
        all_summaries.append({"rubric": rname, "summaries": summaries})
    return all_summaries


def main() -> None:
    p = argparse.ArgumentParser(description="Controlled experiments for the teaser judge.")
    p.add_argument("lab_set")
    p.add_argument("--rubric", nargs="+", default=[str(ROOT / "skills" / "teaser-judge.md")])
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--model", help="overrides MODEL_NAME")
    p.add_argument("--store", help="MLflow folder (in Colab: on Google Drive). Without it only the table is written")
    p.add_argument("--experiment", default="teaser-judge")
    p.add_argument("--dry-run", action="store_true", help="code rules only, no model call (tests the setup)")
    args = p.parse_args()

    mlflow = None
    if args.store:
        try:
            import mlflow
        except ImportError:
            print("mlflow is not installed: only the table is written (pip install mlflow)")
    lab = load_lab_set(args.lab_set)
    if args.dry_run:
        model, factory = "dry-run", (lambda rubric: no_judge)
    else:
        client = get_client()
        model = args.model or get_env("MODEL_NAME")
        factory = lambda rubric: (lambda rec, body: judge_with_llm(rec, body, client=client, model=model, rubric_path=rubric))
    print(f"Lab set {lab.get('name')}: {len(lab['cases'])} teasers, {sum(len(c['items']) for c in lab['cases'])} known errors. "
          f"Model {model}, repeats {args.repeats}, rubrics {[Path(r).stem for r in args.rubric]}")
    run_experiment(lab, args.rubric, model, args.repeats, factory, store=args.store, experiment=args.experiment, mlflow=mlflow)
    print("Table: results/experiments.csv")


if __name__ == "__main__":
    main()
