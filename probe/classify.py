"""The decision tree: turn probe replies into one of the four labels.

Rules are checked IN ORDER; the first one that matches decides.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from .config import RECURSIVE, AUTH_ONLY, REFUSED, INCONCLUSIVE
from .probes import ProbeResult


def is_resolved(r1: Optional[ProbeResult], expected_txt: str) -> bool:
    """P1 got the correct answer for a never-before-seen name from a server offering recursion.
    The AA flag is NOT checked here: forwarders such as dnsmasq copy the upstream server's AA
    bit into their reply, so AA alone cannot tell them apart (see classify_attempt)."""
    return bool(
        r1 and r1.ok and r1.rcode == "NOERROR" and r1.ra
        and any(expected_txt in a for a in r1.answers)
    )


def classify_attempt(r1: Optional[ProbeResult], r2: Optional[ProbeResult],
                     expected_txt: str, log_hit: Optional[bool] = None) -> tuple[str, str]:
    """r1 = recursion probe (RD=1, name the target does not own).
       r2 = authority probe (RD=0, the target's own zone) or None.
       Returns (label, reason_code)."""
    r1_ok = bool(r1 and r1.ok)
    r2_ok = bool(r2 and r2.ok)

    # 1. nothing valid came back at all
    if not r1_ok and not r2_ok:
        return INCONCLUSIVE, "no_response"

    # 2. it resolved a name it does not own, for a stranger -> open resolver
    if is_resolved(r1, expected_txt):
        # AA set on a "recursive" answer is ambiguous: a forwarder copying the upstream's flag,
        # or a server that itself hosts the probe zone? Only the test-zone log can settle it.
        if r1.aa and log_hit is not True:
            return INCONCLUSIVE, "aa_set_unconfirmed"
        if log_hit is True:
            return RECURSIVE, "resolved+log_confirmed"
        if log_hit is False:
            return RECURSIVE, "resolved_no_log_entry"
        return RECURSIVE, "resolved"

    # 3. authoritative for its own zone, and did not recurse
    if r2_ok and r2.aa and r2.rcode == "NOERROR":
        return AUTH_ONLY, "aa_on_own_zone"

    # 4. explicitly refused
    if (r1_ok and r1.rcode == "REFUSED") or (r2_ok and r2.rcode == "REFUSED"):
        return REFUSED, "rcode_refused"

    # 5. anything else: say WHY we cannot tell
    if r1_ok:
        if r1.rcode == "SERVFAIL":
            return INCONCLUSIVE, "servfail"
        if r1.ra:
            return INCONCLUSIVE, "ra_no_answer"
        if r1.rcode == "NOERROR":
            return INCONCLUSIVE, "empty_or_referral"
        return INCONCLUSIVE, f"unclassified_{(r1.rcode or 'none').lower()}"
    return INCONCLUSIVE, "p2_only_unclear"


def majority_vote(attempts: list[tuple[str, str]]) -> tuple[str, str, dict]:
    """Combine repeated attempts. A label needs MORE than half the votes;
    otherwise the target is inconclusive (ties and conflicts are not guessed)."""
    counts = Counter(label for label, _ in attempts)
    if not counts:
        return INCONCLUSIVE, "no_attempts", {}
    top, n = counts.most_common(1)[0]
    if n * 2 > len(attempts):
        reasons = Counter(r for l, r in attempts if l == top)
        return top, reasons.most_common(1)[0][0], dict(counts)
    return INCONCLUSIVE, "no_majority", dict(counts)
