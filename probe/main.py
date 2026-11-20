"""Command-line entry point.

    python -m probe.main --config config/probe.yaml --targets config/targets.yaml
    python -m probe.main ... --dry-run        (check everything, send NOTHING)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

from .config import ConfigError, load_config, load_targets
from .report import write_reports
from .runner import run_assessment


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="PS-012 authorised DNS resolver exposure assessment (lab only)")
    ap.add_argument("--config", default="config/probe.yaml")
    ap.add_argument("--targets", default="config/targets.yaml")
    ap.add_argument("--out", default="results")
    ap.add_argument("--dry-run", action="store_true", help="validate and show the plan, send nothing")
    args = ap.parse_args(argv)

    try:
        cfg = load_config(args.config)
        targets = load_targets(args.targets, cfg)
    except (ConfigError, OSError) as e:
        print(f"REFUSING TO RUN: {e}")
        return 2

    r = cfg.rate
    probes_per_attempt = 1 + (1 if any(t.own_zone for t in targets) else 0)
    worst_case = len(targets) * r.attempts_per_probe * probes_per_attempt * (1 + r.retries)
    print(f"Targets: {len(targets)} (limit {cfg.max_targets}) | zone: {cfg.zone}")
    print(f"Rate control: global {r.global_qps}/s, per-target {r.per_target_qps}/s, "
          f"{r.attempts_per_probe} attempts, timeout {r.timeout_s}s, retries {r.retries}, budget {r.max_total_queries}")
    print(f"Worst-case queries for this run: {worst_case}")
    if worst_case > r.max_total_queries:
        print("WARNING: worst case is above the budget; some targets may end as budget_exhausted")
    if args.dry_run:
        for t in targets:
            print(f"  would probe {t.id} {t.ip}:{t.port} (expected: {t.expected})")
        print("Dry run only: nothing was sent.")
        return 0

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"\nRun {run_id} - probing...")
    outcomes, limiter = run_assessment(cfg, targets)

    meta = {"run_id": run_id, "timestamp": datetime.now().isoformat(timespec="seconds"),
            "config_fingerprint": cfg.fingerprint(), "config": args.config, "targets_file": args.targets}
    out_dir = os.path.join(args.out, run_id)
    summary = write_reports(out_dir, cfg, outcomes, limiter, meta)

    ev, st = summary["evaluation"], summary["stats"]
    print(f"\nQueries sent: {st['queries_sent']} (budget {st['budget']}), peak {st['peak_queries_in_1s']} in any 1 s")
    if ev["total"]:
        print(f"Accuracy vs ground truth: {ev['correct']}/{ev['total']} = {ev['accuracy']:.0%}")
        for m in ev["mismatches"]:
            print(f"  MISMATCH {m['id']}: expected {m['expected']}, got {m['label']} ({m['reason']})")
    print(f"Reports written to: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
