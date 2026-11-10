# Controlled experiments for the teaser judge: the same set of teasers, one change at a time
# (rubric file, model), several repeats, every run logged against the standard v2 (sentence by sentence).
#
# Usage:
#   python -m teaser_check.experiment lab_set.json --rubric skills/teaser-judge.md --repeats 3 [--model M] [--out-dir DIR]
#   python -m teaser_check.experiment lab_set.json --rubric a.md b.md --repeats 3 --store /path/to/mlruns
#   python -m teaser_check.experiment lab_set.json --dry-run       (code rules only, no model, tests the setup, writes nothing)
#
# lab_set.json (paths relative to the file; keep it OUTSIDE the repository, it holds real company text):
#   {"name": "lab_set_v1", "gold": "gold_v2.json", "cases": [{"case": "B", "pack": "pack.json", "teaser": "teaser.txt"}]}
# The standard (gold_v2.json, or the file named in "gold", e.g. gold_v3.json for the teaser format of 9 Nov) must lie next to it;
# without it the run stops, there is no other count.
#
# Written (not for --dry-run), all in --out-dir (default results/):
#   experiments_v2.csv      one row per run and teaser (judge statistics and code checks)
#   experiment_runs/<time>_<rubric>_<model>_r<N>/   the result CSV and the HTML report of every teaser
# Also logged when the package `mlflow` is installed and --store is given: one parent run per
# (rubric, model) with one child run per repeat; the same v2 numbers per teaser.

import argparse
import csv
import datetime
import hashlib
import json
import os
import tempfile
from pathlib import Path

from claim_check.common import ROOT
from claim_check.config import get_client, get_env

from .judge import judge_with_llm, no_judge
from .pack import load_pack
from .pipeline import check_teaser, write_csv
from .report import build_report
from .sections import is_sectioned, judge_sections
from .score_v2 import format_table, load_gold, score_case_v2

V2_COLUMNS = ["time", "rubric", "rubric_sha", "model", "repeat", "case", "meant", "read", "errors", "found", "decided",
              "right", "false_flags", "nonclaim_flags", "unmatched", "hyp_unlabelled", "code_n", "code_found"]
V2_KEYS = V2_COLUMNS[6:]  # the numbers of one teaser in one run


def load_lab_set(path) -> dict:
    path = Path(path)
    lab = json.loads(path.read_text(encoding="utf-8"))
    lab["base"] = path.parent
    lab["gold_name"] = lab.get("gold", "gold_v2.json")  # the standard (by sentence): v2 by default, or the file named in lab_set.json
    gold = path.parent / lab["gold_name"]
    lab["gold_v2"] = load_gold(gold) if gold.exists() else None
    return lab


def sha_of(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:8]


def patient(judge, tries: int = 5, wait: int = 120, sleep=None):
    """Wraps a judge: if the model stays unavailable after chat()'s own retries (503 for minutes), wait and try the
    same teaser again, so one busy period does not throw away the whole repeat."""
    import time
    sleep = sleep or time.sleep

    def run(record_text, body):
        for attempt in range(1, tries + 1):
            try:
                return judge(record_text, body)
            except Exception as error:  # the API client raises its own error types; any failure here is retried
                if attempt == tries:
                    raise
                print(f"Judge failed ({type(error).__name__}), waiting {wait} s, then try {attempt + 1} of {tries} ...")
                sleep(wait)
    return run



def run_once(lab: dict, judge, out_dir) -> dict:
    """One pass over all teasers of the lab set. Returns the summary; result CSVs go to out_dir."""
    out_dir = Path(out_dir)
    tokens, v2 = {"input": 0, "output": 0}, {}
    for case in lab["cases"]:
        pack = load_pack(lab["base"] / case["pack"])
        text = (lab["base"] / case["teaser"]).read_text(encoding="utf-8")
        rows, tok = check_teaser(pack, text, judge)
        tokens["input"] += tok["input"]
        tokens["output"] += tok["output"]
        write_csv([{"case": case["case"], "id": pack["group_id"], **r} for r in rows], out_dir / f"{case['case']}.csv")
        if judge is not no_judge:  # a readable page per teaser (not for dry runs: no judge, nothing to show)
            (out_dir / f"report_{case['case']}.html").write_text(
                build_report([dict(r) for r in rows], text, f"Teaser {case['case']}", pack), encoding="utf-8")
        if lab.get("gold_v2") and case["case"] in lab["gold_v2"]:
            v2[case["case"]] = score_case_v2(lab["gold_v2"][case["case"]], rows)
    return {"tokens": tokens, "v2": v2}


