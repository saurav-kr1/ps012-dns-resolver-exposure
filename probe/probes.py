"""Send ONE small DNS query and describe the reply.

Safety rules baked in here:
  * plain UDP query, no EDNS (so no big-buffer request), never type ANY
  * the real source address is used (no spoofing; the OS sets it)
  * every send goes through the rate limiter first
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import dns.exception
import dns.flags
import dns.message
import dns.query
import dns.rcode

from .config import Target
from .ratelimit import RateLimiter


@dataclass
class ProbeResult:
    qname: str
    qtype: str
    rd: bool                      # did we ask for recursion?
    ok: bool = False              # got a valid reply (ID and source matched)
    rcode: Optional[str] = None   # NOERROR, SERVFAIL, NXDOMAIN, REFUSED ...
    ra: bool = False              # server says "recursion available"
    aa: bool = False              # server says "authoritative answer"
    answers: list = field(default_factory=list)
    latency_ms: Optional[float] = None
    error: Optional[str] = None   # timeout / bad_response / os_error ...
    tries: int = 0

    def brief(self) -> dict:
        return {
            "qname": self.qname, "qtype": self.qtype, "rd": self.rd, "ok": self.ok,
            "rcode": self.rcode, "ra": self.ra, "aa": self.aa, "answers": self.answers,
            "latency_ms": self.latency_ms, "error": self.error, "tries": self.tries,
        }


def send_probe(limiter: RateLimiter, target: Target, qname: str, qtype: str, rd: bool,
               timeout: float, retries: int, backoff_s: float = 0.5) -> ProbeResult:
    """Ask `target` one question. Retries only on timeout/network errors."""
    result = ProbeResult(qname=qname, qtype=qtype, rd=rd)
    query = dns.message.make_query(qname, qtype, use_edns=False)
    if not rd:
        query.flags &= ~dns.flags.RD

    for attempt in range(retries + 1):
        limiter.acquire(target.id)          # may raise BudgetExceeded
        result.tries = attempt + 1
        started = time.monotonic()
        try:
            reply = dns.query.udp(query, target.ip, port=target.port, timeout=timeout)
        except dns.exception.Timeout:
            result.error = "timeout"
        except (dns.query.BadResponse, dns.query.UnexpectedSource, dns.exception.FormError):
            result.error = "bad_response"
        except OSError as e:
            result.error = f"os_error:{type(e).__name__}"
        else:
            result.ok = True
            result.error = None
            result.latency_ms = round((time.monotonic() - started) * 1000, 1)
            result.rcode = dns.rcode.to_text(reply.rcode())
            result.ra = bool(reply.flags & dns.flags.RA)
            result.aa = bool(reply.flags & dns.flags.AA)
            result.answers = [rr.to_text() for rrset in reply.answer for rr in rrset]
            return result
        if attempt < retries:
            time.sleep(backoff_s)
    return result
