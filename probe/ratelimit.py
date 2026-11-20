"""Rate control: a token bucket plus a hard query budget.

A token bucket refills at `rate` tokens per second and holds at most `burst`
tokens. Sending one query spends one token. If the bucket is empty the caller
waits, so the tool can never go faster than the configured rate.
"""
from __future__ import annotations

import threading
import time


class BudgetExceeded(Exception):
    """The run reached max_total_queries; no more queries may be sent."""


class TokenBucket:
    def __init__(self, rate: float, burst: float = 1.0, clock=time.monotonic, sleep=time.sleep):
        self.rate = float(rate)
        self.burst = float(burst)
        self._clock = clock
        self._sleep = sleep
        self._tokens = self.burst
        self._last = clock()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = self._clock()
                self._tokens = min(self.burst, self._tokens + (now - self._last) * self.rate)
                self._last = now
                # tiny tolerance: floating-point maths can leave 0.9999999999 tokens
                if self._tokens >= 1.0 - 1e-9:
                    self._tokens = max(0.0, self._tokens - 1.0)
                    return
                wait = max((1.0 - self._tokens) / self.rate, 1e-4)
            self._sleep(wait)


class RateLimiter:
    """Global limit + per-target limit + total budget, with simple statistics."""

    def __init__(self, global_qps, per_target_qps, max_total_queries, clock=time.monotonic, sleep=time.sleep):
        self._global = TokenBucket(global_qps, clock=clock, sleep=sleep)
        self._per_target_qps = per_target_qps
        self._per_target: dict[str, TokenBucket] = {}
        self._max_total = int(max_total_queries)
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self.sent = 0
        self.timestamps: list[float] = []

    def _bucket(self, target_id: str) -> TokenBucket:
        with self._lock:
            if target_id not in self._per_target:
                self._per_target[target_id] = TokenBucket(self._per_target_qps, clock=self._clock, sleep=self._sleep)
            return self._per_target[target_id]

    def acquire(self, target_id: str) -> None:
        """Call this immediately before every query. Blocks until allowed."""
        with self._lock:
            if self.sent >= self._max_total:
                raise BudgetExceeded(f"query budget of {self._max_total} reached")
        self._bucket(target_id).acquire()
        self._global.acquire()
        with self._lock:
            if self.sent >= self._max_total:
                raise BudgetExceeded(f"query budget of {self._max_total} reached")
            self.sent += 1
            self.timestamps.append(self._clock())

    def peak_qps(self) -> int:
        """Largest number of queries sent inside any 1-second window."""
        ts = sorted(self.timestamps)
        best, j = 0, 0
        for i in range(len(ts)):
            # 1e-6 s tolerance so clock rounding noise is not counted as an extra query
            while ts[i] - ts[j] >= 1.0 - 1e-6:
                j += 1
            best = max(best, i - j + 1)
        return best

    def duration_s(self) -> float:
        return (max(self.timestamps) - min(self.timestamps)) if len(self.timestamps) > 1 else 0.0
