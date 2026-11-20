"""Experiments used for the false/inconclusive result analysis.

    python -m probe.experiments lossy --runs 40

Experiment B ("lossy"): the lossy target (t08) is a genuine open resolver whose replies are
dropped 20% of the time. We repeat the assessment of that ONE target many times with 0, 1 and 2
retries and count how often it is (wrongly) not labelled "recursive".
Every query still goes through the rate limiter, and each run keeps its own query budget.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from datetime import datetime

from .config import load_config, load_targets
from .runner import run_assessment


def lossy(args) -> int:
    base = load_config(args.config)
    targets = [t for t in load_targets(args.targets, base) if t.id == args.target]
    if not targets:
        print(f"target {args.target} not found")
        return 2

    results = []
    for retries in (0, 1, 2):
        cfg = load_config(args.config)
        cfg.rate.retries = retries
        cfg.rate.per_target_qps = args.per_target_qps       # still bounded, just a faster experiment
        counts, sent = Counter(), 0
        started = time.monotonic()
        for _ in range(args.runs):
            outcomes, limiter = run_assessment(cfg, targets, log=lambda m: None)
            counts[outcomes[0].label] += 1
            sent += limiter.sent
        row = {
            "retries": retries, "runs": args.runs,
            "recursive": counts.get("recursive", 0),
            "not_recursive": args.runs - counts.get("recursive", 0),
            "labels": dict(counts),
            "avg_queries_per_run": round(sent / args.runs, 2),
            "seconds": round(time.monotonic() - started, 1),
        }
        results.append(row)
        print(f"retries={retries}: recursive {row['recursive']}/{args.runs}, "
              f"labels={row['labels']}, avg queries/run={row['avg_queries_per_run']}")

    out = {"experiment": "lossy_retries", "target": args.target, "loss_percent": 20,
           "attempts_per_probe": base.rate.attempts_per_probe, "per_target_qps": args.per_target_qps,
           "timestamp": datetime.now().isoformat(timespec="seconds"), "results": results}
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "lossy_retries.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("saved", path)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PS-012 analysis experiments (lab only)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lossy", help="retries vs false-inconclusive rate on the lossy target")
    p.add_argument("--config", default="config/probe.yaml")
    p.add_argument("--targets", default="config/targets.yaml")
    p.add_argument("--target", default="t08")
    p.add_argument("--runs", type=int, default=40)
    p.add_argument("--per-target-qps", type=float, default=5.0, dest="per_target_qps")
    p.add_argument("--out", default="results/experiments")
    args = ap.parse_args(argv)
    return lossy(args)


if __name__ == "__main__":
    raise SystemExit(main())
