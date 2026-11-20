"""Compare predicted labels with the seeded ground truth."""
from __future__ import annotations

from .config import LABELS


def evaluate(rows: list[dict]) -> dict:
    """rows: dicts with 'id', 'expected' (may be None) and 'label'."""
    scored = [r for r in rows if r.get("expected")]
    matrix = {e: {p: 0 for p in LABELS} for e in LABELS}
    for r in scored:
        matrix[r["expected"]][r["label"]] += 1

    correct = sum(1 for r in scored if r["expected"] == r["label"])
    per_class = {}
    for c in LABELS:
        tp = matrix[c][c]
        fp = sum(matrix[e][c] for e in LABELS if e != c)
        fn = sum(matrix[c][p] for p in LABELS if p != c)
        per_class[c] = {
            "support": tp + fn,
            "precision": (tp / (tp + fp)) if (tp + fp) else None,
            "recall": (tp / (tp + fn)) if (tp + fn) else None,
        }
    return {
        "total": len(scored),
        "correct": correct,
        "accuracy": (correct / len(scored)) if scored else None,
        "matrix": matrix,
        "per_class": per_class,
        "mismatches": [r for r in scored if r["expected"] != r["label"]],
    }
