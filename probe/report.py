"""Write the results: JSON (raw), CSV (table) and a readable Markdown report."""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime

from .config import LABELS, Config, RECURSIVE, AUTH_ONLY, REFUSED, INCONCLUSIVE
from .evaluate import evaluate
from .runner import Outcome
from .ratelimit import RateLimiter

REASON_TEXT = {
    "no_response": "No valid reply to any probe (firewalled, not listening on the probed address, or heavy packet loss).",
    "servfail": "The server answered SERVFAIL: it probably tried to recurse and failed upstream. It may be a resolver with a broken upstream, not proof either way.",
    "ra_no_answer": "The server says recursion is available but gave no usable answer (for example NXDOMAIN or an empty reply).",
    "empty_or_referral": "An empty or referral-style reply with recursion not offered; neither refused nor authoritative.",
    "no_majority": "The repeated attempts disagreed and no label won more than half the votes.",
    "p2_only_unclear": "Only the authority probe was answered and it showed no authoritative data.",
    "aa_set_unconfirmed": "The server returned the correct answer with the AA flag set. That happens both for forwarders (they copy the upstream's flag) and for servers that host the probe zone themselves, and the test-zone log did not confirm that this server asked upstream, so the tool does not guess.",
    "budget_exhausted": "The query budget ran out before this target was finished.",
}

ADVICE = {
    RECURSIVE: "Open resolver. Apply RFC 5358 Section 4: restrict recursion to intended clients (ACL, incoming interface, TSIG, VPN) and deploy ingress filtering (BCP 38).",
    AUTH_ONLY: "Correct for an authoritative-only server: recursion is off (RFC 5358, Section 4).",
    REFUSED: "Correct for a restricted resolver: outsiders are refused (RFC 5358, Section 4).",
    INCONCLUSIVE: "Could not be classified from this vantage point; see the reason code.",
}


def _key_evidence(o: Outcome) -> str:
    if not o.attempts:
        return ""
    p1 = o.attempts[0]["p1"]
    bits = [f"P1 rcode={p1['rcode'] or p1['error']}"]
    if p1["ok"]:
        bits.append(f"RA={int(p1['ra'])} AA={int(p1['aa'])}")
    return ", ".join(bits)


def write_reports(out_dir: str, cfg: Config, outcomes: list[Outcome], limiter: RateLimiter, meta: dict) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for o in outcomes:
        rows.append({
            "id": o.target.id, "name": o.target.name, "ip": o.target.ip,
            "expected": o.target.expected, "label": o.label, "reason": o.reason,
            "match": (o.target.expected == o.label) if o.target.expected else None,
            "votes": o.votes, "evidence": _key_evidence(o),
        })
    ev = evaluate(rows)
    stats = {
        "queries_sent": limiter.sent, "budget": cfg.rate.max_total_queries,
        "peak_queries_in_1s": limiter.peak_qps(), "duration_s": round(limiter.duration_s(), 1),
        "global_qps_limit": cfg.rate.global_qps, "per_target_qps_limit": cfg.rate.per_target_qps,
    }

    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as f:
        json.dump({
            "meta": meta, "stats": stats, "evaluation": ev, "results": rows,
            "attempts": {o.target.id: o.attempts for o in outcomes},
        }, f, indent=2)

    with open(os.path.join(out_dir, "results.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "ip", "expected", "label", "match", "reason", "evidence"])
        for r in rows:
            w.writerow([r["id"], r["name"], r["ip"], r["expected"], r["label"], r["match"], r["reason"], r["evidence"]])

    md = [f"# DNS resolver exposure assessment report", "",
          f"- Run: `{meta['run_id']}`  |  Date: {meta['timestamp']}",
          f"- Config fingerprint: `{meta['config_fingerprint']}`  |  Targets: {len(rows)}", "",
          "## 1. Safety and rate-control evidence", "",
          f"- Queries sent: **{stats['queries_sent']}** (budget {stats['budget']})",
          f"- Peak queries in any 1-second window: **{stats['peak_queries_in_1s']}** (global limit {stats['global_qps_limit']}/s)",
          f"- Duration of sending: {stats['duration_s']} s",
          "- Only allowlisted lab targets, real source address, small plain queries, no spoofing, no amplification testing.", "",
          "## 2. Results per target", "",
          "| ID | Name | Expected | Predicted | Match | Reason | Evidence |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        m = "-" if r["match"] is None else ("yes" if r["match"] else "**NO**")
        md.append(f"| {r['id']} | {r['name']} | {r['expected'] or '-'} | {r['label']} | {m} | {r['reason']} | {r['evidence']} |")

    md += ["", "## 3. Accuracy against ground truth", ""]
    if ev["total"]:
        md.append(f"Accuracy: **{ev['correct']}/{ev['total']} = {ev['accuracy']:.0%}**")
        md += ["", "Confusion matrix (rows = expected, columns = predicted):", "",
               "| expected \\ predicted | " + " | ".join(LABELS) + " |", "|---|" + "---|" * len(LABELS)]
        for e in LABELS:
            md.append(f"| **{e}** | " + " | ".join(str(ev["matrix"][e][p]) for p in LABELS) + " |")
        md += ["", "| Class | Support | Precision | Recall |", "|---|---|---|---|"]
        for c in LABELS:
            pc = ev["per_class"][c]
            fmt = lambda v: "n/a" if v is None else f"{v:.2f}"
            md.append(f"| {c} | {pc['support']} | {fmt(pc['precision'])} | {fmt(pc['recall'])} |")
    else:
        md.append("No ground truth was provided, so no accuracy was computed.")

    md += ["", "## 4. False and inconclusive result analysis", ""]
    problems = [o for o in outcomes if o.label == INCONCLUSIVE or (o.target.expected and o.target.expected != o.label)]
    if not problems:
        md.append("No mismatches and no inconclusive results.")
    for o in problems:
        exp = o.target.expected
        kind = "MISMATCH" if exp and exp != o.label else "inconclusive (as expected)" if exp == o.label else "inconclusive"
        md.append(f"- **{o.target.id}** ({o.target.name}): expected `{exp}`, predicted `{o.label}`, reason `{o.reason}` - {kind}. "
                  f"{REASON_TEXT.get(o.reason, '')} Votes: {o.votes}")

    md += ["", "## 5. Findings and RFC 5358 recommendations", ""]
    for o in outcomes:
        md.append(f"- **{o.target.id}** `{o.label}`: {ADVICE[o.label]}")

    md += ["", "## 6. Limitations", "",
           "- The lab models real networks; results come from a single vantage point.",
           "- A server that is open only to some source networks may look refused from here.",
           "- Only recursion exposure is tested."]
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    return {"rows": rows, "evaluation": ev, "stats": stats}
