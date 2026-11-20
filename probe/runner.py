"""Run the assessment: probe every target, classify, vote."""
from __future__ import annotations

import secrets
import string
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Optional

from .classify import classify_attempt, is_resolved, majority_vote
from .config import Config, Target, INCONCLUSIVE
from .probes import send_probe
from .ratelimit import BudgetExceeded, RateLimiter
from .testzone_log import nonce_seen

_ALPHABET = string.ascii_lowercase + string.digits


def make_nonce(n: int = 10) -> str:
    """A fresh random label. A never-before-asked name cannot be answered from cache."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


@dataclass
class Outcome:
    target: Target
    label: str
    reason: str
    votes: dict = field(default_factory=dict)
    attempts: list = field(default_factory=list)   # evidence for every attempt


def assess_target(target: Target, cfg: Config, limiter: RateLimiter,
                  nonce_fn: Callable[[], str] = make_nonce) -> Outcome:
    r = cfg.rate
    attempt_labels, evidence = [], []
    for i in range(r.attempts_per_probe):
        nonce = nonce_fn()
        qname = f"{nonce}.{cfg.zone}"

        # P1: recursion probe - ask for a name the target does NOT own, with RD=1
        r1 = send_probe(limiter, target, qname, "TXT", True, r.timeout_s, r.retries, r.backoff_s)

        # P2: authority probe - ask for the target's OWN zone, with RD=0
        r2 = None
        if target.own_zone:
            r2 = send_probe(limiter, target, target.own_zone, "SOA", False, r.timeout_s, r.retries, r.backoff_s)

        # second proof of recursion: did the test zone server see this nonce?
        log_hit = None
        if is_resolved(r1, cfg.expected_txt):
            log_hit = nonce_seen(cfg.testzone_log, nonce, target.lab_ip)

        label, reason = classify_attempt(r1, r2, cfg.expected_txt, log_hit)
        attempt_labels.append((label, reason))
        evidence.append({
            "attempt": i + 1, "nonce": nonce, "label": label, "reason": reason, "log_hit": log_hit,
            "p1": r1.brief(), "p2": r2.brief() if r2 else None,
        })

    label, reason, votes = majority_vote(attempt_labels)
    return Outcome(target, label, reason, votes, evidence)


def run_assessment(cfg: Config, targets: list[Target], limiter: Optional[RateLimiter] = None,
                   log: Callable[[str], None] = print):
    r = cfg.rate
    limiter = limiter or RateLimiter(r.global_qps, r.per_target_qps, r.max_total_queries)

    def work(t: Target) -> Outcome:
        try:
            out = assess_target(t, cfg, limiter)
        except BudgetExceeded:
            out = Outcome(t, INCONCLUSIVE, "budget_exhausted")
        log(f"  {t.id:<5} -> {out.label:<19} ({out.reason})")
        return out

    with ThreadPoolExecutor(max_workers=int(r.max_concurrency)) as pool:
        outcomes = list(pool.map(work, targets))
    return sorted(outcomes, key=lambda o: o.target.id), limiter
