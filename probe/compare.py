"""Reproducibility check: do several runs give the same label for every target?

    python -m probe.compare results/RUN1 results/RUN2 results/RUN3
"""
from __future__ import annotations

import json
import os
import sys


def labels(run_dir: str) -> dict:
    with open(os.path.join(run_dir, "results.json"), encoding="utf-8") as f:
        return {r["id"]: r["label"] for r in json.load(f)["results"]}


def main(argv=None) -> int:
    runs = (argv if argv is not None else sys.argv[1:])
    if len(runs) < 2:
        print("give at least two run folders")
        return 2
    all_labels = [labels(r) for r in runs]
    ids = sorted(set().union(*[set(l) for l in all_labels]))
    diffs = [(i, [l.get(i) for l in all_labels]) for i in ids if len({l.get(i) for l in all_labels}) > 1]
    if not diffs:
        print(f"IDENTICAL: all {len(runs)} runs gave the same label for all {len(ids)} targets.")
        return 0
    print("DIFFERENT labels between runs:")
    for i, ls in diffs:
        print(f"  {i}: {ls}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