def append_v2(path, rubric: str, sha: str, model: str, repeat: int, v2: dict) -> None:
    """Statistics against the standard v2: one row per teaser and run."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=V2_COLUMNS)
        if new:
            writer.writeheader()
        for case, v in v2.items():
            writer.writerow({"time": datetime.datetime.now().isoformat(timespec="seconds"), "rubric": rubric,
                             "rubric_sha": sha, "model": model, "repeat": repeat, "case": case,
                             **{k: v[k] for k in V2_COLUMNS[6:]}})


def log_child(mlflow, summary: dict, params: dict, out_dir: Path, rubric: str) -> None:
    """One MLflow run for one repeat: the v2 numbers per teaser."""
    mlflow.log_params(params)
    mlflow.log_metrics({"tokens_in": summary["tokens"]["input"], "tokens_out": summary["tokens"]["output"]})
    for name, v in summary["v2"].items():
        for key in V2_KEYS:
            mlflow.log_metric(f"v2_{name}_{key}", v[key])
    mlflow.log_artifacts(str(out_dir), artifact_path="results")
    mlflow.log_artifact(rubric, artifact_path="rubric")


def log_parent(mlflow, summaries: list[dict]) -> None:
    """Over all repeats of one configuration: mean, minimum and maximum of the main numbers per teaser."""
    mlflow.log_metric("repeats", len(summaries))
    for name in summaries[0]["v2"]:
        for key in ("read", "found", "false_flags", "right", "code_found"):
            values = [s["v2"][name][key] for s in summaries]
            mlflow.log_metrics({f"v2_{name}_{key}_mean": sum(values) / len(values),
                                f"v2_{name}_{key}_min": min(values), f"v2_{name}_{key}_max": max(values)})


def setup_mlflow(mlflow, store: str, experiment: str) -> None:
    """A folder becomes a SQLite database inside it (new MLflow versions refuse the plain file store).
    A server address (http://...) or a database address (sqlite:///...) is used as it is."""
    artifacts = None
    if "://" not in store:
        folder = Path(store)
        folder.mkdir(parents=True, exist_ok=True)
        store = f"sqlite:///{(folder / 'mlflow.db').resolve()}"
        artifacts = (folder / "artifacts").resolve().as_uri()
    mlflow.set_tracking_uri(store)
    if artifacts and mlflow.get_experiment_by_name(experiment) is None:
        mlflow.create_experiment(experiment, artifact_location=artifacts)  # keep the artifacts inside the folder too
    mlflow.set_experiment(experiment)



def run_experiment(lab: dict, rubrics: list[str], model: str, repeats: int, judge_factory, store=None,
                   experiment="teaser-judge", out_dir=None, mlflow=None, dry_run=False) -> list[dict]:
    """Every rubric x repeats. judge_factory(rubric_path) returns the judge function.
    A dry run prints only: nothing goes into the table, the run folders or MLflow."""
    if not lab.get("gold_v2"):
        raise SystemExit(f"{lab.get('gold_name', 'gold_v2.json')} not found next to lab_set.json: put it in the same folder (step 3 of the notebook).")
    out_dir = Path(out_dir or ROOT / "results")
    runs_dir = Path(tempfile.mkdtemp()) if dry_run else out_dir / "experiment_runs"
    table = out_dir / "experiments_v2.csv"
    use_mlflow = bool(mlflow and store and not dry_run)
    if use_mlflow:
        setup_mlflow(mlflow, store, experiment)
    stamp = f"{datetime.datetime.now():%Y-%m-%d_%H-%M-%S}"
    all_summaries = []
    for rubric in rubrics:
        rname, sha = Path(rubric).stem, sha_of(rubric)
        judge = patient(judge_factory(rubric))
        parent = mlflow.start_run(run_name=f"{stamp} {rname}@{model}") if use_mlflow else None
        summaries = []
        for repeat in range(1, repeats + 1):
            run_dir = runs_dir / f"{stamp}_{rname}_{model}_r{repeat}".replace("/", "-")
            summary = run_once(lab, judge, run_dir)
            summaries.append(summary)
            params = {"lab_set": lab.get("name", ""), "rubric": rname, "rubric_sha": sha, "model": model, "repeat": repeat}
            if use_mlflow:
                with mlflow.start_run(run_name=f"{stamp} {rname}@{model} r{repeat}", nested=True):
                    log_child(mlflow, summary, params, run_dir, rubric)
            if not dry_run:
                append_v2(table, rname, sha, model, repeat, summary["v2"])
            print(f"{rname} r{repeat}: " + "; ".join(
                f"{c} read {v['read']}/{v['meant']}, errors found {v['found']}/{v['errors']}, false flags {v['false_flags']}"
                for c, v in summary["v2"].items()) + f"; tokens {summary['tokens']['input']}/{summary['tokens']['output']}")
        if parent:
            log_parent(mlflow, summaries)
            mlflow.end_run()
        all_summaries.append({"rubric": rname, "summaries": summaries})
    if use_mlflow:
        try:   # readable copy of the MLflow database next to the table
            from .mlflow_export import write_overview
            for path in write_overview(store, str(out_dir / "mlflow_overview")):
                print("MLflow overview:", path)
        except Exception as error:
            print("MLflow overview not written:", error)
    return all_summaries


def main() -> None:
    p = argparse.ArgumentParser(description="Controlled experiments for the teaser judge.")
    p.add_argument("lab_set")
    p.add_argument("--rubric", nargs="+", default=[str(ROOT / "skills" / "teaser-judge.md")])
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--model", help="overrides MODEL_NAME")
    p.add_argument("--out-dir", help="where experiments_v2.csv and experiment_runs/ are written (in Colab: a folder on Google Drive). Default: results/")
    p.add_argument("--store", help="MLflow folder or database address (optional). Without it only the table is written")
    p.add_argument("--experiment", default="teaser-judge", help="MLflow experiment name (default: teaser-judge)")
    p.add_argument("--dry-run", action="store_true", help="code rules only, no model call, writes nothing (tests the setup)")
    args = p.parse_args()

    mlflow = None
    if args.store and not args.dry_run:
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
        def factory(rubric):  # a rubric with '## SECTION' blocks is applied part by part
            call = judge_sections if is_sectioned(rubric) else judge_with_llm
            return lambda rec, body: call(rec, body, client=client, model=model, rubric_path=rubric)
    print(f"Lab set {lab.get('name')}: {len(lab['cases'])} teasers, standard v2 (by sentence). "
          f"Model {model}, repeats {args.repeats}, rubrics {[Path(r).stem for r in args.rubric]}"
          + (" (dry run: nothing is saved)" if args.dry_run else ""))
    done = run_experiment(lab, args.rubric, model, args.repeats, factory, store=args.store, experiment=args.experiment,
                          out_dir=args.out_dir, mlflow=mlflow, dry_run=args.dry_run)
    print()
    for case, gold_case in sorted(lab["gold_v2"].items()):  # per teaser first
        by_rubric = {d["rubric"]: [s["v2"][case] for s in d["summaries"] if case in s["v2"]] for d in done}
        if any(by_rubric.values()):
            print(format_table(case, gold_case.get("title", case), {k: v for k, v in by_rubric.items() if v}), "\n")
    if not args.dry_run:
        print("Table per run and teaser:", Path(args.out_dir or ROOT / "results") / "experiments_v2.csv")


if __name__ == "__main__":
    main()
